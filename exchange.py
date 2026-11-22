"""Synchronous dYdX Chain adapter using the official async Python SDK.

Every placement is journalled before submission. An uncertain submission is
reconciled by client ID, never replaced with a new order automatically.
"""
import asyncio
import os
import secrets
import time
from collections import namedtuple
from decimal import ROUND_DOWN, ROUND_UP

import grpc
import requests
from dydx_v4_client import OrderFlags
from dydx_v4_client.indexer.rest.constants import OrderType
from dydx_v4_client.network import make_mainnet, make_testnet
from dydx_v4_client.node.client import NodeClient
from dydx_v4_client.node.market import Market
from dydx_v4_client.wallet import Wallet
from v4_proto.dydxprotocol.clob.order_pb2 import Order

from runtime import State, number

TERMINAL = {"FILLED", "CANCELED", "CANCELLED", "EXPIRED", "BEST_EFFORT_CANCELED"}


class CallDetails(namedtuple("CallDetails", "method timeout metadata credentials wait_for_ready compression"), grpc.ClientCallDetails):
    pass


class Deadline(grpc.UnaryUnaryClientInterceptor):
    def intercept_unary_unary(self, continuation, details, request):
        timeout = min(details.timeout, 20) if details.timeout is not None else 20
        return continuation(CallDetails(details.method, timeout, details.metadata, details.credentials, details.wait_for_ready, details.compression), request)


