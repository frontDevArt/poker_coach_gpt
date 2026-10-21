"""Советник `preflop`: форма ответа, пометки, линия героя, реестр.

Спека плана 5, §5.4, §6.9, §7–§9 и §10, инварианты 4, 13–16; Review Focus 4. Стол фикстур —
6-max `conftest.preflop_frame`, у всех 40 BB до раздачи.
"""

import copy

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
    pushfold_first_in_node_8max,
    pushfold_first_in_node_9max,
)
from poker_engine import (
    advice,
    allin_matrix,
    nash,
    preflop_advisor,
    preflop_solver,
    profiles,
    pushfold,
)
from poker_engine.handstate import context_from_dict, node_from_dict, validate_hand
from poker_engine.preflop_line import MULTIWAY, PUSHFOLD_SPOT, read_line
from poker_engine.preflop_tree import LIMP_RERAISE, build, chip_payoffs, icm_payoffs

SPOTS = {
    "open": preflop_open,
    "vs_open": preflop_vs_open,
    "vs_3bet": preflop_vs_3bet,
    "vs_4bet": preflop_vs_4bet,
    "vs_allin_after_raise": preflop_vs_allin_after_raise,
    "vs_limp": preflop_vs_limp,
    # `BB` против лимпа `SB`: вместо фолда — чек.
    "vs_limp_bb": lambda: [preflop_frame(6, {5: 1.0}, folded={7, 2, 3, 4})],
}

TREE_FLAGS = (
    "no_overcall",
    "no_cold_call",
    "fold_as_walk",
    "fixed_sizing",
    "postflop_checkdown",
    "deep_stack",
    "no_hero_limp",
    "limper_range_profile",
)

ROLES = {"opener", "3bettor", "4bettor", "limper", "shover", "responder"}


def _advise(raws, context=None, history=()):
    return advice.advise(context or _context(), copy.deepcopy(raws), list(history))


def _nodes(raws, context=None):
    nodes = [node_from_dict(raw) for raw in raws]
    validate_hand(context_from_dict(context or _context()), nodes)
    return nodes


def _tree(raws, context=None):
    nodes = _nodes(raws, context)
    return build(read_line(nodes), nodes[-1])


def _icm_eps(tree, chips, icm):
    """`EPS_CHIP_BB` в долларах по цене фишки участников на исходе первого действия корня."""
    at = tree.nodes[tree.root].actions[0].child
    return nash.EPS_CHIP_BB * icm[at][0].sum() / chips[at][0].sum()


def _priced(raws):
    raws = copy.deepcopy(raws)
    for raw in raws:
        for seat in raw["seats"]:
            seat["bountyUsd"] = 10.0
    return raws


@pytest.fixture(scope="module")
def answers():
    """Ответы на все споты §4, посчитанные один раз на модуль: тесты их только читают."""
    return {name: _advise(make()) for name, make in SPOTS.items()}


# --- реестр ---------------------------------------------------------------------------------


def test_the_module_is_an_advisor():
    assert preflop_advisor.name == "preflop"
    assert advice.ADVISORS == (pushfold, preflop_advisor)


@pytest.mark.parametrize(
    "make",
    [
        pushfold_first_in_node,
        pushfold_first_in_node_8max,
        pushfold_first_in_node_9max,
        pushfold_facing_allin_node,
    ],
    ids=["first_in", "first_in_8max", "first_in_9max", "facing_allin"],
)
def test_pushfold_answers_unchanged(make):
    # Инварианты 15 и 16: узлы плана 4 берёт `pushfold` с тем же ответом, `preflop` их
    # отвергает своим текстом.
    raw = make()
    nodes = _nodes([raw])
    context = context_from_dict(_context())
    assert preflop_advisor.applies(context, nodes) == PUSHFOLD_SPOT
    answer = _advise([raw])
    assert answer["advisor"] == "pushfold"
    assert answer == pushfold.advise(context, nodes, [])


def test_refusals_are_the_line_and_tree_texts():
    # Линия: колд-колл открытия — мультипот. Дерево: лимпер ответил на изоляцию рейзом.
    multiway = [preflop_frame(4, {7: 2.0, 2: 2.0}, folded={3})]
    limp_raise = [
        preflop_frame(4, {7: 1.0}, folded={2, 3}),
        preflop_frame(4, {7: 12.0, 4: 4.0}, folded={2, 3, 5, 6}),
    ]
    for raws, reason in ((multiway, MULTIWAY), (limp_raise, LIMP_RERAISE)):
        answer = _advise(raws)
        assert answer["advisor"] is None
        assert answer["notApplicable"][-1] == {"advisor": "preflop", "reason": reason}


