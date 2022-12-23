import datetime
import json
import requests
import urllib
import websocket
import threading
import os
import time

from bisect import bisect
from decimal import Decimal

from dydx3 import Client
from dydx3.constants import *
from dydx3.helpers.request_helpers import generate_now_iso

from config import config


# Constants
TO_INT = 1000000000  # Based on the number of decimals in the market
GOOD_TILL = 31536000

# Global Vars
xchange = None
signature = None
signature_time = None
grid = {}
account = None
wait = 0
begin_order = None
trades = []
user = None


def log(msg):
    def _log(_msg):
        conf = config()
        _msg = conf['main']['name'] + ':' + _msg
        print(datetime.datetime.now().isoformat(), _msg)

        if conf['telegram']['chatid'] == '' or conf['telegram']['bottoken'] == '':
            return

        params = {
            'chat_id': conf['telegram']['chatid'],
            'text': _msg
        }
        payload_str = urllib.parse.urlencode(params, safe='@')
        requests.get(
            'https://api.telegram.org/bot' +
            conf['telegram']['bottoken'] + '/sendMessage',
            params=payload_str
        )
    threading.Thread(target=_log, args=[msg]).start()


def save_state():
    # Save state of grid so that it can resume in case it dies for some reason
    global grid
    global trades

    # Update grid orders before saving
    # TODO - get all orders in one batch to avoid calling get_order_by_id for each order
    for row in grid:
        if grid[row] is None:
            continue
        grid[row] = xchange.private.get_order_by_id(
            grid[row]['id']).data['order']

    save_data = {
        'grid': grid,
        'trades': trades
    }

    with open("data/state.json", "w") as f:
        json.dump(save_data, f)


def load_state():
    global grid
    global trades
    log('Check for saved state.')
    if not os.path.isfile('data/state.json'):
        log('No state saved. Start new.')
        return False

    with open("data/state.json", "r") as f:
        load_data = json.load(f)
    log('State loaded.')
    grid = load_data['grid'].copy()
    trades = load_data['trades'].copy()

    # check if all orders are as we left them
    # for order in grid:
    #    if grid[order] is None:
    #        continue
    #    if xchange.private.get_order_by_id(grid['order']['id']).data['order']['status'] != grid[order]['status']:
    #        log('Orders changed can not start.')
    #        exit()
    return True


def place_order(side, size, price):
    global xchange
    global account

    conf = config()

    order = xchange.private.create_order(
        position_id=account['positionId'],
        market=conf['main']['market'],
        side=side,
        order_type=ORDER_TYPE_LIMIT,
        post_only=False,
        size=str(size),
        price=str(price),
        limit_fee='0.1',
        expiration_epoch_seconds=int(time.time()) + GOOD_TILL,
    ).data['order']

    log(f'{side} order placed at {price} ')
    return order


def profit():
    global trades
    global user

    xchange_fee = Decimal(user['makerFeeRate'])
    conf = config()
    step = Decimal(str(conf['bounds']['step']))
    total = Decimal('0')
    fee = Decimal('0')
    calc = trades.copy()

    while len(calc)>0:
        open_trade = calc[0]
        calc.remove(open_trade)
        open_trade['price'] = Decimal(str(open_trade['price']))
        open_trade['size'] = Decimal(str(open_trade['size']))
        for close_trade in calc:
            close_trade['price'] = Decimal(str(close_trade['price']))
            close_trade['size'] = Decimal(str(close_trade['size']))
            if open_trade['size'] < 0: # this is a buy order, find corresponding sell order
                if close_trade == {'price':open_trade['price'] + step, 'size':-open_trade['size']}:
                    total += step * close_trade['size']
                    fee = close_trade['size'] * xchange_fee
                    total -= (fee * 2)
                    calc.remove(close_trade)
                    break
            if open_trade['size'] > 0: # this is a sell order, find corresponding buy order
                if close_trade == {'price':open_trade['price'] - step, 'size':-open_trade['size']}:
                    total += step * -close_trade['size']
                    fee = -close_trade['size'] * xchange_fee
                    total -= (fee * 2)
                    calc.remove(close_trade)
                    break

    log(f'Total profit 💰 {total}')

def ws_open(ws):
    # Subscribe to order book updates
    log('Subscribing to order changes')
    ws.send(json.dumps({
        'type': 'subscribe',
        'channel': 'v3_accounts',
        'accountNumber': '0',
        'apiKey': xchange.api_key_credentials['key'],
        'passphrase': xchange.api_key_credentials['passphrase'],
        'timestamp': signature_time,
        'signature': signature,
    }))