class Exchange:
    def __init__(self, settings):
        network = settings["network"]
        if network not in {"testnet", "mainnet"}:
            raise ValueError("network must be testnet or mainnet")
        maker = make_mainnet if network == "mainnet" else make_testnet
        self.network = maker(rest_indexer=settings["indexer"], websocket_indexer=settings["websocket"], node_url=settings["node"])
        self.network.node.channel = grpc.intercept_channel(self.network.node.channel, Deadline())
        self.address = settings["address"]
        self.subaccount = int(settings["subaccount"])
        if not 0 <= self.subaccount < 128:
            raise ValueError("Only cross-margin subaccounts 0 through 127 are supported")
        self.runner = asyncio.Runner()
        self.node = self.runner.run(NodeClient.connect(self.network.node))
        mnemonic = os.environ["DYDX_MNEMONIC"]
        self.wallet = self.runner.run(Wallet.from_mnemonic(self.node, mnemonic, self.address))
        if self.wallet.address != self.address:
            raise ValueError("DYDX_MNEMONIC does not match the configured address")
        self.journal = State("data/exchange.json", {"orders": {}, "account": [network, self.address, self.subaccount]})
        if self.journal.data["account"] != [network, self.address, self.subaccount]:
            raise ValueError("Exchange journal belongs to a different account or network")
        self.session = requests.Session()
        self.markets = {}

    def get(self, path, **params):
        response = self.session.get(self.network.rest_indexer.rstrip("/") + "/v4/" + path, params=params, timeout=20)
        response.raise_for_status()
        return response.json()

    def market(self, ticker):
        if ticker not in self.markets:
            self.markets[ticker] = self.get("perpetualMarkets", ticker=ticker)["markets"][ticker]
        return self.markets[ticker]

    def price(self, ticker):
        book = self.get("orderbooks/perpetualMarket/" + ticker)
        return (number(book["bids"][0]["price"]) + number(book["asks"][0]["price"])) / 2

    def round_price(self, ticker, price, side):
        tick = number(self.market(ticker)["tickSize"])
        rounding = ROUND_DOWN if side == "BUY" else ROUND_UP
        return (number(price) / tick).to_integral_value(rounding=rounding) * tick

    def find(self, reference):
        if "id" in reference:
            return self.get("orders/" + reference["id"])
        orders = self.get("orders", address=self.address, subaccountNumber=self.subaccount, ticker=reference["market"], limit=100, returnLatestOrders="true")
        for order in orders:
            if int(order["clientId"]) == reference["client_id"] and int(order["orderFlags"]) == reference["flags"]:
                reference["id"] = order["id"]
                self.journal.save()
                return order
        return None

    def status(self, reference):
        order = self.find(reference)
        if order is None:
            raise RuntimeError("Order not visible in the indexer; submission remains uncertain. Do not delete exchange.json.")
        return order

    def wait_visible(self, reference):
        for _ in range(30):
            order = self.find(reference)
            if order is not None:
                return order
            time.sleep(1)
        raise TimeoutError("Order not indexed after submission; reconcile the saved client ID before continuing")

    def place(self, key, ticker, side, size, price=None, *, reduce_only=False, post_only=False, till=None, slippage="0.01"):
        if side not in {"BUY", "SELL"} or number(size) <= 0:
            raise ValueError("An order needs BUY or SELL and a positive size")
        market = self.market(ticker)
        step = number(market["stepSize"])
        if number(size) % step:
            raise ValueError("Order size must be an exact multiple of market stepSize")
        is_market = price is None
        if is_market:
            if not 0 < number(slippage) < 1:
                raise ValueError("slippage must be between zero and one")
            book = self.get("orderbooks/perpetualMarket/" + ticker)
            best = number(book["asks" if side == "BUY" else "bids"][0]["price"])
            price = best * (1 + number(slippage) if side == "BUY" else 1 - number(slippage))
        price = self.round_price(ticker, price, "SELL" if is_market and side == "BUY" else "BUY" if is_market else side)
        if price <= 0:
            raise ValueError("Order price must be positive")
        intent = [ticker, side, str(number(size)), bool(reduce_only), bool(post_only), is_market, None if is_market else str(price)]
        orders = self.journal.data["orders"]
        if key in orders:
            reference = orders[key]
            if reference["intent"] != intent:
                raise ValueError("An existing order key cannot be reused for a different order")
            self.wait_visible(reference)
            return reference
        flags = OrderFlags.SHORT_TERM if is_market else OrderFlags.LONG_TERM
        reference = {"client_id": secrets.randbits(32), "flags": int(flags), "market": ticker, "side": side, "size": str(number(size)), "price": str(price), "intent": intent}
        expiry = int(till) if till is not None else int(time.time()) + 86400
        if not is_market and not int(time.time()) + 60 <= expiry <= int(time.time()) + 95 * 86400:
            raise ValueError("Limit order expiry must be 60 seconds to 95 days in the future")
        sdk_market = Market(market)
        oid = sdk_market.order_id(self.address, self.subaccount, reference["client_id"], flags)
        expiry_args = {"good_til_block": self.runner.run(self.node.latest_block_height()) + 20} if is_market else {"good_til_block_time": expiry}
        message = sdk_market.order(oid, OrderType.MARKET if is_market else OrderType.LIMIT, Order.SIDE_BUY if side == "BUY" else Order.SIDE_SELL, size=float(number(size)), price=float(price), time_in_force=Order.TIME_IN_FORCE_IOC if is_market else Order.TIME_IN_FORCE_UNSPECIFIED, reduce_only=reduce_only, post_only=post_only, **expiry_args)
        # Save before the network call, including on ambiguous timeout failures.
        orders[key] = reference
        self.journal.save()
        response = self.runner.run(self.node.place_order(self.wallet, message))
        if response.tx_response.code:
            raise RuntimeError("Order rejected: " + response.tx_response.raw_log)
        reference["txhash"] = response.tx_response.txhash
        self.journal.save()
        self.wait_visible(reference)
        return reference

    def cancel(self, reference):
        current = self.status(reference)
        if current["status"] in TERMINAL:
            return current
        market = Market(self.market(reference["market"]))
        oid = market.order_id(self.address, self.subaccount, reference["client_id"], reference["flags"])
        expiry = {"good_til_block": self.runner.run(self.node.latest_block_height()) + 20} if reference["flags"] == int(OrderFlags.SHORT_TERM) else {"good_til_block_time": int(time.time()) + 120}
        response = self.runner.run(self.node.cancel_order(self.wallet, oid, **expiry))
        if response.tx_response.code:
            current = self.status(reference)
            if current["status"] in TERMINAL:
                return current
            raise RuntimeError("Cancellation rejected: " + response.tx_response.raw_log)
        for _ in range(30):
            current = self.status(reference)
            if current["status"] in TERMINAL:
                return current
            time.sleep(1)
        raise TimeoutError("Cancellation not confirmed; replacement order was not submitted")

    def execution(self, reference):
        order = self.status(reference)
        filled = number(order["totalFilled"])
        if filled == 0:
            return filled, number(0), number(0)
        matching = {}
        cursor = None
        while True:
            params = dict(address=self.address, subaccountNumber=self.subaccount, ticker=reference["market"], limit=100)
            if cursor is not None:
                params["createdBeforeOrAt"] = cursor
            batch = self.get("fills", **params)["fills"]
            for fill in batch:
                if fill["orderId"] == order["id"]:
                    matching[fill["id"]] = fill
            quantity = sum((number(f["size"]) for f in matching.values()), number(0))
            if quantity == filled:
                reference["last_fill_at"] = max(f["createdAt"] for f in matching.values())
                value = sum((number(f["size"]) * number(f["price"]) for f in matching.values()), number(0))
                fee = sum((number(f["fee"]) for f in matching.values()), number(0))
                return quantity, value / quantity, fee
            if not batch or batch[-1]["createdAt"] == cursor:
                raise RuntimeError("Fill history has not reconciled with the order; refusing to guess execution price")
            cursor = batch[-1]["createdAt"]

    def close(self):
        self.session.close()
        self.runner.close()
        self.network.node.channel.close()
