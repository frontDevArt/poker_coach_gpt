"""Модель «стол поимённо, поле счётчиком»: аналитические инварианты."""

import math

import pytest

from poker_engine.icm import icm_equities
from poker_engine.icm_field import MAX_TABLE_SEATS, table_equities
from poker_engine.ladder import PayoutLadder


def flat_ladder(places, amount, paid=None):
    return PayoutLadder([(1, places, amount)], places_paid=paid or places)


def test_winner_take_all_two_players_is_the_chip_share():
    # Победитель забирает всё: эквити = доля фишек.
    ladder = PayoutLadder([(1, 1, 100.0)], places_paid=1)
    seats, field = table_equities([75.0, 25.0], 0, 0.0, ladder)
    assert seats == pytest.approx([75.0, 25.0])
    assert field == pytest.approx(0.0)


def test_money_is_never_lost():
    # Главный инвариант модели: всё, что раздано, равно сумме лесенки.
    ladder = PayoutLadder(
        [(1, 1, 500.0), (2, 2, 300.0), (3, 5, 100.0)], places_paid=5
    )
    seats, field = table_equities([40.0, 30.0, 20.0], 6, 10.0, ladder)
    assert sum(seats) + field == pytest.approx(ladder.total())


def test_places_already_paid_out_are_not_handed_out_again():
    # Живых четверо (2 за столом + 2 в поле), оплачиваемых мест шесть:
    # места 5-6 уже достались выбывшим. Раздаются места 1-4:
    # 100 + 50 + 2 x 20 = 190, а не вся лесенка 100 + 50 + 4 x 20 = 230.
    ladder = PayoutLadder([(1, 1, 100.0), (2, 2, 50.0), (3, 6, 20.0)], places_paid=6)
    seats, field = table_equities([30.0, 10.0], 2, 20.0, ladder)
    assert ladder.total() == pytest.approx(230.0)
    assert sum(seats) + field == pytest.approx(190.0)


def test_an_empty_field_reproduces_the_exact_enumeration():
    # F = 0: модель обязана совпасть со старым точным перебором.
    stacks = [5000, 3000, 2000, 1500, 900]
    payouts = [500.0, 300.0, 200.0]
    reference = icm_equities(stacks, payouts)
    ladder = PayoutLadder(
        [(1, 1, 500.0), (2, 2, 300.0), (3, 3, 200.0)], places_paid=3
    )
    seats, field = table_equities([float(s) for s in stacks], 0, 0.0, ladder)
    assert field == pytest.approx(0.0)
    assert seats == pytest.approx(reference, abs=1e-12)


def test_a_field_of_one_counts_like_a_named_seat():
    # Игрок поля — тот же игрок, только без имени: поле из одного со стеком
    # 20 обязано дать то же, что четвёртое место за столом со стеком 20.
    # Место разыгрывается как |S| + k + 1 — поле сдвигает места стола.
    ladder = PayoutLadder([(1, 1, 500.0), (2, 2, 300.0), (3, 3, 200.0)], places_paid=3)
    named, nobody = table_equities([50.0, 30.0, 10.0, 20.0], 0, 0.0, ladder)
    seats, field = table_equities([50.0, 30.0, 10.0], 1, 20.0, ladder)
    assert nobody == pytest.approx(0.0)
    assert seats == pytest.approx(named[:3], abs=1e-12)
    assert field == pytest.approx(named[3], abs=1e-12)


def test_only_the_last_place_paid_is_reached_through_the_field():
    # Платят только за третье место. Трое равных: один за столом, двое в
    # поле — по симметрии каждый занимает третье с вероятностью 1/3.
    ladder = PayoutLadder([(3, 3, 90.0)], places_paid=3)
    seats, field = table_equities([10.0], 2, 10.0, ladder)
    assert seats == pytest.approx([30.0])
    assert field == pytest.approx(60.0)


def test_equal_stacks_everywhere_split_the_pool_evenly():
    # Шесть за столом плюс четверо в поле, все по 50: каждому десятая доля.
    ladder = flat_ladder(10, 100.0)
    seats, field = table_equities([50.0] * 6, 4, 50.0, ladder)
    assert seats == pytest.approx([100.0] * 6)
    assert field == pytest.approx(400.0)


