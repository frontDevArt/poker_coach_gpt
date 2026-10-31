"""Состояние раздачи `Hand` и итог префлопа (план 6, Задача 7).

Спека тренера §7.1, §7.3, инварианты 6–7 §12; Review Focus 5–6. Итог — линия префлопа целиком и
диапазоны дошедших до флопа по ICM-равновесию того же дерева, что на последнем шаге префлопа:
ожидания сверяются с равновесием этого дерева, решённым отдельно, а не с числами из памяти.
"""

import json

import pytest

from conftest import (
    _context,
    flop_frame,
    preflop_frame,
    preflop_open,
    preflop_vs_allin_after_raise,
    preflop_vs_open,
    preflop_vs_3bet,
)
from poker_engine import advice, coach, preflop_advisor
from poker_engine.advice import advise, read_hand
from poker_engine.handstate import context_from_dict, node_from_dict
from poker_engine.preflop_advisor import (
    MULTIWAY_FLOP,
    NO_PREFLOP,
    OFF_TREE_LINE,
    PUSHFOLD_LINE,
    close_street,
)
from poker_engine.preflop_solver import reach
from poker_engine.pushfold import _classes

def _summary(frames):
    return read_hand(_context(), frames).street_summary("preflop")


def _solved(frames):
    nodes = [node_from_dict(raw) for raw in frames]
    return preflop_advisor._solve(context_from_dict(_context()), nodes)


def _child(tree, at, kind):
    return next(action.child for action in tree.nodes[at].actions if action.kind == kind)


def _freq(tree, solution, at, kind):
    kinds = [action.kind for action in tree.nodes[at].actions]
    return solution.strategy[at][kinds.index(kind)]


def _close(got, expected, tol=0.01):
    # Частоты классов печатаются с шагом 0.01: класс без частоты — ноль.
    names = set(got) | set(expected)
    return all(abs(got.get(name, 0.0) - expected.get(name, 0.0)) <= tol for name in names)


def _by_seat(summary):
    return {entry["seatIndex"]: entry for entry in summary["ranges"]}


# --- Hand и реестры ---------------------------------------------------------------------------


def test_every_advisor_explains_and_the_preflop_closes():
    # Инвариант 6.
    assert all(callable(advisor.explain) for advisor in advice.ADVISORS)
    assert advice.STREET_CLOSERS == {"preflop": close_street}


def test_an_open_street_has_no_summary():
    assert _summary(preflop_vs_3bet()) is None
    assert read_hand(_context(), preflop_vs_3bet()).street_summary("flop") is None


def test_the_summary_is_computed_once(monkeypatch):
    calls = []
    frames = [preflop_frame(3, folded={7, 2}), flop_frame(3, {3: 2.0, 6: 2.0}, {7, 2, 4, 5})]
    hand = read_hand(_context(), frames)
    monkeypatch.setitem(
        advice.STREET_CLOSERS, "preflop", lambda h: calls.append(h) or {"street": "preflop"}
    )
    first = hand.street_summary("preflop")
    assert hand.street_summary("preflop") is first and calls == [hand]


# --- итог: линия и диапазоны ------------------------------------------------------------------


def test_open_and_the_big_blind_call():
    # Инвариант 7: герой `CO` открыл до 2.0 (размер правила — дерево то же, что на шаге 1),
    # `BTN` и `SB` сфолдили, `BB` заколлировал. `reach` героя — его частоты рейза шага 1, `BB` —
    # частоты колла на его узле того же равновесия.
    first = preflop_frame(3, folded={7, 2})
    summary = _summary([first, flop_frame(3, {3: 2.0, 6: 2.0}, {7, 2, 4, 5})])
    answer = advise(_context(), [first], [])
    solved = _solved([first])
    tree = solved.tree
    big_blind = _child(tree, _child(tree, _child(tree, tree.root, "raise"), "fold"), "fold")
    calls = _classes(_freq(tree, solved.by_icm, big_blind, "call"))

    assert summary["street"] == "preflop"
    assert summary["line"][-1] == {"seatIndex": 6, "position": "BB", "action": "call", "toBb": 2.0}
    ranges = _by_seat(summary)
    assert set(ranges) == {3, 6}
    hero, bb = ranges[3], ranges[6]
    assert (hero["isHero"], hero["position"], hero["role"]) == (True, "CO", "opener")
    assert (bb["isHero"], bb["position"], bb["role"]) == (False, "BB", "responder")
    assert (hero["stackBb"], bb["stackBb"]) == (38.0, 38.0)
    assert _close(hero["reach"], answer["ranges"]["hero"]["byAction"]["raise"])
    assert _close(bb["reach"], calls)
    assert 0 < hero["reachPct"] < 1 and 0 < bb["reachPct"] < 1


