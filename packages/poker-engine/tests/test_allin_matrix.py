"""Таблица эквити олл-ина класс против класса: инварианты спеки плана 4, §9 п.1–4."""

from __future__ import annotations

import json

import numpy
import pytest

from poker_engine import allin_matrix
from poker_engine.allin_matrix import (
    CLASSES,
    STANDARD_ERROR,
    class_index,
    class_of,
    combos_of,
    equity_matrix,
    hand_weights,
    weight_matrix,
)
from poker_engine.preflop import hand_classes, preflop_order
from poker_engine.ranges import parse_range


def test_classes_follow_hand_classes_order():
    assert CLASSES == tuple(hand_classes())
    assert class_index("AA") == CLASSES.index("AA")


def test_matrices_are_square_and_read_only():
    e, w = equity_matrix(), weight_matrix()
    assert e.shape == w.shape == (169, 169)
    assert not e.flags.writeable and not w.flags.writeable


def test_equity_is_complementary():
    e = equity_matrix()
    assert numpy.allclose(e + e.T, 1.0, atol=1e-12)


def test_weights_are_symmetric_and_integral():
    w = weight_matrix()
    assert (w == w.T).all() and w.dtype.kind in "iu"


def test_weights_of_a_class_sum_to_its_combos_times_the_rest_of_the_deck():
    w = weight_matrix()
    for a, name in enumerate(CLASSES):
        assert w[a].sum() == combos_of(name) * 1225  # C(50, 2)


def test_blockers_reduce_weight():
    w = weight_matrix()
    # AKs против AA: у пары нет туза той же масти — блокер; 72o блокеров с AKs не имеет
    assert w[class_index("AKs"), class_index("AA")] < combos_of("AKs") * combos_of("AA")
    assert w[class_index("AKs"), class_index("72o")] == combos_of("AKs") * combos_of("72o")


def test_blocked_weight_is_counted_on_paper():
    w = weight_matrix()
    # Одномастный AK убирает одного туза: у AA остаются C(3, 2) = 3 комбинации.
    assert w[class_index("AKs"), class_index("AA")] == 4 * 3
    # Пара тузов против пары тузов: вторая пара — из двух оставшихся тузов, одна.
    assert w[class_index("AA"), class_index("AA")] == 6 * 1


def test_weighted_row_matches_equity_vs_random_hand():
    order = {row["hand"]: row["equity"] for row in preflop_order()}
    e, w = equity_matrix(), weight_matrix()
    for a, name in enumerate(CLASSES):
        mean = (e[a] * w[a]).sum() / w[a].sum()
        assert abs(mean - order[name]) <= 4 * (STANDARD_ERROR + 0.0035)


def test_combos_of_each_kind():
    assert (combos_of("AA"), combos_of("AKs"), combos_of("AKo")) == (6, 4, 12)


@pytest.mark.parametrize(
    "cards, expected",
    [
        (["Ah", "As"], "AA"),
        (["Jh", "Th"], "JTs"),
        (["Th", "Jh"], "JTs"),
        (["2c", "Kd"], "K2o"),
        (["Kd", "2c"], "K2o"),
    ],
)
def test_class_of(cards, expected):
    assert class_of(cards) == expected


def test_hand_weights_remove_the_hero_cards():
    weights = hand_weights(["Ah", "Kh"])
    assert weights.shape == (169,)
    assert weights[class_index("AA")] == 3
    assert weights[class_index("72o")] == 12
    assert weights[class_index("AKs")] == 3
    assert weights[class_index("AKo")] == 6
    assert weights.sum() == 1225


def test_hand_weights_sum_over_a_class_to_its_weight_row():
    w = weight_matrix()
    for name in ("AA", "AKs", "T9o", "72o"):
        row = sum(hand_weights([combo[:2], combo[2:]]) for combo in parse_range(name))
        assert (row == w[class_index(name)]).all()


def test_class_index_rejects_unknown_class():
    with pytest.raises(ValueError, match=r"^неизвестный класс руки: 'AKx'$"):
        class_index("AKx")


@pytest.mark.parametrize("cards", [["Ah"], ["Ah", "Ah"], ["Ah", "Kh", "Qh"]])
def test_class_of_rejects_anything_but_two_distinct_cards(cards):
    with pytest.raises(ValueError, match=r"^нужно ровно две разные карты: "):
        class_of(cards)


def test_class_of_rejects_unknown_card():
    with pytest.raises(ValueError, match=r"^неизвестная карта: 'Xx'$"):
        class_of(["Xx", "Ah"])


def test_hand_weights_reject_bad_cards():
    with pytest.raises(ValueError, match=r"^нужно ровно две разные карты: "):
        hand_weights(["Ah", "Ah"])


def test_load_rejects_classes_out_of_order(tmp_path, monkeypatch):
    swapped = list(CLASSES)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    data = tmp_path / "allin_matrix.json"
    data.write_text(json.dumps({"classes": swapped}), encoding="utf-8")
    monkeypatch.setattr(allin_matrix, "_DATA", data)
    with pytest.raises(
        ValueError, match=r"^порядок классов в allin_matrix.json не совпадает с hand_classes\(\)$"
    ):
        allin_matrix._load.__wrapped__()
