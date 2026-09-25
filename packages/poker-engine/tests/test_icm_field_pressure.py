"""Давление лесенки на новой модели поля."""

import pytest

from poker_engine import icm_field

from poker_engine.icm_field import (
    PressureUndefined,
    bubble_factor,
    hero_equity,
    pressure,
    risk_premium,
    table_equities,
)
from poker_engine.ladder import PayoutLadder


def winner_take_all():
    return PayoutLadder([(1, 1, 100.0)], places_paid=1)


def flat(places, amount):
    return PayoutLadder([(1, places, amount)], places_paid=places)


def test_winner_take_all_has_no_ladder_pressure():
    # Единственный приз: эквити = доля фишек и с полем, деньги линейны по
    # фишкам, давить нечему.
    ladder = winner_take_all()
    assert risk_premium([50.0, 50.0, 50.0], 0, 0.0, ladder, 0, 1) == (
        pytest.approx(0.0, abs=1e-12)
    )
    assert bubble_factor([50.0, 50.0, 50.0], 0, 0.0, ladder, 0, 1) == (
        pytest.approx(1.0, abs=1e-12)
    )
    assert risk_premium([60.0, 20.0], 3, 40.0, ladder, 1, 0) == (
        pytest.approx(0.0, abs=1e-12)
    )
    assert bubble_factor([60.0, 20.0], 3, 40.0, ladder, 1, 0) == (
        pytest.approx(1.0, abs=1e-12)
    )


@pytest.mark.parametrize(
    "table, field_count",
    [([30.0, 30.0, 30.0], 0), ([30.0, 30.0], 1)],
    ids=["three at the table", "third in the field"],
)
def test_three_equal_stacks_two_paid_on_paper(table, field_count):
    # Трое равных, платят по 50 за места 1-2. Сейчас: последним уходит
    # каждый с вероятностью 1/3, эквити 2/3 x 50. Выиграл — соперник
    # занял третье, двое оставшихся в деньгах: 50. Проиграл — герой
    # третий: 0. Порог в деньгах (100/3 - 0) / (50 - 0) = 2/3, риск-премия
    # 2/3 - 1/2 = 1/6; bubble factor (100/3) / (50 - 100/3) = 2.
    # Третий игрок в поле обязан дать то же: место вылетевшего героя
    # абсолютное — `за столом + поле + 1`, а не последнее за столом.
    ladder = flat(2, 50.0)
    assert risk_premium(table, field_count, 30.0, ladder, 0, 1) == (
        pytest.approx(1.0 / 6.0, abs=1e-12)
    )
    assert bubble_factor(table, field_count, 30.0, ladder, 0, 1) == (
        pytest.approx(2.0, abs=1e-12)
    )


def test_a_ladder_creates_positive_pressure():
    ladder = PayoutLadder([(1, 1, 500.0), (2, 2, 300.0), (3, 3, 200.0)], places_paid=3)
    assert risk_premium([50.0, 50.0, 50.0], 0, 0.0, ladder, 0, 1) > 0.0
    assert bubble_factor([50.0, 50.0, 50.0], 0, 0.0, ladder, 0, 1) > 1.0


def test_a_flat_ladder_paying_everyone_does_not_press():
    # Сателлит: всем оставшимся (трое за столом и двое в поле) платят
    # поровну — исход олл-ина денег не меняет.
    ladder = flat(5, 100.0)
    assert risk_premium([40.0, 30.0, 30.0], 2, 25.0, ladder, 0, 1) == (
        pytest.approx(0.0, abs=1e-9)
    )
    assert bubble_factor([40.0, 30.0, 30.0], 2, 25.0, ladder, 0, 1) == 1.0


def test_pressure_is_higher_on_the_bubble_than_deep_in_the_money():
    # Одна и та же раздача: лесенка на 3 места при четверых за столом (бабл)
    # против лесенки на 4 места (все в деньгах).
    table = [50.0, 40.0, 30.0, 20.0]
    bubble = PayoutLadder([(1, 3, 100.0)], places_paid=3)
    in_money = PayoutLadder([(1, 4, 75.0)], places_paid=4)
    assert risk_premium(table, 0, 0.0, bubble, 0, 3) > risk_premium(
        table, 0, 0.0, in_money, 0, 3
    )


def test_scaling_the_ladder_leaves_pressure_untouched():
    table, count, stack = [60.0, 40.0, 30.0], 5, 20.0
    base = PayoutLadder([(1, 1, 100.0), (2, 3, 40.0)], places_paid=3)
    big = PayoutLadder([(1, 1, 115.0), (2, 3, 46.0)], places_paid=3)
    assert risk_premium(table, count, stack, big, 0, 1) == pytest.approx(
        risk_premium(table, count, stack, base, 0, 1)
    )
    assert bubble_factor(table, count, stack, big, 0, 1) == pytest.approx(
        bubble_factor(table, count, stack, base, 0, 1)
    )


