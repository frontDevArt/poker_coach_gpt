"""Лесенка выплат: приз берётся по настоящему месту в турнире."""

import pytest

from poker_engine.ladder import PayoutLadder


def test_prize_comes_from_the_interval_that_covers_the_place():
    ladder = PayoutLadder([(1, 1, 100.0), (2, 3, 50.0)], places_paid=3)
    assert ladder.prize(1) == 100.0
    assert ladder.prize(2) == 50.0
    assert ladder.prize(3) == 50.0


def test_places_past_the_ladder_pay_nothing():
    ladder = PayoutLadder([(1, 2, 10.0)], places_paid=2)
    assert ladder.prize(3) == 0.0
    assert ladder.prize(100_000) == 0.0


def test_total_is_the_sum_over_every_paid_place():
    # 100 за первое плюс 50 за два места = 200.
    ladder = PayoutLadder([(1, 1, 100.0), (2, 3, 50.0)], places_paid=3)
    assert ladder.total() == pytest.approx(200.0)


def test_real_ladder_is_twelve_lines_for_a_hundred_forty_four_places():
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
    assert ladder.prize(7) == 0.0


def test_place_below_one_is_rejected():
    ladder = PayoutLadder([(1, 1, 5.0)], places_paid=1)
    with pytest.raises(ValueError, match="номер места должен быть > 0"):
        ladder.prize(0)


def test_non_positive_places_paid_is_rejected():
    with pytest.raises(ValueError, match="размер лесенки выплат должен быть > 0"):
        PayoutLadder([(1, 1, 5.0)], places_paid=0)


def test_interval_outside_places_paid_is_rejected():
    with pytest.raises(ValueError, match="интервал выплат 140–150 выходит за 144"):
        PayoutLadder([(140, 150, 10.0)], places_paid=144)
