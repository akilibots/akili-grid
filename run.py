import datetime
import json
import urllib
import websocket
from os import environ
from bisect import bisect

from dydx3 import Client
from dydx3.constants import *
from dydx3.helpers.request_helpers import generate_now_iso

J = 10000000000

def log(msg):
    msg = config['main']['name'] + ':' + msg
    print(datetime.datetime.now().isoformat(), msg)

    if config['telegram']['chatid'] == '' or config['telegram']['bottoken'] == '':
        return

    params = {
        'chat_id': config['telegram']['chatid'].telegram.chatid,
        'text': msg
    }
    payload_str = urllib.parse.urlencode(params, safe='@')
    urllib.get('https://api.telegram.org/bot' + config['telegram']['bottoken'] + '/sendMessage', params=payload_str)

def ws_open(ws):
    # Subscribe to order book updates
    log('Subscribing to account details')
    ws.send(json.dumps({
        'type':'subscribe',
        'channel':'v3_accounts',
        'accountNumber':'0',
        'apiKey': xchange.api_key_credentials['key'],
        'passphrase': xchange.api_key_credentials['passphrase'],
        'timestamp':signature_time,
        'signature':signature,
    }))

def ws_message(ws, message):
    # We are realoading configs so that you can update the grid when it is running
    config = json.loads(environ['strategy'])

    message = json.loads(message)
    if message['type']!='channel_data':
        return

    if len(message['contents']['orders']) == 0:
        return

    order = message['contents']['orders'][0]
    if order['status']!='FILLED':
        return
   
    orderType = order['side']
    orderPrice = order['price']
    log(F'{orderType} order filled at {orderPrice}')

    if config['main']['above'] == 'buy':
        aboveOrder = ORDER_SIDE_BUY
    else:
        aboveOrder = ORDER_SIDE_SELL

    if config['main']['below'] == 'buy':
        belowOrder = ORDER_SIDE_BUY
    else:
        belowOrder = ORDER_SIDE_SELL

    # Lets find the order that has been filled
    for j in grid:
        if grid[j] is None:
            continue

        if order['id'] != grid[j]['id']:
            continue

        # found it, let's build around it
        grid[j] = None
        
        x = j
        a = config['orders']['above']
        numOrders = 0
        for i in range(j + int(config['bounds']['step'] * J),int(config['bounds']['high'] * J) + int(config['bounds']['step'] * J), int(config['bounds']['step'] * J)):
            if numOrders < config['orders']['above'] and grid[i] is None:
                price =str(i / J)    
                log(f'Placing {aboveOrder} order above at {price} - {numOrders+1}/{a}')
                grid[i] = xchange.private.create_order(
                    position_id=position_id,
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
                log(f'Cancelling {orderType} at {orderPrice}')
                xchange.private.cancel_order(grid[i]['id'])
                grid[i] = None
            numOrders += 1

 
        x = j
        a = config['orders']['below']
        numOrders = 0
        for i in range(j - int(config['bounds']['step'] * J),int(config['bounds']['low'] * J) -int(config['bounds']['step'] * J), int(-config['bounds']['step'] * J)):
            if numOrders < config['orders']['below'] and grid[i] is None:
                price =str(i / J)    
                log(f'Placing {belowOrder} order below at {price} - {numOrders+1}/{a}')
                grid[i] = xchange.private.create_order(
                    position_id=position_id,
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
                log(f'Cancelling {orderType} at {orderPrice}')
                xchange.private.cancel_order(grid[i]['id'])
                grid[i] = None
            numOrders += 1
        break


def ws_close(ws,p2,p3):
    pass

def main():
    global config
    global xchange 
    global signature
    global signature_time
    global grid
    global position_id
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
    position_id = xchange.private.get_account().data['account']['positionId']

    log('Building grid')
    x = int(config['bounds']['low'] * J)
    i =0
    while x <= config['bounds']['high'] * J:
        grid[x]=None
        x+=int(config['bounds']['step'] * J)

    orderBook = xchange.public.get_orderbook(config['main']['market']).data
    ask = float(orderBook['asks'][0]['price'])
    bid = float(orderBook['bids'][0]['price'])
    price = (ask + bid) / 2

    log('Placing starting orders')
    location=list(grid)[bisect(list(grid),price*J)]
    if config['main']['above'] == 'buy':
        aboveOrder = ORDER_SIDE_BUY
    else:
        aboveOrder = ORDER_SIDE_SELL

    if config['main']['below'] == 'buy':
        belowOrder = ORDER_SIDE_BUY
    else:
        belowOrder = ORDER_SIDE_SELL
    
    x = location        
    a = config['orders']['above']
    for i in range(a):
        x += config['bounds']['step'] * J
        price =str(x / J)    
        log(f'Placing {aboveOrder} order above at {price} - {i+1}/{a}')
        grid[x] = xchange.private.create_order(
            position_id=position_id,
            market=config['main']['market'],
            side=aboveOrder,
            order_type=ORDER_TYPE_LIMIT,
            post_only=True,
            size=str(config['orders']['size']),
            price=price,
            limit_fee='0',
            expiration_epoch_seconds=9000000000,
        ).data['order']

    x = location
    a = config['orders']['below']
    for i in range(a):
        x -= config['bounds']['step'] * J
        price = str(x / J)    
        log(f'Placing {belowOrder} order below at {price} - {i+1}/{a}')
        grid[x] = xchange.private.create_order(
            position_id=position_id,
            market=config['main']['market'],
            side=belowOrder,
            order_type=ORDER_TYPE_LIMIT,
            post_only=True,
            size=str(config['orders']['size']),
            price=price,
            limit_fee='0',
            expiration_epoch_seconds=9000000000,
        ).data['order']

    log('Starting bot loop')
    wsapp = websocket.WebSocketApp(
        WS_HOST_MAINNET,
        on_open = ws_open,
        on_message = ws_message,
        on_close = ws_close,
    )

    wsapp.run_forever()

if __name__ == "__main__":
    main()