def test_a_three_bet_and_the_call():
    # Инвариант 7 на два уровня: `BTN` 3-бет до 7.0, герой заколлировал. Дерево итога — дерево
    # шага 2: `reach` героя — его рейз в корне на колл на своём узле, `BTN` — его 3-бет.
    frames = preflop_vs_3bet()
    summary = _summary([*frames, flop_frame(3, {3: 7.0, 4: 7.0}, {7, 2, 5, 6})])
    answer = advise(_context(), frames, [advise(_context(), frames[:1], [])])
    solved = _solved(frames)
    tree = solved.tree
    me = next(at for at, seat in enumerate(tree.players) if seat.is_hero)
    mine = reach(tree, solved.by_icm, me) * _freq(tree, solved.by_icm, tree.hero_node, "call")

    assert summary["line"][-1] == {"seatIndex": 3, "position": "CO", "action": "call", "toBb": 7.0}
    ranges = _by_seat(summary)
    assert ranges[3]["role"] == "opener" and ranges[4]["role"] == "3bettor"
    assert _close(ranges[3]["reach"], _classes(mine))
    btn = next(o for o in answer["ranges"]["opponents"] if o["seatIndex"] == 4)
    assert ranges[4]["reach"] == btn["reach"]


@pytest.mark.parametrize("seat, noise", [(4, -0.1), (3, -0.1), (3, 0.1), (5, -0.1)])
def test_rounding_of_the_flop_stacks_is_not_an_action(seat, noise):
    # Приёмка, Фаза 14 (WSOP, кадр флопа): стек на экране округлён до 0.1 BB, и вложенное
    # префлопа — разность стеков двух кадров — уходит на шаг от уравненного 7.0. Это колл, а не
    # рейз до 7.1 (`BTN` — 3-беттор, не 4-беттор) и не колл до 6.9; у сфолдившего `SB` — фолд.
    frames = preflop_vs_3bet()
    flop = flop_frame(3, {3: 7.0, 4: 7.0}, {7, 2, 5, 6})
    exact = _summary([*frames, flop])
    next(s for s in flop["seats"] if s["seatIndex"] == seat)["stackBb"] += noise
    summary = _summary([*frames, flop])

    assert summary["line"] == exact["line"]
    assert summary["line"][-1] == {"seatIndex": 3, "position": "CO", "action": "call", "toBb": 7.0}
    assert {s: e["role"] for s, e in _by_seat(summary).items()} == {3: "opener", 4: "3bettor"}


@pytest.mark.parametrize("seat, position", [(4, "BTN"), (5, "SB")])
def test_rounding_of_a_fold_after_the_last_frame_is_not_a_call(seat, position):
    # Фаза 14b, N3: `BTN` и `SB` в раздаче на кадре открытия героя и сфолдили после него. Их
    # вложенное по кадру флопа уходит от своего (0.0 и 0.5) на шаг — это фолд, а не колл до 0.1
    # или 0.6: прижим к своему вложенному на последнем кадре префлопа.
    first = preflop_frame(3, folded={7, 2})
    flop = flop_frame(3, {3: 2.0, 6: 2.0}, {7, 2, 4, 5})
    exact = _summary([first, flop])
    next(s for s in flop["seats"] if s["seatIndex"] == seat)["stackBb"] -= 0.1
    summary = _summary([first, flop])

    assert summary["line"] == exact["line"]
    assert [a for a in summary["line"] if a["seatIndex"] == seat] == [
        {"seatIndex": seat, "position": position, "action": "fold"}
    ]


_OPEN_AND_CALL = (preflop_open, {3: 2.0, 6: 2.0}, {7, 2, 4, 5}, 3, 6)
_THREE_BET_AND_CALL = (preflop_vs_open, {7: 6.0, 3: 6.0}, {2, 4, 5, 6}, 3, 7)


