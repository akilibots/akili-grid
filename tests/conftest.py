import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import State, number


class FakeExchange:
    def __init__(self):
        self.orders = {}
        self.calls = []
        self.mid = number(100)
        self.base, self.quote = 'BTC', 'USDT'
        self.cancel_race = None

    def price(self, *args):
        return self.mid

    def place(self, key, *args, **kwargs):
        if key in self.orders:
            return self.orders[key]
        if len(args) == 4:
            ticker, side, size, price = args
        elif len(args) == 3 and args[0] in {'BUY', 'SELL'}:
            side, size, price = args
        elif len(args) == 3:
            ticker, side, size = args
            price = self.mid
        elif len(args) == 2:
            side, size = args
            price = self.mid
        else:
            raise AssertionError(args)
        ref = {'id': key, 'client_id': key, 'side': side, 'size': str(size), 'price': str(price), 'status': 'OPEN', 'totalFilled': '0', 'executedQty': '0', 'last_fill_at': key, 'fee': '0', 'market': 'BTC-USD'}
        self.orders[key] = ref
        self.calls.append((key, args, kwargs))
        return ref

    def status(self, ref):
        return self.orders[ref['id']]

    def fill(self, key, size=None, price=None, fee='0', status='FILLED'):
        ref = self.orders[key]
        ref['totalFilled'] = str(size if size is not None else ref['size'])
        ref['executedQty'] = ref['totalFilled']
        ref['execution_price'] = str(price if price is not None else ref['price'])
        ref['status'], ref['fee'] = status, fee

    def cancel(self, ref):
        if self.cancel_race == ref['id']:
            self.fill(ref['id'])
        if self.status(ref)['status'] != 'FILLED':
            self.orders[ref['id']]['status'] = 'CANCELED'
        return self.status(ref)

    def execution(self, ref):
        order = self.status(ref)
        return number(order['totalFilled']), number(order.get('execution_price', order['price'])), number(order['fee'])


@pytest.fixture
def fake():
    return FakeExchange()


@pytest.fixture
def conf():
    return json.loads(Path('data/strategy.json').read_text())


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path
