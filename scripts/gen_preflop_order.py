"""Считает эквити каждого стартового класса против случайной руки.

Запуск (из packages/poker-engine):

    .venv/Scripts/python ../../scripts/gen_preflop_order.py

Результат перезаписывает src/poker_engine/data/preflop_order.json.
Внутри класса все комбинации эквивалентны с точностью до перестановки
мастей, поэтому считается по одному представителю на класс.

Сид ОДИН на все 169 классов намеренно — не разнообразить. Живых
комбинаций у любого класса героя ровно 1225, а колоды под ранаут — ровно
48, поэтому при общем сиде поток индексов у всех классов идентичен: это
общие случайные числа (common random numbers). Они снижают дисперсию
РАЗНОСТЕЙ, и сравнение двух классов между собой получается точнее, чем
маргинальная ошибка ±0.0035 у каждой оценки по отдельности. Свой сид на
класс разрушил бы это и ухудшил порядок.

Цена прогона — около 27 минут (измерено: ~9.5 с на класс, 169 классов),
почти всё время уходит в `equity._best_hand`. Это разовая плата: результат
коммитится, и тесты читают готовый JSON, а не пересчитывают его.
"""

from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

from poker_engine.equity import FULL_DECK, equity_vs_range
from poker_engine.preflop import hand_classes
from poker_engine.ranges import parse_range

TRIALS = 20_000
SEED = 20260910
OUT = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "poker-engine"
    / "src"
    / "poker_engine"
    / "data"
    / "preflop_order.json"
)

RANDOM_HAND = ["".join(sorted(pair)) for pair in combinations(FULL_DECK, 2)]


def main() -> None:
    # Итоговая строка русская, а перенаправленный stdout на Windows берёт
    # кодировку консоли (cp1252) и падает на кириллице — уже после того,
    # как JSON записан. Тот же приём, что в cli.py: принудительный UTF-8.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")

    classes = hand_classes()
    rows = []
    for index, name in enumerate(classes, start=1):
        combos = parse_range(name)
        shares = equity_vs_range(combos[0], RANDOM_HAND, [], TRIALS, SEED)
        rows.append({"hand": name, "combos": len(combos), "equity": round(shares[0], 6)})
        print(f"{index:3}/{len(classes)}  {name:4}  {shares[0]:.4f}", flush=True)

    rows.sort(key=lambda row: row["equity"], reverse=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    print(f"записано {len(rows)} классов в {OUT}")


if __name__ == "__main__":
    main()
