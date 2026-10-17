"""Приёмка T2 (спека плана 4, §9 п.12): HU push/fold по фишкам против опубликованного чарта.

Чарт — `tests/data/hu_nash_chart.json`, источник и дата внутри. Значение класса — наибольший
эффективный стек, при котором он играет; `null` — «20+», любой стек до 20 BB; список отрезков —
пробелы стратегии из сносок чарта.

Пограничные классы не считаются (решение пользователя, Фаза 3, 2026-10-18): класс, у которого
порог чарта не дальше `BORDER_BB` от глубины, почти безразличен между действиями, и его сторона
решается шумом таблицы эквити (`STANDARD_ERROR` клетки) и упрощением чарта, а не солвером. На
10 BB у солвера J3s и Q7o (пороги 10.6 и 10.3) — разница EV пуша и фолда меньше 0.001 BB.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import heads_up_spot
from poker_engine.allin_matrix import CLASSES
from poker_engine.nash import EPS_CHIP_BB, Game, solve
from poker_engine.pushfold_game import chip_outcomes

BORDER_BB = 0.5

_CHART = json.loads(
    (Path(__file__).parent / "data" / "hu_nash_chart.json").read_text(encoding="utf-8")
)


def _charted(table: dict, depth: float) -> set[str]:
    def plays(value) -> bool:
        if value is None:
            return True
        if isinstance(value, list):
            return any(low <= depth <= high for low, high in value)
        return value >= depth

    return {name for name in CLASSES if plays(table[name])}


def _borderline(table: dict, depth: float) -> set[str]:
    """Классы, у которых граница чарта ближе `BORDER_BB` к глубине; «20+» границы не даёт."""

    def edges(value) -> list[float]:
        if value is None:
            return []
        if isinstance(value, list):
            return [edge for pair in value for edge in pair if edge > 0]
        return [value]

    return {
        name
        for name in CLASSES
        if any(abs(edge - depth) <= BORDER_BB for edge in edges(table[name]))
    }


def test_the_border_band_is_the_agreed_one():
    # Ширина полосы — решение пользователя (Фаза 3); 10 BB — глубина, ради которой она введена.
    assert BORDER_BB == 0.5
    assert {"43s", "Q7o"} <= _borderline(_CHART["sbPush"], 10)
    assert "J3s" not in _borderline(_CHART["sbPush"], 10)


def test_chart_names_its_source_and_every_class():
    assert _CHART["source"].startswith("https://")
    assert _CHART["retrieved"]
    assert set(_CHART["sbPush"]) == set(_CHART["bbCall"]) == set(CLASSES)


@pytest.mark.parametrize("depth", [3, 5, 8, 10, 15, 20])
def test_heads_up_chip_equilibrium_matches_the_chart(depth):
    equilibrium = solve(Game(chip_outcomes(heads_up_spot(depth)), 1), EPS_CHIP_BB)
    assert equilibrium.converged
    solved = {
        "sbPush": {CLASSES[at] for at in range(len(CLASSES)) if equilibrium.push[at] > 0.5},
        "bbCall": {CLASSES[at] for at in range(len(CLASSES)) if equilibrium.call[0][at] > 0.5},
    }
    for side in ("sbPush", "bbCall"):
        chart = _charted(_CHART[side], depth)
        border = _borderline(_CHART[side], depth)
        extra = sorted(solved[side] - chart - border)
        missing = sorted(chart - solved[side] - border)
        assert len(extra) + len(missing) <= 1, (
            f"{depth} BB, {side}: лишние {extra}, недостающие {missing}, "
            f"пограничные (не считаются) {sorted(border)}"
        )
