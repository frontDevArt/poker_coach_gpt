"""Солвер дерева префлопа: сведение к `nash`, эксплуатируемость, ICM, масштаб, головы.

Спека плана 5, §6.8 и §10, инварианты 6, 9–12. Стол фикстур — 6-max `conftest.preflop_frame`.
"""

import copy
import dataclasses

import numpy
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
    pushfold_first_in_node,
)
from poker_engine import allin_matrix, nash, preflop_solver, preflop_tree, pushfold_game
from poker_engine.handstate import context_from_dict, node_from_dict, validate_hand
from poker_engine.preflop_line import read_line
from poker_engine.preflop_solver import action_values, exploitability, reach, solve
from poker_engine.preflop_tree import Decision, build, chip_payoffs, icm_payoffs
from poker_engine.pushfold import icm_eps_usd

FIXTURES = {
    "open": preflop_open,
    "vs_open": preflop_vs_open,
    "vs_limp": preflop_vs_limp,
    "vs_3bet": preflop_vs_3bet,
    "vs_4bet": preflop_vs_4bet,
    "vs_allin_after_raise": preflop_vs_allin_after_raise,
    "sb_limp": lambda: [preflop_frame(6, {5: 1.0}, folded={7, 2, 3, 4})],
}


def _nodes(raws, context=None):
    nodes = [node_from_dict(raw) for raw in raws]
    validate_hand(context_from_dict(context or _context()), nodes)
    return nodes


def _tree(raws, context=None):
    nodes = _nodes(raws, context)
    return build(read_line(nodes), nodes[-1]), nodes[-1]


def _icm_eps(tree, chips, icm):
    """`EPS_CHIP_BB` в долларах по цене фишки участников на исходе первого действия корня."""
    at = tree.nodes[tree.root].actions[0].child
    return nash.EPS_CHIP_BB * icm[at][0].sum() / chips[at][0].sum()


def _games(tree, node, context=None, bounties=False):
    chips = chip_payoffs(tree)
    icm = icm_payoffs(tree, node, context_from_dict(context or _context()), bounties)
    return {"chip": (chips, nash.EPS_CHIP_BB), "icm": (icm, _icm_eps(tree, chips, icm))}


# --- сведение к push/fold -------------------------------------------------------------------


def _heads_up_node(depth):
    def seat(index, invested, hero):
        return {
            "seatIndex": index,
            "name": f"p{index}",
            "stackBb": depth - invested,
            "investedBb": invested,
            "inHand": True,
            "isHero": hero,
            "vpip": 25.0,
            "vpipHands": 60,
        }

    return {
        "street": "preflop",
        "level": 13,
        "blinds": {"sb": 700, "bb": 1400, "ante": 0},
        "heroRank": 90,
        "playersLeft": 496,
        "seats": [seat(1, 0.5, True), seat(2, 1.0, False)],
        "buttonSeat": 1,
        "heroCards": ["Jh", "Th"],
        "board": [],
        "potBb": 1.5,
        "toCallBb": 0.5,
        "raiseToBb": None,
    }


def _chain(tree, at):
    """Узлы отвечающих по фолдам от `at` до терминала."""
    nodes = []
    while isinstance(tree.nodes[at], Decision):
        nodes.append(at)
        at = tree.nodes[at].actions[0].child
    return nodes


def _subgame(node, payout):
    """Подыгра push/fold узла плана 4 для `nash` и её допуск."""
    spot = pushfold_game.read_spot(node)
    assert isinstance(spot, pushfold_game.Spot)
    context = context_from_dict(_context())
    chips = pushfold_game.chip_outcomes(spot)
    outcomes = {
        "chip": chips,
        "icm": pushfold_game.icm_outcomes(spot, node, context, bounties=False),
    }[payout]
    game = nash.Game(outcomes, len(spot.players) - 1)
    return game, nash.EPS_CHIP_BB if payout == "chip" else icm_eps_usd(chips, outcomes)


def _payoffs(tree, node, payout):
    if payout == "chip":
        return chip_payoffs(tree)
    return icm_payoffs(tree, node, context_from_dict(_context()), False)


SUBGAMES = pytest.mark.parametrize(
    "make", [lambda: _heads_up_node(10.0), pushfold_first_in_node], ids=["hu_10bb", "6max"]
)


