"""Линия префлопа по кадрам раздачи: действия, спот и отказы (спека плана 5, §4–§5).

Стол фикстур — 6-max `conftest.preflop_frame`: кнопка 4, ход `UTG` 7, `HJ` 2, `CO` 3,
`BTN` 4, `SB` 5, `BB` 6. Каждый отказ пинится текстом целиком: проверки модуля затеняют
друг друга, и голый `pytest.raises` или подстрока поймали бы не ту.
"""

import pytest

from conftest import (
    _context,
    preflop_frame,
    preflop_open,
    preflop_vs_3bet,
    preflop_vs_4bet,
    preflop_vs_allin_after_raise,
    preflop_vs_limp,
    preflop_vs_open,
    pushfold_facing_allin_node,
    pushfold_first_in_node,
)
from poker_engine.handstate import context_from_dict, node_from_dict, validate_hand
from poker_engine.preflop_line import AMBIGUOUS, HERO_FLAT, MULTIWAY, Act, Line, read_line


def _line(raws):
    nodes = [node_from_dict(raw) for raw in raws]
    validate_hand(context_from_dict(_context()), nodes)
    return read_line(nodes)


def _seats(line):
    return [seat.seat_index for seat in line.players]


def test_open():
    line = _line(preflop_open())
    assert isinstance(line, Line)
    assert line.kind == "open"
    assert line.acts == [Act(7, "fold", None), Act(2, "fold", None)]
    # Корень — герой; дальше по ходу все, кто в раздаче.
    assert _seats(line) == [3, 4, 5, 6]
    assert line.hero_at == 0
    assert line.opponent_at is None


def test_vs_open():
    line = _line(preflop_vs_open())
    assert line.kind == "vs_open"
    assert line.acts == [Act(7, "raise", 2.0), Act(2, "fold", None)]
    assert _seats(line) == [7, 3, 4, 5, 6]
    assert (line.hero_at, line.opponent_at) == (1, 0)


@pytest.mark.parametrize("size", [1.5, 2.0])
def test_an_open_below_or_at_two_blinds_is_a_raise(size):
    # Review Focus 2: открытие до 1.5 и мин-рейз до 2.0 при вложенном `BB` 1.0 — рейз, не колл.
    line = _line([preflop_frame(3, {7: size}, folded={2})])
    assert line.kind == "vs_open"
    assert line.acts[0] == Act(7, "raise", size)


def test_vs_limp():
    line = _line(preflop_vs_limp())
    assert line.kind == "vs_limp"
    assert line.acts == [
        Act(7, "limp", 1.0),
        Act(2, "fold", None),
        Act(3, "fold", None),
    ]
    assert _seats(line) == [7, 4, 5, 6]
    assert (line.hero_at, line.opponent_at) == (1, 0)


def test_a_small_blind_completion_is_a_limp():
    # Все сфолдили до `SB`, он доставил до 1 BB; герой — `BB`: спот против лимпа.
    line = _line([preflop_frame(6, {5: 1.0}, folded={7, 2, 3, 4})])
    assert line.kind == "vs_limp"
    assert line.acts[-1] == Act(5, "limp", 1.0)
    assert _seats(line) == [5, 6]
    assert (line.hero_at, line.opponent_at) == (1, 0)


def test_vs_3bet_keeps_the_hero_open_from_the_previous_frame():
    line = _line(preflop_vs_3bet())
    assert line.kind == "vs_3bet"
    assert line.acts == [
        Act(7, "fold", None),
        Act(2, "fold", None),
        Act(3, "raise", 2.0),
        Act(4, "raise", 7.0),
        Act(5, "fold", None),
        Act(6, "fold", None),
    ]
    # Сфолдившие блайнды вкладывали на префлопе и остаются в списке.
    assert _seats(line) == [3, 4, 5, 6]
    assert (line.hero_at, line.opponent_at) == (0, 1)


def test_vs_4bet_keeps_the_hero_3bet_from_the_previous_frame():
    line = _line(preflop_vs_4bet())
    assert line.kind == "vs_4bet"
    assert line.acts == [
        Act(7, "raise", 2.0),
        Act(2, "fold", None),
        Act(3, "raise", 6.0),
        Act(4, "fold", None),
        Act(5, "fold", None),
        Act(6, "fold", None),
        Act(7, "raise", 15.0),
    ]
    assert _seats(line) == [7, 3, 5, 6]
    assert (line.hero_at, line.opponent_at) == (1, 0)


def test_vs_allin_after_raise():
    line = _line(preflop_vs_allin_after_raise())
    assert line.kind == "vs_allin_after_raise"
    assert line.acts[3] == Act(4, "allin", 40.0)
    assert (line.hero_at, line.opponent_at) == (0, 1)


def test_an_allin_after_the_hero_3bet_is_vs_allin_after_raise():
    raws = preflop_vs_4bet()
    raws[1] = preflop_frame(3, {7: 40.0, 3: 6.0}, folded={2, 4, 5, 6})
    line = _line(raws)
    assert line.kind == "vs_allin_after_raise"
    assert line.acts[-1] == Act(7, "allin", 40.0)
    assert (line.hero_at, line.opponent_at) == (1, 0)


# --- отказы ------------------------------------------------------------------------------


def test_not_preflop_is_refused():
    raw = preflop_frame(3, folded={7, 2})
    raw.update(street="flop", board=["8c", "2s", "9d"])
    assert _line([raw]) == "советник префлопа работает только на префлопе"


def test_hero_all_in_is_refused():
    # Герой — `BB` с одним блайндом в стеке: всё уже в банке.
    raw = preflop_frame(6, {7: 2.0}, folded={2, 3, 4, 5}, starting={6: 1.0})
    assert _line([raw]) == "герой уже в олл-ине: решения нет"