@pytest.mark.parametrize("case", [_OPEN_AND_CALL, _THREE_BET_AND_CALL])
@pytest.mark.parametrize("who", ["raiser", "caller"])
@pytest.mark.parametrize("noise", [-0.1, 0.1])
def test_rounding_of_a_raise_after_the_last_frame_is_not_an_action(case, who, noise):
    # Фаза 14b, N1: наибольшее вложенное префлопа ставит рейз героя после последнего кадра, и
    # прижать его к вложенному кадра нечем. Шум в шаг у рейзера или у уравнявшего — не рейз
    # уравнявшего (линия вне дерева) и не колл на другую сумму: оба на наибольшем вложенном, с
    # шагом печати.
    frames, put, folded, raiser, caller = case
    flop = flop_frame(3, put, folded)
    seat = raiser if who == "raiser" else caller
    next(s for s in flop["seats"] if s["seatIndex"] == seat)["stackBb"] -= noise
    summary = _summary([*frames(), flop])

    assert "line" in summary, summary.get("reason")
    acts = {a["seatIndex"]: a for a in summary["line"] if a["action"] != "fold"}
    assert (acts[raiser]["action"], acts[caller]["action"]) == ("raise", "call")
    # Наибольшее на исходе улицы: шум вверх у любого из двух поднимает его на шаг.
    size = put[raiser] + max(noise, 0.0)
    assert acts[raiser]["toBb"] == acts[caller]["toBb"] == pytest.approx(size, abs=1e-9)
    assert acts[raiser]["toBb"] == round(acts[raiser]["toBb"], 1)


@pytest.mark.parametrize("case", [_OPEN_AND_CALL, _THREE_BET_AND_CALL])
@pytest.mark.parametrize("raiser_noise, caller_noise", [(0.1, -0.1), (-0.1, 0.1), (0.2, -0.2), (-0.2, 0.2)])
def test_rounding_of_both_after_the_last_frame_is_not_an_action(case, raiser_noise, caller_noise):
    # Фаза 14c, N4: шумят оба — вложенное каждого до двух шагов от уравненного, и разойтись они
    # могут на четыре. Это колл наибольшего, а не колл на другую сумму и не рейз уравнявшего.
    frames, put, folded, raiser, caller = case
    flop = flop_frame(3, put, folded)
    for seat in flop["seats"]:
        seat["stackBb"] -= {raiser: raiser_noise, caller: caller_noise}.get(seat["seatIndex"], 0.0)
    summary = _summary([*frames(), flop])

    assert "line" in summary, summary.get("reason")
    acts = {a["seatIndex"]: a for a in summary["line"] if a["action"] != "fold"}
    assert (acts[raiser]["action"], acts[caller]["action"]) == ("raise", "call")
    size = put[raiser] + max(raiser_noise, caller_noise)
    assert acts[raiser]["toBb"] == acts[caller]["toBb"] == pytest.approx(size, abs=1e-9)


def test_a_limp_and_the_check():
    # Чек виден только тем, что вложенное `BB` не выросло: линия дочитывает его чеком. Герой
    # `SB` первым в банк залимпил — `reach` героя — его частоты лимпа шага 1.
    first = preflop_frame(5, folded={7, 2, 3, 4})
    summary = _summary([first, flop_frame(5, {5: 1.0}, {7, 2, 3, 4})])
    answer = advise(_context(), [first], [])
    assert summary["line"][-2:] == [
        {"seatIndex": 5, "position": "SB", "action": "limp", "toBb": 1.0},
        {"seatIndex": 6, "position": "BB", "action": "check"},
    ]
    ranges = _by_seat(summary)
    assert (ranges[5]["role"], ranges[6]["role"]) == ("limper", "responder")
    assert _close(ranges[5]["reach"], answer["ranges"]["hero"]["byAction"]["limp"])


# --- итога нет: причины -----------------------------------------------------------------------


def test_no_preflop_frames():
    # Review Focus 5: первый кадр раздачи — флоп.
    flop = flop_frame(3, {3: 2.0, 6: 2.0}, {7, 2, 4, 5})
    assert _summary([flop]) == {"street": "preflop", "reason": NO_PREFLOP}


@pytest.mark.parametrize(
    ("hero", "put", "folded", "bets"),
    [
        # `CO` открыл, `BTN` и `BB` заколлировали.
        (3, {3: 2.0, 4: 2.0, 6: 2.0}, {7, 2, 5}, None),
        # `BTN` открыл, блайнды заколлировали, `SB` поставил на флопе, `BB` сфолдил до героя: на
        # кадре героя `BB` вне раздачи, но на флоп пришёл — уравнял вложенное префлопа.
        (4, {4: 2.0, 5: 2.0, 6: 2.0}, {7, 2, 3, 6}, {5: 3.0}),
    ],
    ids=["three_in_hand", "folded_on_the_flop"],
)
def test_three_on_the_flop_is_multiway(hero, put, folded, bets):
    first = preflop_frame(hero, folded={7, 2} if hero == 3 else {7, 2, 3})
    flop = flop_frame(hero, put, folded, bets=bets)
    assert _summary([first, flop]) == {"street": "preflop", "reason": MULTIWAY_FLOP}


