"""Солвер push/fold: равновесие fictitious play, EV, эксплуатируемость (план 4, Задача 3).

Инварианты спеки плана 4, §9 п.5–7 и 9, на синтетических играх: исходы по фишкам HU и стола
с тремя отвечающими, исходы по ICM фикстур `conftest.py`.
"""

from __future__ import annotations

import dataclasses

import numpy
import pytest

from conftest import (
    _context,
    heads_up_spot,
    pushfold_facing_allin_node,
    pushfold_first_in_node,
)
from poker_engine.allin_matrix import (
    CLASSES,
    class_index,
    equity_matrix,
    hand_weights,
    weight_matrix,
)
from poker_engine.handstate import Seat, context_from_dict, node_from_dict
from poker_engine.nash import (
    EPS_CHIP_BB,
    Game,
    exploitability,
    opener_ev,
    range_share,
    responder_ev,
    solve,
)
from poker_engine.pushfold_game import Outcomes, Spot, chip_outcomes, icm_outcomes, read_spot


def _seat(index: int, stack: float, invested: float = 0.0) -> Seat:
    return Seat(
        seat_index=index,
        name=f"p{index}",
        stack_bb=stack,
        invested_bb=invested,
        in_hand=True,
        is_hero=False,
        vpip=None,
        vpip_hands=None,
        bounty_usd=None,
    )


def _three_responders() -> Game:
    """`CO` 10 открывает, за ним `BTN` 12, `SB` 8 (+0.5), `BB` 15 (+1); анте 0.4 в банке."""
    players = [_seat(3, 10.0), _seat(4, 12.0), _seat(5, 7.5, 0.5), _seat(6, 14.0, 1.0)]
    spot = Spot(
        kind="first_in",
        players=players,
        hero_at=0,
        bb_at=3,
        totals=[10.0, 12.0, 8.0, 15.0],
        dead_bb=0.4,
        bystanders=[],
    )
    return Game(chip_outcomes(spot), 3)


def _hu(depth: float = 10.0) -> Game:
    return Game(chip_outcomes(heads_up_spot(depth)), 1)


def _icm_game(make, context_raw: dict) -> Game:
    raw = make()
    node = node_from_dict(raw)
    spot = read_spot(node)
    assert isinstance(spot, Spot), spot
    outcomes = icm_outcomes(spot, node, context_from_dict(context_raw), bounties=False)
    return Game(outcomes, len(spot.players) - 1)


def _chip_game(make) -> Game:
    spot = read_spot(node_from_dict(make()))
    assert isinstance(spot, Spot), spot
    return Game(chip_outcomes(spot), len(spot.players) - 1)


def _played(equilibrium) -> list[set[str]]:
    rows = [equilibrium.push, *equilibrium.call]
    return [{CLASSES[at] for at in range(len(CLASSES)) if row[at] > 0.5} for row in rows]


# --- равновесие ------------------------------------------------------------------------------


@pytest.mark.parametrize("make", [_hu, _three_responders])
def test_the_equilibrium_is_eps_exploitable(make):
    # Инвариант 5: ни один игрок не выигрывает больше eps, отклонившись.
    game = make()
    equilibrium = solve(game, EPS_CHIP_BB)
    assert equilibrium.converged
    assert equilibrium.exploitability <= EPS_CHIP_BB
    assert exploitability(game, equilibrium.push, equilibrium.call) == pytest.approx(
        equilibrium.exploitability, abs=1e-12
    )
    assert equilibrium.push.shape == (169,)
    assert equilibrium.call.shape == (game.responders, 169)


def test_winner_take_all_removes_the_icm_correction():
    # Инвариант 6: при одном призе ICM-эквити пропорционально фишкам, равновесие то же.
    context_raw = _context()
    context_raw.update(payouts=[{"from": 1, "to": 1, "amount": 1000.0}], placesPaid=1)
    icm = _icm_game(pushfold_first_in_node, context_raw)
    chips = _chip_game(pushfold_first_in_node)
    scale = icm.outcomes.steal[0] / chips.outcomes.steal[0]
    assert icm.outcomes.lose[0] == pytest.approx(
        [scale * x for x in chips.outcomes.lose[0]], rel=1e-9
    )
    by_icm = solve(icm, EPS_CHIP_BB * scale)
    by_chips = solve(chips, EPS_CHIP_BB)
    assert by_icm.converged and by_chips.converged
    assert _played(by_icm) == _played(by_chips)