@SUBGAMES
@pytest.mark.parametrize("payout", ["chip", "icm"])
def test_tree_reduces_to_pushfold(monkeypatch, make, payout):
    nodes = _nodes([make()])
    node = nodes[0]
    game, eps = _subgame(node, payout)

    monkeypatch.setattr(pushfold_game, "PUSHFOLD_MAX_BB", 0.0)
    monkeypatch.setattr(preflop_tree, "COMMIT_SHARE", 0.0)
    tree = build(read_line(nodes), node)
    payoffs = _payoffs(tree, node, payout)
    root = tree.nodes[tree.root]
    assert [a.kind for a in root.actions] == ["fold", "allin"]
    chain = _chain(tree, root.actions[1].child)
    assert len(chain) == game.responders

    # Равновесие дерева — в `nash.exploitability` той же подыгры.
    solution = solve(tree, payoffs, eps)
    assert solution.converged
    push = solution.strategy[tree.root][1]
    call = numpy.array([solution.strategy[at][1] for at in chain])
    assert nash.exploitability(game, push, call) <= 2 * eps

    # И наоборот: равновесие `nash.solve` — в эксплуатируемости дерева.
    equilibrium = nash.solve(game, eps)
    assert equilibrium.converged
    strategy = {tree.root: numpy.stack([1 - equilibrium.push, equilibrium.push])}
    for at, row in zip(chain, equilibrium.call, strict=True):
        strategy[at] = numpy.stack([1 - row, row])
    assert exploitability(tree, payoffs, strategy) <= 2 * eps

    # Модели EV одни и те же: на любой стратегии эксплуатируемости равны, не только на равновесии.
    classes = numpy.arange(169) / 168
    push = 0.2 + 0.6 * classes
    call = numpy.array([(0.7 - 0.5 * classes) * (j + 1) / len(chain) for j in range(len(chain))])
    strategy = {tree.root: numpy.stack([1 - push, push])}
    for at, row in zip(chain, call, strict=True):
        strategy[at] = numpy.stack([1 - row, row])
    assert exploitability(tree, payoffs, strategy) == pytest.approx(
        nash.exploitability(game, push, call), rel=1e-9
    )


@SUBGAMES
@pytest.mark.parametrize("payout", ["chip", "icm"])
def test_responder_gap_counts_every_entry(monkeypatch, make, payout):
    # У корня рейз и олл-ин — две цепочки отвечающих. Открывший всегда олл-ин, все всегда
    # фолд: рейз крадёт столько же, сколько олл-ин, выигрыша у открывшего нет, а выигрыш
    # отвечающих — тот же, что в подыгре push/fold. Масса входа — по обеим цепочкам: по одной
    # цепочке рейза она нулевая, и выигрыш отвечающих пропал бы.
    nodes = _nodes([make()])
    node = nodes[0]
    game, _ = _subgame(node, payout)
    monkeypatch.setattr(pushfold_game, "PUSHFOLD_MAX_BB", 0.0)
    tree = build(read_line(nodes), node)
    payoffs = _payoffs(tree, node, payout)
    assert [a.kind for a in tree.nodes[tree.root].actions] == ["fold", "raise", "allin"]
    strategy = {}
    for at, decision in enumerate(tree.nodes):
        if isinstance(decision, Decision):
            strategy[at] = numpy.zeros((len(decision.actions), 169))
            strategy[at][0] = 1.0
    strategy[tree.root] = numpy.zeros((3, 169))
    strategy[tree.root][2] = 1.0
    expected = nash.exploitability(game, numpy.ones(169), numpy.zeros((game.responders, 169)))
    assert expected > 0
    assert exploitability(tree, payoffs, strategy) == pytest.approx(expected, rel=1e-9)


# --- равновесие -----------------------------------------------------------------------------


@pytest.mark.parametrize("make", FIXTURES.values(), ids=FIXTURES)
@pytest.mark.parametrize("payout", ["chip", "icm"])
def test_equilibrium_is_unexploitable(make, payout):
    tree, node = _tree(make())
    payoffs, eps = _games(tree, node)[payout]
    solution = solve(tree, payoffs, eps)
    assert solution.converged
    assert solution.exploitability <= eps
    assert exploitability(tree, payoffs, solution.strategy) == pytest.approx(
        solution.exploitability, abs=1e-12
    )
    for at, strategy in solution.strategy.items():
        assert strategy.shape == (len(tree.nodes[at].actions), 169)
        assert numpy.allclose(strategy.sum(axis=0), 1.0)


