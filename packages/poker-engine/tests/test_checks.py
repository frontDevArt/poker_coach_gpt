"""Общие скалярные гарды `_checks.py`."""

import math

import pytest

from poker_engine._checks import (
    check_integer,
    check_non_negative,
    check_positive,
)


def test_integer_passes_check_integer():
    check_integer(0, "размер призовой зоны")
    check_integer(144, "размер призовой зоны")


@pytest.mark.parametrize(
    ("value", "shown"),
    [(True, "True"), (False, "False"), (2.0, "2.0"), ("3", "'3'")],
)
def test_non_integer_is_rejected_by_check_integer(value, shown):
    # bool — подкласс int, но размер призовой зоны True — ошибка вызова;
    # 2.0 и "3" — не целые, даже если равны целому.
    with pytest.raises(
        ValueError, match=f"размер призовой зоны должен быть целым, получено {shown}$"
    ):
        check_integer(value, "размер призовой зоны")


def test_nan_is_rejected_by_check_positive():
    # `nan <= 0` ложно: прямое сравнение пропустило бы NaN.
    with pytest.raises(ValueError, match="банк должен быть > 0, получено nan$"):
        check_positive(math.nan, "банк")


def test_negative_infinity_is_rejected_by_check_positive():
    with pytest.raises(ValueError, match="банк должен быть > 0, получено -inf$"):
        check_positive(-math.inf, "банк")


def test_infinity_is_rejected_by_check_positive():
    with pytest.raises(ValueError, match="банк не может быть бесконечным: inf$"):
        check_positive(math.inf, "банк")


def test_nan_is_rejected_by_check_non_negative():
    with pytest.raises(
        ValueError, match="размер колла не может быть отрицательным: nan$"
    ):
        check_non_negative(math.nan, "размер колла")


def test_negative_infinity_is_rejected_by_check_non_negative():
    with pytest.raises(
        ValueError, match="размер колла не может быть отрицательным: -inf$"
    ):
        check_non_negative(-math.inf, "размер колла")


def test_infinity_is_rejected_by_check_non_negative():
    with pytest.raises(
        ValueError, match="размер колла не может быть бесконечным: inf$"
    ):
        check_non_negative(math.inf, "размер колла")


def test_huge_integer_is_finite_for_both_guards():
    # `math.isfinite(10**400)` бросил бы OverflowError; гард сравнивает
    # с `math.inf`, и огромное целое проходит как обычное число.
    check_positive(10**400, "размер призовой зоны")
    check_non_negative(10**400, "размер колла")


def test_boundaries_of_both_guards():
    check_non_negative(0, "размер колла")
    with pytest.raises(ValueError, match="банк должен быть > 0, получено 0$"):
        check_positive(0, "банк")
