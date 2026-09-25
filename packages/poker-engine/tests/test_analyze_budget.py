"""Приёмка плана: разбор укладывается в две секунды, ICM считается трижды."""

import copy
import time

import pytest

from poker_engine import icm_field
from poker_engine.analyze import analyze

BUDGET_SECONDS = 2.0


def test_a_full_analysis_fits_the_budget(analyze_context, analyze_node):
    start = time.perf_counter()
    analyze(analyze_context, [analyze_node])
    elapsed = time.perf_counter() - start
    assert elapsed < BUDGET_SECONDS, (
        f"разбор занял {elapsed:.2f} с при бюджете {BUDGET_SECONDS} с"
    )


@pytest.fixture
def icm_calls(monkeypatch):
    """Счётчик вызовов `table_equities` за разбор."""
    calls = []
    original = icm_field.table_equities

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(icm_field, "table_equities", counted)
    return calls


def _bubble(context, node, refund, payouts=None):
    """Бабл: девять живых на шесть оплачиваемых мест, возврат бай-ина."""
    context = copy.deepcopy(context)
    context["placesPaid"] = 6
    context["bubbleRefundUsd"] = refund
    if payouts is not None:
        context["payouts"] = payouts
    node = copy.deepcopy(node)
    node["playersLeft"] = 9
    node["heroRank"] = 9
    return context, node


def test_the_icm_half_of_the_budget_is_spent_three_times_not_seven(
    analyze_context, analyze_node, icm_calls
):
    # Эквити героя сейчас, после выигрыша и после проигрыша олл-ина — три
    # ветви, и каждая считается один раз на эквити, риск-премию и bubble
    # factor разом (долг D7).
    result = analyze(analyze_context, [analyze_node], trials=200, seed=1)
    assert "riskPremium" in result
    assert len(icm_calls) <= 3, f"ICM посчитан {len(icm_calls)} раз вместо трёх"


def test_without_a_villain_the_icm_is_computed_once(
    analyze_context, analyze_node, icm_calls
):
    node = copy.deepcopy(analyze_node)
    for seat in node["seats"]:
        seat["inHand"] = seat["isHero"]
    analyze(analyze_context, [node], trials=200, seed=1)
    assert len(icm_calls) == 1


def test_bubble_protection_costs_three_calls_per_ladder(
    analyze_context, analyze_node, icm_calls
):
    # С защитой на баббле давление считается и по лесенке лобби, чтобы
    # показать риск-премию без возврата (долг D20): по три вызова на
    # лесенку, шесть на разбор.
    context, node = _bubble(analyze_context, analyze_node, 6.60)
    result = analyze(context, [node], trials=200, seed=1)
    assert "riskPremiumWithoutRefund" in result["bubbleProtection"]
    assert len(icm_calls) <= 6, f"ICM посчитан {len(icm_calls)} раз вместо шести"


def test_undefined_pressure_costs_one_more_call_for_the_equity(
    analyze_context, analyze_node, icm_calls
):
    # Возврат больше минимального приза: давление с возвратом не определено,
    # отказ уносит эквити героя, и оно считается ещё раз — 3 + 1 по
    # удлинённой лесенке и 3 по лесенке лобби.
    context, node = _bubble(
        analyze_context, analyze_node, 6.60, [{"from": 1, "to": 6, "amount": 5.0}]
    )
    result = analyze(context, [node], trials=200, seed=1)
    assert "icm_pressure_undefined" in result["flags"]
    assert len(icm_calls) <= 7, f"ICM посчитан {len(icm_calls)} раз вместо семи"
