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
    # Прежде эта ветка (villain покрыт, bounty > 0) считала по формуле
    # напрямую, минуя required_equity, и потому не проверяла pot_before_call.
    with pytest.raises(ValueError):
        required_equity_with_bounty(
            pot_before_call=-10,
            call_amount=50,
            villain_stack=50,
            bounty=2.50,
            chip_value=0.025,
        )


def test_rejects_nonpositive_call_amount():
    # call_amount <= 0 всегда даёт covers_villain=False, раз villain_stack
    # гарантированно положителен (см. свою же проверку выше) — значит,
    # эта ошибка всегда всплывает через делегирование в required_equity,
    # а не через ветку "villain покрыт". Тест фиксирует, что
    # required_equity_with_bounty не глотает эту ошибку по пути.
    with pytest.raises(ValueError):
        required_equity_with_bounty(
            pot_before_call=100,
            call_amount=0,
            villain_stack=50,
            bounty=2.50,
            chip_value=0.025,
        )
