"""Progressive Knockout: перевод головы в фишки и порог колла с учётом баунти.

Число на экране клиента — это **наличные, которые получит выбивший**, то
есть половина полного баунти игрока: участник вносит $3.00 на голову, а
над ним висит $1.50. При нокауте выбивший получает показанное число
целиком и вдобавок наращивает собственный ценник на его половину.

Проверено сохранением фонда: двое по $3.00, итого $6.00. A выбивает B,
берёт $1.50, его полный баунти становится $4.50 и достаётся ему при
победе. Выплачено $6.00 (спека 2026-09-12, раздел 5.2).

В EV конкретной руки считается только наличная часть: прирост своего
ценника обналичится лишь при последующих нокаутах и здесь не моделируется.
"""

from __future__ import annotations

from ._checks import check_non_negative, check_positive
from .potodds import required_equity

# Доля показанного ценника, которая садится на голову выбившего. Наличные
# при этом равны показанному числу целиком, а не его доле — см. шапку.
PROGRESSIVE_SHARE = 0.5


def knockout_cash(bounty: float) -> float:
    """Наличные, которые герой получает сразу за нокаут.

    Равны показанному на экране числу. Это не половина — половиной оно уже
    является по отношению к полному баунти выбитого.
    """
    _check_bounty(bounty)
    return bounty


def own_bounty_growth(bounty: float) -> float:
    """На сколько вырастет собственный ценник героя после нокаута."""
    _check_bounty(bounty)
    return bounty * PROGRESSIVE_SHARE


def bounty_in_chips(bounty: float, chip_value: float) -> float:
    """Наличные за нокаут, выраженные в фишках.

    chip_value — сколько долларов стоит одна фишка на текущей стадии.
    Берётся как призовой фонд, делённый на общее число фишек в турнире.
    """
    _check_chip_value(chip_value)
    return knockout_cash(bounty) / chip_value


def required_equity_with_bounty(
    pot_before_call: float,
    call_amount: float,
    villain_stack: float,
    bounty: float,
    chip_value: float,
) -> float:
    """Порог эквити для колла в PKO.

    `bounty` — ценник над соперником, как показан на экране: наличные за
    нокаут равны ему целиком. Голова засчитывается только если колл героя
    покрывает стек соперника, то есть нокаут действительно возможен в
    этой раздаче.

    Валидация всех параметров — `bounty`, `villain_stack`, `chip_value`,
    `call_amount`, `pot_before_call` — выполняется безусловно,
    до вычисления `covers_villain`: валидность одного аргумента не должна
    зависеть от значения другого. В частности `chip_value` — обязательный
    позиционный параметр без "неприменимого" значения, а этот модуль и
    есть слой валидации CLI-ввода: `--chip-value -5` обязан падать
    одинаково вне зависимости от того, что передано в `--bounty`.
    """
    _check_bounty(bounty)
    _check_villain_stack(villain_stack)
    _check_chip_value(chip_value)
    check_positive(call_amount, "call_amount")
    check_non_negative(pot_before_call, "pot_before_call")

    covers_villain = call_amount >= villain_stack
    if not (covers_villain and bounty > 0):
        return required_equity(pot_before_call, call_amount)
    extra = bounty_in_chips(bounty, chip_value)
    return required_equity(pot_before_call + extra, call_amount)


# `bounty`, `chip_value` и `villain_stack` проверяются общими гардами: шаблоны у прежних копий
# были те же, поэтому тексты не изменились, а NaN и `inf` теперь
# отвергаются здесь же, до арифметики. Иначе `--bounty inf` доходил до
# `required_equity` внутри сдвинутого банка и отказ называл
# `pot_before_call`, а `--villain-stack nan` молча выключал баунти.


def _check_bounty(value: float) -> None:
    check_non_negative(value, "bounty")


def _check_chip_value(value: float) -> None:
    check_positive(value, "chip_value")


def _check_villain_stack(value: float) -> None:
    check_positive(value, "villain_stack")