# --- форма ответа ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SPOTS)
def test_answer_shape(answers, name):
    answer = answers[name]
    tree = _tree(SPOTS[name]())
    hero = tree.nodes[tree.hero_node]
    kinds = [a.kind for a in hero.actions]

    assert answer["advisor"] == "preflop"
    assert answer["spot"] == name.removesuffix("_bb")
    keys = {
        "advisor", "spot", "action", "heroHand", "effectiveStackBb", "line", "actions",
        "ranges", "nash", "flags",
    }
    if answer["action"] not in ("fold", "check"):
        keys.add("sizeBb")
    assert set(answer) == keys

    assert [entry["action"] for entry in answer["actions"]] == kinds
    for entry, action in zip(answer["actions"], hero.actions, strict=True):
        if action.kind in ("fold", "check"):
            assert set(entry) == {"action", "evUsd", "evBb"}
        else:
            assert set(entry) == {"action", "toBb", "evUsd", "evBb"}
            assert entry["toBb"] == action.to_bb
    chosen = kinds.index(answer["action"])
    if "sizeBb" in answer:
        assert answer["sizeBb"] == hero.actions[chosen].to_bb

    assert answer["heroHand"] == "JTs"
    by_action = answer["ranges"]["hero"]["byAction"]
    assert list(by_action) == kinds
    for classes in by_action.values():
        for name_, freq in classes.items():
            assert name_ in allin_matrix.CLASSES
            assert 0 < freq <= 1
            assert round(freq * 100) == pytest.approx(freq * 100, abs=1e-9)
    hand_freq = answer["ranges"]["hero"]["handFreq"]
    assert list(hand_freq) == kinds
    assert sum(hand_freq.values()) == pytest.approx(1.0)

    for opponent in answer["ranges"]["opponents"]:
        assert set(opponent) == {
            "seatIndex", "position", "stackBb", "role", "reach", "reachPct",
        }
        assert opponent["role"] in ROLES
        assert 0 < opponent["reachPct"] <= 1
    assert set(answer["nash"]) == {"icm", "chip"}
    assert set(answer["nash"]["icm"]) == {"exploitabilityUsd", "iterations"}
    assert set(answer["nash"]["chip"]) == {"exploitabilityBb", "iterations"}


@pytest.mark.parametrize("name", SPOTS)
def test_action_is_the_best_ev(answers, name):
    # Наибольший `evUsd`, равенство — к пассивному (раньше в списке действий узла).
    entries = answers[name]["actions"]
    best = max(entry["evUsd"] for entry in entries)
    first = next(entry for entry in entries if entry["evUsd"] == best)
    assert answers[name]["action"] == first["action"]


def test_a_tie_goes_to_the_passive_action(monkeypatch):
    # Равные EV всех действий: совет — первое в списке узла, фолд.
    monkeypatch.setattr(
        preflop_advisor,
        "action_values",
        lambda tree, *args: [1.0] * len(tree.nodes[tree.hero_node].actions),
    )
    answer = _advise(preflop_vs_open())
    assert answer["action"] == "fold"
    assert "sizeBb" not in answer


@pytest.mark.parametrize("name", SPOTS)
def test_named_size_is_in_the_tree(name):
    # Анти-цель спеки §3: названный размер — размер одного из действий узла героя, с EV.
    raws = SPOTS[name]()
    for cards in (["Ah", "Ad"], ["Ks", "Qs"], ["7c", "2d"]):
        for raw in raws:
            raw["heroCards"] = cards
        answer = _advise(raws)
        tree = _tree(raws)
        sizes = [a.to_bb for a in tree.nodes[tree.hero_node].actions]
        if "sizeBb" in answer:
            assert answer["sizeBb"] in sizes


