"""Порядок силы 169 стартовых классов, вычисленный против случайной руки.

Данные лежат в `data/preflop_order.json` и порождаются
`scripts/gen_preflop_order.py`. Они вычислены этим же движком, а не
взяты из чарта: конвенция репозитория запрещает числа из памяти.

Порядок соседних классов в основном НЕ разрешён расчётом. При 20 000
прогонов стандартная ошибка одной оценки ~0.0035, а из 168 соседских
зазоров 130 меньше этой величины; медианный зазор 0.0014875, минимальный
ненулевой — 0.000025 (`J6s`/`K2o`). Две пары совпадают точно: `33`/`K3s`
и `52o`/`62o`.

При равном эквити порядок задаёт стабильная сортировка в
`scripts/gen_preflop_order.py`, то есть порядок выдачи `hand_classes()` —
по возрастанию старшего ранга. Отсюда `33` выше `K3s`, а `52o` выше `62o`:
при ничьей наверху оказывается визуально более слабая рука. Правило
детерминировано и воспроизводимо, но произвольно.

Для Task 4 это важно, а не безразлично: почти-ничьи ложатся ровно на
типовые отсечки по VPIP — `A5s`/`A6s` (зазор 0.000075) на ~14.5 %,
`K9o`/`A6o` (0.000050) на ~20.8 %, `33`/`K3s` (0.000000) на ~34.4 %,
`Q3s`/`Q6o` (0.000050) на ~44.9 %. Состав диапазона У САМОЙ ГРАНИЦЫ
отсечения — артефакт сортировки, а не результат расчёта. Крупные блоки
порядка (пары по рангу, одномастная выше своего разномастного двойника)
расчётом разрешены надёжно, см. `tests/test_preflop_order.py`.
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
