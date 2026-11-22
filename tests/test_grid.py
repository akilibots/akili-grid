import json

import pytest

from run import Grid, profit
from runtime import State, number


def settings(conf):
    conf['bounds'] = {'low': 80, 'high': 120, 'step': 10}
    conf['orders'] = {'above': 1, 'below': 1, 'size': 1}
    conf['start'] = {'price': 100, 'size': 1, 'order': 'buy'}
    return conf


def test_start_fill_recentre_and_resume(conf, fake, state_dir):
    conf = settings(conf)
    bot = Grid(conf, fake)
    bot.tick()
    assert len(fake.calls) == 1
    fake.fill('start:0')
    bot.tick()
    assert bot.state.data['centre'] == 2
    assert {r['side'] for r in bot.state.data['active'].values()} == {'BUY', 'SELL'}
    restored = Grid(conf, fake, State())
    restored.tick()
    assert len(fake.calls) == 3
    fake.fill('grid:3:0')
    restored.tick()
    assert restored.state.data['centre'] == 3
    assert all(isinstance(key, str) for key in restored.state.data['active'])


def test_cancelled_start_is_recreated_once(conf, fake, state_dir):
    bot = Grid(settings(conf), fake)
    bot.tick()
    fake.orders['start:0']['status'] = 'CANCELED'
    bot.tick()
    bot.tick()
    assert [c[0] for c in fake.calls] == ['start:0', 'start:1']


def test_multiple_fills_are_processed(conf, fake, state_dir):
    conf = settings(conf)
    conf['orders']['above'] = 2
    bot = Grid(conf, fake)
    bot.tick()
    fake.fill('start:0')
    bot.tick()
    fake.fill('grid:3:0')
    fake.fill('grid:4:0')
    bot.tick()
    assert len(bot.state.data['trades']) == 3
    assert bot.state.data['centre'] == 4


def test_actual_price_quantity_and_fees_in_profit():
    trades = [{'level': 0, 'side': 'BUY', 'size': '2', 'price': '100', 'fee': '0.2'}, {'level': 1, 'side': 'SELL', 'size': '1', 'price': '110', 'fee': '0.11'}, {'level': 1, 'side': 'SELL', 'size': '1', 'price': '111', 'fee': '0.111'}]
    assert profit(trades) == number('20.579')
    assert 'remaining' not in trades[0]


def test_bounds_and_unsupported_stop_rejected(conf, fake, state_dir):
    conf = settings(conf)
    conf['stop']['price'] = 99
    with pytest.raises(ValueError):
        Grid(conf, fake)


def test_partial_cancel_does_not_duplicate_position(conf, fake, state_dir):
    bot = Grid(settings(conf), fake)
    bot.tick()
    fake.fill('start:0', size='0.5', status='CANCELED')
    with pytest.raises(RuntimeError, match='partially filled'):
        bot.tick()
    assert len(fake.calls) == 1


def test_state_rejects_legacy_and_does_not_truncate(state_dir):
    state = State(initial={'position': '1'})
    state.save()
    assert json.loads(state.path.read_text())['position'] == '1'
    state.path.write_text('{"version": 3}')
    with pytest.raises(ValueError):
        State()
