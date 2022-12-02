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
wait = 0
beginOrder = None
trades = []
user = None


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
    global trades
    conf = config()

    order = xchange.private.create_order(
        position_id=account['positionId'],
        market=conf['main']['market'],
        side=aSide,
        order_type=ORDER_TYPE_LIMIT,
        post_only=False,
        size=str(aSize),
        price=str(aPrice),
        limit_fee='0.1',
        expiration_epoch_seconds=GOOD_TILL,
    ).data['order']

    log(f'{aSide} order placed at {aPrice} ')
    return order

def profit():
    global trades
    global user

    fee = user['makerFeeRate']
    conf = config()
    aFee = 0

    matcher = trades
    total = 0

    while len(matcher)>0:

        i1 = matcher[0]
        aSide = i1[0] # buy or sell
        aOpposite = 'sell' if aSide == 'buy' else 'buy'
        print(matcher)

        # lets look for corresponding opposite order
        matcher.remove(i1)
        for i2 in matcher:
            print(i2)
            print((aOpposite,i1[1] + conf['bounds']['step'],i1[2]))
            if i2 == (aOpposite,i1[1] + conf['bounds']['step'],i1[2]):
                print('in')
                total += abs(int(i2[1] * J) - int(i1[1] * J)) * i2[2]
                # remove fee
                aFee = int(i2[1] * i2[2] * fee * J)
                aFee += int(i1[1] * i1[2] * fee * J)

                matcher.remove(i2)
                break

    log(f'Total profit 💰 {total/J} - fee {aFee/J} = {(total - aFee)/J}')


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
    global beginOrder
    conf = config()

    message = json.loads(message)
    if message['type'] != 'channel_data':
        return

    if len(message['contents']['orders']) == 0:
        return

    foundFlag = False
    for order in message['contents']['orders']:
        if order['status'] != 'FILLED':
            break

        # Lets find the order that has been filled
        for j in grid:
            if grid[j] is not None:
                if order['id'] == grid[j]['id']:
                    foundFlag = True
                    break

    if not foundFlag:
        return

    if beginOrder is not None:
            if order['id'] == beginOrder['id']:
            # trigger order executed
                log('Start order filled 🚀 We are in business!')
                beginOrder = None

    orderType = grid[j]['side']
    orderPrice = grid[j]['price']
    orderSize = grid[j]['size']
    log(F'{orderType} order filled at {orderPrice}')
    trades.append((orderType.lower(),float(orderPrice),float(orderSize)))
    
    profit()

    # found it, let's build around it
    grid[j] = None

    x = j

    numOrders = 0
    for i in range(j + int(conf['bounds']['step'] * J), int(conf['bounds']['high'] * J) + int(conf['bounds']['step'] * J), int(conf['bounds']['step'] * J)):
        if numOrders < conf['orders']['above'] and grid[i] is None:
            price = i / J
            grid[i] = createOrder(ORDER_SIDE_SELL, conf['orders']['size'], price)

        if numOrders >= conf['orders']['above'] and grid[i] is not None:
            orderType = grid[i]['side']
            orderPrice = grid[i]['price']
            log(f'Cancel {orderType} above at {orderPrice}')
            try:
                xchange.private.cancel_order(grid[i]['id'])
            except:
                log('Cancel order error 😡 manually canceled?')
            grid[i] = None
        numOrders += 1

    j = x

    numOrders = 0
    for i in range(j - int(conf['bounds']['step'] * J), int(conf['bounds']['low'] * J) - int(conf['bounds']['step'] * J), int(-conf['bounds']['step'] * J)):
        if numOrders < conf['orders']['below'] and grid[i] is None:
            price = i / J
            grid[i] = createOrder(ORDER_SIDE_BUY, conf['orders']['size'], price)

        if numOrders >= conf['orders']['below'] and grid[i] is not None:
            orderType = grid[i]['side']
            orderPrice = grid[i]['price']
            log(f'Cancel {orderType} order below at {orderPrice}')
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
    global user
    global beginOrder        
    # To keep connection API active
    user = xchange.private.get_user().data['user']

    conf = config()
    if conf['start']['price'] == 0:
        if beginOrder is not None:
                if beginOrder['status'] == 'PENDING':
                    log('Start order time out 😴 Exiting.')
                    xchange.private.cancel_order(beginOrder['id'])
                    ws.close()


def main():
    global xchange
    global signature
    global signature_time
    global grid
    global account
    global beginOrder
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

    log('Grid build.')

    for x in range(
            int(conf['bounds']['low'] * J),
            int(conf['bounds']['high'] * J) +
        int(conf['bounds']['step'] * J),
            int(conf['bounds']['step'] * J)):
        grid[x] = None

    
    if conf['start']['price'] == 0: # zero means start at market price
        orderBook = xchange.public.get_orderbook(conf['main']['market']).data
        ask = float(orderBook['asks'][0]['price'])
        bid = float(orderBook['bids'][0]['price'])
        price = (ask + bid) / 2
    else:
        price = conf['start']['price']

    log('Place start order.')
    # location = gridline above current price
    location = list(grid)[bisect(list(grid), price*J)]

    if conf['start']['order'] == 'buy':
        startOrder = ORDER_SIDE_BUY
        x = location - int(conf['bounds']['step'] * J)

    if conf['start']['order'] == 'sell':
        startOrder = ORDER_SIDE_SELL
        x = location

    price = x / J

    grid[x] = createOrder(startOrder, conf['start']['size'], price)
    beginOrder = grid[x]

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