import math

import pytest

from poker_engine.bounty import (
    PROGRESSIVE_SHARE,
    bounty_in_chips,
    knockout_cash,
    own_bounty_growth,
    required_equity_with_bounty,
)
from poker_engine.potodds import required_equity


def test_cash_equals_the_price_shown_on_screen():
    # Экран показывает $1.50 — это и есть наличные выбившему (спека 5.2).
    assert knockout_cash(bounty=1.50) == pytest.approx(1.50)


def test_own_price_grows_by_half_of_what_was_taken():
    # Ценник 1.50 плюс половина взятого 1.50 = 2.25 — ровно как на скриншоте.
    assert own_bounty_growth(bounty=1.50) == pytest.approx(0.75)


def test_the_screenshot_arithmetic_reproduces():
    # damdreiQ3 = $2.25: стартовые 1.50 плюс половина одного выбитого новичка.
    assert 1.50 + own_bounty_growth(1.50) == pytest.approx(2.25)
    # LRDAM = $3.00: двое выбитых новичков.
    assert 1.50 + 2 * own_bounty_growth(1.50) == pytest.approx(3.00)
    # $4.87 ≈ 1.50 + три новичка по 0.75 + один с ценником 2.25 (спека 5.2):
    # точно 4.875, на экране округлено вниз до цента.
    assert 1.50 + 3 * own_bounty_growth(1.50) + own_bounty_growth(2.25) == (
        pytest.approx(4.875)
    )


def test_the_bounty_pool_is_conserved():
    # Двое по $3.00 в фонде. A выбивает B: берёт 1.50 наличными, его полный
    # баунти становится 3.00 + 1.50 = 4.50 и достаётся ему при победе.
    pool = 2 * 3.00
    cash = knockout_cash(1.50)
    winner_total = 3.00 + 2 * own_bounty_growth(1.50)
    assert cash + winner_total == pytest.approx(pool)


@pytest.mark.parametrize("shown", [0.0, 1.50, 2.25, 4.875, 37.0])
def test_a_knockout_moves_the_whole_bounty_of_the_busted(shown):
    # Инвариант спеки §9.9. Полный баунти игрока вдвое больше показанного
    # ценника (внёс $3.00 — показано $1.50). При нокауте он целиком уходит
    # выбившему: наличными плюс прирост его полного баунти, который тоже
    # вдвое больше прироста показанного ценника.
    full_bounty = shown / PROGRESSIVE_SHARE
    full_growth = own_bounty_growth(shown) / PROGRESSIVE_SHARE
    assert knockout_cash(shown) + full_growth == pytest.approx(full_bounty)


def test_own_price_growth_rejects_a_negative_price():
    with pytest.raises(ValueError, match="^bounty не может быть отрицательным: -1.0$"):
        own_bounty_growth(-1.0)


def test_bounty_in_chips_converts_by_chip_value():
    # 2.50 наличными при цене фишки 0.025 = 100 фишек.
    assert bounty_in_chips(bounty=2.50, chip_value=0.025) == pytest.approx(100.0)


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
    # Ценник 2.50 — наличные целиком, цена фишки 0.025 -> 100 фишек добавки.
    # Порог = 50 / (100 + 100 + 50) = 0.2
    q = required_equity_with_bounty(
        pot_before_call=100,
        call_amount=50,
        villain_stack=50,
        bounty=2.50,
        chip_value=0.025,
    )
    assert q == pytest.approx(0.2)


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
    with pytest.raises(ValueError, match="^chip_value должен быть > 0, получено 0.0$"):
        bounty_in_chips(bounty=2.50, chip_value=0.0)


def test_rejects_nonpositive_chip_value_even_when_villain_not_covered():
    # Соперник не покрыт — цена фишки в арифметику не входит, и без
    # собственного гарда функции ноль прошёл бы молча: `bounty_in_chips`,
    # где стоит второй гард, на этом пути не вызывается. Docstring обещает
    # проверку всех параметров до `covers_villain`.
    with pytest.raises(ValueError, match="^chip_value должен быть > 0, получено 0.0$"):
        required_equity_with_bounty(
            pot_before_call=100,
            call_amount=50,
            villain_stack=500,
            bounty=2.50,
            chip_value=0.0,
        )


def test_rejects_negative_bounty_even_when_villain_not_covered():
    # Когда villain не покрыт, bounty вообще не входит в арифметику
    # результата — так что этот guard не предотвращает неверное число
    # (оно и без guard'а было бы верным). Причина держать проверку здесь —
    # отклонять семантически бессмысленный ввод на любом пути одинаково,
    # а не только там, где он случайно влияет на результат, — так же,
    # как knockout_cash уже отклоняет отрицательный bounty сам по себе.
    with pytest.raises(ValueError, match="^bounty не может быть отрицательным: -1.0$"):
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
    with pytest.raises(ValueError, match="^villain_stack должен быть > 0, получено 0$"):
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
    with pytest.raises(
        ValueError, match="^pot_before_call не может быть отрицательным: -10$"
    ):
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
    with pytest.raises(ValueError, match="^call_amount должен быть > 0, получено 0$"):
        required_equity_with_bounty(
            pot_before_call=100,
            call_amount=0,
            villain_stack=50,
            bounty=2.50,
            chip_value=0.025,
        )


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
