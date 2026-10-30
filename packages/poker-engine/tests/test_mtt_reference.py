"""Эталон T2 модели колла: публичные чарты MTT (спека модели колла, §2.1, §6, инвариант 13).

Точки — `tests/data/mtt_reference.json`, таблица §2.1 спеки дословно. Модель — дерево советника
`preflop` по фишкам на столе спеки §2.2: `n` мест 1..n, кнопка — место `n − 1`, у всех один стек
до раздачи, анте с каждого места в банке, все до героя сфолдили (в `vs_open` — кроме открывшего).
Доля действия — `prior @ стратегия` узла героя, % всех рук. Порог push/fold обходится: T2 меряет
дерево, а не маршрут советников.

Этот модуль — и мерка подбора: `scripts/calibrate_realization.py` берёт отсюда стол, доли, метрику
и допуски §6.3, чтобы подбор и тест не разошлись. Тест допусков (инвариант 13) — при константах
`realization`, подобранных скриптом (журнал плана 6, «Фаза 3c»), и с лимпом `SB` (Задача 4):
`SB` первым в банк — роль `holdout_sb_limp`, допуск отложенных. Точки вне T2 — роли
`holdout_cold_call` (E6: в чарте есть колд-колл незакрывающего, в модели нет), `holdout_sb_rfi`
(`E11.SB.open`: чарт RFI без лимпа, а у `SB` модели лимп есть — доли рейза несравнимы) и
`holdout_sb_size` (доля рейза и олл-ина `SB`, которую решает единственный размер рейза, D33).
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

import numpy
import pytest

from conftest import _context
from poker_engine import allin_matrix, nash, pushfold_game, realization
from poker_engine.handstate import (
    assign_positions,
    context_from_dict,
    node_from_dict,
    validate_hand,
)
from poker_engine.preflop_line import read_line
from poker_engine.preflop_solver import solve
from poker_engine.preflop_tree import Tree, build, chip_payoffs
from poker_engine.types import Position, positions_for

REFERENCE = pathlib.Path(__file__).parent / "data" / "mtt_reference.json"
# Допуски §6.3, п.п.: E11 — кэш с другим рейком и размером открытия.
TOLERANCE_PP = {"calibration": 6.0, "holdout": 10.0, "holdout_sb_limp": 10.0}
CASH_TOLERANCE_PP = 12.0
CASH_SOURCE = "E11"
# Роли вне `holdout` — спека §6.1 и решения Задач 3–4 плана 6 (Фазы 3b–4): `E4.SB.open` — `SB`
# первым в банк, как E7–E9; E6 целиком — ответ незакрывающего, у которого в чарте колд-колл;
# `E11.SB.open` — `SB` первым в банк по кэш-чарту RFI, где лимпа нет; рейз и олл-ин `SB` на
# 20–25 BB и `E4.SB.open` — частоты единственного размера рейза (решение пользователя, Фаза 4).
ROLE_OF_SOURCE = {
    "E1": "calibration",
    "E2": "calibration",
    "E6": "holdout_cold_call",
    "E7": "holdout_sb_limp",
    "E8": "holdout_sb_limp",
    "E9": "holdout_sb_limp",
}
ROLE_OF_POINT = {
    "E4.SB.open": "holdout_sb_size",
    "E7.SB.25bb.raise": "holdout_sb_size",
    "E7.SB.25bb.allin": "holdout_sb_size",
    "E9.SB.raise": "holdout_sb_size",
    "E9.SB.allin": "holdout_sb_size",
    "E11.SB.open": "holdout_sb_rfi",
}

_PRIOR = numpy.array([allin_matrix.combos_of(name) for name in allin_matrix.CLASSES]) / 1326


def load_points() -> list[dict]:
    return json.loads(REFERENCE.read_text(encoding="utf-8"))["points"]


def source_of(point: dict) -> str:
    """`E1` у точки `E1.UTG1.open`."""
    return point["id"].split(".")[0]


def tolerance(point: dict) -> float:
    if source_of(point) == CASH_SOURCE:
        return CASH_TOLERANCE_PP
    return TOLERANCE_PP[point["role"]]


def deviation(model: float, value: float | list[float]) -> float:
    """Отклонение в п.п.; у интервала источников — от его краёв."""
    if isinstance(value, list):
        lo, hi = value
        return max(lo - model, model - hi, 0.0)
    return abs(model - value)


def reference_frame(point: dict) -> dict:
    """Кадр точки на столе спеки §2.2."""
    n, depth = point["table"], point["depthBb"]
    # Кнопка — место `n − 1`: первый по порядку `positions_for` ходит с места 2, `BB` — место 1.
    seat_of = {role: (i + 1) % n + 1 for i, role in enumerate(positions_for(n))}
    hero = seat_of[Position[point["hero"]]]
    put = {seat_of[Position.SB]: 0.5, seat_of[Position.BB]: 1.0}
    acting = [seat_of[role] for role in positions_for(n)]
    if point["spot"] == "vs_open":
        opener = seat_of[Position[point["villain"]]]
        put[opener] = point["openBb"]
        entered = {opener}
    else:
        entered = set()
    folded = set(acting[: acting.index(hero)]) - entered
    return {
        "street": "preflop",
        "level": 1,
        "blinds": {"sb": 50, "bb": 100, "ante": 0},
        "heroRank": 1,
        "playersLeft": _context()["playersLeft"],
        "buttonSeat": n - 1,
        "heroCards": ["Jh", "Th"],
        "board": [],
        "seats": [
            {
                "seatIndex": seat,
                "name": f"p{seat}",
                "stackBb": depth - put.get(seat, 0.0),
                "investedBb": put.get(seat, 0.0),
                "inHand": seat not in folded,
                "isHero": seat == hero,
                "vpip": 25.0,
                "vpipHands": 60,
            }
            for seat in range(1, n + 1)
        ],
        "potBb": sum(put.values()) + point["antePerSeatBb"] * n,
        "toCallBb": max(put.values()) - put.get(hero, 0.0),
        "raiseToBb": None,
    }


def reference_tree(point: dict) -> Tree:
    """Дерево точки: кадр проходит проверку схемы, линия читается спотом точки."""
    raw = reference_frame(point)
    context = context_from_dict({**_context(), "seatsPerTable": point["table"]})
    nodes = [node_from_dict(raw)]
    validate_hand(context, nodes)
    saved = pushfold_game.PUSHFOLD_MAX_BB
    pushfold_game.PUSHFOLD_MAX_BB = 0.0
    try:
        line = read_line(nodes)
    finally:
        pushfold_game.PUSHFOLD_MAX_BB = saved
    assert not isinstance(line, str), line
    assert line.kind == point["spot"]
    tree = build(line, nodes[-1])
    assert not isinstance(tree, str), tree
    return tree


@dataclass(frozen=True)
class Solved:
    """Доли действий узла героя, % всех рук, при константах `realization` на момент решения."""

    shares: dict[str, float]
    converged: bool


def solve_point(point: dict) -> Solved:
    tree = reference_tree(point)
    solution = solve(tree, chip_payoffs(tree), nash.EPS_CHIP_BB)
    actions = tree.nodes[tree.hero_node].actions
    shares = solution.strategy[tree.hero_node] @ _PRIOR * 100
    return Solved(
        {action.kind: float(share) for action, share in zip(actions, shares)}, solution.converged
    )


def model_value(point: dict, shares: dict[str, float]) -> float:
    """Метрика точки по долям действий узла героя."""
    entered = shares.get("raise", 0.0) + shares.get("allin", 0.0)
    if point["metric"] == "open":
        return entered
    if point["metric"] == "allinShareOfOpen":
        return 100 * shares.get("allin", 0.0) / entered
    return shares.get(point["metric"], 0.0)


def tree_key(point: dict) -> tuple:
    return tuple(
        point.get(field)
        for field in ("table", "depthBb", "antePerSeatBb", "openBb", "spot", "hero", "villain")
    )


def test_reference_file_shape():
    # Таблица §2.1: у каждой точки источник, дата и способ; роли — из спеки §6.1; id уникальны.
    points = load_points()
    assert len({point["id"] for point in points}) == len(points)
    roles = {point["role"] for point in points}
    assert roles == {
        "calibration",
        "holdout",
        "holdout_sb_limp",
        "holdout_cold_call",
        "holdout_sb_rfi",
        "holdout_sb_size",
    }
    assert {source_of(point) for point in points} == {f"E{i}" for i in range(1, 12)}
    for point in points:
        assert point["payout"] == "chip"
        assert point["source"] and point["accessed"] and point["method"]
        expected = ROLE_OF_POINT.get(point["id"], ROLE_OF_SOURCE.get(source_of(point), "holdout"))
        assert point["role"] == expected, point["id"]


@pytest.mark.parametrize("point", load_points(), ids=lambda point: point["id"])
def test_reference_point_is_the_named_spot(point):
    # Кадр каждой точки читается её спотом, герой — на названной позиции, рейз героя в `open` —
    # размер `openBb` (у `SB` — `OPEN_SB_BB`), открытие соперника в `vs_open` — тоже `openBb`.
    tree = reference_tree(point)
    hero = next(seat for seat in tree.players if seat.is_hero)
    node = node_from_dict(reference_frame(point))
    assert assign_positions(node)[hero.seat_index] is Position[point["hero"]]
    if point["spot"] == "open":
        raises = [a.to_bb for a in tree.nodes[tree.hero_node].actions if a.kind == "raise"]
        assert raises == [point["openBb"]]
    else:
        opener = next(seat for seat in node.seats if seat.invested_bb > 1.0)
        assert assign_positions(node)[opener.seat_index] is Position[point["villain"]]
        assert opener.invested_bb == point["openBb"]


_SOLVED: dict[tuple, Solved] = {}


def _solved(point: dict) -> Solved:
    """Одно равновесие на дерево: точки E1, E4 и E5 на `UTG1` 40 BB — одно и то же дерево."""
    key = (tree_key(point), realization.REALIZATION_KAPPA, realization.REALIZATION_LAMBDA)
    if key not in _SOLVED:
        _SOLVED[key] = solve_point(point)
    return _SOLVED[key]


@pytest.mark.parametrize(
    "point",
    [point for point in load_points() if point["role"] in TOLERANCE_PP],
    ids=lambda point: point["id"],
)
def test_model_is_within_the_reference_tolerance(point):
    # Инвариант 13, допуски §6.3 при константах модуля: калибровочные ±6 п.п., отложенные ±10
    # (и `SB` первым в банк, §7), E11 ±12; у интервала источников — от краёв. Равновесие обязано
    # сойтись: доли несошедшегося решения — не модель.
    solved = _solved(point)
    assert solved.converged
    model = model_value(point, solved.shares)
    assert deviation(model, point["value"]) <= tolerance(point), (model, point["value"])
