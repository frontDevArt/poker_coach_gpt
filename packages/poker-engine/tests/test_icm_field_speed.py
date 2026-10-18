"""Быстрый ICM модели поля (спека D27): сверка с эталоном плана 3 и пакетный вызов."""

import math

import numpy
import pytest

from conftest import _context
from icm_field_reference import reference_table_equities
from poker_engine.handstate import context_from_dict
from poker_engine.icm_field import MAX_TABLE_SEATS, table_equities, table_equities_batch
from poker_engine.ladder import PayoutLadder

FIELD_SIZES = [0, 1, 2, 9, 490, 1000]
FIELD_STACK = 30.0


def _ladders():
    return {
        "lobby": context_from_dict(_context()).ladder(),
        "winner": PayoutLadder([(1, 1, 100.0)], places_paid=1),
    }


def _stack_sets(seats):
    # Равные; один крупный против мелких; мелкий рядом с крупными; лесенка
    # стеков без повторов — спека D27 §5, п.1.
    return [
        [20.0] * seats,
        [50.0] + [5.0] * (seats - 1),
        [0.5] + [40.0] * (seats - 1),
        [1.0 + 3.0 * i for i in range(seats)],
    ]


def _assert_close(seats, field, ref_seats, ref_field, total):
    tolerance = 1e-12 * total
    assert len(seats) == len(ref_seats)
    for got, want in zip(seats, ref_seats):
        assert abs(got - want) <= tolerance
    assert abs(field - ref_field) <= tolerance


@pytest.mark.parametrize("ladder_name", ["lobby", "winner"])
@pytest.mark.parametrize("field_count", FIELD_SIZES)
@pytest.mark.parametrize("seats", range(1, MAX_TABLE_SEATS + 1))
def test_matches_reference_on_the_grid(seats, field_count, ladder_name):
    ladder = _ladders()[ladder_name]
    for table in _stack_sets(seats):
        got_seats, got_field = table_equities(table, field_count, FIELD_STACK, ladder)
        ref_seats, ref_field = reference_table_equities(
            table, field_count, FIELD_STACK, ladder
        )
        _assert_close(got_seats, got_field, ref_seats, ref_field, ladder.total())


@pytest.mark.parametrize("ladder_name", ["lobby", "winner"])
@pytest.mark.parametrize("field_count", FIELD_SIZES)
@pytest.mark.parametrize("seats", range(1, MAX_TABLE_SEATS + 1))
def test_batch_equals_single_calls(seats, field_count, ladder_name):
    ladder = _ladders()[ladder_name]
    tables = _stack_sets(seats)
    batch_seats, batch_field = table_equities_batch(
        tables, field_count, FIELD_STACK, ladder
    )
    assert batch_seats.shape == (len(tables), seats)
    assert batch_field.shape == (len(tables),)
    for row, table in enumerate(tables):
        one_seats, one_field = table_equities(table, field_count, FIELD_STACK, ladder)
        _assert_close(
            list(batch_seats[row]), batch_field[row], one_seats, one_field, ladder.total()
        )


def test_zero_stack_in_batch_gets_nothing():
    ladder = _ladders()["lobby"]
    seats, field = table_equities_batch([[10.0, 0.0, 20.0]], 9, 15.0, ladder)
    assert seats[0, 1] == 0.0
    # Живых 2 + 9 = 11, покрытых мест 6: раздаётся вся лесенка.
    assert seats[0, 0] + seats[0, 2] + field[0] == pytest.approx(ladder.total(), abs=1e-9)


def test_zero_stack_seat_is_the_same_as_no_seat():
    # Выбывший не занимает верхних мест: остальным достаются места
    # 1..t−1+F, как если бы его за столом не было вовсе.
    ladder = _ladders()["lobby"]
    seats, field = table_equities_batch([[10.0, 0.0, 20.0]], 9, 15.0, ladder)
    ref_seats, ref_field = reference_table_equities([10.0, 20.0], 9, 15.0, ladder)
    _assert_close(
        [seats[0, 0], seats[0, 2]], field[0], ref_seats, ref_field, ladder.total()
    )


def test_several_zero_stacks_are_the_same_as_no_seats():
    # Несколько выбывших в одном исходе (мультипот-олл-ин): места
    # 1..t−z+F делят живые, как за столом без выбывших.
    ladder = _ladders()["lobby"]
    seats, field = table_equities_batch([[10.0, 0.0, 0.0, 20.0]], 9, 15.0, ladder)
    ref_seats, ref_field = reference_table_equities([10.0, 20.0], 9, 15.0, ladder)
    _assert_close(
        [seats[0, 0], seats[0, 3]], field[0], ref_seats, ref_field, ladder.total()
    )
    assert seats[0, 1] == 0.0
    assert seats[0, 2] == 0.0


def test_zero_stack_with_an_empty_field():
    # Поля нет, живой за столом один: ему первое место, выбывшему — ноль.
    ladder = _ladders()["lobby"]
    seats, field = table_equities_batch([[0.0, 12.0]], 0, math.nan, ladder)
    assert list(seats[0]) == [0.0, pytest.approx(ladder.prize(1))]
    assert field[0] == 0.0


