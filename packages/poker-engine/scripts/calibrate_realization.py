"""Подбор `κ`, `λ` реализации по эталону T2 (спека модели колла, §6.2–§6.4; план 6, Задача 3).

Сетка `κ ∈ {0.00, 0.05, …, 0.60}`, `λ ∈ {0, 0.02, 0.05, 0.08}`. На каждом узле сетки решаются по
фишкам деревья всех точек T2 файла `tests/data/mtt_reference.json` (роли `calibration` и
`holdout`) — стол, доли, метрика и допуски те же, что у теста T2 (`tests/test_mtt_reference.py`).
Константы `realization` подменяются на время вызова, модуль не меняется.

Цель — сумма квадратов отклонений точек `calibration` в п.п. Правило выбора — §6.2 среди узлов,
где проходят допуски §6.3 всех точек T2 (решение пользователя по стопу Фазы 3b, вариант A):
наименьшая цель; `λ ≠ 0` берётся, только если снижает корень средней цели не меньше чем на 1 п.п.
против лучшего `λ = 0`; при равенстве — меньший `κ`. Нет проходящего узла с `λ = 0` — выбора нет
(стоп §6.4).

`--cap C` — запасная форма §6.4: `s = 1 + κ · min(SPR, C)`; матрица реализации подменяется в
процессах подбора, движок формы с насыщением не знает.

Вывод — Markdown: сетка (корень средней цели, п.п., и число точек вне допуска), лучшие узлы по
всей сетке и среди проходящих, выбор по правилу; отклонение каждой точки у выбора, у лучшего
проходящего `λ ≠ 0` и у лучших по всей сетке; у выбора — ещё точки вне теста T2 (роли
`holdout_sb_limp` и `holdout_cold_call`, кроме метрики `limp`), справочно. Узел, где хоть одно
равновесие не сошлось, помечен `*`.

Узлы сетки решаются параллельно, по процессу на ядро; `numpy` — в один поток: матрицы 169 × 169
малы, а потоки BLAS нескольких процессов только мешают друг другу.

Запуск из `packages/poker-engine`: `.venv/bin/python scripts/calibrate_realization.py [--cap C]`.
"""

from __future__ import annotations

import os

for _variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_variable, "1")

import argparse  # noqa: E402
import math  # noqa: E402
import pathlib  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402
from functools import lru_cache  # noqa: E402

import numpy  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tests"))

from test_mtt_reference import (  # noqa: E402
    TOLERANCE_PP,
    deviation,
    load_points,
    model_value,
    solve_point,
    tolerance,
    tree_key,
)

from poker_engine import allin_matrix, realization  # noqa: E402

KAPPAS = [round(0.05 * i, 2) for i in range(13)]
LAMBDAS = [0.0, 0.02, 0.05, 0.08]
SIMPLER_BY_PP = 1.0
OUTSIDE = ("holdout_sb_limp", "holdout_cold_call")
_MATRIX = realization.matrix


@lru_cache(maxsize=512)
def _capped(spr: float, in_position: bool, kappa: float, lam: float, cap: float) -> numpy.ndarray:
    """Матрица запасной формы §6.4; зажим и `σ` — как в `realization.win_probability`."""
    e = numpy.clip(allin_matrix.equity_matrix(), 1e-9, 1.0 - 1e-9)
    side = 1.0 if in_position else -1.0
    z = (1.0 + kappa * min(spr, cap)) * numpy.log(e / (1.0 - e)) + lam * spr * side
    return 0.5 * (1.0 + numpy.tanh(0.5 * z))