def test_fold_is_the_stack_and_the_line_is_read(answers):
    # `CO` открывает: фолд — стек 40 до конца раздачи, линия — два фолда до героя.
    answer = answers["open"]
    assert answer["actions"][0] == {
        "action": "fold",
        "evUsd": answer["actions"][0]["evUsd"],
        "evBb": pytest.approx(40.0, abs=1e-9),
    }
    assert answer["effectiveStackBb"] == 40.0
    # Герой глубже всех: эффективный стек — наибольший из чужих, не свой.
    deeper = _advise([preflop_frame(3, {7: 2.0}, folded={2}, starting={3: 60.0})])
    assert deeper["effectiveStackBb"] == 40.0
    assert answer["line"] == [
        {"seatIndex": 7, "position": "UTG", "action": "fold"},
        {"seatIndex": 2, "position": "HJ", "action": "fold"},
    ]
    line = answers["vs_3bet"]["line"]
    assert line == [
        {"seatIndex": 7, "position": "UTG", "action": "fold"},
        {"seatIndex": 2, "position": "HJ", "action": "fold"},
        {"seatIndex": 3, "position": "CO", "action": "raise", "toBb": 2.0},
        {"seatIndex": 4, "position": "BTN", "action": "raise", "toBb": 7.0},
        {"seatIndex": 5, "position": "SB", "action": "fold"},
        {"seatIndex": 6, "position": "BB", "action": "fold"},
    ]


@pytest.mark.parametrize(
    ("name", "roles"),
    [
        ("open", {4: "responder", 5: "responder", 6: "responder"}),
        ("vs_open", {7: "opener", 4: "responder", 5: "responder", 6: "responder"}),
        ("vs_3bet", {4: "3bettor"}),
        ("vs_4bet", {7: "4bettor"}),
        ("vs_allin_after_raise", {4: "shover"}),
        ("vs_limp", {7: "limper", 5: "responder", 6: "responder"}),
        ("vs_limp_bb", {5: "limper"}),
    ],
)
def test_opponents_are_the_seats_still_in_hand(answers, name, roles):
    # Сфолдившие по линии в соперниках не числятся; порядок — порядок хода дерева.
    opponents = answers[name]["ranges"]["opponents"]
    assert {o["seatIndex"]: o["role"] for o in opponents} == roles
    tree = _tree(SPOTS[name]())
    order = [p.seat_index for p in tree.players]
    assert [o["seatIndex"] for o in opponents] == sorted(
        (o["seatIndex"] for o in opponents), key=order.index
    )
    for opponent in opponents:
        seat = next(p for p in tree.players if p.seat_index == opponent["seatIndex"])
        assert opponent["stackBb"] == seat.stack_bb
        if opponent["role"] == "responder":
            # Ещё не ходил: дошёл весь диапазон.
            assert opponent["reach"] == {name_: 1.0 for name_ in allin_matrix.CLASSES}
            assert opponent["reachPct"] == pytest.approx(1.0)


def test_opponent_reach_is_the_equilibrium_line():
    # `UTG` открыл: его reach — частота открытия ICM-равновесия, с шагом 0.01.
    raws = preflop_vs_open()
    answer = _advise(raws)
    solved = preflop_advisor._solve(context_from_dict(_context()), _nodes(raws))
    expected = preflop_solver.reach(solved.tree, solved.by_icm, 0)
    opener = answer["ranges"]["opponents"][0]
    assert opener["role"] == "opener"
    for at, name in enumerate(allin_matrix.CLASSES):
        assert opener["reach"].get(name, 0.0) == pytest.approx(expected[at], abs=0.005 + 1e-12)
    assert opener["reachPct"] == pytest.approx(nash.range_share(expected), abs=1e-12)


def test_hero_range_is_the_icm_strategy_on_his_node():
    raws = preflop_vs_open()
    answer = _advise(raws)
    solved = preflop_advisor._solve(context_from_dict(_context()), _nodes(raws))
    strategy = solved.by_icm.strategy[solved.tree.hero_node]
    index = allin_matrix.class_index("JTs")
    by_action = answer["ranges"]["hero"]["byAction"]
    for row, kind in zip(strategy, by_action, strict=True):
        assert answer["ranges"]["hero"]["handFreq"][kind] == pytest.approx(row[index], abs=1e-12)
        for at, name in enumerate(allin_matrix.CLASSES):
            assert by_action[kind].get(name, 0.0) == pytest.approx(row[at], abs=0.005 + 1e-12)