def test_iteration_cap_reports_not_converged():
    tree, node = _tree(preflop_vs_3bet())
    payoffs, eps = _games(tree, node)["chip"]
    solution = solve(tree, payoffs, eps, max_iterations=3)
    assert (solution.iterations, solution.converged) == (3, False)
    assert solution.exploitability > eps
    assert solution.exploitability == pytest.approx(
        exploitability(tree, payoffs, solution.strategy), abs=1e-12
    )


def _winner_take_all():
    return {
        **_context(),
        "payouts": [{"from": 1, "to": 1, "amount": 5000.0}],
        "placesPaid": 1,
    }


@pytest.mark.parametrize("make", [preflop_open, preflop_vs_3bet], ids=["open", "vs_3bet"])
def test_winner_take_all_icm_equals_chips(make):
    context = _winner_take_all()
    tree, node = _tree(make(), context)
    games = _games(tree, node, context)
    by_chip = solve(tree, *games["chip"])
    by_icm = solve(tree, *games["icm"])
    for at in by_chip.strategy:
        assert numpy.abs(by_chip.strategy[at] - by_icm.strategy[at]).max() <= 0.01


def test_ladder_scale():
    tree, node = _tree(preflop_vs_3bet())
    payoffs, eps = _games(tree, node)["icm"]
    tripled = [None if p is None else 3.0 * p for p in payoffs]
    base = solve(tree, payoffs, eps)
    scaled = solve(tree, tripled, 3.0 * eps)
    assert base.iterations == scaled.iterations
    for at in base.strategy:
        assert numpy.allclose(base.strategy[at], scaled.strategy[at], rtol=0, atol=1e-9)
    for combo in (("Ah", "Kd"), ("7c", "2d")):
        plain = action_values(tree, payoffs, base, tree.hero_node, combo)
        triple = action_values(tree, tripled, scaled, tree.hero_node, combo)
        assert triple == pytest.approx([3.0 * v for v in plain], rel=1e-9)


def _priced(raws, price):
    raws = copy.deepcopy(raws)
    for raw in raws:
        for seat in raw["seats"]:
            seat["bountyUsd"] = 1.0
            if seat["seatIndex"] == 4:
                seat["bountyUsd"] = price
    return raws


def test_call_value_grows_with_covered_bounty():
    # Герой `CO` с 40 против олл-ина `BTN` на 40: колл накрывает `BTN`.
    raws = preflop_vs_allin_after_raise()
    tree, node = _tree(_priced(raws, 1.0))
    payoffs = icm_payoffs(tree, node, context_from_dict(_context()), bounties=True)
    solution = solve(tree, payoffs, _icm_eps(tree, chip_payoffs(tree), payoffs))
    kinds = [a.kind for a in tree.nodes[tree.hero_node].actions]
    assert kinds == ["fold", "call"]
    for combo in (("Ah", "Ad"), ("9c", "8c"), ("7c", "2d")):
        calls = []
        for price in (1.0, 2.0, 3.0, 5.0):
            priced, priced_node = _tree(_priced(raws, price))
            values = icm_payoffs(priced, priced_node, context_from_dict(_context()), True)
            calls.append(action_values(priced, values, solution, tree.hero_node, combo)[1])
        assert all(b >= a for a, b in zip(calls, calls[1:]))
        assert calls[-1] > calls[0]


def test_deterministic():
    tree, node = _tree(preflop_vs_limp())
    payoffs, eps = _games(tree, node)["icm"]
    first, second = solve(tree, payoffs, eps), solve(tree, payoffs, eps)
    assert first.iterations == second.iterations
    assert first.exploitability == second.exploitability
    for at in first.strategy:
        assert numpy.array_equal(first.strategy[at], second.strategy[at])


# --- reach и EV действий --------------------------------------------------------------------


def test_reach_is_the_product_along_the_path():
    tree, node = _tree(preflop_vs_4bet())
    payoffs, eps = _games(tree, node)["chip"]
    solution = solve(tree, payoffs, eps)
    me = tree.nodes[tree.hero_node].player
    expected = numpy.ones(169)
    for at, index in tree.path:
        if tree.nodes[at].player == me:
            expected = expected * solution.strategy[at][index]
    assert numpy.array_equal(reach(tree, solution, me), expected)
    # Сфолдивший по линии `HJ` (участник 1): его reach — частота фолда.
    hj = tree.path[1][0]
    assert numpy.array_equal(reach(tree, solution, 1), solution.strategy[hj][0])