def ws_message(ws, message):
    # Process order book updates
    global grid
    global begin_order
    conf = config()

    message = json.loads(message)
    if message['type'] != 'channel_data':
        # Not an order book update
        return

    if len(message['contents']['orders']) == 0:
        # No orders to process
        return

    for order in message['contents']['orders']:
        if order['status'] == 'CANCELED':
            # Reinstate ALL cancelled orders (CANCELED is mis-spelt smh Americans!!)
            for cancelled_order in grid:
                if grid[cancelled_order] is not None:
                    if grid[cancelled_order]['id'] == order['id']:
                        log(
                            f'Recreating cancelled 😡 {grid[cancelled_order]["side"]} order at {grid[cancelled_order]["price"]}')
                        grid[cancelled_order] = place_order(
                            grid[cancelled_order]['side'], grid[cancelled_order]['size'], grid[cancelled_order]['price'])
            # Save any re-instated orders
            save_state()

    found_flag = False
    for order in message['contents']['orders']:
        if order['status'] == 'FILLED':
            # Lets find the order that has been filled
            for filled_order in grid:
                if grid[filled_order] is not None:
                    if grid[filled_order]['id'] == order['id']:
                        found_flag = True
                        break
    if not found_flag:
        # Not one of our orders
        return

    if begin_order is not None:
        if order['id'] == begin_order['id']:
            # Start order filled
            log('Start order filled 🚀')
            begin_order = None

    order_type = grid[filled_order]['side']
    order_price = grid[filled_order]['price']
    order_size = grid[filled_order]['size']
    log(F'{order_type} filled 🥧 at {order_price}')
    trades.append({'price':float(order_price), 'size':-float(order_size) if order_type=='BUY' else float(order_size)})

    # found it, let's build around it
    grid[filled_order] = None

    # Build sell orders upwards to highest order
    num_orders = 0
    step = int(conf['bounds']['step'] * TO_INT)
    high_order = int(conf['bounds']['high'] * TO_INT)

    for i in range(filled_order + step, high_order + step, step):
        if i in grid:
            if num_orders < conf['orders']['above'] and grid[i] is None:
                price = i / TO_INT
                grid[i] = place_order(
                    ORDER_SIDE_SELL, conf['orders']['size'], price)

            if num_orders >= conf['orders']['above'] and grid[i] is not None:
                order_type = grid[i]['side']
                order_price = grid[i]['price']
                log(f'Cancel {order_type} above at {order_price}')
                try:
                    xchange.private.cancel_order(grid[i]['id'])
                except:
                    log('Cancel order error 🤔')
                grid[i] = None
            num_orders += 1

    num_orders = 0

    low_order = int(conf['bounds']['low'] * TO_INT)
    # Build buy orders downwards to lowest order
    for i in range(filled_order - step, low_order - step, -step):
        if i in grid:
            if num_orders < conf['orders']['below'] and grid[i] is None:
                price = i / TO_INT
                grid[i] = place_order(
                    ORDER_SIDE_BUY, conf['orders']['size'], price)

            if num_orders >= conf['orders']['below'] and grid[i] is not None:
                order_type = grid[i]['side']
                order_price = grid[i]['price']
                log(f'Cancel {order_type} order below at {order_price}')
                try:
                    xchange.private.cancel_order(grid[i]['id'])
                except:
                    log('Cancel order error 🤔')
                grid[i] = None
            num_orders += 1
    
    profit()
    save_state()


def ws_close(ws, p2, p3):
    global grid

    log('NO, not going to bed 🛌')
    save_state()
    #log('Grid terminated by user.')
    #for i in grid:
    #    if grid[i] is not None:
    #        order_type = grid[i]['side']
    #        order_price = grid[i]['price']

    #        log(f'Cancelling {order_type} order at {order_price}')
    #        xchange.private.cancel_order(grid[i]['id'])
    #        grid[i] = None


def on_ping(ws, message):
    global user
    global begin_order
    # To keep connection API active
    user = xchange.private.get_user().data['user']

    conf = config()
    if conf['start']['price'] == 0:
        if begin_order is not None:
            # TODO: The starting order can be partially filled. We need to compare remainingSize and size
            if begin_order['status'] == 'PENDING':
                log('Start order time out 😴 Exiting.')
                xchange.private.cancel_order(begin_order['id'])
                os.remove('data/state.json')
                ws.close()


def main():
    global xchange
    global signature
    global signature_time
    global grid
    global account
    global begin_order
    global user

    startTime = datetime.datetime.now()
    conf = config()

    log(f'Start time {startTime.isoformat()} - strategy loaded.')

    log('dYdX connect.')
    xchange = Client(
        network_id=NETWORK_ID_MAINNET,
        host=API_HOST_MAINNET,
        api_key_credentials={
            'key': conf['dydx']['APIkey'],
            'secret': conf['dydx']['APIsecret'],
            'passphrase': conf['dydx']['APIpassphrase'],
        },
        stark_private_key=conf['dydx']['stark_private_key'],
        default_ethereum_address=conf['dydx']['default_ethereum_address'],
    )

    signature_time = generate_now_iso()
    signature = xchange.private.sign(
        request_path='/ws/accounts',
        method='GET',
        iso_timestamp=signature_time,
        data={},
    )

    log('Initialise account.')
    account = xchange.private.get_account().data['account']
    user = xchange.private.get_user().data['user']

    if not load_state():
        # New grid
        log('Start grid.')

        for price_index in range(
                int(conf['bounds']['low'] * TO_INT),
                int(conf['bounds']['high'] * TO_INT) +
            int(conf['bounds']['step'] * TO_INT),
                int(conf['bounds']['step'] * TO_INT)):
            grid[price_index] = None

        if conf['start']['price'] == 0:  # zero means start at market price
            orderBook = xchange.public.get_orderbook(
                conf['main']['market']).data
            ask = float(orderBook['asks'][0]['price'])
            bid = float(orderBook['bids'][0]['price'])
            price = (ask + bid) / 2
        else:
            price = conf['start']['price']

        log('Place start order.')
        # location = gridline above current price
        location = list(grid)[bisect(list(grid), price*TO_INT)]

        if conf['start']['order'] == 'buy':
            startOrder = ORDER_SIDE_BUY
            price_index = location - int(conf['bounds']['step'] * TO_INT)

        if conf['start']['order'] == 'sell':
            startOrder = ORDER_SIDE_SELL
            price_index = location

        price = price_index / TO_INT

        grid[price_index] = place_order(
            startOrder, conf['start']['size'], price)
        begin_order = grid[price_index]
        save_state()

    # websocket.enableTrace(True)
    wsapp = websocket.WebSocketApp(
        WS_HOST_MAINNET,
        on_open=ws_open,
        on_message=ws_message,
        on_close=ws_close,
        on_ping=on_ping
    )

    wsapp.run_forever(ping_interval=60, ping_timeout=20)


if __name__ == "__main__":
    main()
