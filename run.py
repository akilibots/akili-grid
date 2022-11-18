import datetime
import json
import urllib
import websocket
import rel
from os import environ

from dydx3 import Client
from dydx3.constants import *
from dydx3.helpers.request_helpers import generate_now_iso



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
    print(f'{message}')
    order = xchange.private.create_order(position_id=242057,
        market=config['main']['market'],
        side=ORDER_SIDE_BUY,
        order_type=ORDER_TYPE_LIMIT,
        post_only=True,
        size='6.8',
        price='9',
        limit_fee='0',
        expiration_epoch_seconds=9000000000,
    )
    print(order)



def ws_close(ws,p2,p3):
    pass

def main():
    global config
    global xchange 
    global signature
    global signature_time
    
    
    startTime = datetime.datetime.now()
    
    # Load configuration
    config = json.loads(environ['strategy'])

    log(f'Start time {startTime.isoformat()} - strategy loaded.')

    log('Connecting to exchange.')
    xchange = Client(
        network_id=NETWORK_ID_MAINNET,
        host=API_HOST_MAINNET,
        api_key_credentials={
            'key': '8229996a-0599-1467-9d32-fc0d419b954b',
            "secret": "4imKEFSvjDyD-BPRLqkn05dUg9i1Fmp-31_0AOiu",
            "passphrase": "p5BYwGTmptkeWNeSqHhU",
        },
        stark_private_key="037a4c3eb5d94dc257c467c14f5a45fa8bfe19e85c1d240839caae676b935bcf",
        default_ethereum_address="0x54Be6C01459F2c27d9966E064C20D954ec3c22B1",
    )
    log('Signing URL')
    signature_time = generate_now_iso()
    signature = xchange.private.sign(
        request_path='/ws/accounts',
        method='GET',
        iso_timestamp=signature_time,
        data={},
    )   

    log('Starting web loop')
    websocket.enableTrace(True)
    wsapp = websocket.WebSocketApp(
        WS_HOST_MAINNET,
        on_open = ws_open,
        on_message = ws_message,
        on_close = ws_close,
    )

    wsapp.run_forever()

    # log('Fetching ticker.')
    # price = Decimal(xchange.fetch_ticker(CONFIG.type.market)['last'])

    # # Wait for start trigger
    # log(f'Base price is {price}. Waiting for start price.')
    # while price > CONFIG.start.low and price < CONFIG.start.high:
    #     price = Decimal(xchange.fetch_ticker(CONFIG.type.market)['last'])

    # log('Building grid and placing first order.')
    # log(f'Start price hit at {price}')
    # grid = {}
    # gridPrice = CONFIG.bounds.low
    # gridList = [gridPrice]
    # while gridPrice <= CONFIG.bounds.high:
    #     grid[gridPrice] = None
    #     priceDiff = gridPrice - price
    #     if abs(priceDiff) < CONFIG.bounds.step:
    #         if priceDiff > 0 and CONFIG.start.location == 'above':
    #             # gridPrice is above current price. Place above order
    #             log(f'Placing start {CONFIG.start.order} order at {gridPrice} {CONFIG.start.location} {price}')
    #             if CONFIG.start.order == 'buy':
    #                 grid[gridPrice] = xchange.createLimitBuyOrder(CONFIG.type.market, CONFIG.start.amount, gridPrice)['id']
    #             if CONFIG.start.order == 'sell':
    #                 grid[gridPrice] = xchange.createLimitSellOrder(CONFIG.type.market, CONFIG.start.amount, gridPrice)['id']

    #         if priceDiff < 0 and CONFIG.start.location == 'below':
    #             # gridPrice is below current price place below order
    #             log(f'Placing start {CONFIG.start.order} order at {gridPrice} {CONFIG.start.location} {price}')
    #             if CONFIG.start.order == 'buy':
    #                 grid[gridPrice] = xchange.createLimitBuyOrder(CONFIG.type.market, CONFIG.start.amount, gridPrice)['id']
    #             if CONFIG.start.order == 'sell':
    #                 grid[gridPrice] = xchange.createLimitSellOrder(CONFIG.type.market, CONFIG.start.amount, gridPrice)['id']

    #     gridList += [gridPrice]
    #     gridPrice += CONFIG.bounds.step

    # # Main loop
    # price = Decimal(xchange.fetch_ticker(CONFIG.type.market)['last'])
    # log('Starting main loop.')
    # # I use while true and several separate exit conditions because the boolean logic
    # # becomes a headache: There are too many exit conditions to concot one massive while clause        
    # while True:

    #     # EXIT Conditions
    #     if price < CONFIG.stop.low or price > CONFIG.stop.high:
    #         break

    #     if (datetime.datetime.now() - startTime).total_seconds() > CONFIG.stop.time:
    #         break

    #     #TODO: This can be optimised by getting all open orders from the exchange in one call before
    #     # executing the loop instead of calling the exchange to check for each order. But for now, this works.

    #     #TODO: Also need to think of a better way to handle high frequency grids, if several orders have been filled
    #     # as price falls this will work, but not as it goes up
    #     for gridIndex in range(0, len(gridList)):
    #         if grid[gridList[gridIndex]] is not None:
    #             # Check if order is still alive
    #             if xchange.fetch_order(grid[gridList[gridIndex]])['status'] == 'closed':
    #                 # Order has been closed. Mark as closed
    #                 log(f'Order at {gridList[gridIndex]} filled.')
    #                 grid[gridList[gridIndex]] = None

    #                 # Check or place new orders below and remove any not needed
    #                 numOrders = 1
    #                 for newIndex in reversed(range(0, gridIndex)):
    #                     if grid[gridList[newIndex]] is None and numOrders <= CONFIG.orders.below:
    #                         log(f'Placing {CONFIG.type.below} order at price {gridList[newIndex]} below')
    #                         if CONFIG.type.below == 'buy':
    #                             grid[gridList[newIndex]] = xchange.createLimitBuyOrder(CONFIG.type.market, CONFIG.orders.size, gridList[newIndex])['id']
    #                         if CONFIG.type.below == 'sell':
    #                             grid[gridList[newIndex]] = xchange.createLimitSellOrder(CONFIG.type.market, CONFIG.orders.size, gridList[newIndex])['id']

    #                     if numOrders > CONFIG.orders.below and grid[gridList[newIndex]] is not None:
    #                         xchange.cancel_order(grid[gridList[newIndex]])
    #                         grid[gridList[newIndex]] = None

    #                     numOrders += 1

    #                 # Check or place new above and remove any not needed
    #                 numOrders = 1
    #                 for newIndex in range(gridIndex + 1, len(gridList)):
    #                     if grid[gridList[newIndex]] is None and numOrders <= CONFIG.orders.above:
    #                         log(f'Placing {CONFIG.type.above} order at price {gridList[newIndex]} above')
    #                         if CONFIG.type.above == 'buy':
    #                             grid[gridList[newIndex]] = xchange.createLimitBuyOrder(CONFIG.type.market, CONFIG.orders.size, gridList[newIndex])['id']
    #                         if CONFIG.type.above == 'sell':
    #                             grid[gridList[newIndex]] = xchange.createLimitSellOrder(CONFIG.type.market, CONFIG.orders.size, gridList[newIndex])['id']

    #                     if numOrders > CONFIG.orders.above and grid[gridList[newIndex]] is not None:
    #                         xchange.cancel_order(grid[gridList[newIndex]])
    #                         grid[gridList[newIndex]] = None

    #                     numOrders += 1

    #     price = Decimal(xchange.fetch_ticker(CONFIG.type.market)['last'])
    # log("Exiting main loop let's find out why.")
    # #TODO: Finish the app 😁

if __name__ == "__main__":
    main()