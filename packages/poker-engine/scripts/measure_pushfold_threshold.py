"""Замер порога `PUSHFOLD_MAX_BB` правилом потери EV (спека модели колла §8; план 6, Задача 5).

Сетка эффективных стеков 6–20 BB шагом 1; позиции первого в банк — 6-max `UTG`, `HJ`, `CO`,
`BTN`, `SB` и 8-max `UTG1`, `MP`, `LJ`, `HJ`, `CO`, `BTN`, `SB`; у всех один стек, до героя все
сфолдили. Стол — кадр эталона T2 (`test_mtt_reference.reference_frame`: анте 0.125 с места),
контекст — `conftest._context()` с `seatsPerTable` стола. На каждой точке решаются дерево `open`
советника `preflop` и подыгра push/fold советника `pushfold`, по фишкам и по ICM. Порог
обходится на время вызова: линия читается при `PUSHFOLD_MAX_BB = 0`, подыгра — при пороге выше
сетки. Константа модуля не меняется.

**Потеря EV** класса героя `h` — лучшее действие корня дерева минус действие, которое советует
`pushfold` (`allin`, если в его равновесии EV пуша больше EV фолда, иначе `fold`); оба EV — из
`_opener_values` солвера против равновесия дерева, будущие решения героя — лучший ответ, как у
`action_values`. Масти симметричны, поэтому EV класса равно EV любой его комбинации; среднее по
1326 рукам — `prior @ потеря`. У `SB` среди действий корня есть лимп, у `pushfold` — нет.

Правило (§8): порог — наибольшее целое `D`, на котором средняя потеря по фишкам `≤ 0.01` BB на
руку на каждой позиции обоих столов. ICM — в отчёт, в долларах на руку.

Запуск из `packages/poker-engine`: `.venv/bin/python scripts/measure_pushfold_threshold.py`
(Windows — `.venv/Scripts/python`). Точки решаются в пуле процессов.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import pathlib
import sys
import time

import numpy

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tests"))

from conftest import _context  # noqa: E402
from test_mtt_reference import reference_frame  # noqa: E402

from poker_engine import allin_matrix, nash, preflop_advisor, preflop_solver, pushfold, pushfold_game  # noqa: E402,E501
from poker_engine.handstate import context_from_dict, node_from_dict, validate_hand  # noqa: E402
from poker_engine.preflop_solver import action_values  # noqa: E402

DEPTHS = range(6, 21)
TABLES = {
    6: ("UTG", "HJ", "CO", "BTN", "SB"),
    8: ("UTG1", "MP", "LJ", "HJ", "CO", "BTN", "SB"),
}
LOSS_BB = 0.01
PAYOUTS = ("chip", "icm")


@contextlib.contextmanager
def _threshold(value: float):
    saved = pushfold_game.PUSHFOLD_MAX_BB
    pushfold_game.PUSHFOLD_MAX_BB = value
    try:
        yield
    finally:
        pushfold_game.PUSHFOLD_MAX_BB = saved


def _root_values(tree, payoffs, solution) -> numpy.ndarray:
    """`(действия корня, 169)`: EV каждого действия корня по классу героя против равновесия."""
    shape = preflop_solver._shape(tree, payoffs)
    side, _ = preflop_solver._class_sides(shape)
    _, rk = preflop_solver._reach(shape, solution.strategy)
    shares = preflop_solver._shares(shape, rk, side)
    _, actions, _ = preflop_solver._opener_values(shape, solution.strategy, shares, side, best=True)
    return actions[shape.root]


def _pushes(context, node) -> dict[str, numpy.ndarray]:
    """По выплате — `(169,)` булев: совет `pushfold` по классу — пуш (EV пуша больше фолда)."""
    with _threshold(1e9):
        spot = pushfold_game.read_spot(node)
    assert isinstance(spot, pushfold_game.Spot) and spot.hero_at == 0, spot
    chips = pushfold_game.chip_outcomes(spot)
    plain = pushfold_game.icm_outcomes(spot, node, context, bounties=False)
    responders = len(spot.players) - 1
    games = {"chip": nash.Game(chips, responders), "icm": nash.Game(plain, responders)}
    eps = {"chip": nash.EPS_CHIP_BB, "icm": pushfold.icm_eps_usd(chips, plain)}
    weights, equity = allin_matrix.weight_matrix(), allin_matrix.equity_matrix()
    result = {}
    for payout in PAYOUTS:
        solved = nash.solve(games[payout], eps[payout], nash.MAX_ITERATIONS)
        assert solved.converged, (payout, solved)
        ev = [nash.opener_ev(games[payout], solved.call, weights[h], equity[h]) for h in range(169)]
        result[payout] = numpy.array([push > fold for push, fold in ev])
    return result


def _combo(name: str) -> tuple[str, str]:
    """Комбинация класса: пара — пики и черви, одномастная — пики, разномастная — пики и черви."""
    if len(name) == 2:
        return name[0] + "s", name[1] + "h"
    return name[0] + "s", name[1] + ("s" if name[2] == "s" else "h")


def _point(task: tuple[int, str, int]) -> dict:
    table, position, depth = task
    point = {
        "table": table,
        "depthBb": float(depth),
        "hero": position,
        "spot": "open",
        "antePerSeatBb": 0.125,
    }
    context = context_from_dict({**_context(), "seatsPerTable": table})
    nodes = [node_from_dict(reference_frame(point))]
    validate_hand(context, nodes)
    with _threshold(0.0):
        solved = preflop_advisor._solve(context, nodes)
    tree = solved.tree
    assert tree.hero_node == tree.root
    kinds = [action.kind for action in tree.nodes[tree.root].actions]
    pushes = _pushes(context, nodes[0])
    _, _, prior = preflop_solver._tables()
    row = {"table": table, "position": position, "depth": depth, "kinds": kinds}
    for payout in PAYOUTS:
        solution = solved.by_chip if payout == "chip" else solved.by_icm
        payoffs = solved.chips if payout == "chip" else solved.icm
        values = _root_values(tree, payoffs, solution)
        # Сверка с публичным `action_values` на одном классе: тот же EV, что у советника.
        probe = allin_matrix.class_index("A5s")
        public = action_values(tree, payoffs, solution, tree.root, _combo("A5s"))
        assert numpy.allclose(values[:, probe], public, rtol=0, atol=1e-9), (values[:, probe], public)
        advised = numpy.where(pushes[payout], kinds.index("allin"), kinds.index("fold"))
        loss = values.max(axis=0) - values[advised, numpy.arange(169)]
        row[payout] = {
            "loss": float(prior @ loss),
            "shares": dict(zip(kinds, solution.strategy[tree.root] @ prior)),
            "push": float(prior @ pushes[payout]),
            "converged": solution.converged,
        }
    return row


def _shares(row: dict) -> str:
    shares = row["chip"]["shares"]
    return " / ".join(
        f"{100 * shares[kind]:.1f}" if kind in shares else "—"
        for kind in ("fold", "limp", "raise", "allin")
    )


def main() -> None:
    start = time.perf_counter()
    tasks = [(t, p, d) for d in DEPTHS for t, positions in TABLES.items() for p in positions]
    with concurrent.futures.ProcessPoolExecutor() as pool:
        rows = list(pool.map(_point, tasks))
    print(
        "| Стек | Стол | Позиция | Потеря, BB на руку (фишки) | Потеря, $ на руку (ICM) "
        "| Дерево по фишкам: фолд / лимп / рейз / олл-ин, % | Пуш `pushfold`, % (фишки / ICM) "
        "| Сошлось |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        c, i = r["chip"], r["icm"]
        print(
            f"| {r['depth']} | {r['table']}-max | {r['position']} "
            f"| {c['loss']:.4f} | {i['loss']:.4f} | {_shares(r)} "
            f"| {100 * c['push']:.1f} / {100 * i['push']:.1f} "
            f"| {'да' if c['converged'] and i['converged'] else 'нет'} |"
        )
    print("\n| Стек | Наибольшая потеря, BB (позиция) | Правило ≤ 0.01 |")
    print("|---|---|---|")
    passing = []
    for depth in DEPTHS:
        here = [r for r in rows if r["depth"] == depth]
        worst = max(here, key=lambda r: r["chip"]["loss"])
        ok = worst["chip"]["loss"] <= LOSS_BB
        if ok:
            passing.append(depth)
        print(
            f"| {depth} | {worst['chip']['loss']:.4f} ({worst['table']}-max {worst['position']}) "
            f"| {'да' if ok else 'нет'} |"
        )
    print(f"\nПорог по правилу: {max(passing) if passing else 'нет'}")
    print(f"Время: {time.perf_counter() - start:.0f} с")


if __name__ == "__main__":
    main()