def test_empty_field_is_not_read():
    # Спека D27 §7.3: при `field_count = 0` стек поля не читается — NaN не
    # отравляет эквити, а эквити поля ровно ноль.
    ladder = _ladders()["lobby"]
    seats, field = table_equities_batch([[30.0, 20.0, 10.0]], 0, math.nan, ladder)
    assert field[0] == 0.0
    assert numpy.isfinite(seats).all()
    assert seats.sum() == pytest.approx(
        ladder.prize(1) + ladder.prize(2) + ladder.prize(3)
    )


def test_lone_seat_takes_first_prize():
    ladder = _ladders()["lobby"]
    seats, field = table_equities_batch([[7.0]], 0, 0.0, ladder)
    assert seats[0, 0] == pytest.approx(ladder.prize(1))
    assert field[0] == 0.0


def test_batch_rows_do_not_mix():
    # Строки пакета независимы: перестановка строк переставляет ответ.
    ladder = _ladders()["lobby"]
    tables = [[30.0, 20.0, 10.0], [5.0, 5.0, 50.0]]
    seats, field = table_equities_batch(tables, 9, 15.0, ladder)
    swapped_seats, swapped_field = table_equities_batch(tables[::-1], 9, 15.0, ladder)
    assert swapped_seats[0] == pytest.approx(seats[1], abs=1e-12)
    assert swapped_seats[1] == pytest.approx(seats[0], abs=1e-12)
    assert swapped_field == pytest.approx(field[::-1], abs=1e-12)


def test_empty_batch_is_rejected():
    with pytest.raises(ValueError, match="^пакет столов пуст$"):
        table_equities_batch([], 0, 0.0, _ladders()["lobby"])


def test_ragged_batch_is_rejected():
    with pytest.raises(
        ValueError, match="^наборы стеков разной длины: в наборе 0 мест 2, в наборе 1 — 3$"
    ):
        table_equities_batch([[1.0, 2.0], [1.0, 2.0, 3.0]], 0, 0.0, _ladders()["lobby"])


def test_empty_set_in_batch_is_rejected():
    with pytest.raises(ValueError, match="^за столом нет игроков$"):
        table_equities_batch([[]], 0, 0.0, _ladders()["lobby"])


def test_too_many_seats_in_batch_is_rejected():
    table = [10.0] * (MAX_TABLE_SEATS + 1)
    with pytest.raises(
        ValueError,
        match=f"^мест за столом \\({MAX_TABLE_SEATS + 1}\\) больше предела "
        f"{MAX_TABLE_SEATS}:",
    ):
        table_equities_batch([table], 0, 0.0, _ladders()["lobby"])


def test_negative_stack_in_batch_is_rejected():
    with pytest.raises(
        ValueError, match="^стек на месте 1 в наборе 1 не может быть отрицательным: -1.0$"
    ):
        table_equities_batch([[1.0, 2.0], [3.0, -1.0]], 0, 0.0, _ladders()["lobby"])


def test_nan_stack_in_batch_is_rejected():
    with pytest.raises(
        ValueError, match="^стек на месте 0 в наборе 0 не может быть нечислом: nan$"
    ):
        table_equities_batch([[math.nan, 2.0]], 0, 0.0, _ladders()["lobby"])


def test_infinite_stack_in_batch_is_rejected():
    with pytest.raises(
        ValueError, match="^стек на месте 1 в наборе 0 не может быть бесконечным: inf$"
    ):
        table_equities_batch([[1.0, math.inf]], 0, 0.0, _ladders()["lobby"])


def test_set_without_chips_in_batch_is_rejected():
    with pytest.raises(
        ValueError, match="^в наборе 1 нет ни одного положительного стека$"
    ):
        table_equities_batch([[1.0, 2.0], [0.0, 0.0]], 0, 0.0, _ladders()["lobby"])


def test_negative_field_size_in_batch_is_rejected():
    with pytest.raises(ValueError, match="^размер поля не может быть отрицательным: -1$"):
        table_equities_batch([[10.0]], -1, 5.0, _ladders()["lobby"])


def test_fractional_field_size_in_batch_is_rejected():
    with pytest.raises(ValueError, match="^размер поля должен быть целым, получено 2.5$"):
        table_equities_batch([[10.0]], 2.5, 5.0, _ladders()["lobby"])


def test_a_non_empty_field_in_batch_needs_a_positive_stack():
    with pytest.raises(ValueError, match="^стек игрока поля должен быть > 0, получено 0.0$"):
        table_equities_batch([[10.0]], 3, 0.0, _ladders()["lobby"])


def test_zero_stack_beside_a_lone_survivor_and_a_field():
    # Живой за столом один, рядом выбывший, поле есть. Когда живой занял
    # своё место, за столом остаются только нулевые фишки: дальше места
    # достаются полю, а состояние, где не осталось никого, не делит ноль
    # на ноль.
    ladder = _ladders()["lobby"]
    seats, field = table_equities_batch([[0.0, 12.0], [12.0, 0.0]], 3, 15.0, ladder)
    ref_seats, ref_field = reference_table_equities([12.0], 3, 15.0, ladder)
    _assert_close([seats[0, 1]], field[0], ref_seats, ref_field, ladder.total())
    _assert_close([seats[1, 0]], field[1], ref_seats, ref_field, ladder.total())
    assert seats[0, 0] == 0.0
    assert seats[1, 1] == 0.0