def test_a_bigger_stack_is_worth_more_but_less_than_proportionally():
    # Неплоская лесенка: доля эквити крупного стека строго меньше доли фишек.
    ladder = PayoutLadder(
        [(1, 1, 500.0), (2, 2, 300.0), (3, 3, 200.0)], places_paid=3
    )
    table = [100.0, 50.0, 50.0]
    seats, field = table_equities(table, 0, 0.0, ladder)
    assert seats[0] > seats[1]
    chip_share = table[0] / sum(table)
    money_share = seats[0] / ladder.total()
    assert money_share < chip_share


def test_scaling_the_ladder_scales_every_equity():
    table, count, stack = [60.0, 40.0, 30.0], 5, 20.0
    base = PayoutLadder([(1, 1, 100.0), (2, 3, 40.0)], places_paid=3)
    big = PayoutLadder([(1, 1, 300.0), (2, 3, 120.0)], places_paid=3)
    seats_base, field_base = table_equities(table, count, stack, base)
    seats_big, field_big = table_equities(table, count, stack, big)
    assert seats_big == pytest.approx([3.0 * x for x in seats_base])
    assert field_big == pytest.approx(3.0 * field_base)


def test_scaling_every_stack_changes_nothing():
    ladder = PayoutLadder([(1, 1, 100.0), (2, 2, 50.0)], places_paid=2)
    small, _ = table_equities([6.0, 4.0, 3.0], 4, 2.0, ladder)
    big, _ = table_equities([600.0, 400.0, 300.0], 4, 200.0, ladder)
    assert big == pytest.approx(small)


def test_a_field_player_is_worth_less_than_a_bigger_table_stack():
    ladder = PayoutLadder([(1, 1, 100.0), (2, 4, 25.0)], places_paid=4)
    seats, field = table_equities([80.0, 20.0], 4, 20.0, ladder)
    per_field_player = field / 4
    assert seats[0] > per_field_player
    assert seats[1] == pytest.approx(per_field_player)


def test_the_field_stack_is_ignored_when_the_field_is_empty():
    # Без игроков поля их стек ничего не значит, и NaN там не должен
    # проникнуть в сумму фишек: 0 x nan = nan отравил бы все эквити.
    ladder = PayoutLadder([(1, 1, 100.0)], places_paid=1)
    seats, field = table_equities([75.0, 25.0], 0, math.nan, ladder)
    assert seats == pytest.approx([75.0, 25.0])
    assert field == 0.0


def test_the_full_table_is_accepted():
    # Граница предела: MAX_TABLE_SEATS мест считаются, равные делят поровну.
    ladder = flat_ladder(2, 50.0)
    seats, field = table_equities([1.0] * MAX_TABLE_SEATS, 0, 0.0, ladder)
    assert seats == pytest.approx([100.0 / MAX_TABLE_SEATS] * MAX_TABLE_SEATS)


def test_too_many_seats_is_rejected():
    ladder = flat_ladder(1, 10.0)
    table = [10.0] * (MAX_TABLE_SEATS + 1)
    with pytest.raises(
        ValueError,
        match=f"^мест за столом \\({MAX_TABLE_SEATS + 1}\\) больше предела "
        f"{MAX_TABLE_SEATS}:",
    ):
        table_equities(table, 0, 0.0, ladder)


def test_empty_table_is_rejected():
    with pytest.raises(ValueError, match="^за столом нет игроков$"):
        table_equities([], 0, 0.0, flat_ladder(1, 10.0))


def test_non_positive_table_stack_is_rejected():
    with pytest.raises(ValueError, match="стек на месте 1 должен быть > 0"):
        table_equities([10.0, 0.0], 0, 0.0, flat_ladder(2, 10.0))


def test_negative_field_size_is_rejected():
    with pytest.raises(ValueError, match="размер поля не может быть отрицательным"):
        table_equities([10.0], -1, 5.0, flat_ladder(1, 10.0))


def test_fractional_field_size_is_rejected():
    # Поле считается счётчиком, дробного игрока в нём нет.
    with pytest.raises(ValueError, match="размер поля должен быть целым"):
        table_equities([10.0], 2.5, 5.0, flat_ladder(1, 10.0))


def test_a_non_empty_field_needs_a_positive_stack():
    with pytest.raises(ValueError, match="стек игрока поля должен быть > 0"):
        table_equities([10.0], 3, 0.0, flat_ladder(1, 10.0))
