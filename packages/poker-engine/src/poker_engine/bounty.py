"""Progressive Knockout: перевод головы в фишки и порог колла с учётом баунти.

В стандартном PKO половина головы выбитого выплачивается наличными,
половина увеличивает собственную голову героя. В EV конкретной руки
считается только наличная половина: прирост своей головы обналичится
лишь при последующих нокаутах и здесь не моделируется.
"""

from __future__ import annotations

from .potodds import required_equity

DEFAULT_SPLIT = 0.5


def knockout_cash(bounty: float, split: float = DEFAULT_SPLIT) -> float:
    """Наличные, которые герой получает сразу за нокаут."""
    _check_bounty(bounty)
    _check_split(split)
    return bounty * split


def bounty_in_chips(
    bounty: float, chip_value: float, split: float = DEFAULT_SPLIT
) -> float:
    """Наличная половина головы, выраженная в фишках.

    chip_value — сколько долларов стоит одна фишка на текущей стадии.
    Берётся как призовой фонд, делённый на общее число фишек в турнире.
    """
    _check_chip_value(chip_value)
    return knockout_cash(bounty, split) / chip_value


def required_equity_with_bounty(
    pot_before_call: float,
    call_amount: float,
    villain_stack: float,
    bounty: float,
    chip_value: float,
    split: float = DEFAULT_SPLIT,
) -> float:
    """Порог эквити для колла в PKO.

    Голова засчитывается только если колл героя покрывает стек соперника,
    то есть нокаут действительно возможен в этой раздаче.

    Валидация всех параметров выполняется здесь безусловно, а не только
    на том пути, где формула фактически использует конкретное значение:
    иначе, например, отрицательный bounty или бессмысленный villain_stack
    молча проваливались бы в «план без баунти» вместо явной ошибки.
    """
    _check_bounty(bounty)
    _check_villain_stack(villain_stack)
    _check_amount(call_amount, "call_amount")
    _check_pot(pot_before_call, "pot_before_call")

    covers_villain = call_amount >= villain_stack
    extra = (
        bounty_in_chips(bounty, chip_value, split)
        if covers_villain and bounty > 0
        else 0.0
    )
    if extra == 0.0:
        return required_equity(pot_before_call, call_amount)
    return call_amount / (pot_before_call + extra + call_amount)


def _check_bounty(value: float) -> None:
    if value < 0:
        raise ValueError(f"bounty не может быть отрицательным: {value}")


def _check_split(value: float) -> None:
    if not 0.0 < value <= 1.0:
        raise ValueError(f"split должен быть в (0, 1], получено {value}")


def _check_chip_value(value: float) -> None:
    if value <= 0:
        raise ValueError(f"chip_value должен быть > 0, получено {value}")


def _check_villain_stack(value: float) -> None:
    if value <= 0:
        raise ValueError(f"villain_stack должен быть > 0, получено {value}")


def _check_amount(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} должен быть > 0, получено {value}")


def _check_pot(value: float, name: str) -> None:
    if value < 0:
        raise ValueError(f"{name} не может быть отрицательным: {value}")
