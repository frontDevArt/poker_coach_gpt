import math

import pytest

from poker_engine.bounty import (
    bounty_in_chips,
    knockout_cash,
    required_equity_with_bounty,
)
from poker_engine.potodds import required_equity


def test_knockout_pays_half_by_default():
    assert knockout_cash(bounty=2.50) == pytest.approx(1.25)


def test_knockout_split_is_configurable():
    assert knockout_cash(bounty=2.50, split=1.0) == pytest.approx(2.50)


def test_bounty_in_chips_converts_by_chip_value():
    # 1.25 наличными при цене фишки 0.025 = 50 фишек.
    assert bounty_in_chips(bounty=2.50, chip_value=0.025) == pytest.approx(50.0)


def test_required_equity_with_zero_bounty_matches_plain_pot_odds():
    with_b = required_equity_with_bounty(
        pot_before_call=100,
        call_amount=50,
        villain_stack=50,
        bounty=0.0,
        chip_value=0.025,
    )
    plain = required_equity(pot_before_call=100, call_amount=50)
    assert with_b == pytest.approx(plain)


def test_required_equity_with_bounty_is_analytic():
    # Голова 2.50, сплит 0.5, цена фишки 0.025 -> 50 фишек добавки.
    # Порог = 50 / (100 + 50 + 50) = 0.25
    q = required_equity_with_bounty(
        pot_before_call=100,
        call_amount=50,
        villain_stack=50,
        bounty=2.50,
        chip_value=0.025,
    )
    assert q == pytest.approx(0.25)


def test_bounty_lowers_the_bar():
    plain = required_equity(pot_before_call=100, call_amount=50)
    with_b = required_equity_with_bounty(
        pot_before_call=100,
        call_amount=50,
        villain_stack=50,
        bounty=2.50,
        chip_value=0.025,
    )
    assert with_b < plain


def test_no_bounty_credit_when_villain_is_not_covered():
    # Стек соперника больше колла героя -> нокаута не будет, голова не считается.
    q = required_equity_with_bounty(
        pot_before_call=100,
        call_amount=50,
        villain_stack=500,
        bounty=2.50,
        chip_value=0.025,
    )
    assert q == pytest.approx(required_equity(pot_before_call=100, call_amount=50))


def test_rejects_nonpositive_chip_value():
    with pytest.raises(ValueError):
        bounty_in_chips(bounty=2.50, chip_value=0.0)


def test_rejects_negative_bounty_even_when_villain_not_covered():
    # Когда villain не покрыт, bounty вообще не входит в арифметику
    # результата — так что этот guard не предотвращает неверное число
    # (оно и без guard'а было бы верным). Причина держать проверку здесь —
    # отклонять семантически бессмысленный ввод на любом пути одинаково,
    # а не только там, где он случайно влияет на результат, — так же,
    # как knockout_cash уже отклоняет отрицательный bounty сам по себе.
    with pytest.raises(ValueError):
        required_equity_with_bounty(
            pot_before_call=100,
            call_amount=50,
            villain_stack=500,
            bounty=-1.0,
            chip_value=0.025,
        )


def test_rejects_nonpositive_villain_stack():
    # villain_stack <= 0 не может произойти в реальной раздаче и не должен
    # молча трактоваться как "герой покрывает соперника".
    with pytest.raises(ValueError):
        required_equity_with_bounty(
            pot_before_call=100,
            call_amount=50,
            villain_stack=0,
            bounty=2.50,
            chip_value=0.025,
        )


def test_rejects_negative_pot_even_when_bounty_applies():
    # На ветке "villain покрыт, bounty > 0" required_equity видит только
    # уже сдвинутый pot_before_call + extra (который неотрицателен, раз
    # extra >= 0), так что отрицательный pot_before_call может поймать
    # только собственный eager-guard этой функции. Тест фиксирует, что
    # этот guard действительно есть и не обходится веткой с баунти.
    with pytest.raises(ValueError):
        required_equity_with_bounty(
            pot_before_call=-10,
            call_amount=50,
            villain_stack=50,
            bounty=2.50,
            chip_value=0.025,
        )


def test_rejects_nonpositive_call_amount():
    # required_equity_with_bounty отклоняет call_amount <= 0 своим
    # собственным eager-guard'ом (до вычисления covers_villain), с тем же
    # сообщением, что и potodds.required_equity — так что контракт ошибки
    # для вызывающей стороны (в частности, будущего CLI) одинаков вне
    # зависимости от того, задействован ли путь с баунти.
    with pytest.raises(ValueError):
        required_equity_with_bounty(
            pot_before_call=100,
            call_amount=0,
            villain_stack=50,
            bounty=2.50,
            chip_value=0.025,
        )


def test_split_reaches_the_threshold():
    # split=1.0 -> вся голова 2.50 наличными -> 2.50/0.025 = 100 фишек.
    # Порог = 50 / (100 + 100 + 50) = 0.2
    assert required_equity_with_bounty(
        pot_before_call=100,
        call_amount=50,
        villain_stack=50,
        bounty=2.50,
        chip_value=0.025,
        split=1.0,
    ) == pytest.approx(0.2)


@pytest.mark.parametrize(
    ("param", "value", "message"),
    [
        ("bounty", math.nan, "bounty не может быть нечислом: nan$"),
        ("bounty", math.inf, "bounty не может быть бесконечным: inf$"),
        ("villain_stack", math.nan, "villain_stack не может быть нечислом: nan$"),
        ("villain_stack", math.inf, "villain_stack не может быть бесконечным: inf$"),
        ("chip_value", math.nan, "chip_value не может быть нечислом: nan$"),
        ("chip_value", math.inf, "chip_value не может быть бесконечным: inf$"),
    ],
)
def test_non_finite_bounty_inputs_are_rejected_by_their_own_name(
    param, value, message
):
    # Без гарда `bounty=inf` доходил до `required_equity` внутри сдвинутого
    # банка, и отказ называл `pot_before_call`; `villain_stack=nan` молча
    # выключал баунти, а `chip_value=inf` обнулял его.
    args = dict(
        pot_before_call=10.0,
        call_amount=20.0,
        villain_stack=20.0,
        bounty=10.0,
        chip_value=0.01,
    )
    args[param] = value
    with pytest.raises(ValueError, match=message):
        required_equity_with_bounty(**args)


def test_prior_bounty_texts_are_unchanged():
    # Копии гардов заменены общими: шаблоны совпадали, тексты — прежние.
    with pytest.raises(ValueError, match="bounty не может быть отрицательным: -1.0$"):
        knockout_cash(-1.0)
    with pytest.raises(ValueError, match="chip_value должен быть > 0, получено 0.0$"):
        bounty_in_chips(bounty=2.50, chip_value=0.0)
    with pytest.raises(ValueError, match="villain_stack должен быть > 0, получено 0$"):
        required_equity_with_bounty(
            pot_before_call=100,
            call_amount=50,
            villain_stack=0,
            bounty=2.50,
            chip_value=0.025,
        )
