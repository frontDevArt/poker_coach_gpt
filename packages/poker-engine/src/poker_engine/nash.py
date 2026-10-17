"""Солвер push/fold: равновесие fictitious play на таблице эквити класс против класса.

О столе не знает: вход — выплаты исходов подыгры (`pushfold_game.Outcomes`) и число
отвечающих, единицы выплат — любые (BB по фишкам, доллары по ICM). Игрок 0 — открывающий
(олл-ин или фолд), `1..m` — отвечающие по порядку хода (колл или фолд); первый колл закрывает
действие (спека плана 4, §5.1–5.4).

**Модель EV.** Классы рук — строки и столбцы `allin_matrix`: `e[h, x]` — доля банка класса
`h` против `x`, `w[h, x]` — число совместимых пар комбинаций. Блокеры только попарные: рука
открывающего меняет распределение каждого отвечающего, но отвечающие друг на друга не влияют.
Для класса открывающего `h` вероятность колла отвечающего `i` — `q_i(h) = Σ_x call_i[x]·w[h, x]
/ Σ_x w[h, x]`, колла и победы открывающего — `a_i(h)` с весом `w·e`. Отвечающий с классом `x`
видит класс открывающего с вероятностью `∝ push[h]·w[h, x]`; фолды отвечающих перед ним этого
распределения не меняют (это и есть отказ от блокеров троих).

Значение «действие дошло до отвечающего `l`» считается с конца: `G = steal`, затем для
`l = m − 1 … start` — `G ← a_l·win[l] + (q_l − a_l)·lose[l] + (1 − q_l)·G`. Пуш открывающего —
`G` с `start = 0` по его выплатам, фолд отвечающего `k` — с `start = k + 1` по выплатам `k`.

**Fictitious play.** На шаге `t` каждый игрок берёт чистый лучший ответ на текущие средние
стратегии остальных, средние сдвигаются на `2·(BR − σ)/(t + 3)` — линейное усреднение, шаг `t`
весит `t + 1`. Классическое `1/(t + 2)` из плана сходится как `C/t` и на 6-max по фишкам
требует ~11 000 шагов (11 с), линейное — 200 (0.2 с); замер — журнал плана 4, Фаза 3. Старт —
все частоты 0.5. При равенстве EV (до `1e-12` наибольшей по модулю выплаты: суммы в разном
порядке расходятся в последнем знаке) лучший ответ — фолд. Эксплуатируемость — наибольший по
игрокам выигрыш `Σ_x prior(x)·(max EV(x) − EV_σ(x))`, `prior(x)` — доля комбинаций класса из
1326; EV отвечающего — условное, при пуше перед ним. Проверяется каждые 10 шагов и на
последнем.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy

from . import allin_matrix
from ._checks import check_positive
from .pushfold_game import Outcomes

__all__ = [
    "EPS_CHIP_BB",
    "EPS_ICM_SHARE",
    "MAX_ITERATIONS",
    "Equilibrium",
    "Game",
    "exploitability",
    "opener_ev",
    "range_share",
    "responder_ev",
    "solve",
]

# Калибровка, а не результат расчёта (план 4, Задача 3, шаг 6).
MAX_ITERATIONS = 2000
EPS_CHIP_BB = 1e-3
# Доля денег в игре — призов мест `1..playersLeft` лесенки, по которой считан ICM.
EPS_ICM_SHARE = 1e-6

_CHECK_EVERY = 10
# Относительный допуск равенства EV: шум суммирования, а не стратегия.
_TIE = 1e-12


@dataclass(frozen=True)
class Game:
    """Подыгра для солвера: выплаты исходов и число отвечающих `m`."""

    outcomes: Outcomes
    responders: int

    def __post_init__(self) -> None:
        for rows in (self.outcomes.win, self.outcomes.lose):
            if len(rows) != self.responders:
                raise ValueError(f"выплат на {len(rows)} отвечающих, а в игре {self.responders}")


@dataclass(frozen=True)
class Equilibrium:
    """Средние стратегии fictitious play: `push` `(169,)`, `call` `(m, 169)` — частоты."""

    push: numpy.ndarray
    call: numpy.ndarray
    exploitability: float
    iterations: int
    converged: bool


@dataclass(frozen=True)
class _Payoffs:
    steal: numpy.ndarray  # (m + 1,)
    walk: numpy.ndarray  # (m + 1,)
    win: numpy.ndarray  # (m, m + 1)
    lose: numpy.ndarray  # (m, m + 1)
    tie: float  # разница EV, ниже которой действия равны


@lru_cache(maxsize=1)
def _tables() -> tuple[numpy.ndarray, numpy.ndarray, numpy.ndarray, numpy.ndarray]:
    """`e`, `w`, `w·e` и `prior` — один раз на процесс."""
    equity = allin_matrix.equity_matrix()
    weight = allin_matrix.weight_matrix().astype(numpy.float64)
    prior = numpy.array([allin_matrix.combos_of(name) for name in allin_matrix.CLASSES]) / 1326
    return equity, weight, weight * equity, prior


def _payoffs(game: Game) -> _Payoffs:
    o = game.outcomes
    steal = numpy.asarray(o.steal, dtype=numpy.float64)
    walk = numpy.asarray(o.walk, dtype=numpy.float64)
    win = numpy.asarray(o.win, dtype=numpy.float64).reshape(game.responders, -1)
    lose = numpy.asarray(o.lose, dtype=numpy.float64).reshape(game.responders, -1)
    scale = max(numpy.abs(rows).max() for rows in (steal, walk, win, lose))
    return _Payoffs(steal=steal, walk=walk, win=win, lose=lose, tie=_TIE * float(scale))


def _call_odds(
    call: numpy.ndarray, weights: numpy.ndarray, weighted_equity: numpy.ndarray
) -> tuple[numpy.ndarray, numpy.ndarray]:
    """`q` и `a` `(m, K)` для `K` рук открывающего, заданных строками весов и `веса·эквити`."""
    total = weights.sum(axis=1)
    return (call @ weights.T) / total, (call @ weighted_equity.T) / total


def _reached(
    pay: _Payoffs, q: numpy.ndarray, a: numpy.ndarray, recipient: int, start: int
) -> numpy.ndarray:
    """Выплата `recipient`, когда действие дошло до отвечающего `start` (индекс 0..m−1)."""
    value = numpy.full(q.shape[1], pay.steal[recipient])
    for at in range(q.shape[0] - 1, start - 1, -1):
        value = (
            a[at] * pay.win[at, recipient]
            + (q[at] - a[at]) * pay.lose[at, recipient]
            + (1.0 - q[at]) * value
        )
    return value


@dataclass(frozen=True)
class _Facing:
    """Что видит отвечающий с рукой-столбцом: распределение класса открывающего при пуше.

    Общее для всех отвечающих (блокеры попарные), поэтому считается один раз на шаг.
    """

    reach: numpy.ndarray  # (169, K): push[h]·weights[h, x]
    total: numpy.ndarray  # (K,): Σ_h reach
    seen: numpy.ndarray  # (K,): до руки действие доходит
    share: numpy.ndarray  # (K,): 1, где доходит, иначе 0
    opener_share: numpy.ndarray  # (K,): доля банка открывающего, взвешенная reach


def _facing(push: numpy.ndarray, weights: numpy.ndarray, equity: numpy.ndarray) -> _Facing:
    """`weights`, `equity` — `(169, K)`; `equity[h, x]` — доля банка **открывающего**.

    Рука, против которой открывающий не пушит ни одной совместимой комбинацией, получает EV 0
    у обоих действий: до неё действие не доходит, и лучший ответ — фолд.
    """
    reach = push[:, None] * weights
    total = reach.sum(axis=0)
    seen = total > 0
    zeros = numpy.zeros_like(total)
    return _Facing(
        reach=reach,
        total=total,
        seen=seen,
        share=numpy.divide(total, total, out=zeros.copy(), where=seen),
        opener_share=numpy.divide(
            (reach * equity).sum(axis=0), total, out=zeros.copy(), where=seen
        ),
    )


def _responder_values(
    pay: _Payoffs, facing: _Facing, q: numpy.ndarray, a: numpy.ndarray, k: int
) -> tuple[numpy.ndarray, numpy.ndarray]:
    """EV колла и фолда отвечающего `k` (0..m−1) для рук-столбцов `facing`."""
    win, lose = pay.win[k, k + 1], pay.lose[k, k + 1]
    call_ev = facing.opener_share * win + (facing.share - facing.opener_share) * lose
    fold = _reached(pay, q, a, k + 1, k + 1)
    fold_ev = numpy.divide(
        fold @ facing.reach, facing.total, out=numpy.zeros_like(facing.total), where=facing.seen
    )
    return call_ev, fold_ev


def _values(
    pay: _Payoffs, push: numpy.ndarray, call: numpy.ndarray
) -> list[tuple[numpy.ndarray, numpy.ndarray]]:
    """EV действия и фолда каждого класса каждого игрока: `[0]` — пуш открывающего."""
    equity, weight, weighted, _ = _tables()
    q, a = _call_odds(call, weight, weighted)
    facing = _facing(push, weight, equity)
    values = [(_reached(pay, q, a, 0, 0), numpy.full(169, pay.walk[0]))]
    for k in range(call.shape[0]):
        values.append(_responder_values(pay, facing, q, a, k))
    return values


def _gap(values: list[tuple[numpy.ndarray, numpy.ndarray]], push, call) -> float:
    prior = _tables()[3]
    worst = 0.0
    for (act, fold), freq in zip(values, [push, *call]):
        played = freq * act + (1.0 - freq) * fold
        worst = max(worst, float(prior @ (numpy.maximum(act, fold) - played)))
    return worst


def solve(game: Game, eps: float, max_iterations: int = MAX_ITERATIONS) -> Equilibrium:
    """Равновесие fictitious play с эксплуатируемостью не больше `eps` (в единицах выплат)."""
    check_positive(eps, "допуск равновесия")
    check_positive(max_iterations, "предел итераций")
    pay = _payoffs(game)
    push = numpy.full(169, 0.5)
    call = numpy.full((game.responders, 169), 0.5)
    iterations = 0
    while True:
        values = _values(pay, push, call)
        if iterations == max_iterations or (iterations and iterations % _CHECK_EVERY == 0):
            gap = _gap(values, push, call)
            if gap <= eps or iterations == max_iterations:
                break
        step = 2.0 / (iterations + 3)
        best = [act > fold + pay.tie for act, fold in values]
        push = push + (best[0] - push) * step
        call = call + (numpy.array(best[1:], dtype=numpy.float64) - call) * step
        iterations += 1
    return Equilibrium(
        push=push,
        call=call,
        exploitability=gap,
        iterations=iterations,
        converged=gap <= eps,
    )


def opener_ev(
    game: Game, call: numpy.ndarray, weights: numpy.ndarray, equity: numpy.ndarray
) -> tuple[float, float]:
    """EV пуша и фолда открывающего с рукой: строка весов и строка эквити против классов."""
    pay = _payoffs(game)
    weights = numpy.asarray(weights, dtype=numpy.float64)[None, :]
    q, a = _call_odds(numpy.asarray(call), weights, weights * numpy.asarray(equity)[None, :])
    return float(_reached(pay, q, a, 0, 0)[0]), float(pay.walk[0])


def responder_ev(
    game: Game,
    push: numpy.ndarray,
    call: numpy.ndarray,
    j: int,
    weights: numpy.ndarray,
    equity: numpy.ndarray,
) -> tuple[float, float]:
    """EV колла и фолда отвечающего `j` (1..m) с рукой.

    `weights[h]` — совместимые комбинации класса открывающего `h`, `equity[h]` — доля банка
    руки отвечающего против класса `h`.
    """
    pay = _payoffs(game)
    _, weight, weighted, _ = _tables()
    q, a = _call_odds(numpy.asarray(call), weight, weighted)
    column = numpy.asarray(weights, dtype=numpy.float64)[:, None]
    opener_equity = 1.0 - numpy.asarray(equity, dtype=numpy.float64)[:, None]
    facing = _facing(numpy.asarray(push, dtype=numpy.float64), column, opener_equity)
    call_ev, fold_ev = _responder_values(pay, facing, q, a, j - 1)
    return float(call_ev[0]), float(fold_ev[0])


def exploitability(game: Game, push: numpy.ndarray, call: numpy.ndarray) -> float:
    """Наибольший выигрыш одного игрока от лучшего ответа, в единицах выплат."""
    push, call = numpy.asarray(push), numpy.asarray(call)
    return _gap(_values(_payoffs(game), push, call), push, call)


def range_share(freq: numpy.ndarray) -> float:
    """Доля диапазона из 1326 комбинаций, взвешенная частотой."""
    return float(_tables()[3] @ numpy.asarray(freq, dtype=numpy.float64))