@pytest.mark.parametrize("make", [pushfold_first_in_node, pushfold_facing_allin_node])
def test_a_pushfold_spot_is_refused(make):
    assert _line([make()]) == "спот push/fold: отвечает советник pushfold"


@pytest.mark.parametrize("total", [40.0, 1.0])
def test_an_open_allin_the_pushfold_advisor_refuses_is_still_refused(total):
    # `facing_allin` — спот `pushfold` при любом стеке (спека §4), даже когда сам он узел не
    # взял: здесь у сфолдившего `HJ` стек 0 вне раздачи, ICM не определён. Олл-ин ровно на
    # 1 BB — тоже олл-ин, а не лимп.
    raw = preflop_frame(3, {7: total}, folded={2}, starting={2: 0.0, 7: total})
    assert _line([raw]) == "спот push/fold: отвечает советник pushfold"


@pytest.mark.parametrize(
    "invested",
    [
        {7: 2.0, 2: 2.0},  # колд-колл открытия
        {7: 1.0, 2: 1.0},  # два лимпера
        {7: 1.0, 2: 3.0},  # лимп и рейз
        {7: 2.0, 2: 6.0},  # 3-бет перед героем
    ],
)
def test_two_voluntary_entrants_before_the_hero_are_refused(invested):
    assert (
        _line([preflop_frame(3, invested)])
        == "в банк до героя вошли двое и больше: мультипот вне модели"
    )


def test_a_squeeze_after_the_hero_call_is_refused():
    # Герой `CO` заколлировал открытие `UTG`, `BTN` сделал сквиз: вошли двое.
    raws = [
        preflop_frame(3, {7: 2.0}, folded={2}),
        preflop_frame(3, {7: 2.0, 3: 2.0, 4: 8.0}, folded={2, 5, 6}),
    ]
    assert _line(raws) == "в банк до героя вошли двое и больше: мультипот вне модели"


def test_one_frame_after_a_hero_raise_is_ambiguous():
    # Только второй кадр `vs_3bet`: герой уже вложил 2.0, `BTN` — 7.0. «Открыл и получил
    # 3-бет» или «изолировал лимп и получил лимп-рейз» — по одному кадру не различить.
    raws = preflop_vs_3bet()[1:]
    assert _line(raws) == "линия неоднозначна: нужен кадр предыдущего решения героя"


def test_a_5bet_not_allin_is_refused():
    raws = [
        preflop_frame(3, folded={7, 2}),
        preflop_frame(3, {3: 2.0, 4: 6.0}, folded={7, 2, 5, 6}),
        preflop_frame(3, {3: 15.0, 4: 30.0}, folded={7, 2, 5, 6}),
    ]
    assert _line(raws) == "5-бет не олл-ином: вне дерева префлопа"


def test_a_5bet_allin_is_vs_allin_after_raise():
    raws = [
        preflop_frame(3, folded={7, 2}),
        preflop_frame(3, {3: 2.0, 4: 6.0}, folded={7, 2, 5, 6}),
        preflop_frame(3, {3: 15.0, 4: 40.0}, folded={7, 2, 5, 6}),
    ]
    line = _line(raws)
    assert line.kind == "vs_allin_after_raise"
    assert (line.hero_at, line.opponent_at) == (0, 1)


def test_big_blind_walk_is_refused():
    assert (
        _line([preflop_frame(6, folded={7, 2, 3, 4, 5})])
        == "все сфолдили до большого блайнда: решения нет"
    )


def _sb_limped(big_blind):
    """Герой `SB` первым в банк залимпил, `BB` поставил до `big_blind`: два кадра."""
    return [
        preflop_frame(5, folded={7, 2, 3, 4}),
        preflop_frame(5, {5: 1.0, 6: big_blind}, folded={7, 2, 3, 4}),
    ]


def test_vs_iso():
    # Спека модели колла §7: `SB` залимпил, `BB` изолировал не олл-ином.
    line = _line(_sb_limped(4.0))
    assert line.kind == "vs_iso"
    assert line.acts[-2:] == [Act(5, "limp", 1.0), Act(6, "raise", 4.0)]
    assert _seats(line) == [5, 6]
    assert (line.hero_at, line.opponent_at) == (0, 1)


def test_vs_allin_after_limp():
    line = _line(_sb_limped(40.0))
    assert line.kind == "vs_allin_after_limp"
    assert line.acts[-1] == Act(6, "allin", 40.0)
    assert (line.hero_at, line.opponent_at) == (0, 1)


@pytest.mark.parametrize("big_blind", [4.0, 40.0])
def test_one_frame_after_a_hero_limp_is_ambiguous(big_blind):
    # Только второй кадр: «`SB` залимпил» по одному кадру не отличить от рейза героя до 1.0 —
    # нужен кадр решения `SB` первым в банк.
    assert _line(_sb_limped(big_blind)[1:]) == AMBIGUOUS


def test_a_hero_limp_not_from_the_small_blind_is_refused():
    # Лимп не с `SB` — вне модели (за ним колл лимпа и мультипот): `UTG` залимпил, `BB`
    # изолировал. Текст отказа прежний.
    raws = [
        preflop_frame(7),
        preflop_frame(7, {7: 1.0, 6: 4.0}, folded={2, 3, 4, 5}),
    ]
    assert _line(raws) == HERO_FLAT
    assert HERO_FLAT == "герой вошёл в банк лимпом или коллом: линия вне дерева префлопа"


def test_cold_call_before_the_hero_is_multiway():
    # Спека модели колла §4, инвариант 3: колд-колл незакрывающего до героя до дерева не доходит.
    assert _line([preflop_frame(4, {7: 2.0, 2: 2.0}, folded={3})]) == MULTIWAY
