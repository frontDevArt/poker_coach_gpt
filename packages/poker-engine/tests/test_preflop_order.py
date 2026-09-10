"""Инварианты вычисленного порядка силы стартовых рук.

Проверяется не «какое эквити у AKs», а структура: полнота перебора,
монотонность сортировки и два факта, доказуемых без счёта — лучшая
и худшая стартовая рука.
"""

from poker_engine.equity import RANKS
from poker_engine.preflop import hand_classes, preflop_order
from poker_engine.ranges import parse_range

TOTAL_COMBOS = 1326  # C(52,2)


def _rank_by_strength() -> dict[str, int]:
    return {entry["hand"]: index for index, entry in enumerate(preflop_order())}


def test_there_are_exactly_169_classes():
    # 13 пар + 78 одномастных + 78 разномастных.
    assert len(hand_classes()) == 169
    assert len(set(hand_classes())) == 169


def test_classes_partition_the_whole_deck():
    combos = set()
    for name in hand_classes():
        combos |= set(parse_range(name))
    assert len(combos) == TOTAL_COMBOS


def test_order_covers_every_class_once():
    order = preflop_order()
    assert len(order) == 169
    assert {entry["hand"] for entry in order} == set(hand_classes())


def test_combos_column_matches_the_parser():
    for entry in preflop_order():
        assert entry["combos"] == len(parse_range(entry["hand"]))


def test_combos_sum_to_the_whole_deck():
    assert sum(entry["combos"] for entry in preflop_order()) == TOTAL_COMBOS


def test_order_is_monotone_by_equity():
    values = [entry["equity"] for entry in preflop_order()]
    assert values == sorted(values, reverse=True)


def test_every_equity_is_a_probability():
    for entry in preflop_order():
        assert 0.0 < entry["equity"] < 1.0


def test_aces_are_first_and_the_worst_offsuit_hand_is_last():
    # Против случайной руки AA — сильнейшая стартовая рука, 32o — слабейшая.
    # Это свойство игры, а не результат конкретного прогона.
    order = preflop_order()
    assert order[0]["hand"] == "AA"
    assert order[-1]["hand"] == "32o"


def test_pairs_beat_their_own_offsuit_kickers():
    # Пара против случайной руки сильнее любой неспаренной руки тех же рангов.
    rank = _rank_by_strength()
    for pair, weaker in [("KK", "KQo"), ("77", "76o"), ("33", "32o")]:
        assert rank[pair] < rank[weaker]


def test_suited_class_always_outranks_its_offsuit_twin():
    # Одномастная рука доминирует разномастную того же состава: ранги те же,
    # значит все пары, стриты и старшие карты достижимы одинаково, но флеш
    # доступен только одномастной. Строго сильнее — доказуемо без счёта.
    rank = _rank_by_strength()
    for i, high in enumerate(RANKS):
        for low in RANKS[:i]:
            assert rank[high + low + "s"] < rank[high + low + "o"]


def test_pairs_are_ordered_by_rank():
    # Старшая пара против случайной руки сильнее младшей: она бьёт младшую
    # напрямую и доминирует её по любому «оверпэр» сценарию.
    rank = _rank_by_strength()
    pairs = [r + r for r in RANKS]  # от 22 к AA
    for lower, higher in zip(pairs, pairs[1:]):
        assert rank[higher] < rank[lower]