def test_scaling_the_ladder_keeps_strategies_and_scales_ev():
    # Инвариант 7: лесенка × 3 — те же частоты, EV × 3.
    tripled = _context()
    for interval in tripled["payouts"]:
        interval["amount"] *= 3
    base = _icm_game(pushfold_facing_allin_node, _context())
    big = _icm_game(pushfold_facing_allin_node, tripled)
    assert big.outcomes.steal == pytest.approx([3 * x for x in base.outcomes.steal], rel=1e-12)
    pool = 1090.51 + 840.37 + 648.01 + 3 * 400.0
    one = solve(base, 1e-6 * pool)
    three = solve(big, 3e-6 * pool)
    assert one.iterations == three.iterations
    numpy.testing.assert_allclose(three.push, one.push, rtol=0, atol=1e-12)
    numpy.testing.assert_allclose(three.call, one.call, rtol=0, atol=1e-12)
    hand = class_index("JTs")
    weights, equity = weight_matrix()[hand], equity_matrix()[hand]
    push_one, fold_one = opener_ev(base, one.call, weights, equity)
    push_three, fold_three = opener_ev(big, three.call, weights, equity)
    assert push_three == pytest.approx(3 * push_one, rel=1e-9)
    assert fold_three == pytest.approx(3 * fold_one, rel=1e-9)


def test_ties_break_to_fold():
    # Все исходы платят одно и то же: пуш и фолд равны, лучший ответ — фолд.
    flat = Outcomes(steal=[1.0, 1.0], walk=[1.0, 1.0], win=[[1.0, 1.0]], lose=[[1.0, 1.0]])
    equilibrium = solve(Game(flat, 1), EPS_CHIP_BB)
    assert equilibrium.converged
    # Стартовое «всё 0.5» здесь тоже равновесие: сходимость на нулевом шаге не проверяется,
    # иначе солвер вернул бы его, не сделав ни шага к фолду (решение 7 Фазы 3).
    assert equilibrium.iterations > 0
    assert equilibrium.push.max() < 0.5 and equilibrium.call.max() < 0.5
    # После n шагов с лучшим ответом 0 и шагом 2/(t + 3) средняя частота
    # 0.5 · Π (t + 1)/(t + 3) = 1 / ((n + 1)(n + 2)).
    n = equilibrium.iterations
    expected = 1.0 / ((n + 1) * (n + 2))
    numpy.testing.assert_allclose(equilibrium.push, expected, rtol=1e-12)
    numpy.testing.assert_allclose(equilibrium.call, expected, rtol=1e-12)


def test_not_converged_is_reported():
    game = _hu()
    equilibrium = solve(game, EPS_CHIP_BB, max_iterations=1)
    assert equilibrium.converged is False
    assert equilibrium.iterations == 1
    actual = exploitability(game, equilibrium.push, equilibrium.call)
    assert equilibrium.exploitability == pytest.approx(actual, abs=1e-12)
    assert actual > EPS_CHIP_BB


# --- EV на бумаге ----------------------------------------------------------------------------


def test_opener_ev_against_always_fold_and_always_call():
    game = _hu()
    o = game.outcomes
    hand = class_index("A5s")
    weights, equity = weight_matrix()[hand], equity_matrix()[hand]
    push, fold = opener_ev(game, numpy.zeros((1, 169)), weights, equity)
    assert (push, fold) == pytest.approx((o.steal[0], o.walk[0]), abs=1e-12)
    # Колл всеми: выигрыш с долей эквити, взвешенной числом совместимых пар.
    share = float((weights * equity).sum() / weights.sum())
    push, _ = opener_ev(game, numpy.ones((1, 169)), weights, equity)
    assert push == pytest.approx(share * o.win[0][0] + (1 - share) * o.lose[0][0], abs=1e-12)


def test_opener_ev_respects_blockers():
    # `AA` против колла одними `AA`: у руки `AhAs` совместима только одна комбинация `AdAc`.
    game = _hu()
    o = game.outcomes
    call = numpy.zeros((1, 169))
    call[0, class_index("AA")] = 1.0
    weights = hand_weights(["Ah", "As"])
    assert weights[class_index("AA")] == 1
    equity = equity_matrix()[class_index("AA")]
    q = 1.0 / float(weights.sum())
    push, _ = opener_ev(game, call, weights, equity)
    tie = 0.5 * o.win[0][0] + 0.5 * o.lose[0][0]
    assert push == pytest.approx((1 - q) * o.steal[0] + q * tie, abs=1e-9)