def _models(task: tuple[list[dict], float, float, float | None]) -> tuple[list[float], bool]:
    """Метрика каждой точки и «все равновесия сошлись»; одно дерево на стол, глубину и героя.

    Выполняется в процессе пула: константы и матрица подменяются на весь процесс, поэтому каждая
    задача ставит свои заново.
    """
    points, kappa, lam, cap = task
    realization.REALIZATION_KAPPA, realization.REALIZATION_LAMBDA = kappa, lam
    realization.matrix = _MATRIX
    if cap is not None:
        realization.matrix = lambda spr, side: _capped(round(spr, 2), side, kappa, lam, cap)
    solved = {}
    for point in points:
        if tree_key(point) not in solved:
            solved[tree_key(point)] = solve_point(point)
    models = [model_value(point, solved[tree_key(point)].shares) for point in points]
    return models, all(result.converged for result in solved.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--cap", type=float, default=None, help="запасная форма §6.4")
    cap = parser.parse_args().cap

    points = load_points()
    tested = [point for point in points if point["role"] in TOLERANCE_PP]
    calibration = [i for i, point in enumerate(tested) if point["role"] == "calibration"]
    outside = [point for point in points if point["role"] in OUTSIDE and point["metric"] != "limp"]

    started = time.perf_counter()
    cells = [(kappa, lam) for kappa in KAPPAS for lam in LAMBDAS]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as pool:
        results = dict(zip(cells, pool.map(_models, [(tested, *cell, cap) for cell in cells])))
    elapsed = time.perf_counter() - started

    def offs(cell: tuple[float, float]) -> list[float]:
        return [deviation(m, point["value"]) for m, point in zip(results[cell][0], tested)]

    def target(cell: tuple[float, float]) -> float:
        return sum(offs(cell)[i] ** 2 for i in calibration)

    def rms(cell: tuple[float, float]) -> float:
        return math.sqrt(target(cell) / len(calibration))

    def misses(cell: tuple[float, float]) -> list[int]:
        return [i for i, off in enumerate(offs(cell)) if off > tolerance(tested[i])]

    def best(lams: list[float], among: list[tuple[float, float]]) -> tuple[float, float] | None:
        # Наименьшая цель, при равенстве — меньший `κ`.
        return min(
            (cell for cell in among if cell[1] in lams),
            key=lambda c: (target(c), c[0]),
            default=None,
        )

    passing = [cell for cell in cells if not misses(cell)]
    plain, shifted = best(LAMBDAS[:1], cells), best(LAMBDAS[1:], cells)
    gain = rms(plain) - rms(shifted)
    plain_ok, shifted_ok = best(LAMBDAS[:1], passing), best(LAMBDAS[1:], passing)
    if plain_ok is None:
        chosen = None
    elif shifted_ok is not None and rms(plain_ok) - rms(shifted_ok) >= SIMPLER_BY_PP:
        chosen = shifted_ok
    else:
        chosen = plain_ok

    form = "основная" if cap is None else f"запасная §6.4, CAP = {cap:g}"
    print(f"Форма — {form}. Сетка {len(KAPPAS)} × {len(LAMBDAS)}, точек T2 — {len(tested)} "
          f"(`calibration` — {len(calibration)}), {elapsed:.0f} с.\n")
    print("Корень средней цели, п.п. (в скобках — точек вне допуска §6.3):\n")
    print("| κ | " + " | ".join(f"λ = {lam:g}" for lam in LAMBDAS) + " |")
    print("|---|" + "---|" * len(LAMBDAS))
    for kappa in KAPPAS:
        row = (
            f"{rms((kappa, lam)):.2f} ({len(misses((kappa, lam)))})"
            + ("" if results[kappa, lam][1] else "*")
            for lam in LAMBDAS
        )
        print(f"| {kappa:.2f} | " + " | ".join(row) + " |")

    def verdict(cell: tuple[float, float]) -> str:
        missed = [tested[i]["id"] for i in misses(cell)]
        return "проходят" if not missed else "не проходят: " + ", ".join(missed)

    def name(cell: tuple[float, float]) -> str:
        return f"κ = {cell[0]:.2f}, λ = {cell[1]:g}"

    print(f"\nЛучший λ = 0 по всей сетке: κ = {plain[0]:.2f}, корень {rms(plain):.2f} п.п.; "
          f"допуски {verdict(plain)}.")
    print(f"Лучший λ ≠ 0 по всей сетке: {name(shifted)}, корень {rms(shifted):.2f} п.п. "
          f"(выигрыш {gain:.2f} п.п.); допуски {verdict(shifted)}.")
    print("Узлы, где допуски проходят: "
          + (", ".join(name(cell) for cell in passing) or "нет") + ".")
    if plain_ok is not None:
        print(f"Среди них лучший λ = 0: κ = {plain_ok[0]:.2f}, корень {rms(plain_ok):.2f} п.п.")
    if shifted_ok is not None:
        line = f"Среди них лучший λ ≠ 0: {name(shifted_ok)}, корень {rms(shifted_ok):.2f} п.п."
        if plain_ok is not None:
            line += f" (выигрыш {rms(plain_ok) - rms(shifted_ok):.2f} п.п.)"
        print(line)
    if chosen is None:
        print("**Выбора нет: ни один узел с λ = 0 не проходит допуски — стоп §6.4.**\n")
    else:
        print(f"**Выбор по правилу: {name(chosen)}, корень {rms(chosen):.2f} п.п.**\n")

    columns = list(dict.fromkeys(c for c in (chosen, shifted_ok, plain, shifted) if c is not None))
    print("| Точка | Роль | Эталон | "
          + " | ".join(f"{name(cell)} | откл." for cell in columns) + " | допуск |")
    print("|---|---|---|" + "---|---|" * len(columns) + "---|")
    for i, point in enumerate(tested):
        cells_text = " | ".join(
            f"{results[cell][0][i]:.1f} | {offs(cell)[i]:.1f}" for cell in columns
        )
        print(f"| {point['id']} | {point['role']} | {point['value']} | {cells_text} | "
              f"{tolerance(point):g} |")

    reference = chosen or plain
    print(f"\nВне теста T2, у {name(reference)} (справочно):\n")
    print("| Точка | Роль | Эталон | Модель |")
    print("|---|---|---|---|")
    with ProcessPoolExecutor(max_workers=1) as pool:
        models, _ = pool.submit(_models, (outside, *reference, cap)).result()
    for point, model in zip(outside, models):
        print(f"| {point['id']} | {point['role']} | {point['value']} | {model:.1f} |")


if __name__ == "__main__":
    main()
