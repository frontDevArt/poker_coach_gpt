"""Приёмка плана: совет push/fold укладывается в две секунды, ICM — один пакет на подыгру."""

import time

import pytest

from conftest import (
    _context,
    pushfold_first_in_node,
    pushfold_first_in_node_8max,
    pushfold_first_in_node_9max,
)
from poker_engine import icm_field
from poker_engine.advice import advise

BUDGET_SECONDS = 2.0


def _assert_fits_the_budget(node):
    start = time.perf_counter()
    answer = advise(_context(), [node], [])
    elapsed = time.perf_counter() - start
    assert answer["advisor"] == "pushfold"
    assert elapsed < BUDGET_SECONDS, (
        f"совет занял {elapsed:.2f} с при бюджете {BUDGET_SECONDS} с"
    )


def test_advice_on_six_max_first_in_fits_the_budget():
    # `UTG` и пятеро отвечающих — самый дорогой спот 6-max: два решения по 2 + 5 стратегий.
    _assert_fits_the_budget(pushfold_first_in_node())


def test_advice_on_eight_max_first_in_fits_the_budget():
    # `UTG` и семеро отвечающих — самый дорогой спот 8-max (D27).
    _assert_fits_the_budget(pushfold_first_in_node_8max())


def test_advice_on_nine_max_first_in_fits_the_budget():
    # `UTG` и восьмеро отвечающих — самый дорогой спот 9-max (D27).
    _assert_fits_the_budget(pushfold_first_in_node_9max())


def test_icm_is_one_batch_per_subgame(monkeypatch):
    # Исходы: `steal`, `walk` и по `win`/`lose` на каждого из пяти отвечающих — 2·5 + 2
    # наборов стеков в одном пакетном вызове. ICM-эквити с головами и без строится на одних
    # стеках исходов, повторно не считается; одиночный `table_equities` не зовётся вовсе.
    batches = []
    original = icm_field.table_equities_batch

    def counted(tables, *args, **kwargs):
        batches.append(len(tables))
        return original(tables, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("одиночный table_equities в совете push/fold")

    monkeypatch.setattr(icm_field, "table_equities_batch", counted)
    monkeypatch.setattr(icm_field, "table_equities", forbidden)
    raw = pushfold_first_in_node()
    for seat in raw["seats"]:
        seat["bountyUsd"] = 10.0
    advise(_context(), [raw], [])
    assert batches == [2 * 5 + 2]