def test_ev_is_the_hero_combo_against_both_equilibria():
    raws = preflop_vs_3bet()
    answer = _advise(raws)
    solved = preflop_advisor._solve(context_from_dict(_context()), _nodes(raws))
    tree, combo = solved.tree, ("Jh", "Th")
    usd = preflop_solver.action_values(tree, solved.icm, solved.by_icm, tree.hero_node, combo)
    bb = preflop_solver.action_values(tree, solved.chips, solved.by_chip, tree.hero_node, combo)
    assert [e["evUsd"] for e in answer["actions"]] == usd
    assert [e["evBb"] for e in answer["actions"]] == bb
    assert answer["nash"]["icm"]["iterations"] == solved.by_icm.iterations
    assert answer["nash"]["chip"]["exploitabilityBb"] == solved.by_chip.exploitability


def test_the_answer_is_deterministic():
    raws = preflop_vs_limp()
    assert _advise(raws) == _advise(raws)


# --- линия героя между шагами ---------------------------------------------------------------


def test_steps_are_consistent(answers):
    # Инвариант 14: герой открылся размером совета первого кадра и получил 3-бет. Его reach в
    # дереве второго шага — частота рейза ответа первого шага: корень, стеки и размеры те же.
    # 3-бет `BTN` — размером правила 3 × 2.0: сыгранный размер иной поменял бы дерево.
    first = answers["open"]
    raise_ = next(e for e in first["actions"] if e["action"] == "raise")
    assert raise_["toBb"] == 2.0
    raws = [
        preflop_frame(3, folded={7, 2}),
        preflop_frame(3, {3: 2.0, 4: 3 * 2.0}, folded={7, 2, 5, 6}),
    ]
    solved = preflop_advisor._solve(context_from_dict(_context()), _nodes(raws))
    tree = solved.tree
    opened = _tree(preflop_open())
    assert [p.seat_index for p in tree.players] == [p.seat_index for p in opened.players]
    me = tree.nodes[tree.hero_node].player
    hero_reach = preflop_solver.reach(tree, solved.by_icm, me)
    advised = first["ranges"]["hero"]["byAction"]["raise"]
    for at, name in enumerate(allin_matrix.CLASSES):
        assert hero_reach[at] == pytest.approx(advised.get(name, 0.0), abs=0.005 + 1e-12)


def _vs_3bet_after_open(size):
    return [
        preflop_frame(3, folded={7, 2}),
        preflop_frame(3, {3: size, 4: 7.0}, folded={7, 2, 5, 6}),
    ]


@pytest.mark.parametrize(
    ("history", "size", "deviates"),
    [
        ([{"advisor": "preflop", "action": "raise", "sizeBb": 2.0}], 2.0, False),
        # Размер в пределах шага округления — та же линия.
        ([{"advisor": "preflop", "action": "raise", "sizeBb": 2.0}], 2.1, False),
        ([{"advisor": "preflop", "action": "raise", "sizeBb": 2.0}], 2.5, True),
        ([{"advisor": "preflop", "action": "fold"}], 2.0, True),
        ([{"advisor": "preflop", "action": "allin", "sizeBb": 40.0}], 2.0, True),
        # Последний ответ `preflop` — тот, что сверяется.
        (
            [
                {"advisor": "preflop", "action": "fold"},
                {"advisor": "preflop", "action": "raise", "sizeBb": 2.0},
            ],
            2.0,
            False,
        ),
        # Ответ `pushfold` — тоже совет: герой открыл рейзом вместо фолда.
        ([{"advisor": "pushfold", "action": "fold"}], 2.0, True),
        # Отказ — не ответ: сверяется ответ советника до него.
        (
            [
                {"advisor": "preflop", "action": "raise", "sizeBb": 2.0},
                {"advisor": None, "notApplicable": []},
            ],
            2.0,
            False,
        ),
        ([{"advisor": None, "notApplicable": []}], 2.0, False),
        ([], 2.0, False),
        # История — вход пользователя: ответ без `sizeBb` сверяется только по действию.
        ([{"advisor": "preflop", "action": "raise"}], 2.0, False),
    ],
    ids=[
        "same", "within_step", "other_size", "fold", "allin", "last", "pushfold",
        "refusal_skipped", "only_refusal", "none", "no_size",
    ],
)
def test_line_deviates(history, size, deviates):
    answer = _advise(_vs_3bet_after_open(size), history=history)
    assert answer["advisor"] == "preflop"
    assert ("line_deviates" in answer["flags"]) == deviates