def test_a_cold_call_is_off_the_tree():
    # `CO` открыл, `BTN` заколлировал не закрывающим, блайнды сфолдили: колла у `BTN` в дереве
    # нет (D30) — линия вне дерева.
    first = preflop_frame(3, folded={7, 2})
    flop = flop_frame(3, {3: 2.0, 4: 2.0}, {7, 2, 5, 6})
    assert _summary([first, flop]) == {"street": "preflop", "reason": OFF_TREE_LINE}


def test_everyone_folded_to_the_open_is_off_the_tree():
    # Находка ревью Фазы 8: `CO` открыл, все сфолдили, а кадр флопа есть — герой на нём один.
    # Валидатор серию пропускает; путь кончается терминалом `fold`, диапазонов дошедших нет.
    first = preflop_frame(3, folded={7, 2})
    flop = flop_frame(3, {3: 2.0}, {7, 2, 4, 5, 6})
    assert _summary([first, flop]) == {"street": "preflop", "reason": OFF_TREE_LINE}


def test_an_all_in_and_the_call_is_a_pushfold_line():
    # Герой `CO` открыл, `BTN` пошёл олл-ин, герой заколлировал — на флопе решений нет.
    frames = preflop_vs_allin_after_raise()
    flop = flop_frame(3, {3: 40.0, 4: 40.0}, {7, 2, 5, 6})
    assert _summary([*frames, flop]) == {"street": "preflop", "reason": PUSHFOLD_LINE}


def test_a_pushfold_spot_on_the_last_preflop_frame_is_a_pushfold_line():
    # У всех 8 BB: последний кадр префлопа — спот `pushfold`, дерева префлопа у него нет.
    starting = dict.fromkeys(range(2, 8), 8.0)
    first = preflop_frame(3, folded={7, 2}, starting=starting)
    flop = flop_frame(3, {3: 8.0, 6: 8.0}, {7, 2, 4, 5}, starting=starting)
    assert _summary([first, flop]) == {"street": "preflop", "reason": PUSHFOLD_LINE}


# --- coach: итог в файле раздачи --------------------------------------------------------------


@pytest.fixture
def hand(tmp_path):
    path = tmp_path / "hand.json"
    coach.start(str(path), _context())
    return path


def test_a_hand_that_starts_on_the_flop_is_a_refusal_with_a_reason(hand):
    # Review Focus 5: шаг-отказ советников и причина итога, без исключения.
    flop = flop_frame(3, {3: 2.0, 6: 2.0}, {7, 2, 4, 5})
    result = coach.step(str(hand), flop)
    reason = {"street": "preflop", "reason": NO_PREFLOP}
    assert result["advisor"] is None
    assert result["streets"] == {"preflop": reason}
    assert {"key": "preflop.reason", "value": NO_PREFLOP, "display": NO_PREFLOP} in result["why"]
    assert json.loads(hand.read_text(encoding="utf-8"))["streets"] == {"preflop": reason}


def test_the_closing_frame_brings_the_summary_and_undo_takes_it_away(hand):
    # Review Focus 6: итог улицы снимается вместе с кадром, который её закрыл.
    first = preflop_frame(3, folded={7, 2})
    coach.step(str(hand), first)
    before = hand.read_bytes()
    result = coach.step(str(hand), flop_frame(3, {3: 2.0, 6: 2.0}, {7, 2, 4, 5}))
    summary = result["streets"]["preflop"]
    assert summary == _summary([first, flop_frame(3, {3: 2.0, 6: 2.0}, {7, 2, 4, 5})])
    assert any(fact["key"] == "preflop.line" for fact in result["why"])
    assert coach.undo(str(hand)) == {"undone": 2, "steps": 1}
    assert hand.read_bytes() == before
    assert [p.name for p in hand.parent.iterdir()] == [hand.name]


def test_a_damaged_street_name_is_named(hand):
    data = json.loads(hand.read_text(encoding="utf-8"))
    data["streets"] = {"preflp": {}}
    hand.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="^файл раздачи повреждён: streets$"):
        coach.undo(str(hand))