def test_a_busted_hero_takes_the_last_place_among_everyone_left():
    # Герой 20 против 40, в поле ещё двое: проиграв, он вылетает четвёртым
    # из четверых живых и берёт ровно приз за место 4 — 25. Не 40 (место 3,
    # «последний за столом»), не 0 (место 5). Выигрыш никого не выбивает,
    # его ветвь — обычное эквити стола [40, 20].
    ladder = PayoutLadder([(1, 1, 100.0), (2, 3, 40.0), (4, 4, 25.0)], places_paid=4)
    now = table_equities([20.0, 40.0], 2, 30.0, ladder)[0][0]
    win = table_equities([40.0, 20.0], 2, 30.0, ladder)[0][0]
    lose = 25.0
    assert risk_premium([20.0, 40.0], 2, 30.0, ladder, 0, 1) == pytest.approx(
        (now - lose) / (win - lose) - 0.5, abs=1e-12
    )
    assert bubble_factor([20.0, 40.0], 2, 30.0, ladder, 0, 1) == pytest.approx(
        (now - lose) / (win - now), abs=1e-12
    )


def test_a_busted_villain_leaves_the_upper_places_unshifted():
    # Герой 40 (место 1) выбивает соперника 20 (место 0) при третьем за
    # столом и двоих в поле: соперник уходит шестым, а герой разыгрывает
    # места 1-5 со столом [60, 35] и полем — лесенка не сдвигается и не
    # обрезается. Соперник сидит раньше героя, поэтому после вылета номер
    # героя за столом сдвигается на единицу. Проигрыш никого не выбивает.
    ladder = PayoutLadder([(1, 1, 100.0), (2, 3, 40.0), (4, 6, 25.0)], places_paid=6)
    now = table_equities([20.0, 40.0, 35.0], 2, 30.0, ladder)[0][1]
    win = table_equities([60.0, 35.0], 2, 30.0, ladder)[0][0]
    lose = table_equities([40.0, 20.0, 35.0], 2, 30.0, ladder)[0][1]
    assert risk_premium([20.0, 40.0, 35.0], 2, 30.0, ladder, 1, 0) == pytest.approx(
        (now - lose) / (win - lose) - 0.5, abs=1e-12
    )
    assert bubble_factor([20.0, 40.0, 35.0], 2, 30.0, ladder, 1, 0) == pytest.approx(
        (now - lose) / (win - now), abs=1e-12
    )


def test_hero_equity_matches_the_seat_from_table_equities():
    ladder = PayoutLadder([(1, 1, 100.0), (2, 3, 30.0)], places_paid=3)
    seats, _ = table_equities([50.0, 30.0, 20.0], 4, 25.0, ladder)
    assert hero_equity([50.0, 30.0, 20.0], 4, 25.0, ladder, 1) == pytest.approx(
        seats[1]
    )


def test_hero_and_villain_must_differ():
    with pytest.raises(ValueError, match="^hero и villain должны различаться$"):
        risk_premium([50.0, 50.0], 0, 0.0, winner_take_all(), 0, 0)


@pytest.mark.parametrize("hero", [5, -1])
def test_hero_outside_the_table_is_rejected(hero):
    # -1 — не «последнее место» по-питоновски, а ошибка вызова.
    text = rf"^hero={hero} вне диапазона игроков \[0, 1\]$"
    with pytest.raises(ValueError, match=text):
        risk_premium([50.0, 50.0], 0, 0.0, winner_take_all(), hero, 1)
    with pytest.raises(ValueError, match=text):
        bubble_factor([50.0, 50.0], 0, 0.0, winner_take_all(), hero, 1)
    with pytest.raises(ValueError, match=text):
        hero_equity([50.0, 50.0], 0, 0.0, winner_take_all(), hero)


@pytest.mark.parametrize("villain", [2, -1])
def test_villain_outside_the_table_is_rejected(villain):
    with pytest.raises(
        ValueError, match=rf"^villain={villain} вне диапазона игроков \[0, 1\]$"
    ):
        risk_premium([50.0, 50.0], 0, 0.0, winner_take_all(), 0, villain)


def test_zero_effective_stack_is_rejected():
    # Соперник уже в олл-ине на ноль: на кону нечего, и этот текст выходит
    # раньше гарда стека `table_equities` — как в `icm._icm_branches`.
    with pytest.raises(ValueError, match="^эффективный стек равен нулю$"):
        risk_premium([50.0, 0.0], 0, 0.0, winner_take_all(), 0, 1)
    with pytest.raises(ValueError, match="^эффективный стек равен нулю$"):
        bubble_factor([50.0, 0.0], 0, 0.0, winner_take_all(), 0, 1)


