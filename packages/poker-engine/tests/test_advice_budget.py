"""Приёмка плана: совет push/fold укладывается в две секунды, ICM — `2m + 2` раз."""

import time

from conftest import _context, pushfold_first_in_node
from poker_engine import icm_field
from poker_engine.advice import advise

BUDGET_SECONDS = 2.0


def test_advice_on_six_max_first_in_fits_the_budget():
    # `UTG` и пятеро отвечающих — самый дорогой спот 6-max: два решения по 2 + 5 стратегий.
    start = time.perf_counter()
    answer = advise(_context(), [pushfold_first_in_node()], [])
    elapsed = time.perf_counter() - start
    assert answer["advisor"] == "pushfold"
    assert elapsed < BUDGET_SECONDS, (
        f"совет занял {elapsed:.2f} с при бюджете {BUDGET_SECONDS} с"
    )


def test_icm_is_computed_once_per_outcome(monkeypatch):
    # Исходы: `steal`, `walk` и по `win`/`lose` на каждого из пяти отвечающих — 2·5 + 2.
    # ICM-эквити с головами и без строится на одних стеках исходов, повторно не считается.
    calls = []
    original = icm_field.table_equities

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(icm_field, "table_equities", counted)
    raw = pushfold_first_in_node()
    for seat in raw["seats"]:
        seat["bountyUsd"] = 10.0
    advise(_context(), [raw], [])
    assert len(calls) == 2 * 5 + 2
