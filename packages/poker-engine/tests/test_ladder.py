"""Лесенка выплат: приз берётся по настоящему месту в турнире."""

import tracemalloc

import pytest

from poker_engine.ladder import PayoutLadder


def test_prize_comes_from_the_interval_that_covers_the_place():
    ladder = PayoutLadder([(1, 1, 100.0), (2, 3, 50.0)], places_paid=3)
    assert ladder.prize(1) == 100.0
    assert ladder.prize(2) == 50.0
    assert ladder.prize(3) == 50.0


def test_intervals_may_come_in_any_order():
    # Со скриншота строки приходят как распознались; порядок — не контракт.
    ladder = PayoutLadder([(2, 3, 50.0), (1, 1, 100.0)], places_paid=3)
    assert ladder.prize(1) == 100.0
    assert ladder.prize(3) == 50.0
    assert ladder.is_complete


def test_places_past_the_ladder_pay_nothing():
    ladder = PayoutLadder([(1, 2, 10.0)], places_paid=2)
    assert ladder.prize(3) == 0.0
    assert ladder.prize(100_000) == 0.0


def test_places_inside_the_prize_pool_but_outside_the_intervals_pay_nothing():
    # Недоснятый скриншот: места 7-144 не описаны, платить за них нечем.
    ladder = PayoutLadder([(1, 6, 400.0)], places_paid=144)
    assert ladder.prize(7) == 0.0
    assert ladder.prize(144) == 0.0


def test_total_is_the_sum_over_every_paid_place():
    # 100 за первое плюс 50 за два места = 200.
    ladder = PayoutLadder([(1, 1, 100.0), (2, 3, 50.0)], places_paid=3)
    assert ladder.total() == pytest.approx(200.0)


def test_real_ladder_is_sixteen_lines_for_a_hundred_forty_four_places():
    # Лесенка Mini SUPER SIX Bounty Turbo, 1244 входа, 144 места (спека 4.1).
    ladder = PayoutLadder(
        [
            (1, 1, 1098.45), (2, 2, 1097.86), (3, 3, 832.02), (4, 4, 630.55),
            (5, 5, 476.41), (6, 6, 361.05), (7, 7, 273.62), (8, 8, 163.54),
            (9, 10, 122.37), (11, 13, 91.55), (14, 18, 68.50), (19, 26, 51.25),
            (27, 39, 38.35), (40, 59, 28.69), (60, 92, 21.46), (93, 144, 16.06),
        ],
        places_paid=144,
    )
    assert ladder.is_complete
    assert ladder.places_covered == 144
    assert ladder.prize(144) == 16.06
    assert ladder.prize(145) == 0.0


def test_partial_coverage_is_visible_and_is_not_an_error():
    # Пользователь снял только первый экран лобби: описаны места 1-6 из 144.
    ladder = PayoutLadder([(1, 6, 400.0)], places_paid=144)
    assert ladder.places_covered == 6
    assert ladder.is_complete is False


def test_adjacent_intervals_cover_the_whole_prize_pool():
    # 3 места плюс 1 место = 4 покрытых из 4 оплачиваемых.
    ladder = PayoutLadder([(1, 3, 10.0), (4, 4, 5.0)], places_paid=4)
    assert ladder.places_covered == 4
    assert ladder.is_complete


def test_a_complete_ladder_always_pays_something():
    # Все призы > 0 по гарду, значит полная лесенка не может стоить ноль:
    # 144 места по 1.0 = 144.0.
    ladder = PayoutLadder([(1, 144, 1.0)], places_paid=144)
    assert ladder.is_complete
    assert ladder.total() == pytest.approx(144.0)


def test_memory_does_not_scale_with_places_paid():
    # Список на places_paid + 1 элементов дал бы здесь ~160 МБ; двоичный
    # поиск по интервалам держит память на числе интервалов.
    tracemalloc.start()
    try:
        ladder = PayoutLadder([(1, 6, 400.0)], places_paid=20_000_000)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 100_000
    assert ladder.prize(10_000_000) == 0.0


def test_place_below_one_is_rejected_by_prize():
    ladder = PayoutLadder([(1, 1, 5.0)], places_paid=1)
    with pytest.raises(ValueError, match="номер места должен быть > 0"):
        ladder.prize(0)


def test_fractional_place_is_rejected_by_prize():
    ladder = PayoutLadder([(1, 1, 5.0)], places_paid=1)
    with pytest.raises(ValueError, match="номер места должен быть целым"):
        ladder.prize(2.5)


def test_non_positive_places_paid_is_rejected():
    with pytest.raises(ValueError, match="размер призовой зоны должен быть > 0"):
        PayoutLadder([(1, 1, 5.0)], places_paid=0)


def test_fractional_places_paid_is_rejected():
    with pytest.raises(ValueError, match="размер призовой зоны должен быть целым"):
        PayoutLadder([(1, 1, 5.0)], places_paid=2.5)


def test_empty_ladder_is_rejected():
    with pytest.raises(ValueError, match="лесенка выплат пуста"):
        PayoutLadder([], places_paid=144)


def test_interval_outside_places_paid_is_rejected():
    with pytest.raises(
        ValueError, match="выплаты описаны до места 150, а призовых мест 144"
    ):
        PayoutLadder([(140, 150, 10.0)], places_paid=144)


def test_backwards_interval_is_rejected():
    with pytest.raises(
        ValueError, match="неверный интервал мест в выплатах: 10–3"
    ):
        PayoutLadder([(10, 3, 10.0)], places_paid=144)


def test_interval_starting_below_place_one_is_rejected():
    with pytest.raises(
        ValueError, match="неверный интервал мест в выплатах: 0–3"
    ):
        PayoutLadder([(0, 3, 10.0)], places_paid=144)


def test_fractional_interval_bound_is_rejected():
    with pytest.raises(ValueError, match="номер места должен быть целым"):
        PayoutLadder([(1.5, 3, 10.0)], places_paid=144)
    with pytest.raises(ValueError, match="номер места должен быть целым"):
        PayoutLadder([(1, 2.5, 10.0)], places_paid=144)


def test_non_positive_prize_is_rejected():
    with pytest.raises(ValueError, match="приз за место 1 должен быть > 0"):
        PayoutLadder([(1, 1, -500.0)], places_paid=1)
    with pytest.raises(ValueError, match="приз за место 1 должен быть > 0"):
        PayoutLadder([(1, 144, 0.0)], places_paid=144)


def test_overlapping_intervals_are_rejected():
    # Места 2-3 описаны дважды: считать их пришлось бы дважды.
    with pytest.raises(
        ValueError, match="интервалы выплат пересекаются на месте 2"
    ):
        PayoutLadder([(1, 3, 10.0), (2, 4, 5.0)], places_paid=4)


def test_overlap_names_the_lowest_place_described_twice():
    # Принятые интервалы 1-3 и 5-12; новый 10-20 пересекается с 5-12
    # начиная с места 10 — как и считает `handstate._validate_context`.
    with pytest.raises(
        ValueError, match="интервалы выплат пересекаются на месте 10"
    ):
        PayoutLadder(
            [(1, 3, 10.0), (10, 20, 5.0), (5, 12, 7.0)], places_paid=20
        )
