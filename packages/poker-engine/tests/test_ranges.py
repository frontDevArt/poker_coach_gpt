"""Инварианты разбора диапазонов. Числа здесь — комбинаторика, а не память."""

import pytest

from poker_engine.equity import FULL_DECK
from poker_engine.ranges import parse_range


def test_pair_has_six_combos():
    # C(4,2) способов выбрать две масти из четырёх.
    assert len(parse_range("AA")) == 6


def test_suited_has_four_combos():
    # По одной комбинации на каждую из четырёх мастей.
    assert len(parse_range("AKs")) == 4


def test_offsuit_has_twelve_combos():
    # 4 масти старшей × 3 оставшиеся масти младшей.
    assert len(parse_range("AKo")) == 12


def test_unsuffixed_class_is_suited_plus_offsuit():
    assert len(parse_range("AK")) == len(parse_range("AKs")) + len(parse_range("AKo"))


def test_all_pairs_plus_covers_thirteen_ranks():
    # 13 рангов × 6 комбинаций.
    assert len(parse_range("22+")) == 78


def test_suited_plus_walks_the_lower_rank_up():
    # ATs, AJs, AQs, AKs — четыре класса по четыре комбинации.
    assert len(parse_range("ATs+")) == 16


def test_plus_ranges_are_nested():
    assert set(parse_range("ATs+")) < set(parse_range("A9s+"))


def test_explicit_combo_is_a_single_entry():
    assert parse_range("AsKh") == ["AsKh"]


def test_comma_list_is_the_union():
    assert set(parse_range("AA,KK")) == set(parse_range("AA")) | set(parse_range("KK"))


def test_overlapping_tokens_do_not_duplicate():
    assert len(parse_range("AA,AA")) == 6


def test_every_combo_is_two_distinct_real_cards():
    for combo in parse_range("22+,ATs+,KQo"):
        assert len(combo) == 4
        first, second = combo[:2], combo[2:]
        assert first != second
        assert first in FULL_DECK
        assert second in FULL_DECK


def test_result_is_sorted_and_unique():
    combos = parse_range("22+,A2s+")
    assert combos == sorted(combos)
    assert len(combos) == len(set(combos))


@pytest.mark.parametrize(
    "text",
    ["", "AA,", "XX", "AAs", "AsKs+", "AsAs", "A", "AKx", "9Ts"],
)
def test_bad_input_is_rejected(text):
    with pytest.raises(ValueError):
        parse_range(text)
