import pytest

from poker_engine.potodds import (
    ev_call,
    ev_shove,
    required_equity,
)


def test_required_equity_third_of_pot():
    # Банк 100, колл 50. Герой вкладывает 50 в итоговый банк 150 -> 1/3.
    assert required_equity(pot_before_call=100, call_amount=50) == pytest.approx(1 / 3)


def test_required_equity_half_when_pot_equals_call():
    assert required_equity(pot_before_call=50, call_amount=50) == pytest.approx(0.5)


def test_required_equity_rejects_zero_call():
    with pytest.raises(ValueError):
        required_equity(pot_before_call=100, call_amount=0)


def test_ev_call_is_zero_at_required_equity():
    # Ключевая связка: при эквити ровно на пороге chip-EV равен нулю.
    q = required_equity(pot_before_call=100, call_amount=50)
    assert ev_call(pot_before_call=100, call_amount=50, equity=q) == pytest.approx(0.0)


def test_ev_call_positive_above_threshold():
    assert ev_call(pot_before_call=100, call_amount=50, equity=0.5) == pytest.approx(25.0)


def test_ev_call_negative_below_threshold():
    assert ev_call(pot_before_call=100, call_amount=50, equity=0.2) == pytest.approx(-20.0)


def test_ev_shove_with_certain_fold_equals_pot():
    # Оппонент всегда фолдит -> герой забирает банк, риска нет.
    assert ev_shove(
        pot_before_shove=100, shove_amount=200, fold_equity=1.0, equity_when_called=0.0
    ) == pytest.approx(100.0)


def test_ev_shove_without_fold_equity_reduces_to_ev_call():
    # Оппонент никогда не фолдит -> шов эквивалентен всаживанию тех же фишек.
    shove = ev_shove(
        pot_before_shove=100, shove_amount=200, fold_equity=0.0, equity_when_called=0.4
    )
    manual = 0.4 * (100 + 200) - 0.6 * 200
    assert shove == pytest.approx(manual)
