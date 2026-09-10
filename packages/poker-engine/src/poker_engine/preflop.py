"""Порядок силы 169 стартовых классов, вычисленный против случайной руки.

Данные лежат в `data/preflop_order.json` и порождаются
`scripts/gen_preflop_order.py`. Они вычислены этим же движком, а не
взяты из чарта: конвенция репозитория запрещает числа из памяти.

Соседние по силе классы могут стоять в порядке, продиктованном шумом
выборки — эквити у них различается в третьем знаке. Для построения
диапазонов по VPIP это несущественно: там важна верхняя граница отсечения,
а не точное соседство двух почти равных рук.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .equity import RANKS

_DATA = Path(__file__).parent / "data" / "preflop_order.json"


def hand_classes() -> list[str]:
    """169 стартовых классов: пары, одномастные, разномастные."""
    out: list[str] = []
    for i, high in enumerate(RANKS):
        for j, low in enumerate(RANKS):
            if i == j:
                out.append(high + low)
            elif i > j:
                out.append(high + low + "s")
                out.append(high + low + "o")
    return out


@lru_cache(maxsize=1)
def _load() -> tuple[dict, ...]:
    with _DATA.open(encoding="utf-8") as handle:
        return tuple(json.load(handle))


def preflop_order() -> list[dict]:
    """Классы по убыванию эквити против случайной руки."""
    return [dict(entry) for entry in _load()]
