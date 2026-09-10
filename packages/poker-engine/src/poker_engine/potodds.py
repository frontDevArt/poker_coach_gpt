"""Пот-оддсы и chip-EV. Никакого ICM — только фишки.

Соглашение: `pot_before_call` — банк до доплаты героя, то есть ровно то,
что герой забирает при победе. `call_amount` — сколько герой доплачивает.

Решение «колл или фолд» на пороге безубыточности следует принимать сравнением
эквити с `required_equity`, а не по знаку `ev_call`/`ev_shove`: из-за
погрешности float знак результата у самой границы ненадёжен.
"""

from __future__ import annotations

from ._checks import check_non_negative, check_positive, check_probability


def required_equity(pot_before_call: float, call_amount: float) -> float:
    """Минимальное эквити, при котором колл безубыточен по фишкам."""
    check_positive(call_amount, "call_amount")
    check_non_negative(pot_before_call, "pot_before_call")
    return call_amount / (pot_before_call + call_amount)


def ev_call(pot_before_call: float, call_amount: float, equity: float) -> float:
    """Chip-EV колла: выигрываем банк с вероятностью equity, иначе теряем колл."""
    check_probability(equity, "equity")
    check_positive(call_amount, "call_amount")
    check_non_negative(pot_before_call, "pot_before_call")
    return equity * pot_before_call - (1.0 - equity) * call_amount


def ev_shove(
    pot_before_shove: float,
    shove_amount: float,
    fold_equity: float,
    equity_when_called: float,
) -> float:
    """Chip-EV шова.

    С вероятностью fold_equity оппонент фолдит и герой забирает банк.
    Иначе идёт вскрытие: герой выигрывает банк плюс колл оппонента,
    либо теряет свой шов.
    """
    check_probability(fold_equity, "fold_equity")
    check_probability(equity_when_called, "equity_when_called")
    check_positive(shove_amount, "shove_amount")
    check_non_negative(pot_before_shove, "pot_before_shove")
    ev_fold = pot_before_shove
    ev_called = (
        equity_when_called * (pot_before_shove + shove_amount)
        - (1.0 - equity_when_called) * shove_amount
    )
    return fold_equity * ev_fold + (1.0 - fold_equity) * ev_called
