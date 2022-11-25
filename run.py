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

from config import config


# Constants
J = 10000000000
GOOD_TILL = 1672531200

# Global Vars
xchange = None
signature = None
signature_time = None
grid = {}
account = None


def log(msg):
    conf = config()
    msg = conf['main']['name'] + ':' + msg
    print(datetime.datetime.now().isoformat(), msg)

    if conf['telegram']['chatid'] == '' or conf['telegram']['bottoken'] == '':
        return

    params = {
        'chat_id': conf['telegram']['chatid'],
        'text': msg
    }
    payload_str = urllib.parse.urlencode(params, safe='@')
    requests.get(
        'https://api.telegram.org/bot' +
        conf['telegram']['bottoken'] + '/sendMessage',
        params=payload_str
    )

def createOrder(aSide, aSize, aPrice):
    global xchange
    global account
    conf = config()

    order = xchange.private.create_order(
        position_id=account['positionId'],
        market=conf['main']['market'],
        side=aSide,
        order_type=ORDER_TYPE_LIMIT,
        post_only=False,
        size=aSize,
        price=aPrice,
        limit_fee='0.1',
        expiration_epoch_seconds=GOOD_TILL,
    ).data['order']

    log(f'Placed {aSide} order at {aPrice} : {order["status"]}')
    return order 

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
    global grid
    conf = config()

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

    if conf['main']['above'] == 'buy':
        aboveOrder = ORDER_SIDE_BUY
    else:
        aboveOrder = ORDER_SIDE_SELL

    if conf['main']['below'] == 'buy':
        belowOrder = ORDER_SIDE_BUY
    else:
        belowOrder = ORDER_SIDE_SELL

    # found it, let's build around it
    grid[j] = None

    x = j
    maxOrders = conf['orders']['above']
    numOrders = 0
    for i in range(j + int(conf['bounds']['step'] * J), int(conf['bounds']['high'] * J) + int(conf['bounds']['step'] * J), int(conf['bounds']['step'] * J)):
        if numOrders < conf['orders']['above'] and grid[i] is None:
            price = str(i / J)
            grid[i] = createOrder(aboveOrder, str(conf['orders']['size']), price)

        if numOrders >= conf['orders']['above'] and grid[i] is not None:
            orderType = grid[i]['side']
            orderPrice = grid[i]['price']
            log(f'Cancelling {orderType} above at {orderPrice}')
            try:
                xchange.private.cancel_order(grid[i]['id'])
            except:
                log('Error cancelling order, possibly already canceled. Moving on...')
            grid[i] = None
        numOrders += 1

    j = x
    maxOrders = conf['orders']['below']
    numOrders = 0
    for i in range(j - int(conf['bounds']['step'] * J), int(conf['bounds']['low'] * J) - int(conf['bounds']['step'] * J), int(-conf['bounds']['step'] * J)):
        if numOrders < conf['orders']['below'] and grid[i] is None:
            price = str(i / J)
            grid[i] = createOrder(belowOrder, str(conf['orders']['size']), price)

        if numOrders >= conf['orders']['below'] and grid[i] is not None:
            orderType = grid[i]['side']
            orderPrice = grid[i]['price']
            log(f'Cancelling {orderType} order below at {orderPrice}')
            try:
                xchange.private.cancel_order(grid[i]['id'])
            except:
                log('Error cancelling order, possibly already canceled. Moving on...')
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

def on_ping(ws, message):
    global account        
    # To keep connection API active
    account = xchange.private.get_account().data['account']

def main():
    global xchange
    global signature
    global signature_time
    global grid
    global account

    grid = {}
    startTime = datetime.datetime.now()
    conf = config()

    log(f'Start time {startTime.isoformat()} - strategy loaded.')

    log('Connecting to exchange.')
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

    log('Getting initial account data')
    account = xchange.private.get_account().data['account']

    log('Building grid')

    for x in range(
            int(conf['bounds']['low'] * J),
            int(conf['bounds']['high'] * J) +
        int(conf['bounds']['step'] * J),
            int(conf['bounds']['step'] * J)):
        grid[x] = None

    orderBook = xchange.public.get_orderbook(conf['main']['market']).data
    ask = float(orderBook['asks'][0]['price'])
    bid = float(orderBook['bids'][0]['price'])
    price = (ask + bid) / 2

    log('Placing start order')
    # location = gridline above current price
    location = list(grid)[bisect(list(grid), price*J)]

    if conf['start']['order'] == 'buy':
        startOrder = ORDER_SIDE_BUY

    if conf['start']['order'] == 'sell':
        startOrder = ORDER_SIDE_SELL

    startLocation = conf['start']['location']

    if  startLocation == 'below':
        x = location - int(conf['bounds']['step'] * J)
    else:
        x = location

    price = x / J
    grid[x] = createOrder(startOrder, str(conf['start']['size']), str(price))

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
