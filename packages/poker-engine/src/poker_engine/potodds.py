"""Пот-оддсы и chip-EV. Никакого ICM — только фишки.

Соглашение: `pot_before_call` — банк до доплаты героя, то есть ровно то,
что герой забирает при победе. `call_amount` — сколько герой доплачивает.
"""

from __future__ import annotations


def required_equity(pot_before_call: float, call_amount: float) -> float:
    """Минимальное эквити, при котором колл безубыточен по фишкам."""
    if call_amount <= 0:
        raise ValueError(f"call_amount должен быть > 0, получено {call_amount}")
    if pot_before_call < 0:
        raise ValueError(f"pot_before_call не может быть отрицательным: {pot_before_call}")
    return call_amount / (pot_before_call + call_amount)


def ev_call(pot_before_call: float, call_amount: float, equity: float) -> float:
    """Chip-EV колла: выигрываем банк с вероятностью equity, иначе теряем колл."""
    _check_probability(equity, "equity")
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
    _check_probability(fold_equity, "fold_equity")
    _check_probability(equity_when_called, "equity_when_called")
    ev_fold = pot_before_shove
    ev_called = (
        equity_when_called * (pot_before_shove + shove_amount)
        - (1.0 - equity_when_called) * shove_amount
    )
    return fold_equity * ev_fold + (1.0 - fold_equity) * ev_called


def _check_probability(value: float, name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} должен быть в [0, 1], получено {value}")