def test_money_out_of_reach_leaves_both_measures_undefined():
    # Платят только за третье место, а живых двое: места 1-2 ничего не
    # стоят, и ни одна ветвь олл-ина денег не меняет — все три эквити нули.
    ladder = PayoutLadder([(3, 3, 10.0)], places_paid=3)
    with pytest.raises(
        PressureUndefined,
        match="^исход олл-ина не меняет ICM-эквити героя, risk premium не определён$",
    ):
        risk_premium([50.0, 30.0], 0, 0.0, ladder, 0, 1)
    with pytest.raises(
        PressureUndefined,
        match="^выигрыш не увеличивает ICM-эквити, bubble factor не определён$",
    ):
        bubble_factor([50.0, 30.0], 0, 0.0, ladder, 0, 1)


def test_a_ladder_that_rewards_busting_leaves_bubble_factor_undefined():
    # Платят только за третье место, живых трое равных (двое за столом,
    # один в поле): сейчас герой третий с вероятностью 1/3 — 30. Выиграл —
    # третьим ушёл соперник, места 1-2 ничего не стоят: 0. Проиграл —
    # герой третий: 90. Выигрыш уменьшает эквити, bubble factor не
    # определён. Риск-премия при этом определена: (30 - 90) / (0 - 90) - 1/2.
    ladder = PayoutLadder([(3, 3, 90.0)], places_paid=3)
    with pytest.raises(
        PressureUndefined,
        match="^выигрыш не увеличивает ICM-эквити, bubble factor не определён$",
    ):
        bubble_factor([10.0, 10.0], 1, 10.0, ladder, 0, 1)
    assert risk_premium([10.0, 10.0], 1, 10.0, ladder, 0, 1) == pytest.approx(
        1.0 / 6.0, abs=1e-12
    )


@pytest.mark.parametrize(
    "call, text",
    [
        (
            lambda: risk_premium([50.0, 50.0], 0, 0.0, winner_take_all(), 0, 0),
            "^hero и villain должны различаться$",
        ),
        (
            lambda: risk_premium([50.0, 50.0], 0, 0.0, winner_take_all(), 5, 1),
            r"^hero=5 вне диапазона игроков \[0, 1\]$",
        ),
        (
            lambda: bubble_factor([50.0, 0.0], 0, 0.0, winner_take_all(), 0, 1),
            "^эффективный стек равен нулю$",
        ),
        (
            lambda: bubble_factor([50.0, 50.0, 0.0], 0, 0.0, winner_take_all(), 0, 1),
            "^стек на месте 2 должен быть > 0",
        ),
    ],
    ids=["same seat", "seat outside", "zero effective stack", "zero third stack"],
)
def test_call_errors_are_not_undefined_pressure(call, text):
    # `analyze` превращает в пометку только `PressureUndefined` (долг D4):
    # ошибки вызова обязаны оставаться обычным `ValueError`, иначе пометка
    # «давление не определено» спрятала бы их.
    with pytest.raises(ValueError, match=text) as caught:
        call()
    assert not isinstance(caught.value, PressureUndefined)


# --- один проход на три величины (план 3, Задача 8, долг D7) -----------------


def test_pressure_is_the_three_measures_in_one_pass(monkeypatch):
    # Те же ветви, та же арифметика: числа совпадают с тремя функциями
    # порознь точно, а `table_equities` зовётся трижды — по разу на ветвь.
    # Герой (45) накрывает соперника (30): проигрыш его не выбивает, и
    # ветвь проигрыша тоже идёт через `table_equities`.
    table, field_count, field_stack = [30.0, 20.0, 45.0], 5, 25.0
    ladder = PayoutLadder([(1, 1, 50.0), (2, 2, 30.0), (3, 4, 10.0)], places_paid=4)
    expected = (
        hero_equity(table, field_count, field_stack, ladder, 2),
        risk_premium(table, field_count, field_stack, ladder, 2, 0),
        bubble_factor(table, field_count, field_stack, ladder, 2, 0),
    )
    calls = []
    original = icm_field.table_equities

    def counted(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(icm_field, "table_equities", counted)
    assert pressure(table, field_count, field_stack, ladder, 2, 0) == expected
    assert len(calls) == 3


def test_pressure_refuses_like_the_measures_it_joins():
    # Отказ — тот же, что дала бы первая из двух величин: риск-премия
    # раньше bubble factor. На лесенке, награждающей вылет, риск-премия
    # определена, и отказ — про bubble factor.
    with pytest.raises(
        PressureUndefined,
        match="^исход олл-ина не меняет ICM-эквити героя, risk premium не определён$",
    ):
        pressure([50.0, 30.0], 0, 0.0, PayoutLadder([(3, 3, 10.0)], places_paid=3), 0, 1)
    with pytest.raises(
        PressureUndefined,
        match="^выигрыш не увеличивает ICM-эквити, bubble factor не определён$",
    ):
        pressure([10.0, 10.0], 1, 10.0, PayoutLadder([(3, 3, 90.0)], places_paid=3), 0, 1)
    with pytest.raises(ValueError, match="^hero и villain должны различаться$") as caught:
        pressure([50.0, 50.0], 0, 0.0, winner_take_all(), 0, 0)
    assert not isinstance(caught.value, PressureUndefined)