def test_limper_reach_starts_from_his_range():
    tree, node = _tree(preflop_vs_limp())
    payoffs, eps = _games(tree, node)["chip"]
    solution = solve(tree, payoffs, eps)
    limper = len(tree.players) - 1
    assert numpy.array_equal(reach(tree, solution, limper), tree.fixed_ranges[limper])


def test_classes_outside_the_limper_range_do_not_count():
    # Классов вне диапазона лимпера нет: их игра на эксплуатируемость не влияет.
    tree, node = _tree(preflop_vs_limp())
    payoffs, eps = _games(tree, node)["chip"]
    solution = solve(tree, payoffs, eps)
    limper = len(tree.players) - 1
    outside = tree.fixed_ranges[limper] == 0
    assert outside.any() and not outside.all()
    spoiled = dict(solution.strategy)
    for at, strategy in solution.strategy.items():
        if tree.nodes[at].player == limper:
            bad = strategy.copy()
            bad[:, outside] = 0.0
            bad[-1, outside] = 1.0  # олл-ин всем мусором
            spoiled[at] = bad
    assert exploitability(tree, payoffs, spoiled) == pytest.approx(
        solution.exploitability, abs=1e-12
    )


def test_limper_gap_is_normalised_by_his_range():
    # Масштаб диапазона лимпера невидим: веса открывшего и `prior` лимпера нормированы. Масштаб
    # 1 / Σ prior·f доводит массу диапазона до 1 — не вероятность, но число то же. Лимпер всегда
    # фолдит изоляцию: самый эксплуатируемый — он, без нормировки его выигрыш упал бы в
    # Σ prior·f раз.
    tree, node = _tree(preflop_vs_limp())
    payoffs, eps = _games(tree, node)["chip"]
    solution = solve(tree, payoffs, eps)
    limper = len(tree.players) - 1
    spoiled = dict(solution.strategy)
    for at, strategy in solution.strategy.items():
        if tree.nodes[at].player == limper:
            spoiled[at] = numpy.zeros_like(strategy)
            spoiled[at][0] = 1.0
    profile = tree.fixed_ranges[limper]
    prior = numpy.array([allin_matrix.combos_of(name) for name in allin_matrix.CLASSES]) / 1326
    unit = dataclasses.replace(tree, fixed_ranges={limper: profile / (prior @ profile)})
    base = exploitability(tree, payoffs, spoiled)
    assert base > 100 * eps
    assert exploitability(unit, payoffs, spoiled) == pytest.approx(base, rel=1e-9)


def test_check_behind_a_limp_is_equity_against_the_limp_range():
    # `BB` против лимпа `SB`: чек — вскрытие без ставок против диапазона профиля лимпера, руками.
    tree, node = _tree(FIXTURES["sb_limp"]())
    payoffs, eps = _games(tree, node)["chip"]
    solution = solve(tree, payoffs, eps)
    check = tree.nodes[tree.root].actions[0]
    assert check.kind == "check"
    showdown = payoffs[check.child]
    limp = tree.fixed_ranges[1]
    combo = ("Ah", "Kd")
    weights = allin_matrix.hand_weights(list(combo)) * limp
    row = allin_matrix.equity_matrix()[allin_matrix.class_index("AKo")]
    equity = (weights * row).sum() / weights.sum()
    expected = equity * showdown[0, 0] + (1 - equity) * showdown[1, 0]
    assert action_values(tree, payoffs, solution, tree.root, combo)[0] == pytest.approx(
        expected, abs=1e-9
    )


def test_opener_values_are_conditional_on_the_3bet():
    # Открывший против 3-бета: EV фолда — его стек после фолда, как бы редко соперник ни 3-бетил.
    tree, node = _tree(preflop_vs_3bet())
    payoffs, eps = _games(tree, node)["chip"]
    solution = solve(tree, payoffs, eps)
    assert tree.nodes[tree.hero_node].player == 0
    fold = tree.nodes[tree.hero_node].actions[0]
    for combo in (("Ah", "Ad"), ("7c", "2d")):
        values = action_values(tree, payoffs, solution, tree.hero_node, combo)
        assert values[0] == pytest.approx(payoffs[fold.child][0, 0], abs=1e-9)


