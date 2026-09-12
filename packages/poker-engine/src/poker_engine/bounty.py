"""Progressive Knockout: перевод головы в фишки и порог колла с учётом баунти.

В стандартном PKO половина головы выбитого выплачивается наличными,
половина увеличивает собственную голову героя. В EV конкретной руки
считается только наличная половина: прирост своей головы обналичится
лишь при последующих нокаутах и здесь не моделируется.
"""

from __future__ import annotations

from ._checks import check_non_negative, check_positive
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

    Валидация всех параметров — `bounty`, `villain_stack`, `chip_value`,
    `split`, `call_amount`, `pot_before_call` — выполняется безусловно,
    до вычисления `covers_villain`: валидность одного аргумента не должна
    зависеть от значения другого. В частности `chip_value` — обязательный
    позиционный параметр без "неприменимого" значения, а этот модуль и
    есть слой валидации CLI-ввода: `--chip-value -5` обязан падать
    одинаково вне зависимости от того, что передано в `--bounty`.
    """
    _check_bounty(bounty)
    _check_villain_stack(villain_stack)
    _check_chip_value(chip_value)
    _check_split(split)
    check_positive(call_amount, "call_amount")
    check_non_negative(pot_before_call, "pot_before_call")

    covers_villain = call_amount >= villain_stack
    if not (covers_villain and bounty > 0):
        return required_equity(pot_before_call, call_amount)
    extra = bounty_in_chips(bounty, chip_value, split)
    return required_equity(pot_before_call + extra, call_amount)


# `bounty`, `chip_value` и `villain_stack` проверяются общими гардами: шаблоны у прежних копий
# были те же, поэтому тексты не изменились, а NaN и `inf` теперь
# отвергаются здесь же, до арифметики. Иначе `--bounty inf` доходил до
# `required_equity` внутри сдвинутого банка и отказ называл
# `pot_before_call`, а `--villain-stack nan` молча выключал баунти.


def _check_bounty(value: float) -> None:
    check_non_negative(value, "bounty")


def _check_split(value: float) -> None:
    if not 0.0 < value <= 1.0:
        raise ValueError(f"split должен быть в (0, 1], получено {value}")


def _check_chip_value(value: float) -> None:
    check_positive(value, "chip_value")


def _check_villain_stack(value: float) -> None:
    check_positive(value, "villain_stack")