def test_pushfold_advice_the_hero_did_not_follow():
    # У всех 10 BB: `CO` первым в банк — спот `pushfold`. Герой открыл до 2.0 вместо его
    # совета, `BTN` пошёл олл-ин — узел `preflop` с пометкой.
    starting = dict.fromkeys(range(2, 8), 10.0)
    first = [preflop_frame(3, folded={7, 2}, starting=starting)]
    advised = _advise(first)
    assert advised["advisor"] == "pushfold"
    assert advised["action"] in ("allin", "fold")
    second = [
        *first,
        preflop_frame(3, {3: 2.0, 4: 10.0}, folded={7, 2, 5, 6}, starting=starting),
    ]
    answer = _advise(second, history=[advised])
    assert answer["spot"] == "vs_allin_after_raise"
    assert "line_deviates" in answer["flags"]


@pytest.mark.parametrize(("four_bet", "deviates"), [(13.2, False), (16.0, True)])
def test_line_deviates_on_the_last_hero_act(four_bet, deviates):
    # Два действия героя: открытие 2.0 и 4-бет против 3-бета 6.0. Совет последнего шага — 4-бет
    # до 13.2 (2.2 × 6.0) — сверяется с 4-бетом, а не с открытием.
    raws = [
        preflop_frame(3, folded={7, 2}),
        preflop_frame(3, {3: 2.0, 4: 6.0}, folded={7, 2, 5, 6}),
        preflop_frame(3, {3: four_bet, 4: 40.0}, folded={7, 2, 5, 6}),
    ]
    history = [
        {"advisor": "preflop", "action": "raise", "sizeBb": 2.0},
        {"advisor": "preflop", "action": "raise", "sizeBb": 13.2},
    ]
    answer = _advise(raws, history=history)
    assert answer["spot"] == "vs_allin_after_raise"
    assert ("line_deviates" in answer["flags"]) == deviates


def test_no_deviation_without_a_hero_act():
    # Первый кадр: у героя ещё нет действия, сверять нечего.
    history = [{"advisor": "preflop", "action": "fold"}]
    assert "line_deviates" not in _advise(preflop_open(), history=history)["flags"]


# --- пометки --------------------------------------------------------------------------------


def test_mh_bias_is_always_first(answers):
    # Malmuth-Harville применяется всегда: пары «не ставится» у этой пометки нет.
    assert all(answer["flags"][0] == "mh_bias" for answer in answers.values())


def test_context_flags_only_when_true(answers):
    base = answers["vs_open"]["flags"]
    assert {"field_homogeneous", "ladder_incomplete", "late_reg_open"} <= set(base)
    assert "bubble_protection" not in base

    raws = preflop_vs_open()
    for raw in raws:
        raw.update(playersLeft=6, heroRank=3)
    assert "field_homogeneous" not in _advise(raws)["flags"]

    for key, value, flag, present in (
        ("bubbleRefundUsd", 50.0, "bubble_protection", True),
        ("placesPaid", 6, "ladder_incomplete", False),
        ("lateRegOpen", False, "late_reg_open", False),
    ):
        context = {**_context(), key: value}
        assert (flag in _advise(preflop_vs_open(), context)["flags"]) == present, key


def test_classic_has_no_bounty(answers):
    # Инвариант 13: без ценников нет ни `bountyUsd`, ни `pko`.
    for answer in answers.values():
        assert "bountyUsd" not in answer
        assert "pko" not in answer["flags"]


def test_bounty_is_the_head_part_of_the_margin():
    raws = _priced(preflop_vs_allin_after_raise())
    answer = _advise(raws)
    assert "pko" in answer["flags"]
    context = context_from_dict(_context())
    solved = preflop_advisor._solve(context, _nodes(raws))
    tree, combo = solved.tree, ("Jh", "Th")
    plain = icm_payoffs(tree, _nodes(raws)[-1], context, bounties=False)
    without = preflop_solver.action_values(tree, plain, solved.by_icm, tree.hero_node, combo)
    usd = [e["evUsd"] for e in answer["actions"]]
    best = [e["action"] for e in answer["actions"]].index(answer["action"])
    assert answer["bountyUsd"] == pytest.approx(
        (usd[best] - usd[0]) - (without[best] - without[0]), abs=1e-12
    )
    # Колл олл-ина `BTN` на 40 накрывает его: с головой колл дороже.
    assert usd[1] > without[1]


