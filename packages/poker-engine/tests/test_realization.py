"""Модель реализации эквити: инварианты 5–8 спеки модели колла §10 и Review Focus 1–2 плана 6.

Все ожидания — на бумаге: `σ(logit(e)) = e`, `σ(0) = 0.5`, `σ(−z) = 1 − σ(z)`.
"""

import warnings

import numpy
import pytest

from poker_engine import allin_matrix, realization
from poker_engine.realization import matrix, win_probability

EQUITY = numpy.array([0.1, 0.3, 0.5, 0.62, 0.75, 0.9])


@pytest.mark.parametrize(("kappa", "lam"), [(0.0, 0.0), (0.4, 0.0), (1.0, 0.1)])
@pytest.mark.parametrize("in_position", [True, False])
def test_zero_spr_is_the_allin(kappa, lam, in_position):
    # Инвариант 5: за банком ничего — терминал совпадает с олл-ином.
    p = win_probability(EQUITY, 0.0, in_position, kappa, lam)
    assert p == pytest.approx(EQUITY, abs=1e-12)


@pytest.mark.parametrize("spr", [0.0, 0.7, 3.0, 12.0])
def test_a_coin_flip_stays_a_coin_flip(spr):
    # Инвариант 5: `e = 0.5`, `λ = 0` — `logit = 0` при любом растяжении.
    assert win_probability(numpy.array([0.5]), spr, True, 0.8, 0.0)[0] == pytest.approx(0.5)


@pytest.mark.parametrize("spr", [0.5, 2.0, 9.0])
def test_complement_without_position_shift(spr):
    # Инвариант 6 при `λ = 0`: `p(e) + p(1 − e) = 1`.
    p = win_probability(EQUITY, spr, True, 0.6, 0.0)
    q = win_probability(1.0 - EQUITY, spr, True, 0.6, 0.0)
    assert p + q == pytest.approx(numpy.ones_like(EQUITY), abs=1e-12)


@pytest.mark.parametrize("spr", [0.5, 2.0, 9.0])
def test_complement_with_position_shift(spr):
    # Инвариант 6 с `λ`: соперник видит ту же раздачу из другой позиции, `d → −d`.
    p = win_probability(EQUITY, spr, True, 0.6, 0.07)
    q = win_probability(1.0 - EQUITY, spr, False, 0.6, 0.07)
    assert p + q == pytest.approx(numpy.ones_like(EQUITY), abs=1e-12)


def test_monotone_in_equity():
    # Инвариант 7: `p` растёт по `e` при любой позиции.
    grid = numpy.linspace(0.01, 0.99, 99)
    for in_position in (True, False):
        p = win_probability(grid, 4.0, in_position, 0.5, 0.05)
        assert numpy.all(numpy.diff(p) > 0)


def test_stretch_favours_the_stronger_hand():
    # Инвариант 7: `λ = 0`, `κ ≥ 0`, `e > 0.5` — `p ≥ e` и не убывает по SPR.
    strong = EQUITY[EQUITY > 0.5]
    previous = strong
    for spr in (0.0, 0.5, 1.0, 3.0, 10.0):
        p = win_probability(strong, spr, False, 0.3, 0.0)
        assert numpy.all(p >= strong - 1e-12)
        assert numpy.all(p >= previous - 1e-12)
        previous = p


def test_paper_point():
    # Инвариант 8: `κ = 1`, `SPR = 1` — `s = 2`, шансы `(0.75 / 0.25)² = 9`, `p = 9 / 10`.
    p = win_probability(numpy.array([0.75]), 1.0, True, 1.0, 0.0)
    assert p[0] == pytest.approx(0.9, abs=1e-12)


def test_position_shift_sign():
    # `d = +1` в позиции: при `e = 0.5` сдвиг `λ · SPR` целиком в пользу позиции.
    ip = win_probability(numpy.array([0.5]), 2.0, True, 0.0, 0.1)[0]
    oop = win_probability(numpy.array([0.5]), 2.0, False, 0.0, 0.1)[0]
    assert ip == pytest.approx(1.0 / (1.0 + numpy.exp(-0.2)))
    assert oop == pytest.approx(1.0 - ip)


def test_almost_no_chips_behind(monkeypatch):
    # Review Focus 1: колл 3-бета почти на весь стек, за банком 0.1 BB при банке ~40 —
    # `p` в пределах 1e-6 от `e`, без `nan`.
    monkeypatch.setattr(realization, "REALIZATION_KAPPA", 0.5)
    monkeypatch.setattr(realization, "REALIZATION_LAMBDA", 0.1)
    raw = allin_matrix.equity_matrix()
    p = matrix(0.1 / 40.2, True)
    assert numpy.isfinite(p).all()
    weight = allin_matrix.weight_matrix() > 0
    assert numpy.abs(p - raw)[weight].max() <= 1e-6


def test_zero_weight_pairs_stay_finite(monkeypatch):
    # Review Focus 2: эквити 0 или 1 (несовместимые пары) — зажим до логита: ни `nan`, ни
    # деления на ноль в логите (предупреждение numpy здесь — ошибка).
    monkeypatch.setattr(realization, "REALIZATION_KAPPA", 2.0)
    monkeypatch.setattr(realization, "REALIZATION_LAMBDA", 0.3)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        edge = win_probability(numpy.array([0.0, 1.0]), 20.0, False, 2.0, 0.3)
        assert numpy.isfinite(matrix(20.0, False)).all()
    assert numpy.isfinite(edge).all()
    assert 0.0 <= edge[0] < edge[1] <= 1.0


def test_matrix_orientation_and_complement(monkeypatch):
    # Строка — открывший, столбец — отвечающий: `M(d)[h, x] + M(−d)[x, h] = 1`, как у сырой.
    monkeypatch.setattr(realization, "REALIZATION_KAPPA", 0.4)
    monkeypatch.setattr(realization, "REALIZATION_LAMBDA", 0.05)
    raw = allin_matrix.equity_matrix()
    weight = allin_matrix.weight_matrix() > 0
    assert numpy.abs(raw + raw.T - 1.0)[weight].max() <= 1e-9
    ip, oop = matrix(3.0, True), matrix(3.0, False)
    assert numpy.abs(ip + oop.T - 1.0)[weight].max() <= 1e-9
    aa, ak = allin_matrix.class_index("AA"), allin_matrix.class_index("AKs")
    assert ip[aa, ak] > raw[aa, ak]


def test_cache_key_has_the_constants(monkeypatch):
    # Кеш по `(SPR, позиция, κ, λ)`: смена константы даёт другую матрицу, а не старую из кеша.
    plain = matrix(2.0, True)
    monkeypatch.setattr(realization, "REALIZATION_KAPPA", 0.5)
    stretched = matrix(2.0, True)
    monkeypatch.setattr(realization, "REALIZATION_KAPPA", 0.0)
    monkeypatch.setattr(realization, "REALIZATION_LAMBDA", 0.1)
    shifted = matrix(2.0, True)
    assert not numpy.allclose(plain, stretched)
    assert not numpy.allclose(plain, shifted)
    assert matrix(2.004, True) is matrix(2.0, True)  # SPR — до двух знаков
    assert not matrix(2.0, True).flags.writeable
