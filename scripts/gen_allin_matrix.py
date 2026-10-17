"""Считает эквити олл-ина на префлопе для каждой пары стартовых классов.

Запуск (из packages/poker-engine):

    .venv/Scripts/python ../../scripts/gen_allin_matrix.py

Результат перезаписывает src/poker_engine/data/allin_matrix.json: классы в порядке
`hand_classes()`, эквити `equity[a][b]` — доля банка класса `a` против `b` (ничья пополам) и
`weight[a][b]` — число совместимых упорядоченных пар (комбинация `a`, комбинация `b`) без общих
карт. Проверка воспроизводимости: `--pairs 10 --out <файл>` считает первые десять пар и пишет
их списком; два прогона с одним сидом дают один и тот же файл.

Веса — точный перебор. Эквити — Monte-Carlo, но стратифицированный по парам комбинаций: каждая
совместимая пара получает одинаковое число ранаутов `round(TRIALS / weight)`, поэтому вес пары
в оценке точный, а случайны только пять карт доски. Диагональ (класс против самого себя) равна
0.5 по симметрии и не считается.

Сид ОДИН на все пары, как в `gen_preflop_order.py`: доска тянется из 48 оставшихся карт, и при
общем сиде поток индексов у всех пар один и тот же — общие случайные числа. Разности соседних
клеток от этого точнее, чем маргинальная ошибка каждой.

Стандартная ошибка клетки не больше `0.5 / sqrt(n)`, где `n` — наименьшее число ранаутов на
клетку (дисперсия исхода с ничьей пополам не больше 1/4; стратификация её только уменьшает).
При TRIALS = 20 000 наименьшее n = 19 980 (32o против 42o: 108 пар × 185), граница 0.003537.

Цена полного прогона — 34.4 минуты (измерено 2026-10-18, Windows, Python 3.12.3: 14 196 пар
вне диагонали, ~0.15 с на пару). Разовая плата: JSON коммитится, тесты читают его готовым.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

from phevaluator import evaluate_cards

from poker_engine.equity import FULL_DECK, _EVAL_CARDS
from poker_engine.preflop import hand_classes
from poker_engine.ranges import parse_range

TRIALS = 20_000
SEED = 20261017
OUT = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "poker-engine"
    / "src"
    / "poker_engine"
    / "data"
    / "allin_matrix.json"
)


def _combos(name: str) -> list[tuple[str, str]]:
    return [(combo[:2], combo[2:]) for combo in parse_range(name)]


def _weight(first: list[tuple[str, str]], second: list[tuple[str, str]]) -> int:
    return sum(1 for x in first for y in second if not set(x) & set(y))


def _equity(first: list[tuple[str, str]], second: list[tuple[str, str]]) -> tuple[float, int]:
    """Эквити `first` против `second` и число ранаутов."""
    pairs = [(x, y) for x in first for y in second if not set(x) & set(y)]
    per_pair = max(1, round(TRIALS / len(pairs)))
    rng = random.Random(SEED)
    wins = 0.0
    for x, y in pairs:
        hero = [_EVAL_CARDS[card] for card in x]
        villain = [_EVAL_CARDS[card] for card in y]
        deck = [_EVAL_CARDS[card] for card in FULL_DECK if card not in x and card not in y]
        for _ in range(per_pair):
            board = rng.sample(deck, 5)
            ours = evaluate_cards(*hero, *board)
            theirs = evaluate_cards(*villain, *board)
            if ours < theirs:
                wins += 1.0
            elif ours == theirs:
                wins += 0.5
    runs = per_pair * len(pairs)
    return wins / runs, runs


def _write_rows(handle, key: str, rows: list[list]) -> None:
    handle.write(f' "{key}": [\n')
    for index, row in enumerate(rows):
        tail = "," if index < len(rows) - 1 else ""
        handle.write("  " + json.dumps(row, separators=(",", ":")) + tail + "\n")
    handle.write(" ]")


def main() -> None:
    # Итоговая строка русская, а перенаправленный stdout на Windows берёт кодировку консоли
    # и падает на кириллице. Тот же приём, что в cli.py: принудительный UTF-8.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=int, help="посчитать только первые N пар и выйти")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    classes = hand_classes()
    combos = [_combos(name) for name in classes]
    size = len(classes)
    started = time.perf_counter()

    if args.pairs is not None:
        cells = []
        for a in range(size):
            for b in range(a + 1, size):
                if len(cells) == args.pairs:
                    break
                share, runs = _equity(combos[a], combos[b])
                cells.append(
                    {"a": classes[a], "b": classes[b], "equity": round(share, 6), "runs": runs}
                )
        args.out.write_text(json.dumps(cells, indent=1) + "\n", encoding="utf-8")
        elapsed = time.perf_counter() - started
        print(f"{len(cells)} пар за {elapsed:.1f} с, {elapsed / len(cells):.3f} с на пару")
        return

    equity = [[0.5] * size for _ in range(size)]
    weight = [[_weight(combos[a], combos[b]) for b in range(size)] for a in range(size)]
    fewest_runs = math.inf
    total = size * (size - 1) // 2
    done = 0
    for a in range(size):
        for b in range(a + 1, size):
            share, runs = _equity(combos[a], combos[b])
            equity[a][b] = round(share, 6)
            equity[b][a] = round(1.0 - equity[a][b], 6)
            fewest_runs = min(fewest_runs, runs)
            done += 1
        elapsed = time.perf_counter() - started
        print(f"{done:5}/{total}  {classes[a]:4}  {elapsed / 60:.1f} мин", flush=True)
    # Граница ошибки — по наименьшему числу ранаутов среди посчитанных клеток.
    standard_error = round(0.5 / math.sqrt(fewest_runs), 6)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        handle.write("{\n")
        handle.write(f' "classes": {json.dumps(classes)},\n')
        handle.write(f' "trials": {TRIALS},\n')
        handle.write(f' "seed": {SEED},\n')
        handle.write(f' "standardError": {standard_error},\n')
        _write_rows(handle, "equity", equity)
        handle.write(",\n")
        _write_rows(handle, "weight", weight)
        handle.write("\n}\n")
    minutes = (time.perf_counter() - started) / 60
    print(f"записано {size}×{size} в {args.out} за {minutes:.1f} мин, ошибка {standard_error}")


if __name__ == "__main__":
    main()
