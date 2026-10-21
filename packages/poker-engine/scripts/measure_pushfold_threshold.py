"""Замер порога `PUSHFOLD_MAX_BB` (спека плана 5, §11; план 5, Задача 7).

Сетка эффективных стеков 6–20 BB шагом 1, позиции `UTG`, `CO`, `BTN`, `SB` 6-max, у всех один
стек, до героя все сфолдили. Контекст — `conftest._context()`. На каждой точке решаются дерево
`open` советника `preflop` и подыгра push/fold советника `pushfold`, по фишкам и по ICM. Порог
обходится на время вызова: линия читается при `PUSHFOLD_MAX_BB = 0`, подыгра — при пороге выше
сетки. Константа модуля не меняется.

Столбцы таблицы:
- `рейз` и `олл-ин` — доля всех 1326 рук, которой корень дерева играет это действие;
- `рейз в открытии` — доля рейза не олл-ином в диапазоне открытия (рейз + олл-ин);
- `пуш push/fold` — доля всех рук, которой герой пушит в равновесии подыгры push/fold;
- `граница` — класс с наименьшей по модулю разницей EV пуша и фолда в равновесии push/fold;
- `ΔEV` — для комбинации этого класса: лучшее действие дерева минус лучшее действие push/fold,
  в BB по фишкам и в долларах по ICM (оба — EV до конца раздачи против своего равновесия).

Запуск из `packages/poker-engine`: `.venv/bin/python scripts/measure_pushfold_threshold.py`.
"""

from __future__ import annotations

import contextlib
import pathlib
import sys
import time

import numpy

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tests"))

from conftest import _context, preflop_frame  # noqa: E402

from poker_engine import allin_matrix, nash, preflop_advisor, pushfold, pushfold_game  # noqa: E402
from poker_engine.handstate import context_from_dict, node_from_dict, validate_hand  # noqa: E402
from poker_engine.preflop_solver import action_values  # noqa: E402

DEPTHS = range(6, 21)
# Герой и сфолдившие до него на столе `conftest.preflop_frame`.
SEATS = {"UTG": (7, set()), "CO": (3, {7, 2}), "BTN": (4, {7, 2, 3}), "SB": (5, {7, 2, 3, 4})}
PAYOUTS = ("chip", "icm")


@contextlib.contextmanager
def _threshold(value: float):
    saved = pushfold_game.PUSHFOLD_MAX_BB
    pushfold_game.PUSHFOLD_MAX_BB = value
    try:
        yield
    finally:
        pushfold_game.PUSHFOLD_MAX_BB = saved


def _combo(name: str) -> tuple[str, str]:
    """Комбинация класса: пара — пики и черви, одномастная — пики, разномастная — пики и черви."""
    if len(name) == 2:
        return name[0] + "s", name[1] + "h"
    return name[0] + "s", name[1] + ("s" if name[2] == "s" else "h")


def _pushfold(context, node):
    """Равновесие push/fold и функция EV (пуш, фолд) комбинации героя-открывающего."""
    with _threshold(1e9):
        spot = pushfold_game.read_spot(node)
    assert isinstance(spot, pushfold_game.Spot) and spot.hero_at == 0, spot
    chips = pushfold_game.chip_outcomes(spot)
    plain = pushfold_game.icm_outcomes(spot, node, context, bounties=False)
    responders = len(spot.players) - 1
    games = {"chip": nash.Game(chips, responders), "icm": nash.Game(plain, responders)}
    eps = {"chip": nash.EPS_CHIP_BB, "icm": pushfold.icm_eps_usd(chips, plain)}
    solved = {p: nash.solve(games[p], eps[p], nash.MAX_ITERATIONS) for p in PAYOUTS}

    def ev(payout, weights, equity):
        return nash.opener_ev(games[payout], solved[payout].call, weights, equity)

    return solved, ev


def _boundary(ev, payout) -> str:
    weights, equity = allin_matrix.weight_matrix(), allin_matrix.equity_matrix()
    margins = []
    for at in range(169):
        push, fold = ev(payout, weights[at], equity[at])
        margins.append(abs(push - fold))
    return allin_matrix.CLASSES[int(numpy.argmin(margins))]


def _row(position: str, depth: int) -> dict:
    hero, folded = SEATS[position]
    raw = preflop_frame(hero, folded=folded, starting=dict.fromkeys(range(2, 8), float(depth)))
    context = context_from_dict(_context())
    nodes = [node_from_dict(raw)]
    validate_hand(context, nodes)
    with _threshold(0.0):
        solved = preflop_advisor._solve(context, nodes)
    tree = solved.tree
    root = tree.nodes[tree.root]
    kinds = [action.kind for action in root.actions]
    pushes, ev = _pushfold(context, nodes[0])

    row: dict = {"depth": depth, "position": position, "converged": True}
    for payout in PAYOUTS:
        solution = solved.by_chip if payout == "chip" else solved.by_icm
        payoffs = solved.chips if payout == "chip" else solved.icm
        row["converged"] &= solution.converged
        strategy = solution.strategy[tree.root]
        share = {k: nash.range_share(strategy[kinds.index(k)]) if k in kinds else 0.0
                 for k in ("raise", "allin")}
        opened = share["raise"] + share["allin"]
        name = _boundary(ev, payout)
        combo = _combo(name)
        weights = allin_matrix.hand_weights(list(combo))
        equity = allin_matrix.equity_matrix()[allin_matrix.class_index(name)]
        tree_best = max(action_values(tree, payoffs, solution, tree.hero_node, combo))
        pushfold_best = max(ev(payout, weights, equity))
        row[payout] = {
            "raise": share["raise"],
            "allin": share["allin"],
            "raise_in_open": share["raise"] / opened if opened > 0 else 0.0,
            "push": nash.range_share(pushes[payout].push),
            "boundary": name,
            "delta": tree_best - pushfold_best,
        }
    return row


def main() -> None:
    start = time.perf_counter()
    print(
        "| Стек | Позиция | Рейз, % рук (фишки / ICM) | Олл-ин, % рук | Рейз в открытии, % "
        "| Пуш push/fold, % рук | Граница push/fold | ΔEV, BB | ΔEV, $ | Сошлось |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    for depth in DEPTHS:
        for position in SEATS:
            r = _row(position, depth)
            c, i = r["chip"], r["icm"]
            print(
                f"| {depth} | {position} "
                f"| {100 * c['raise']:.1f} / {100 * i['raise']:.1f} "
                f"| {100 * c['allin']:.1f} / {100 * i['allin']:.1f} "
                f"| {100 * c['raise_in_open']:.0f} / {100 * i['raise_in_open']:.0f} "
                f"| {100 * c['push']:.1f} / {100 * i['push']:.1f} "
                f"| {c['boundary']} / {i['boundary']} "
                f"| {c['delta']:+.3f} | {i['delta']:+.3f} "
                f"| {'да' if r['converged'] else 'нет'} |",
                flush=True,
            )
    print(f"\nВремя: {time.perf_counter() - start:.0f} с", flush=True)


if __name__ == "__main__":
    main()