def _flag_cases():
    deep = {seat: 60.0 for seat in range(2, 8)}
    return {
        **{name: make() for name, make in SPOTS.items()},
        "deep_open": [preflop_frame(3, folded={7, 2}, starting=deep)],
        "sb_open": [preflop_frame(5, folded={7, 2, 3, 4})],
        "sb_vs_bb_short": [preflop_frame(5, folded={7, 2, 3, 4}, starting={5: 14.0, 6: 14.0})],
        # `UTG` открыл до 5.0, у остальных по 5 BB: любой колл — на все, рейза правила нет.
        "short_vs_open": [
            preflop_frame(3, {7: 5.0}, folded={2}, starting=dict.fromkeys(range(2, 7), 5.0))
        ],
    }


def test_tree_flags_pass_through():
    # Пометки дерева — в ответе ровно тогда, когда они в дереве; каждая встречена и с, и без.
    seen = {flag: set() for flag in TREE_FLAGS}
    for name, raws in _flag_cases().items():
        answer = _advise(raws)
        tree = _tree(raws)
        for flag in TREE_FLAGS:
            assert (flag in answer["flags"]) == (flag in tree.flags), (name, flag)
            seen[flag].add(flag in tree.flags)
    assert all(states == {True, False} for states in seen.values()), seen


def test_limper_without_badge():
    # Review Focus 4: бейджа нет — диапазон `DEFAULT_VPIP`, пометка, без отказа.
    raws = preflop_vs_limp()
    for raw in raws:
        for seat in raw["seats"]:
            if seat["seatIndex"] == 7:
                seat.update(vpip=None, vpipHands=None)
    answer = _advise(raws)
    assert answer["advisor"] == "preflop"
    assert "limper_range_profile" in answer["flags"]
    combos, used_default = profiles.range_for_vpip(None, None)
    assert used_default
    profile = {allin_matrix.class_of([combo[:2], combo[2:]]) for combo in combos}
    limper = next(o for o in answer["ranges"]["opponents"] if o["role"] == "limper")
    assert set(limper["reach"]) <= profile


def test_close_spot_only_when_the_best_two_are_within_eps(answers, monkeypatch):
    def close(raws, answer):
        tree = _tree(raws)
        node = _nodes(raws)[-1]
        chips = chip_payoffs(tree)
        icm = icm_payoffs(tree, node, context_from_dict(_context()), bounties=False)
        top = sorted((e["evUsd"] for e in answer["actions"]), reverse=True)
        return top[0] - top[1] <= _icm_eps(tree, chips, icm)

    for name, answer in answers.items():
        assert ("close_spot" in answer["flags"]) == close(SPOTS[name](), answer), name
    assert not any("close_spot" in answer["flags"] for answer in answers.values())
    # Допуск в сто фишек: любые два действия «почти равны».
    monkeypatch.setattr(nash, "EPS_CHIP_BB", 100.0)
    raws = preflop_open()
    answer = _advise(raws)
    assert close(raws, answer)
    assert "close_spot" in answer["flags"]


def test_nash_not_converged_only_when_a_solve_stops_short(answers, monkeypatch):
    assert "nash_not_converged" not in answers["vs_open"]["flags"]
    monkeypatch.setattr(preflop_solver, "MAX_ITERATIONS", 1)
    answer = _advise(preflop_vs_open())
    assert "nash_not_converged" in answer["flags"]
    assert answer["nash"]["icm"]["iterations"] == answer["nash"]["chip"]["iterations"] == 1


@pytest.mark.parametrize("short", ["icm", "chip"])
def test_nash_not_converged_when_either_solve_stops_short(short, monkeypatch):
    real = preflop_solver.solve

    def solve_once_for(tree, payoffs, eps, max_iterations):
        is_chip = eps == nash.EPS_CHIP_BB
        return real(tree, payoffs, eps, 1 if is_chip == (short == "chip") else max_iterations)

    monkeypatch.setattr(preflop_solver, "solve", solve_once_for)
    answer = _advise(preflop_vs_open())
    other = "chip" if short == "icm" else "icm"
    assert answer["nash"][short]["iterations"] == 1
    assert answer["nash"][other]["iterations"] > 1
    assert "nash_not_converged" in answer["flags"]


def test_hero_range_for_the_next_street_is_the_chosen_action(answers):
    # §7.2: после хода героя его диапазон — `byAction[action]`; ключ есть у каждого действия.
    for answer in answers.values():
        assert answer["action"] in answer["ranges"]["hero"]["byAction"]
