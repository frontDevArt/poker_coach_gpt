"""Инварианты отображения VPIP в диапазон.

Ничего не проверяется про «правильность» конкретного диапазона — это
калибровочный вопрос, открытый в спеке. Проверяется структура: вложенность,
доля от колоды и поведение при недостаточной выборке.
"""

import math

import pytest

from poker_engine.profiles import (
    DEFAULT_VPIP,
    MIN_VPIP_HANDS,
    TOTAL_COMBOS,
    range_for_vpip,
)

MANY = MIN_VPIP_HANDS * 10
MAX_CLASS_SIZE = 12  # самый крупный класс — разномастный, 12 комбинаций


def test_total_combos_is_the_number_of_two_card_hands():
    # Константа модуля — не запомненное число, а C(52, 2).
    assert TOTAL_COMBOS == math.comb(52, 2)


def test_wider_vpip_is_a_superset():
    tight, _ = range_for_vpip(15, MANY)
    loose, _ = range_for_vpip(30, MANY)
    assert set(tight) < set(loose)


def test_share_of_deck_tracks_vpip():
    for vpip in (5, 15, 25, 40, 60):
        combos, _ = range_for_vpip(vpip, MANY)
        target = TOTAL_COMBOS * vpip / 100
        # Диапазон минимально покрывающий: не меньше цели и не больше,
        # чем цель плюс один класс.
        assert target <= len(combos) <= target + MAX_CLASS_SIZE


def test_hundred_percent_is_the_whole_deck():
    combos, _ = range_for_vpip(100, MANY)
    assert len(combos) == TOTAL_COMBOS


def test_zero_vpip_still_yields_a_playable_range():
    # Ноль наблюдённых входов не означает, что соперник не держит карт.
    combos, _ = range_for_vpip(0, MANY)
    assert len(combos) > 0


def test_small_sample_falls_back_to_default_and_says_so():
    combos, used_default = range_for_vpip(3, MIN_VPIP_HANDS - 1)
    reference, _ = range_for_vpip(DEFAULT_VPIP, MANY)
    assert used_default is True
    assert combos == reference


def test_missing_vpip_falls_back_to_default():
    combos, used_default = range_for_vpip(None, None)
    reference, _ = range_for_vpip(DEFAULT_VPIP, MANY)
    assert used_default is True
    assert combos == reference


def test_missing_hand_count_falls_back_to_default():
    # Бейдж без числа раздач — VPIP неизвестной надёжности, а значит
    # ненадёжный: доверять ему нельзя ровно так же, как отсутствующему.
    combos, used_default = range_for_vpip(22, None)
    reference, _ = range_for_vpip(DEFAULT_VPIP, MANY)
    assert used_default is True
    assert combos == reference


def test_sufficient_sample_is_not_flagged_as_default():
    _, used_default = range_for_vpip(22, MIN_VPIP_HANDS)
    assert used_default is False


def test_default_calibration_is_not_degenerate():
    # Значения дефолтов — калибровочная догадка и тестом не фиксируются.
    # Проверяется только то, что они не вырождены: дефолтный соперник
    # должен быть играющим, а порог выборки — непустым.
    assert 0 < DEFAULT_VPIP < 100
    assert MIN_VPIP_HANDS > 0


def test_result_is_sorted_and_unique():
    combos, _ = range_for_vpip(35, MANY)
    assert combos == sorted(combos)
    assert len(combos) == len(set(combos))


@pytest.mark.parametrize("vpip", [-1, 101])
def test_impossible_vpip_is_rejected(vpip):
    with pytest.raises(ValueError):
        range_for_vpip(vpip, MANY)


def test_negative_hand_count_is_rejected():
    with pytest.raises(ValueError):
        range_for_vpip(20, -1)