def test_fold_value_is_the_fold_payoff():
    tree, node = _tree(preflop_open())
    payoffs, eps = _games(tree, node)["chip"]
    solution = solve(tree, payoffs, eps)
    fold = tree.nodes[tree.root].actions[0].child
    me = tree.nodes[tree.root].player
    for combo in (("Ah", "Kd"), ("7c", "2d")):
        values = action_values(tree, payoffs, solution, tree.root, combo)
        assert values[0] == pytest.approx(payoffs[fold][0, me], abs=1e-12)
        assert len(values) == len(tree.nodes[tree.root].actions)


def test_responder_values_are_conditional_on_the_open():
    # Герой `CO` отвечает на открытие `UTG`: EV фолда — его стек 40, колл и 3-бет — в пределах
    # выплат своих поддеревьев.
    tree, node = _tree(preflop_vs_open())
    payoffs, eps = _games(tree, node)["chip"]
    solution = solve(tree, payoffs, eps)
    me = tree.nodes[tree.hero_node].player
    assert me != 0
    hero = tree.nodes[tree.hero_node]
    assert [a.kind for a in hero.actions] == ["fold", "call", "raise", "allin"]
    for combo in (("Ah", "Ad"), ("7c", "2d")):
        values = action_values(tree, payoffs, solution, tree.hero_node, combo)
        assert values[0] == pytest.approx(40.0, abs=1e-9)
        showdown = payoffs[hero.actions[1].child]
        assert showdown[:, me].min() <= values[1] <= showdown[:, me].max()


# По фишкам фолд героя `CO` — его стек: отвечающий не вложил ничего, открывший — 2.0.
@pytest.mark.parametrize(
    ("make", "fold"),
    [(preflop_vs_open, 40.0), (preflop_vs_3bet, 38.0)],
    ids=["responder", "opener"],
)
def test_unreached_node_takes_the_whole_range(make, fold):
    # Стратегия соперника до узла героя не доходит: EV — против всего диапазона, а не 0/0.
    tree, node = _tree(make())
    payoffs, eps = _games(tree, node)["chip"]
    solution = solve(tree, payoffs, eps)
    strategy = dict(solution.strategy)
    for at, index in tree.path:
        if index and tree.nodes[at].player != tree.nodes[tree.hero_node].player:
            never = numpy.zeros_like(strategy[at])
            never[0] = 1.0  # сыгранное действие соперника — с частотой 0
            strategy[at] = never
    blind = preflop_solver.Solution(strategy, solution.exploitability, solution.iterations, True)
    values = action_values(tree, payoffs, blind, tree.hero_node, ("Ah", "Kd"))
    assert values[0] == pytest.approx(fold, abs=1e-9)
    assert all(numpy.isfinite(values))


def test_opener_values_against_a_shove():
    # Открывший против олл-ина: EV колла — между проигрышем и выигрышем вскрытия.
    tree, node = _tree(preflop_vs_allin_after_raise())
    payoffs, eps = _games(tree, node)["chip"]
    solution = solve(tree, payoffs, eps)
    me = tree.nodes[tree.hero_node].player
    fold, call = action_values(tree, payoffs, solution, tree.hero_node, ("Ah", "Ad"))
    fold_terminal = tree.nodes[tree.hero_node].actions[0].child
    assert fold == pytest.approx(payoffs[fold_terminal][0, me], abs=1e-12)
    showdown = payoffs[tree.nodes[tree.hero_node].actions[1].child]
    low, high = sorted(showdown[:, me])
    assert low < call < high
    assert call > fold


# --- гарды ----------------------------------------------------------------------------------


def test_guards():
    tree, node = _tree(preflop_open())
    payoffs = chip_payoffs(tree)
    with pytest.raises(ValueError, match="^допуск равновесия должен быть > 0, получено 0"):
        solve(tree, payoffs, 0.0)
    with pytest.raises(ValueError, match="^предел итераций должен быть > 0, получено 0"):
        solve(tree, payoffs, 1e-3, max_iterations=0)


def test_module_constants():
    assert preflop_solver.MAX_ITERATIONS == 3000
