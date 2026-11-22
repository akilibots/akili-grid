import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from dydx_v4_client import OrderFlags
from dydx_v4_client.key_pair import KeyPair
from dydx_v4_client.wallet import Wallet
from v4_proto.dydxprotocol.clob.order_pb2 import Order

from exchange import Exchange
from runtime import State, number, single_instance

MARKET = {'clobPairId': '0', 'atomicResolution': -10, 'stepBaseQuantums': 1000000, 'quantumConversionExponent': -9, 'subticksPerTick': 100000, 'tickSize': '1', 'stepSize': '0.0001'}


@pytest.fixture
def adapter(state_dir):
    client = Exchange.__new__(Exchange)
    client.address = 'dydx1test'
    client.subaccount = 0
    client.runner = asyncio.Runner()
    client.wallet = object()
    tx = SimpleNamespace(tx_response=SimpleNamespace(code=0, txhash='test-hash', raw_log=''))
    client.node = SimpleNamespace(place_order=AsyncMock(return_value=tx), cancel_order=AsyncMock(return_value=tx), latest_block_height=AsyncMock(return_value=100))
    client.journal = State('data/exchange.json', {'orders': {}})
    client.markets = {'BTC-USD': MARKET}
    client.get = lambda *args, **kwargs: {'bids': [{'price': '99'}], 'asks': [{'price': '101'}]}
    client.wait_visible = lambda ref: {'status': 'OPEN'}
    yield client
    client.runner.close()


def test_limit_order_real_sdk_message_and_durable_identity(adapter):
    ref = adapter.place('entry', 'BTC-USD', 'BUY', '0.001', '100.9')
    message = adapter.node.place_order.call_args.args[1]
    assert message.order_id.order_flags == int(OrderFlags.LONG_TERM)
    assert message.side == Order.SIDE_BUY
    assert message.quantums == 10000000
    assert ref['price'] == '100'
    assert ref['txhash'] == 'test-hash'
    assert State('data/exchange.json').data['orders']['entry']['client_id'] == ref['client_id']
    adapter.place('entry', 'BTC-USD', 'BUY', '0.001', '100.9')
    assert adapter.node.place_order.call_count == 1


@pytest.mark.parametrize('side, expected', [('BUY', '103'), ('SELL', '98')])
def test_market_slippage_is_side_aware_and_uses_short_term_ioc(adapter, side, expected):
    ref = adapter.place('dca', 'BTC-USD', side, '0.001', slippage='0.01')
    message = adapter.node.place_order.call_args.args[1]
    assert message.order_id.order_flags == int(OrderFlags.SHORT_TERM)
    assert message.good_til_block == 120
    assert message.time_in_force == Order.TIME_IN_FORCE_IOC
    assert ref['price'] == expected


def test_timeout_does_not_resubmit_under_a_new_client_id(adapter):
    adapter.node.place_order.side_effect = TimeoutError('connection lost')
    with pytest.raises(TimeoutError):
        adapter.place('entry', 'BTC-USD', 'BUY', '0.001', 100)
    saved = State('data/exchange.json').data['orders']['entry']
    adapter.journal = State('data/exchange.json')
    adapter.place('entry', 'BTC-USD', 'BUY', '0.001', 100)
    assert adapter.node.place_order.call_count == 1
    assert adapter.journal.data['orders']['entry']['client_id'] == saved['client_id']


def test_rejected_broadcast_is_not_reported_as_success(adapter):
    adapter.node.place_order.return_value.tx_response.code = 5
    adapter.node.place_order.return_value.tx_response.raw_log = 'insufficient collateral'
    with pytest.raises(RuntimeError, match='insufficient collateral'):
        adapter.place('entry', 'BTC-USD', 'BUY', '0.001', 100)


def test_precision_and_invalid_expiry_fail_before_broadcast(adapter):
    with pytest.raises(ValueError, match='stepSize'):
        adapter.place('bad', 'BTC-USD', 'BUY', '0.00001', 100)
    with pytest.raises(ValueError, match='expiry'):
        adapter.place('bad', 'BTC-USD', 'BUY', '0.001', 100, till=1672531200)
    assert adapter.node.place_order.call_count == 0


def test_fill_aggregation_uses_execution_prices_and_actual_fees(adapter):
    ref = {'id': 'order', 'market': 'BTC-USD'}
    adapter.status = lambda ref: {'id': 'order', 'totalFilled': '2'}
    adapter.get = lambda *args, **kwargs: {'fills': [{'id': '1', 'orderId': 'order', 'size': '1', 'price': '100', 'fee': '0.1', 'createdAt': '2026-11-22T00:00:00Z'}, {'id': '2', 'orderId': 'order', 'size': '1', 'price': '102', 'fee': '0.102', 'createdAt': '2026-11-22T00:00:01Z'}]}
    assert adapter.execution(ref) == (number(2), number(101), number('0.202'))
    assert ref['last_fill_at'] == '2026-11-22T00:00:01Z'


def test_unknown_order_is_never_assumed_filled(adapter):
    adapter.find = lambda ref: None
    with pytest.raises(RuntimeError, match='uncertain'):
        adapter.status({})


def test_partial_cancel_does_not_hide_execution(adapter):
    ref = {'id': 'order', 'market': 'BTC-USD', 'client_id': 1, 'flags': int(OrderFlags.LONG_TERM)}
    statuses = iter([{'status': 'OPEN', 'totalFilled': '0.0005'}, {'status': 'CANCELED', 'totalFilled': '0.0005'}])
    adapter.status = lambda ref: next(statuses)
    assert adapter.cancel(ref)['totalFilled'] == '0.0005'
    assert adapter.node.cancel_order.call_count == 1


def test_wallet_derivation_is_local_and_sdk_compatible():
    key = KeyPair.from_mnemonic('abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about')
    wallet = Wallet(key, 0, 0)
    assert wallet.address.startswith('dydx1')
    assert len(wallet.public_key.key) == 33


def test_state_lock_prevents_two_instances(state_dir):
    with single_instance():
        with pytest.raises(BlockingIOError):
            with single_instance():
                raise AssertionError('second instance acquired lock')


def test_sdk_signs_a_real_transaction_without_network(adapter):
    from dydx_v4_client.node.builder import Builder
    from dydx_v4_client.node.message import place_order
    adapter.wallet = Wallet(KeyPair.from_mnemonic('abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about'), 0, 0)
    adapter.address = adapter.wallet.address
    adapter.place('signed', 'BTC-USD', 'BUY', '0.001', 100)
    order = adapter.node.place_order.call_args.args[1]
    transaction = Builder('dydx-testnet-4', 'adv4tnt').build(adapter.wallet, place_order(order))
    assert len(transaction.signatures) == 1
    assert len(transaction.signatures[0]) == 64
    assert transaction.SerializeToString()


def test_order_identity_cannot_be_reused_at_a_different_price(adapter):
    adapter.place('entry', 'BTC-USD', 'BUY', '0.001', 100)
    with pytest.raises(ValueError, match='different order'):
        adapter.place('entry', 'BTC-USD', 'BUY', '0.001', 110)
    assert adapter.node.place_order.call_count == 1
