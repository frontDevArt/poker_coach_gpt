"""Советник всего префлопа: лучший ответ комбинации героя на дереве (спека плана 5, §6.9, §7–§9).

Узел — спот §4 линии `preflop_line.read_line`. Узлы `pushfold` линия отвергает своим текстом,
поэтому реестр остаётся упорядоченным списком без особых случаев. Дерево строится от корня
префлопа по фактической линии на каждом шаге раздачи (§5.4) и решается дважды, как в `pushfold`:
по ICM модели поля (с головами, если турнир PKO) — совет, EV и диапазоны; по фишкам — `evBb`.
Состояния солвера между вызовами нет: вход без истории самодостаточен.

Модуль целиком удовлетворяет протоколу советника (`name`, `applies`, `advise`), поэтому
`name` — атрибут модуля в нижнем регистре.

**Уточнения формы ответа против спеки §7.2** (решения плана 5, Задача 6):

- `line` — все действия линии по порядку, фолды тоже; у фолда ключа `toBb` нет;
- `effectiveStackBb` — меньшее из стека героя и наибольшего стека другого участника дерева,
  стеки с вложенным (то же сравнение, что у пометки `deep_stack`);
- `ranges.hero.handFreq` — частоты класса героя без округления, как `handFreqIcm` плана 4;
- `ranges.opponents` — участники дерева в раздаче, кроме героя, по порядку хода дерева:
  сфолдившие по линии не входят. `role` — по последнему добровольному действию места: лимп —
  `limper`, олл-ин — `shover`, рейз — `opener`, `3bettor`, `4bettor` по номеру рейза в линии;
  не ходил — `responder`. `reach` — частоты ICM-равновесия с шагом `CLASS_FREQ_STEP`,
  `reachPct` — доля из 1326 без округления, `stackBb` — как во входе;
- `bountyUsd` — разница лучшего действия с опорным (фолд, у `BB` против лимпа — чек) с головами
  минус без них при тех же стратегиях: равновесие без голов не перерешивается;
- допуск ICM-решения — `EPS_CHIP_BB` в долларах по цене фишки участников на исходе первого
  действия корня (фолд или чек — без нокаутов, голов в нём нет); `close_spot` — разница двух
  лучших `evUsd` не больше этого допуска;
- `line_deviates` — последний ответ советника в `history` (`advisor` не `null`: `preflop` или
  `pushfold`) против последнего действия героя в линии: другое действие или размер дальше
  `SIZE_STEP_BB`. После ответа `pushfold` узел героя на префлопе бывает, только если герой ему
  не последовал. Отказ в истории — не ответ; действия героя в линии нет — сверять нечего.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import allin_matrix, nash, preflop_solver
from .handstate import DecisionNode, TournamentContext, assign_positions
from .preflop_line import Act, Line, read_line
from .preflop_solver import Solution, action_values, reach
from .preflop_tree import SIZE_STEP_BB, Tree, build, chip_payoffs, icm_payoffs, with_bounties
from .pushfold import _classes, _context_flags

name = "preflop"

_PASSIVE = frozenset({"fold", "check"})
_RAISE_ROLES = ("opener", "3bettor", "4bettor")
# Пометки дерева в порядке ответа: ставит их `preflop_tree.build`.
_TREE_FLAGS = (
    "no_overcall",
    "no_cold_call",
    "fold_as_walk",
    "fixed_sizing",
    "postflop_realization",
    "deep_stack",
    "no_hero_limp",
    "limper_range_profile",
)
# Разность размеров в шаг печатается с хвостом (2.1 − 2.0 > 0.1): шум, а не отклонение.
_SIZE_NOISE = 1e-9


def applies(context: TournamentContext, nodes: list[DecisionNode]) -> str | None:
    """`None`, если линия и дерево последнего узла строятся, иначе причина отказа."""
    line = read_line(nodes)
    if isinstance(line, str):
        return line
    tree = build(line, nodes[-1])
    return tree if isinstance(tree, str) else None


@dataclass(frozen=True)
class _Solved:
    """Линия, дерево, выплаты и оба равновесия последнего узла."""

    line: Line
    tree: Tree
    chips: list
    plain: list  # ICM без голов
    icm: list  # ICM с головами в PKO, иначе `plain`
    eps: float
    pko: bool
    by_icm: Solution
    by_chip: Solution


def _solve(context: TournamentContext, nodes: list[DecisionNode]) -> _Solved:
    """Предусловие — `applies` вернул `None`."""
    node = nodes[-1]
    line = read_line(nodes)
    tree = build(line, node)
    pko = any(seat.bounty_usd is not None for seat in node.seats)
    chips = chip_payoffs(tree)
    plain = icm_payoffs(tree, node, context, bounties=False)
    icm = with_bounties(tree, plain) if pko else plain
    eps = _icm_eps(tree, chips, plain)
    limit = preflop_solver.MAX_ITERATIONS
    return _Solved(
        line=line,
        tree=tree,
        chips=chips,
        plain=plain,
        icm=icm,
        eps=eps,
        pko=pko,
        by_icm=preflop_solver.solve(tree, icm, eps, limit),
        by_chip=preflop_solver.solve(tree, chips, nash.EPS_CHIP_BB, limit),
    )


def _icm_eps(tree: Tree, chips: list, plain: list) -> float:
    at = tree.nodes[tree.root].actions[0].child
    return nash.EPS_CHIP_BB * float(plain[at][0].sum()) / float(chips[at][0].sum())


def advise(context: TournamentContext, nodes: list[DecisionNode], history: list[dict]) -> dict:
    """Совет на последнем узле. Предусловие — `applies` вернул `None`."""
    node = nodes[-1]
    solved = _solve(context, nodes)
    tree = solved.tree
    hero = tree.nodes[tree.hero_node]
    me = hero.player
    combo = (node.hero_cards[0], node.hero_cards[1])
    usd = action_values(tree, solved.icm, solved.by_icm, tree.hero_node, combo)
    bb = action_values(tree, solved.chips, solved.by_chip, tree.hero_node, combo)
    best = 0
    for at, value in enumerate(usd):
        if value > usd[best]:  # равенство — к пассивному, раньше в списке узла
            best = at
    chosen = hero.actions[best]

    hand = allin_matrix.class_of(node.hero_cards)
    result: dict = {"advisor": name, "spot": solved.line.kind, "action": chosen.kind}
    if chosen.kind not in _PASSIVE:
        result["sizeBb"] = chosen.to_bb
    result["heroHand"] = hand
    result["effectiveStackBb"] = _effective(tree, me)
    positions = assign_positions(node)
    result["line"] = [_act(act, positions) for act in solved.line.acts]
    result["actions"] = [
        {
            "action": action.kind,
            **({} if action.kind in _PASSIVE else {"toBb": action.to_bb}),
            "evUsd": value_usd,
            "evBb": value_bb,
        }
        for action, value_usd, value_bb in zip(hero.actions, usd, bb, strict=True)
    ]
    if solved.pko:
        plain = action_values(tree, solved.plain, solved.by_icm, tree.hero_node, combo)
        result["bountyUsd"] = (usd[best] - usd[0]) - (plain[best] - plain[0])

    strategy = solved.by_icm.strategy[tree.hero_node]
    index = allin_matrix.class_index(hand)
    result["ranges"] = {
        "hero": {
            "byAction": {a.kind: _classes(row) for a, row in zip(hero.actions, strategy)},
            "handFreq": {a.kind: float(row[index]) for a, row in zip(hero.actions, strategy)},
        },
        "opponents": _opponents(solved, me, positions),
    }
    result["nash"] = {
        "icm": {
            "exploitabilityUsd": solved.by_icm.exploitability,
            "iterations": solved.by_icm.iterations,
        },
        "chip": {
            "exploitabilityBb": solved.by_chip.exploitability,
            "iterations": solved.by_chip.iterations,
        },
    }
    top = sorted(usd, reverse=True)
    result["flags"] = _flags(
        context, node, solved, top[0] - top[1] <= solved.eps, _deviates(solved.line, node, history)
    )
    return result


def _effective(tree: Tree, me: int) -> float:
    totals = [seat.stack_bb + seat.invested_bb for seat in tree.players]
    return min(totals[me], max(total for at, total in enumerate(totals) if at != me))


def _act(act: Act, positions: dict) -> dict:
    entry = {
        "seatIndex": act.seat_index,
        "position": positions[act.seat_index].value,
        "action": act.action,
    }
    if act.to_bb is not None:
        entry["toBb"] = act.to_bb
    return entry


def _roles(line: Line) -> dict[int, str]:
    """Место → роль по его последнему добровольному действию в линии."""
    roles: dict[int, str] = {}
    raises = 0
    for act in line.acts:
        if act.action == "raise":
            roles[act.seat_index] = _RAISE_ROLES[raises]
            raises += 1
        elif act.action == "limp":
            roles[act.seat_index] = "limper"
        elif act.action == "allin":
            roles[act.seat_index] = "shover"
    return roles


def _opponents(solved: _Solved, me: int, positions: dict) -> list[dict]:
    roles = _roles(solved.line)
    result = []
    for at, seat in enumerate(solved.tree.players):
        if at == me or not seat.in_hand:
            continue
        freq = reach(solved.tree, solved.by_icm, at)
        result.append(
            {
                "seatIndex": seat.seat_index,
                "position": positions[seat.seat_index].value,
                "stackBb": seat.stack_bb,
                "role": roles.get(seat.seat_index, "responder"),
                "reach": _classes(freq),
                "reachPct": nash.range_share(freq),
            }
        )
    return result


def _deviates(line: Line, node: DecisionNode, history: list[dict]) -> bool:
    advised = [answer for answer in history if answer.get("advisor") is not None]
    mine = [act for act in line.acts if act.seat_index == node.hero.seat_index]
    if not advised or not mine:
        return False
    last, act = advised[-1], mine[-1]
    if last.get("action") != act.action:
        return True
    size = last.get("sizeBb")
    if size is None or act.to_bb is None:
        return False
    return abs(act.to_bb - size) > SIZE_STEP_BB + _SIZE_NOISE


def _flags(
    context: TournamentContext,
    node: DecisionNode,
    solved: _Solved,
    close: bool,
    deviates: bool,
) -> list[str]:
    """Пометки спеки §9; каждая ставится, только когда она правда."""
    flags = _context_flags(context, node, solved.pko)
    flags.extend(flag for flag in _TREE_FLAGS if flag in solved.tree.flags)
    if close:
        flags.append("close_spot")
    if not (solved.by_icm.converged and solved.by_chip.converged):
        flags.append("nash_not_converged")
    if deviates:
        flags.append("line_deviates")
    return flags
