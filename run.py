import datetime
import json
import requests
import urllib
import websocket
from os import environ
from bisect import bisect

from dydx3 import Client
from dydx3.constants import *
from dydx3.helpers.request_helpers import generate_now_iso


# Constants
J = 10000000000

# Global Vars
config = None
xchange = None
signature = None
signature_time = None
grid = {}
account = None


def log(msg):
    msg = config['main']['name'] + ':' + msg
    print(datetime.datetime.now().isoformat(), msg)

    if config['telegram']['chatid'] == '' or config['telegram']['bottoken'] == '':
        return

    params = {
        'chat_id': config['telegram']['chatid'],
        'text': msg
    }
    payload_str = urllib.parse.urlencode(params, safe='@')
    requests.get(
        'https://api.telegram.org/bot' +
        config['telegram']['bottoken'] + '/sendMessage',
        params=payload_str
    )


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
    global config
    global grid

    # We are realoading configs so that you can update the grid when it is running
    config = json.loads(environ['strategy'])

    message = json.loads(message)
    if message['type'] != 'channel_data':
        return

    if len(message['contents']['orders']) == 0:
        return

    order = message['contents']['orders'][0]
    if order['status'] != 'FILLED':
        return

    # Lets find the order that has been filled
    foundFlag = False
    for j in grid:
        if grid[j] is not None:
            if order['id'] == grid[j]['id']:
                foundFlag = True
                break

    if not foundFlag:
        return

    orderType = grid[j]['side']
    orderPrice = grid[j]['price']
    log(F'{orderType} order filled at {orderPrice}')

    if config['main']['above'] == 'buy':
        aboveOrder = ORDER_SIDE_BUY
    else:
        aboveOrder = ORDER_SIDE_SELL

    if config['main']['below'] == 'buy':
        belowOrder = ORDER_SIDE_BUY
    else:
        belowOrder = ORDER_SIDE_SELL

    # found it, let's build around it
    grid[j] = None

    x = j
    a = config['orders']['above']
    numOrders = 0
    for i in range(j + int(config['bounds']['step'] * J), int(config['bounds']['high'] * J) + int(config['bounds']['step'] * J), int(config['bounds']['step'] * J)):
        if numOrders < config['orders']['above'] and grid[i] is None:
            price = str(i / J)
            log(f'Placing {aboveOrder} order above at {price} - {numOrders+1}/{a}')
            grid[i] = xchange.private.create_order(
                position_id=account['positionId'],
                market=config['main']['market'],
                side=aboveOrder,
                order_type=ORDER_TYPE_LIMIT,
                post_only=True,
                size=str(config['orders']['size']),
                price=price,
                limit_fee='0',
                expiration_epoch_seconds=9000000000,
            ).data['order']

        if numOrders >= config['orders']['above'] and grid[i] is not None:
            orderType = grid[i]['side']
            orderPrice = grid[i]['price']
            log(f'Cancelling {orderType} above at {orderPrice}')
            xchange.private.cancel_order(grid[i]['id'])
            grid[i] = None
        numOrders += 1

    j = x
    a = config['orders']['below']
    numOrders = 0
    for i in range(j - int(config['bounds']['step'] * J), int(config['bounds']['low'] * J) - int(config['bounds']['step'] * J), int(-config['bounds']['step'] * J)):
        if numOrders < config['orders']['below'] and grid[i] is None:
            price = str(i / J)
            log(f'Placing {belowOrder} order below at {price} - {numOrders+1}/{a}')
            grid[i] = xchange.private.create_order(
                position_id=account['positionId'],
                market=config['main']['market'],
                side=belowOrder,
                order_type=ORDER_TYPE_LIMIT,
                post_only=True,
                size=str(config['orders']['size']),
                price=price,
                limit_fee='0',
                expiration_epoch_seconds=9000000000,
            ).data['order']

        if numOrders >= config['orders']['below'] and grid[i] is not None:
            orderType = grid[i]['side']
            orderPrice = grid[i]['price']
            log(f'Cancelling {orderType} order below at {orderPrice}')
            xchange.private.cancel_order(grid[i]['id'])
            grid[i] = None
        numOrders += 1


def ws_close(ws, p2, p3):
    global grid

    log('Grid terminated by user.')
    for i in grid:
        if grid[i] is not None:
            orderType = grid[i]['side']
            orderPrice = grid[i]['price']

            log(f'Cancelling {orderType} order at {orderPrice}')
            xchange.private.cancel_order(grid[i]['id'])
            grid[i] = None
def on_ping(wsapp, message):
    global account
    account = xchange.private.get_account().data['account']
    # log("I'm alive!")

def main():
    global config
    global xchange
    global signature
    global signature_time
    global grid

    grid = {}

    startTime = datetime.datetime.now()

    # Load configuration
    config = json.loads(environ['strategy'])

    log(f'Start time {startTime.isoformat()} - strategy loaded.')

    log('Connecting to exchange.')
    xchange = Client(
        network_id=NETWORK_ID_MAINNET,
        host=API_HOST_MAINNET,
        api_key_credentials={
            'key': config['dydx']['APIkey'],
            'secret': config['dydx']['APIsecret'],
            'passphrase': config['dydx']['APIpassphrase'],
        },
        stark_private_key=config['dydx']['stark_private_key'],
        default_ethereum_address=config['dydx']['default_ethereum_address'],
    )
    log('Signing URL')
    signature_time = generate_now_iso()
    signature = xchange.private.sign(
        request_path='/ws/accounts',
        method='GET',
        iso_timestamp=signature_time,
        data={},
    )

    log('Getting account data')
    account = xchange.private.get_account().data['account']

    log('Building grid')
    for x in range(
            int(config['bounds']['low'] * J),
            int(config['bounds']['high'] * J) +
        int(config['bounds']['step'] * J),
            int(config['bounds']['step'] * J)):
        grid[x] = None

    orderBook = xchange.public.get_orderbook(config['main']['market']).data
    ask = float(orderBook['asks'][0]['price'])
    bid = float(orderBook['bids'][0]['price'])
    price = (ask + bid) / 2

    log('Placing start order')
    # location = gridline above current price
    location = list(grid)[bisect(list(grid), price*J)]

    if config['start']['order'] == 'buy':
        startOrder = ORDER_SIDE_BUY

    if config['start']['order'] == 'sell':
        startOrder = ORDER_SIDE_SELL

    startLocation = config['start']['location']

    if  startLocation == 'below':
        x = location - int(config['bounds']['step'] * J)
    else:
        x = location

    price = x / J

    log(f'Placing {startOrder} order {startLocation} at {price}')
    grid[x] = xchange.private.create_order(
        position_id=account['positionId'],
        market=config['main']['market'],
        side=startOrder,
        order_type=ORDER_TYPE_LIMIT,
        post_only=True,
        size=str(config['orders']['size']),
        price=str(price),
        limit_fee='0',
        expiration_epoch_seconds=9000000000,
    ).data['order']

    log('Starting bot loop')
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
