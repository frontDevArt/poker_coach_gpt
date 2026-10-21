"""Солвер дерева префлопа: CFR+ по 169 классам на каждом узле решения (спека плана 5, §6.8).

О столе не знает: вход — дерево `preflop_tree.Tree` и выплаты его терминалов по номеру узла
(`chip_payoffs` или `icm_payoffs`), единицы выплат — любые (BB по фишкам, доллары по ICM).

**Строение дерева.** Участник 0 — открывший, корень — его решение. Действие корня ведёт либо в
терминал (фолд — банк большому блайнду, `check` — терминал реализации с лимпером), либо в
**цепочку** отвечающих: узел отвечающего `k`, его фолд — узел `k + 1` или терминал «все
сфолдили», любое другое действие — **пара** `(0, k)`: поддерево, где ходят только 0 и `k`.

**Модель EV — та же, что у `nash` плана 4.** Блокеры попарные: класс открывшего `h` меняет
распределение каждого отвечающего, `x ∝ f_k(x)·w[h, x]`, но отвечающие друг на друга не влияют;
`f_k` — заданный диапазон лимпера (`Tree.fixed_ranges`), у остальных 1. Для открывшего
вероятность фолда отвечающего `k` — `Σ_x f_k·w[h, x]·σ_k(fold)[x] / Σ_x f_k·w[h, x]`, значение
пары — то же среднее по `x` с достижимостью `k` внутри пары. Отвечающий с классом `x` видит класс
открывшего с весом `w[h, x]`, умноженным на достижимость открывшего; фолды отвечающих перед ним
этого распределения не меняют — ровно отказ от блокеров троих в `nash`. Значение фолда
отвечающего — выплата ему, когда действие дошло до следующего, по классу открывшего.

**Матрицы исходов.** У пары вес исхода «выиграл открывший» по классам `(h, x)` — сырая эквити
`allin_matrix` на олл-ине (матрица 0) и `realization.matrix(spr, позиция)` на терминале реализации
(спека модели колла §5.3); терминалы пар группируются по паре «ключ весов отвечающего, номер
матрицы», и всё, что ниже, умножает на `w` матрицу своей группы вместо `e`.

**CFR+.** Сожаления обрезаются снизу нулём, стратегия — их доли (нет положительных — поровну).
Сожаления открывшего в паре `(0, k)` — по его значениям при входе `k`, без вероятности фолдов
отвечающих до `k`: при попарных блокерах игра пары от этих фолдов не зависит, они лишь
множитель всех её значений по классу открывшего. С множителем (контрфактический вес CFR)
6-max `open` UTG 25 BB сходится за 270 итераций, без него — за 110 (замер в журнале плана 5,
Фаза 6); результат в обоих случаях проверяет независимая эксплуатируемость. Обновления
чередуются: сначала открывший, затем все отвечающие против стратегии открывшего после его
шага. Средняя стратегия — квадратичное усреднение: шаг `t` весит `t²`, умноженное на
свою достижимость узла (план писал линейное `t`; квадратичное на тех же деревьях сходится за
0.55–0.65 итераций линейного — замер в журнале плана 5, Фаза 5). Старт — поровну. Лимп
лимпера сыгран до дерева: «войти» задано диапазоном `f_k`, а ответ на изоляцию внутри этого
диапазона решается равновесием (§6.6).

**Эксплуатируемость** — наибольший выигрыш одного игрока от лучшего ответа на среднюю
стратегию, в единицах выплат. Открывший — `Σ_h prior(h)·(BR(h) − EV(h))`, `prior` — доля
комбинаций класса из 1326. Отвечающий — то же по его классам, EV — условное, при входе
открывшего в банк (действие корня, ведущее в цепочку), как у `nash`; у лимпера `prior` взвешен
его диапазоном. На дереве push/fold она совпадает с `nash.exploitability` (инвариант 6).
Проверка — каждые 10 шагов и на последнем. Лучший ответ здесь — только значение, наибольшее
по действиям: у CFR+ нет шага к лучшему ответу, и выбор между равными на результат не влияет.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy

from . import allin_matrix, realization
from ._checks import check_positive
from .preflop_tree import Decision, Terminal, Tree

__all__ = [
    "MAX_ITERATIONS",
    "Solution",
    "action_values",
    "exploitability",
    "reach",
    "solve",
]

# Калибровка, а не результат расчёта (план 5, Задача 5).
MAX_ITERATIONS = 3000

_CHECK_EVERY = 10


@dataclass(frozen=True)
class Solution:
    """Средние стратегии CFR+: узел решения → частоты `(действия, 169)`."""

    strategy: dict[int, numpy.ndarray]
    exploitability: float
    iterations: int
    converged: bool


@lru_cache(maxsize=1)
def _tables() -> tuple[numpy.ndarray, numpy.ndarray, numpy.ndarray]:
    """`e`, `w` и `prior` — один раз на процесс; `w` симметрична."""
    equity = allin_matrix.equity_matrix()
    weight = allin_matrix.weight_matrix().astype(numpy.float64)
    prior = numpy.array([allin_matrix.combos_of(name) for name in allin_matrix.CLASSES]) / 1326
    return equity, weight, prior


@dataclass(frozen=True)
class _Shape:
    """Дерево, разобранное на корень, цепочки и пары; выплаты терминалов — по исходу пары."""

    nodes: int
    players: int
    root: int
    decisions: tuple[int, ...]  # по возрастанию: родитель раньше потомков
    owner: tuple[int, ...]  # игрок узла решения, у терминала −1
    children: tuple[tuple[int, ...], ...]
    responder: tuple[int, ...]  # `k` цепочки или пары узла, у корня и свободных терминалов 0
    chain: tuple[bool, ...]  # узел — решение отвечающего в цепочке
    fold: tuple[int, ...]  # у узла цепочки — индекс фолда
    head: tuple[int, ...]  # у узла пары — узел цепочки (или корень), из которого она растёт
    chains: tuple[tuple[tuple[int, ...], int], ...]  # узлы цепочки и терминал «все сфолдили»
    terms: numpy.ndarray  # терминалы пар, в том числе вскрытие корня с лимпером
    pair_of: numpy.ndarray  # `k` каждого терминала пары
    matrices: tuple[numpy.ndarray, ...]  # вероятность победы открывшего `(169, 169)`, 0 — сырая
    # позиции в `terms`: по ключу весов, по паре «ключ весов, номер матрицы», по номеру матрицы
    by_key: tuple[tuple[int | None, numpy.ndarray], ...]
    groups: tuple[tuple[tuple[int | None, int], numpy.ndarray], ...]
    by_matrix: tuple[tuple[int, numpy.ndarray], ...]
    hung: dict[int, numpy.ndarray]  # узел цепочки → позиции в `terms` его пар
    free: tuple[int, ...]  # фолд корня и «все сфолдили»
    opener_wins: numpy.ndarray  # (узлы, игроки): выплаты, когда пару выиграл открывший
    other_wins: numpy.ndarray  # (узлы, игроки): когда выиграл `k`; у фолда — тот же ряд
    fixed: dict[int, numpy.ndarray]


def _key(fixed: dict[int, numpy.ndarray], k: int) -> int | None:
    """Ключ весов отвечающего `k`: свой у заданного диапазона, общий `None` у остальных."""
    return k if k in fixed else None


def _shape(tree: Tree, payoffs: list[numpy.ndarray | None]) -> _Shape:
    count, players = len(tree.nodes), len(tree.players)
    owner = [-1] * count
    children: list[tuple[int, ...]] = [()] * count
    for at, node in enumerate(tree.nodes):
        if isinstance(node, Decision):
            owner[at] = node.player
            children[at] = tuple(action.child for action in node.actions)
    responder, chain, fold, head = [0] * count, [False] * count, [-1] * count, [-1] * count
    terms: list[int] = []
    free: list[int] = []
    chains: list[tuple[tuple[int, ...], int]] = []

    def mark(at: int, k: int, top: int) -> None:
        responder[at], head[at] = k, top
        if isinstance(tree.nodes[at], Terminal):
            terms.append(at)
        for child in children[at]:
            mark(child, k, top)

    for action in tree.nodes[tree.root].actions:
        at = action.child
        node = tree.nodes[at]
        if isinstance(node, Terminal):
            if node.pair is None:
                free.append(at)
            else:
                mark(at, next(p for p in node.pair if p != 0), tree.root)
            continue
        links = []
        while isinstance(tree.nodes[at], Decision):
            node = tree.nodes[at]
            links.append(at)
            chain[at], responder[at] = True, node.player
            fold[at] = next(i for i, a in enumerate(node.actions) if a.kind == "fold")
            for i, a in enumerate(node.actions):
                if i != fold[at]:
                    mark(a.child, node.player, at)
            at = node.actions[fold[at]].child
        free.append(at)
        chains.append((tuple(links), at))

    equity, _, _ = _tables()
    matrices = [equity]
    known: dict[tuple[float, bool], int] = {}
    numbers = []
    for at in terms:
        node = tree.nodes[at]
        if node.kind != "realization":
            numbers.append(0)
            continue
        spot = (round(node.spr, 2), node.opener_in_position)
        if spot not in known:
            known[spot] = len(matrices)
            matrices.append(realization.matrix(node.spr, node.opener_in_position))
        numbers.append(known[spot])
    keys = [(_key(tree.fixed_ranges, responder[at]), m) for at, m in zip(terms, numbers)]
    opener_wins = numpy.zeros((count, players))
    other_wins = numpy.zeros((count, players))
    for at, node in enumerate(tree.nodes):
        if isinstance(node, Terminal):
            rows = numpy.asarray(payoffs[at], dtype=numpy.float64)
            first = 0 if node.pair is None or node.pair[0] == 0 else 1
            opener_wins[at], other_wins[at] = rows[first], rows[-1 - first]
    return _Shape(
        nodes=count,
        players=players,
        root=tree.root,
        decisions=tuple(at for at in range(count) if owner[at] >= 0),
        owner=tuple(owner),
        children=tuple(children),
        responder=tuple(responder),
        chain=tuple(chain),
        fold=tuple(fold),
        head=tuple(head),
        chains=tuple(chains),
        terms=numpy.array(terms, dtype=numpy.int64),
        pair_of=numpy.array([responder[at] for at in terms], dtype=numpy.int64),
        matrices=tuple(matrices),
        by_key=tuple(
            (key, numpy.array([i for i, (k, _) in enumerate(keys) if k == key], dtype=numpy.int64))
            for key in dict.fromkeys(k for k, _ in keys)
        ),
        groups=tuple(
            (key, numpy.array([i for i, k in enumerate(keys) if k == key], dtype=numpy.int64))
            for key in dict.fromkeys(keys)
        ),
        by_matrix=tuple(
            (m, numpy.array([i for i, n in enumerate(numbers) if n == m], dtype=numpy.int64))
            for m in dict.fromkeys(numbers)
        ),
        hung={
            at: numpy.array([i for i, t in enumerate(terms) if head[t] == at], dtype=numpy.int64)
            for at in range(count)
            if chain[at]
        },
        free=tuple(free),
        opener_wins=opener_wins,
        other_wins=other_wins,
        fixed=dict(tree.fixed_ranges),
    )


@dataclass(frozen=True)
class _Opener:
    """Руки открывшего строками: `w·f_k` `(K, 169)` и суммы по ключу `_key`, `w·p_m·f_k` — по
    паре «ключ, номер матрицы» `m`."""

    weight: dict[int | None, numpy.ndarray]
    wequity: dict[tuple[int | None, int], numpy.ndarray]
    total: dict[int | None, numpy.ndarray]  # (K,): Σ_x f_k·w[h, x]


@dataclass(frozen=True)
class _Responder:
    """Руки отвечающего столбцами: `w` и `w·p_m` по номеру матрицы `m`, `(169, K)`."""

    weight: numpy.ndarray
    wequity: dict[int, numpy.ndarray]


def _opener_side(
    shape: _Shape, weight: numpy.ndarray, wequity: dict[int, numpy.ndarray]
) -> _Opener:
    scaled = {None: numpy.ones(169), **shape.fixed}
    rows = {k: weight * f for k, f in scaled.items()}
    return _Opener(
        weight=rows,
        wequity={(k, m): wequity[m] * scaled[k] for k, m in (key for key, _ in shape.groups)},
        total={k: row.sum(axis=1) for k, row in rows.items()},
    )


def _class_sides(shape: _Shape) -> tuple[_Opener, _Responder]:
    _, weight, _ = _tables()
    wequity = {m: weight * matrix for m, matrix in enumerate(shape.matrices)}
    return _opener_side(shape, weight, wequity), _Responder(weight, wequity)


def _match(regret: numpy.ndarray) -> numpy.ndarray:
    total = regret.sum(axis=0)
    uniform = numpy.full_like(regret, 1.0 / regret.shape[0])
    return numpy.divide(regret, total, out=uniform, where=total > 0)


def _reach(
    shape: _Shape, sigma: dict[int, numpy.ndarray], start: int | None = None
) -> tuple[numpy.ndarray, numpy.ndarray]:
    """Своя достижимость открывшего `r0` и отвечающего пары `rk` на каждом узле, `(узлы, 169)`.

    С `start` — от этого узла с достижимостью 1: верны только узлы его поддерева.
    """
    r0 = numpy.ones((shape.nodes, 169))
    rk = numpy.ones((shape.nodes, 169))
    first = shape.root if start is None else start
    for at in shape.decisions:
        if at < first:
            continue
        strategy = sigma[at]
        for i, child in enumerate(shape.children[at]):
            if shape.owner[at] == 0:
                r0[child], rk[child] = r0[at] * strategy[i], rk[at]
            elif shape.chain[at] and i == shape.fold[at]:
                r0[child], rk[child] = r0[at], 1.0
            else:
                r0[child], rk[child] = r0[at], rk[at] * strategy[i]
    return r0, rk


def _shares(
    shape: _Shape, rk: numpy.ndarray, side: _Opener
) -> tuple[numpy.ndarray, numpy.ndarray]:
    """По терминалам пар и рукам открывшего `(терминалы, K)`: вероятность, что `k` дошёл до
    терминала, и что дошёл и проиграл вскрытие, — при классе открывшего."""
    size = next(iter(side.total.values())).shape[0]
    share = numpy.empty((len(shape.terms), size))
    win = numpy.empty((len(shape.terms), size))
    for key, rows in shape.by_key:
        share[rows] = rk[shape.terms[rows]] @ side.weight[key].T / side.total[key]
    for (key, m), rows in shape.groups:
        win[rows] = rk[shape.terms[rows]] @ side.wequity[(key, m)].T / side.total[key]
    return share, win


def _opener_values(
    shape: _Shape,
    sigma: dict[int, numpy.ndarray],
    shares: tuple[numpy.ndarray, numpy.ndarray],
    side: _Opener,
    best: bool,
) -> tuple[numpy.ndarray, dict[int, numpy.ndarray], dict[int, numpy.ndarray]]:
    """Значения узлов для открывшего по его рукам `(узлы, K)` и значения его действий.

    Значение — условное при классе открывшего и достижимости `k` внутри пары, без фолдов
    отвечающих до `k`. `best` — у открывшего лучший ответ вместо `sigma`. Возвращает ещё
    вероятности фолда узлов цепочки по рукам открывшего.
    """
    share, win = shares
    values = numpy.empty((shape.nodes, share.shape[1]))
    for at in shape.free:
        values[at] = shape.opener_wins[at, 0]
    lose = shape.other_wins[shape.terms, 0][:, None]
    values[shape.terms] = lose * share + (shape.opener_wins[shape.terms, 0][:, None] - lose) * win
    actions: dict[int, numpy.ndarray] = {}
    folds: dict[int, numpy.ndarray] = {}
    for at in reversed(shape.decisions):
        kids = values[list(shape.children[at])]
        if shape.owner[at] == 0:
            actions[at] = kids
            if best:
                values[at] = kids.max(axis=0)
            else:
                values[at] = (sigma[at] * kids).sum(axis=0)
        elif shape.chain[at]:
            key, f = _key(shape.fixed, shape.responder[at]), shape.fold[at]
            folds[at] = side.weight[key] @ sigma[at][f] / side.total[key]
            values[at] = folds[at] * kids[f] + kids.sum(axis=0) - kids[f]
        else:
            values[at] = kids.sum(axis=0)
    return values, actions, folds


def _fold_values(
    shape: _Shape,
    r0: numpy.ndarray,
    shares: tuple[numpy.ndarray, numpy.ndarray],
    folds: dict[int, numpy.ndarray],
) -> dict[int, numpy.ndarray]:
    """Узел цепочки отвечающего `k` → `(169,)`: достижимость открывшего, умноженная на выплату
    `k` после его фолда, по классу открывшего (руки открывшего — все 169 классов).

    С конца цепочки: «все сфолдили» — ряд терминала; узел `j` — его фолд, умноженный на
    вероятность фолда, плюс пары `j`, где выплата получателю взвешена достижимостью открывшего.
    """
    share, win = shares
    result: dict[int, numpy.ndarray] = {}
    for links, end in shape.chains:
        carried = shape.opener_wins[end][:, None] * r0[end][None, :]  # (игроки, 169)
        for at in reversed(links):
            result[at] = carried[shape.responder[at]]
            rows = shape.hung[at]
            terms = shape.terms[rows]
            reached = r0[terms]
            lose = shape.other_wins[terms]
            gain = shape.opener_wins[terms] - lose
            carried = (
                folds[at] * carried
                + lose.T @ (reached * share[rows])
                + gain.T @ (reached * win[rows])
            )
    return result


def _responder_values(
    shape: _Shape,
    sigma: dict[int, numpy.ndarray],
    r0: numpy.ndarray,
    fold_values: dict[int, numpy.ndarray],
    side: _Responder,
    best: bool,
) -> tuple[numpy.ndarray, dict[int, numpy.ndarray]]:
    """Значения узлов цепочек и пар для их отвечающего по его рукам `(узлы, K)`, без нормировки.

    `best` — у отвечающих лучший ответ вместо `sigma`. Возвращает ещё значения их действий.
    """
    values = numpy.zeros((shape.nodes, side.weight.shape[1]))
    terms, ks = shape.terms, shape.pair_of
    lose = shape.other_wins[terms, ks][:, None]
    gain = shape.opener_wins[terms, ks][:, None] - lose
    values[terms] = lose * (r0[terms] @ side.weight)
    for m, rows in shape.by_matrix:
        values[terms[rows]] += gain[rows] * (r0[terms[rows]] @ side.wequity[m])
    actions: dict[int, numpy.ndarray] = {}
    for at in reversed(shape.decisions):
        if at == shape.root:
            continue
        kids = values[list(shape.children[at])]
        if shape.owner[at] == 0:
            values[at] = kids.sum(axis=0)
            continue
        if shape.chain[at]:
            kids[shape.fold[at]] = fold_values[at] @ side.weight
        actions[at] = kids
        if best:
            values[at] = kids.max(axis=0)
        else:
            values[at] = (sigma[at] * kids).sum(axis=0)
    return values, actions


def _gap(
    shape: _Shape, sigma: dict[int, numpy.ndarray], sides: tuple[_Opener, _Responder]
) -> float:
    _, weight, prior = _tables()
    opener_side, responder_side = sides
    r0, rk = _reach(shape, sigma)
    shares = _shares(shape, rk, opener_side)
    played, _, folds = _opener_values(shape, sigma, shares, opener_side, best=False)
    answer, _, _ = _opener_values(shape, sigma, shares, opener_side, best=True)
    worst = float(prior @ (answer[shape.root] - played[shape.root]))
    fold_values = _fold_values(shape, r0, shares, folds)
    own, _ = _responder_values(shape, sigma, r0, fold_values, responder_side, best=False)
    better, _ = _responder_values(shape, sigma, r0, fold_values, responder_side, best=True)
    entered = sum(r0[links[0]] for links, _ in shape.chains) @ weight
    seen = entered > 0
    for k in range(1, shape.players):
        nodes = [at for at in shape.decisions if shape.chain[at] and shape.responder[at] == k]
        gain = sum(better[at] - own[at] for at in nodes)
        mass = prior * shape.fixed.get(k, 1.0)
        conditional = numpy.divide(gain, entered, out=numpy.zeros(169), where=seen)
        worst = max(worst, float(mass @ conditional / mass.sum()))
    return worst


def solve(
    tree: Tree,
    payoffs: list[numpy.ndarray | None],
    eps: float,
    max_iterations: int = MAX_ITERATIONS,
) -> Solution:
    """Равновесие CFR+ с эксплуатируемостью не больше `eps` (в единицах выплат)."""
    check_positive(eps, "допуск равновесия")
    check_positive(max_iterations, "предел итераций")
    shape = _shape(tree, payoffs)
    sides = _class_sides(shape)
    opener_side, responder_side = sides
    sigma = {at: _match(numpy.zeros((len(shape.children[at]), 169))) for at in shape.decisions}
    regret = {at: numpy.zeros_like(sigma[at]) for at in shape.decisions}
    total = {at: numpy.zeros_like(sigma[at]) for at in shape.decisions}
    openers = [at for at in shape.decisions if shape.owner[at] == 0]
    responders = [at for at in shape.decisions if shape.owner[at] != 0]
    iterations = 0
    while True:
        if iterations == max_iterations or (iterations and iterations % _CHECK_EVERY == 0):
            average = {at: _match(weights) for at, weights in total.items()}
            gap = _gap(shape, average, sides)
            if gap <= eps or iterations == max_iterations:
                break
        step = (iterations + 1) ** 2

        r0, rk = _reach(shape, sigma)
        shares = _shares(shape, rk, opener_side)
        values, actions, folds = _opener_values(shape, sigma, shares, opener_side, best=False)
        for at in openers:
            regret[at] = numpy.maximum(regret[at] + actions[at] - values[at], 0.0)
            total[at] += step * r0[at] * sigma[at]
            sigma[at] = _match(regret[at])

        # Вероятности фолда цепочки от шага открывшего не меняются: они — по стратегиям
        # отвечающих.
        r0, _ = _reach(shape, sigma)
        fold_values = _fold_values(shape, r0, shares, folds)
        own, actions = _responder_values(
            shape, sigma, r0, fold_values, responder_side, best=False
        )
        for at in responders:
            regret[at] = numpy.maximum(regret[at] + actions[at] - own[at], 0.0)
            total[at] += step * rk[at] * sigma[at]
            sigma[at] = _match(regret[at])
        iterations += 1
    return Solution(
        strategy=average,
        exploitability=gap,
        iterations=iterations,
        converged=gap <= eps,
    )


def exploitability(
    tree: Tree, payoffs: list[numpy.ndarray | None], strategy: dict[int, numpy.ndarray]
) -> float:
    """Наибольший выигрыш одного игрока от лучшего ответа, в единицах выплат."""
    shape = _shape(tree, payoffs)
    sigma = {at: numpy.asarray(s, dtype=numpy.float64) for at, s in strategy.items()}
    return _gap(shape, sigma, _class_sides(shape))


def reach(tree: Tree, solution: Solution, player: int) -> numpy.ndarray:
    """`(169,)`: вероятность, что класс игрока сыграл `tree.path`; у лимпера — с его диапазоном."""
    result = numpy.array(tree.fixed_ranges.get(player, numpy.ones(169)), dtype=numpy.float64)
    for at, index in tree.path:
        if tree.nodes[at].player == player:
            result = result * solution.strategy[at][index]
    return result


def action_values(
    tree: Tree,
    payoffs: list[numpy.ndarray | None],
    solution: Solution,
    node: int,
    combo: tuple[str, str],
) -> list[float]:
    """EV каждого действия игрока узла `node` для комбинации `combo` против `solution`.

    EV — условное при том, что соперник по паре дошёл до узла по своей стратегии, с блокерами
    комбинации; будущие решения игрока — лучший ответ комбинации. Если соперник по стратегии
    до узла не доходит ни одной совместимой рукой, его диапазон на узле — все руки.
    """
    cards = list(combo)
    weights = allin_matrix.hand_weights(cards).astype(numpy.float64)
    index = allin_matrix.class_index(allin_matrix.class_of(cards))
    shape = _shape(tree, payoffs)
    sigma = solution.strategy
    r0, rk = _reach(shape, sigma)
    if tree.nodes[node].player == 0:
        side = _opener_side(
            shape,
            weights[None, :],
            {m: (weights * matrix[index])[None, :] for m, matrix in enumerate(shape.matrices)},
        )
        mass = 1.0
        if node != shape.root:
            key = _key(shape.fixed, shape.responder[node])
            mass = float(side.weight[key][0] @ rk[node] / side.total[key][0])
            if mass <= 0:
                _, rk = _reach(shape, sigma, start=node)
                mass = 1.0
        shares = _shares(shape, rk, side)
        _, actions, _ = _opener_values(shape, sigma, shares, side, best=True)
        return [float(value) / mass for value in actions[node][:, 0]]
    opener_side, _ = _class_sides(shape)
    shares = _shares(shape, rk, opener_side)
    _, _, folds = _opener_values(shape, sigma, shares, opener_side, best=False)
    mass = float(weights @ r0[node])
    if mass <= 0:
        r0, _ = _reach(shape, sigma, start=node)
        mass = float(weights @ r0[node])
    fold_values = _fold_values(shape, r0, shares, folds)
    side = _Responder(
        weights[:, None],
        {m: (weights * matrix[:, index])[:, None] for m, matrix in enumerate(shape.matrices)},
    )
    _, actions = _responder_values(shape, sigma, r0, fold_values, side, best=True)
    return [float(value) / mass for value in actions[node][:, 0]]
