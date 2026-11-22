"""Bounded moving grid on dYdX Chain."""
import time
from bisect import bisect_right

from exchange import Exchange, TERMINAL
from runtime import State, load_config, log, number, single_instance


def profit(trades):
    """Match opposite executions one grid level apart, including actual fees."""
    pending = []
    total = number(0)
    for trade in trades:
        remaining = number(trade['size'])
        for previous in pending:
            if previous['side'] == trade['side'] or abs(previous['level'] - trade['level']) != 1:
                continue
            quantity = min(previous['remaining'], remaining)
            if quantity <= 0:
                continue
            buy = previous if previous['side'] == 'BUY' else trade
            sell = trade if trade['side'] == 'SELL' else previous
            fees = number(previous['fee']) / number(previous['size']) + number(trade['fee']) / number(trade['size'])
            total += quantity * (number(sell['price']) - number(buy['price']) - fees)
            previous['remaining'] -= quantity
            remaining -= quantity
        if remaining:
            pending.append({**trade, 'remaining': remaining})
    return total


class Grid:
    def __init__(self, conf, exchange, state=None):
        self.conf, self.exchange = conf, exchange
        low, high, step = (number(conf['bounds'][key]) for key in ('low', 'high', 'step'))
        if low <= 0 or high <= low or step <= 0 or (high - low) % step:
            raise ValueError('Bounds must be positive and span an exact number of steps')
        if number(conf['stop']['price']) != 0:
            raise ValueError('stop.price is unsupported; use zero')
        if conf['start']['order'] not in {'buy', 'sell'}:
            raise ValueError('start.order must be buy or sell')
        for key in ('above', 'below'):
            if type(conf['orders'][key]) is not int or conf['orders'][key] < 0:
                raise ValueError('Active order counts must be nonnegative integers')
        if number(conf['orders']['size']) <= 0 or number(conf['start']['size']) <= 0:
            raise ValueError('Order sizes must be positive')
        self.levels = [low + i * step for i in range(int((high - low) / step) + 1)]
        self.state = state or State(initial={'strategy': conf, 'centre': None, 'start_level': None, 'active': {}, 'serials': {}, 'trades': []})
        if self.state.data['strategy'] != conf:
            raise ValueError('Strategy differs from saved state; reconcile existing orders first')

    def desired(self, centre):
        return {**{i: 'BUY' for i in range(max(0, centre - self.conf['orders']['below']), centre)}, **{i: 'SELL' for i in range(centre + 1, min(len(self.levels), centre + 1 + self.conf['orders']['above']))}}

    def tick(self):
        data = self.state.data
        ticker = self.conf['main']['market']
        if data['centre'] is None and not data['active']:
            if data['start_level'] is None:
                price = number(self.conf['start']['price']) or self.exchange.price(ticker)
                if not self.levels[0] <= price <= self.levels[-1]:
                    raise ValueError('Starting price is outside grid bounds')
                index = bisect_right(self.levels, price) - (1 if self.conf['start']['order'] == 'buy' else 0)
                data['start_level'] = min(index, len(self.levels) - 1)
                self.state.save()
            index = data['start_level']
            serial = data['serials'].get(str(index), 0)
            ref = self.exchange.place(f'start:{serial}', ticker, self.conf['start']['order'].upper(), self.conf['start']['size'], self.levels[index])
            data['active'][str(index)] = ref
            self.state.save()

        completed = []
        for key, ref in list(data['active'].items()):
            order = self.exchange.status(ref)
            if order['status'] not in TERMINAL:
                continue
            quantity, price, fee = self.exchange.execution(ref)
            if quantity and order['status'] != 'FILLED':
                raise RuntimeError('A partially filled grid order terminated; reconcile its remaining position before restarting')
            if quantity:
                completed.append((int(key), ref, quantity, price, fee))
            else:
                del data['active'][key]
                data['serials'][key] = data['serials'].get(key, 0) + 1
                self.state.save()
        for index, ref, quantity, price, fee in sorted(completed, key=lambda row: row[1]['last_fill_at']):
            data['trades'].append({'level': index, 'side': ref['side'], 'size': str(quantity), 'price': str(price), 'fee': str(fee)})
            del data['active'][str(index)]
            data['serials'][str(index)] = data['serials'].get(str(index), 0) + 1
            data['centre'] = index
            self.state.save()
        if completed:
            log('Matched net grid profit: ' + str(profit(data['trades'])), self.conf['main']['name'])
        if data['centre'] is None:
            return
        desired = self.desired(data['centre'])
        for key, ref in list(data['active'].items()):
            if int(key) not in desired or ref['side'] != desired[int(key)]:
                result = self.exchange.cancel(ref)
                if number(result['totalFilled']):
                    return
                del data['active'][key]
                data['serials'][key] = data['serials'].get(key, 0) + 1
                self.state.save()
        for index, side in desired.items():
            key = str(index)
            if key not in data['active']:
                serial = data['serials'].get(key, 0)
                ref = self.exchange.place(f'grid:{key}:{serial}', ticker, side, self.conf['orders']['size'], self.levels[index])
                data['active'][key] = ref
                self.state.save()


def main():
    conf = load_config()
    with single_instance():
        exchange = Exchange(conf['exchange'])
        try:
            bot = Grid(conf, exchange)
            while True:
                bot.tick()
                time.sleep(conf['exchange']['poll_seconds'])
        finally:
            exchange.close()


if __name__ == '__main__':
    main()
