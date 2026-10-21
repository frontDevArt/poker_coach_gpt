"""Реализация эквити колла без олл-ина по SPR (спека модели колла, §5).

Колл без олл-ина пары `(a, b)` заканчивается терминалом реализации: банк `P` (всё, что
забирает победитель, с мёртвыми деньгами) достаётся `a` с вероятностью

    p = σ(s · logit(e) + λ · SPR · d),   s = 1 + κ · SPR,   SPR = R / P,

`e` — эквити класса `a` против класса `b` по `allin_matrix`, `R` — меньший из остатков стеков
пары после колла, `d = +1`, если `a` ходит на флопе последним, иначе `−1`. Чем больше фишек за
банком, тем сильнее ставки постфлопа растягивают эквити: сильная рука забирает больше своей
доли, слабая — меньше; `λ` — перекос в пользу позиции. При `SPR = 0` терминал совпадает с
олл-ином (`p = e`).

Форма — калибровочная модель, а не постфлоп-расчёт: этап 6 заменяет `p` своим расчётом, не
трогая дерево. Эквити зажимается в `[1e-9, 1 − 1e-9]` до логита: у несовместимых пар классов
вес 0, а `nan` в матрице недопустим.
"""

from __future__ import annotations

from functools import lru_cache

import numpy

from . import allin_matrix

__all__ = [
    "REALIZATION_KAPPA",
    "REALIZATION_LAMBDA",
    "matrix",
    "win_probability",
]

# Калибровочные константы спеки §5.2, а не результат расчёта: калибровка по T2
# (`scripts/calibrate_realization.py`, `tests/data/mtt_reference.json`), журнал плана 6, Фазы
# 3b–3c. При `κ = λ = 0` модель равна вскрытию без ставок плана 5.
REALIZATION_KAPPA = 0.25
REALIZATION_LAMBDA = 0.0

_CLAMP = 1e-9


def win_probability(
    equity: numpy.ndarray, spr: float, in_position: bool, kappa: float, lam: float
) -> numpy.ndarray:
    """Вероятность, что `a` забирает банк терминала, по эквити `a` против `b` (формула §5.1)."""
    e = numpy.clip(numpy.asarray(equity, dtype=numpy.float64), _CLAMP, 1.0 - _CLAMP)
    side = 1.0 if in_position else -1.0
    z = (1.0 + kappa * spr) * numpy.log(e / (1.0 - e)) + lam * spr * side
    # `σ(z) = (1 + tanh(z / 2)) / 2` — без переполнения `exp` на зажатых краях.
    return 0.5 * (1.0 + numpy.tanh(0.5 * z))


def matrix(spr: float, in_position: bool) -> numpy.ndarray:
    """`(169, 169)`: вероятность победы класса открывшего (строка) против класса отвечающего
    (столбец) при константах модуля; `in_position` — открывший ходит на флопе последним.

    Кеш — по `(round(spr, 2), in_position, κ, λ)`; константы читаются при вызове.
    """
    return _matrix(round(spr, 2), in_position, REALIZATION_KAPPA, REALIZATION_LAMBDA)


@lru_cache(maxsize=256)
def _matrix(spr: float, in_position: bool, kappa: float, lam: float) -> numpy.ndarray:
    result = win_probability(allin_matrix.equity_matrix(), spr, in_position, kappa, lam)
    result.flags.writeable = False
    return result