def test_responder_ev_against_a_single_class():
    # Открывающий пушит только `KQo`: колл — эквити против `KQo`, фолд — пустой банк.
    game = _hu()
    o = game.outcomes
    push = numpy.zeros(169)
    push[class_index("KQo")] = 1.0
    caller = class_index("A2o")
    weights = weight_matrix()[:, caller]
    equity = 1.0 - equity_matrix()[:, caller]
    call_ev, fold_ev = responder_ev(game, push, numpy.zeros((1, 169)), 1, weights, equity)
    mine = float(equity[class_index("KQo")])
    assert call_ev == pytest.approx((1 - mine) * o.win[0][1] + mine * o.lose[0][1], abs=1e-12)
    assert fold_ev == pytest.approx(o.steal[1], abs=1e-12)


def test_a_hand_no_push_reaches_has_zero_ev_both_ways():
    # Открывающий не пушит ничем: до отвечающего действие не доходит, оба EV — 0, ответ — фолд.
    game = _hu()
    caller = class_index("AA")
    weights = weight_matrix()[:, caller]
    equity = 1.0 - equity_matrix()[:, caller]
    nothing = numpy.zeros(169)
    assert responder_ev(game, nothing, numpy.zeros((1, 169)), 1, weights, equity) == (0.0, 0.0)


def test_a_later_caller_shapes_the_fold_ev_of_an_earlier_one():
    # Три отвечающих: фолд `BTN` стоит ему исходов за ним. Если коллирует только `BB` всеми
    # руками, фолд `BTN` — ровно его стек: олл-ин идёт между открывающим и `BB`.
    game = _three_responders()
    o = game.outcomes
    push = numpy.ones(169)
    call = numpy.zeros((3, 169))
    call[2] = 1.0
    caller = class_index("99")
    weights = weight_matrix()[:, caller]
    equity = 1.0 - equity_matrix()[:, caller]
    _, fold_ev = responder_ev(game, push, call, 1, weights, equity)
    assert o.win[2][1] == o.lose[2][1] == 12.0
    assert fold_ev == pytest.approx(12.0, abs=1e-12)
    # Если не коллирует никто, фолд `BTN` — тоже его стек, а фолд `BB` — стек без блайнда.
    _, fold_bb = responder_ev(game, push, numpy.zeros((3, 169)), 3, weights, equity)
    assert fold_bb == pytest.approx(o.steal[3], abs=1e-12) and o.steal[3] == 14.0


def test_monotone_in_bounty():
    # Инвариант 9: рост выплаты отвечающему за нокаут не уменьшает EV его колла.
    game = _hu()
    o = game.outcomes
    bounty_row = list(o.lose[0])
    bounty_row[1] += 5.0  # отвечающий выбил открывающего и взял голову
    richer = Game(dataclasses.replace(o, lose=[bounty_row]), 1)
    push = solve(game, EPS_CHIP_BB).push
    call = numpy.full((1, 169), 0.5)
    e, w = equity_matrix(), weight_matrix()
    for x in range(169):
        before = responder_ev(game, push, call, 1, w[:, x], 1.0 - e[:, x])[0]
        after = responder_ev(richer, push, call, 1, w[:, x], 1.0 - e[:, x])[0]
        assert after > before


def test_range_share_weights_by_combos():
    assert range_share(numpy.ones(169)) == pytest.approx(1.0, abs=1e-12)
    assert range_share(numpy.zeros(169)) == 0.0
    only = numpy.zeros(169)
    only[class_index("AA")] = 1.0
    only[class_index("AKo")] = 0.5
    assert range_share(only) == pytest.approx((6 + 6) / 1326, abs=1e-12)


# --- отказы ----------------------------------------------------------------------------------


@pytest.mark.parametrize("eps", [0.0, -0.001])
def test_refuses_a_non_positive_eps(eps):
    with pytest.raises(ValueError, match=rf"^допуск равновесия должен быть > 0, получено {eps}$"):
        solve(_hu(), eps)


def test_refuses_a_non_positive_iteration_limit():
    with pytest.raises(ValueError, match=r"^предел итераций должен быть > 0, получено 0$"):
        solve(_hu(), EPS_CHIP_BB, max_iterations=0)


def test_refuses_outcomes_for_another_number_of_responders():
    with pytest.raises(ValueError, match=r"^выплат на 1 отвечающих, а в игре 2$"):
        Game(_hu().outcomes, 2)
    o = _three_responders().outcomes
    with pytest.raises(ValueError, match=r"^выплат на 2 отвечающих, а в игре 3$"):
        Game(dataclasses.replace(o, lose=o.lose[:2]), 3)
