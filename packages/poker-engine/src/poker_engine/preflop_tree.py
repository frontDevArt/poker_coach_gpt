"""Дерево префлопа «открывший против вошедшего» и выплаты его терминалов (спека плана 5, §6.1–§6.7).

**Участники.** Корень — первое место, которое ещё может открыть банк: первый добровольно
вошедший по линии, а если таких нет — герой. Места до корня сфолдили до него, их стеки и
вложенное — мёртвые деньги и ICM, как у подыгры плана 4. Участники — корень и **все** места
после него по порядку хода, в том числе сфолдившие по линии: равновесие соперника на сыгранном
узле решается полностью, линия только выбирает ветку (§6.1), и дерево каждого шага раздачи —
одно и то же дерево от одного корня (инвариант 14). `Line.players` сфолдивших без вложенного
не содержит, поэтому участников дерево собирает само.

**Против лимпа** (§6.6) корень — герой: лимп сыгран до дерева, диапазон лимпера задан
профилем (`fixed_ranges`). Участники — герой, места после него и последним лимпер; у лимпера
против изоляции `fold`, `call`, `allin`. Рейз лимпера не олл-ином — вне дерева, отказ.

**Ход.** Корень: `fold`, рейз, `allin` (у `BB` против лимпа `check` вместо `fold`); фолд корня —
банк большому блайнду (`fold_as_walk`, как в плане 4). Отвечающие — по порядку хода: `fold`,
`call`, 3-бет, `allin`; первый вошедший закрывает остальных (§6.3), и дальше идёт пара: открывший
против 3-бета — `fold`, `call`, 4-бет, `allin`; против 4-бета — `fold`, `call`, `allin`; против
олл-ина — `fold`, `call`. Стек не выше ставки — колл на все: у такого места `fold` и `allin`.

**Размеры.** На сыгранном узле рейз — фактический из линии, без слияния (Review Focus 3).
Несыгранный — по правилу §6.2 с округлением до `SIZE_STEP_BB` и слиянием с олл-ином, если он
выше `COMMIT_SHARE` эффективного стека. Эффективный стек не больше своего, поэтому размер не
меньше стека с вложенным (короткий стек, Review Focus 5) сливается тем же правилом.
3-бет без позиции — место, которое на флопе ходит первым: `SB` против любого, `BB` против
всех, кроме `SB`.

**Терминалы.** `fold` — банк оставшемуся; `allin` — вскрытие олл-ина, излишок возвращается;
`checkdown` — колл без олл-ина, банк делится по эквити без ставок (§6.4). Ряды — стеки
участников после раздачи, BB: у `fold` один ряд, у пары — победа первого из `pair`, затем
второго. Сфолдивший теряет вложенное на момент фолда.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy

from . import allin_matrix, bounty, icm_field, profiles
from .handstate import DecisionNode, Seat, TournamentContext, assign_positions
from .preflop_line import Act, Line, _blind
from .pushfold_game import _dead_money
from .ranges import parse_range
from .types import Position, positions_for

# Калибровочные константы спеки §6.2 и §6.4, а не результат расчёта.
OPEN_BB = 2.0
OPEN_SB_BB = 3.0
ISO_BB = 3.0
ISO_PER_LIMPER_BB = 1.0
ISO_FROM_BB_BB = 4.0
THREEBET_IP = 3.0
THREEBET_OOP = 4.0
FOURBET = 2.2
COMMIT_SHARE = 0.4
CHECKDOWN_TRUST_BB = 40.0
SIZE_STEP_BB = 0.1

LIMP_RERAISE = "лимпер ответил на изоляцию рейзом не олл-ином: вне дерева префлопа"


@dataclass(frozen=True)
class Action:
    """Действие узла: `fold | check | call | raise | allin`, вложенное «до» и узел-потомок."""

    kind: str
    to_bb: float | None
    child: int


@dataclass(frozen=True)
class Decision:
    """Узел решения участника `player` (индекс в `Tree.players`)."""

    player: int
    actions: tuple[Action, ...]


@dataclass(frozen=True)
class Terminal:
    """Конец раздачи: `fold`, `allin` или `checkdown`; `rows` — стеки участников по исходам."""

    kind: str
    rows: list[list[float]]
    pair: tuple[int, int] | None


@dataclass(frozen=True)
class Tree:
    """Дерево префлопа. `path` — сыгранная линия парами (узел, индекс действия) до `hero_node`."""

    players: list[Seat]
    nodes: list[Decision | Terminal]
    root: int
    path: list[tuple[int, int]]
    hero_node: int
    fixed_ranges: dict[int, numpy.ndarray]
    flags: set[str]


def build(line: Line, node: DecisionNode) -> Tree | str:
    """Дерево по линии и последнему кадру или причина отказа.

    Предусловие: `line` — ответ `preflop_line.read_line` на кадры, последний из которых `node`.
    """
    positions = assign_positions(node)
    order = positions_for(len(node.seats))
    seats = sorted(node.seats, key=lambda seat: order.index(positions[seat.seat_index]))
    hero = node.hero
    voluntary = [act for act in line.acts if act.action != "fold"]
    limper = voluntary[0].seat_index if voluntary and voluntary[0].action == "limp" else None

    if limper is None:
        root = voluntary[0].seat_index if voluntary else hero.seat_index
        start = [seat.seat_index for seat in seats].index(root)
        players = seats[start:]
        acts = line.acts
    else:
        if any(act.seat_index == limper and act.action == "raise" for act in line.acts):
            return LIMP_RERAISE
        players = [*seats[seats.index(hero) :], *(s for s in seats if s.seat_index == limper)]
        acts = [act for act in line.acts if act.action != "limp"]

    acted = {act.seat_index for act in voluntary}
    for seat in players:
        if seat.stack_bb == 0 and seat.seat_index not in acted:
            if seat.in_hand:
                return f"место {seat.seat_index} уже в олл-ине с блайнда: вне модели"
            return f"на месте {seat.seat_index} стек 0 вне раздачи: ICM не определён"

    # Вложенное на старте дерева — блайнды: стек 0 без хода отвергнут выше, значит блайнд
    # поставлен целиком. Лимпер начинает со своего лимпа.
    roles = [positions[seat.seat_index] for seat in players]
    base = [_blind(role) for role in roles]
    if limper is not None:
        base[-1] = voluntary[0].to_bb
    builder = _Builder(players, roles, base, _dead_money(node, players), acts, limper is not None)
    root_node = builder.root()

    me = next(at for at, seat in enumerate(players) if seat.is_hero)
    totals = builder.totals
    effective = min(totals[me], max(total for at, total in enumerate(totals) if at != me))
    flags = set(builder.flags)
    if effective > CHECKDOWN_TRUST_BB:
        flags.add("deep_stack")
    if len(players) > 2:
        flags.add("no_overcall")
    root_actions = builder.nodes[root_node].actions
    if any(a.kind == "fold" for a in root_actions) and any(
        role is not Position.BB for role in roles[1:]
    ):
        flags.add("fold_as_walk")
    fixed: dict[int, numpy.ndarray] = {}
    if limper is not None:
        fixed[len(players) - 1] = _profile_range(players[-1])
        flags.add("limper_range_profile")
    if line.kind == "open" and positions[hero.seat_index] is Position.SB:
        flags.add("no_hero_limp")

    return Tree(
        players=players,
        nodes=builder.nodes,
        root=root_node,
        path=builder.path,
        hero_node=builder.hero_node,
        fixed_ranges=fixed,
        flags=flags,
    )


def _profile_range(seat: Seat) -> numpy.ndarray:
    """Доля комбинаций каждого класса в диапазоне профиля по VPIP лимпера (§6.6)."""
    combos, _ = profiles.range_for_vpip(seat.vpip, seat.vpip_hands)
    chosen = set(combos)
    return numpy.array(
        [
            sum(combo in chosen for combo in parse_range(name)) / allin_matrix.combos_of(name)
            for name in allin_matrix.CLASSES
        ]
    )


def _round(size: float) -> float:
    return round(round(size / SIZE_STEP_BB) * SIZE_STEP_BB, 6)


# Потомок по признаку «ветка сыграна»: строится после того, как известен сыгранный ход узла.
_Child = Callable[[bool], int]


class _Builder:
    """Строит узлы в глубину; на сыгранной ветке берёт ходы линии по одному."""

    def __init__(
        self,
        players: list[Seat],
        roles: list[Position],
        base: list[float],
        dead: float,
        acts: list[Act],
        vs_limp: bool,
    ) -> None:
        self.players = players
        self.roles = roles
        self.base = base
        self.dead = dead
        self.totals = [seat.stack_bb + seat.invested_bb for seat in players]
        self.acts = acts
        self.vs_limp = vs_limp
        self.nodes: list = []
        self.path: list[tuple[int, int]] = []
        self.hero_node = -1
        self.flags: set[str] = set()
        self._cursor = 0
        self._last = len(players) - 1 if vs_limp else None

    # --- узлы решения ----------------------------------------------------------------------

    def root(self) -> int:
        at = self._reserve()
        played = self._take(0, at, True)
        others = max(self.totals[1:])
        if self.vs_limp:
            rule = ISO_FROM_BB_BB if self.roles[0] is Position.BB else ISO_BB + ISO_PER_LIMPER_BB
        else:
            rule = OPEN_SB_BB if self.roles[0] is Position.SB else OPEN_BB
        inv = list(self.base)
        if self.vs_limp and self.roles[0] is Position.BB:
            passive = ("check", None, self._end("checkdown", 0, self._last, inv))
        else:
            bb = self.roles.index(Position.BB)
            passive = ("fold", None, lambda on: self._fold(bb, inv))
        options = [passive]
        for kind, to in self._aggression(0, rule, min(self.totals[0], others), played):
            options.append((kind, to, self._open_child(to, inv)))
        return self._decide(at, 0, options, played)

    def _open_child(self, to: float, inv: list[float]) -> _Child:
        return lambda on: self._respond(1, _put(inv, 0, to), on)

    def _respond(self, k: int, inv: list[float], on_path: bool) -> int:
        """Ставка открывшего (участник 0) дошла до отвечающего `k`."""
        if k == len(self.players):
            return self._fold(0, inv)
        at = self._reserve()
        played = self._take(k, at, on_path)
        top, total = inv[0], self.totals[k]
        options: list = [("fold", None, lambda on: self._respond(k + 1, inv, on))]
        if top >= self.totals[0]:
            call = min(total, top)
            options.append(("call", call, self._end("allin", 0, k, _put(inv, k, call))))
        elif total <= top:
            options.append(("allin", total, self._end("allin", 0, k, _put(inv, k, total))))
        else:
            options.append(("call", top, self._end("checkdown", 0, k, _put(inv, k, top))))
            if k == self._last:
                options.append(("allin", total, self._raise_child(0, k, inv, total, 2)))
            else:
                factor = THREEBET_OOP if self._out_of_position(k, 0) else THREEBET_IP
                eff = min(total, self.totals[0])
                for kind, to in self._aggression(k, factor * top, eff, played):
                    options.append((kind, to, self._raise_child(0, k, inv, to, 2)))
        return self._decide(at, k, options, played)

    def _facing_raise(self, a: int, b: int, inv: list[float], level: int, on_path: bool) -> int:
        """`a` против рейза `b` уровня `level` (2 — 3-бет, 3 — 4-бет)."""
        at = self._reserve()
        played = self._take(a, at, on_path)
        top, total = inv[b], self.totals[a]
        options: list = [("fold", None, lambda on: self._fold(b, inv))]
        if total <= top:
            options.append(("allin", total, self._end("allin", a, b, _put(inv, a, total))))
        else:
            options.append(("call", top, self._end("checkdown", a, b, _put(inv, a, top))))
            if level == 2:
                eff = min(total, self.totals[b])
                for kind, to in self._aggression(a, FOURBET * top, eff, played):
                    options.append((kind, to, self._raise_child(b, a, inv, to, 3)))
            else:
                options.append(("allin", total, self._raise_child(b, a, inv, total, 3)))
        return self._decide(at, a, options, played)

    def _raise_child(self, a: int, b: int, inv: list[float], to: float, level: int) -> _Child:
        """Потомок рейза `b` до `to`: олл-ин — `a` против олл-ина, иначе — против рейза."""
        after = _put(inv, b, to)
        if to >= self.totals[b]:
            return lambda on: self._facing_allin(a, b, after, on)
        return lambda on: self._facing_raise(a, b, after, level, on)

    def _end(self, kind: str, a: int, b: int, inv: list[float]) -> _Child:
        """Потомок-вскрытие пары `a`, `b` при вложенном `inv`: сыгранной линии дальше нет."""
        return lambda on: self._showdown(kind, a, b, inv)

    def _facing_allin(self, a: int, b: int, inv: list[float], on_path: bool) -> int:
        at = self._reserve()
        played = self._take(a, at, on_path)
        call = min(self.totals[a], inv[b])
        options = [
            ("fold", None, lambda on: self._fold(b, inv)),
            ("call", call, self._end("allin", a, b, _put(inv, a, call))),
        ]
        return self._decide(at, a, options, played)

    def _decide(self, at: int, player: int, options: list, played: Act | None) -> int:
        kinds = [kind for kind, _, _ in options]
        chosen = None
        if played is not None:
            chosen = kinds.index(played.action if played.action in kinds else "call")
            self.path.append((at, chosen))
        actions = tuple(
            Action(kind, to, child(index == chosen))
            for index, (kind, to, child) in enumerate(options)
        )
        self.nodes[at] = Decision(player, actions)
        return at

    def _aggression(
        self, player: int, rule: float, effective: float, played: Act | None
    ) -> list[tuple[str, float]]:
        """Рейз и олл-ин игрока: сыгранный рейз — как есть, рейз правила — со слиянием."""
        total = self.totals[player]
        if played is not None and played.action == "raise":
            return [("raise", played.to_bb), ("allin", total)]
        to = _round(rule)
        if to > COMMIT_SHARE * effective:
            return [("allin", total)]
        self.flags.add("fixed_sizing")
        return [("raise", to), ("allin", total)]

    def _out_of_position(self, responder: int, opener: int) -> bool:
        role = self.roles[responder]
        return role is Position.SB or (
            role is Position.BB and self.roles[opener] is not Position.SB
        )

    # --- линия -----------------------------------------------------------------------------

    def _reserve(self) -> int:
        self.nodes.append(None)
        return len(self.nodes) - 1

    def _take(self, player: int, at: int, on_path: bool) -> Act | None:
        """Следующий сыгранный ход участника; ходов не осталось — это узел героя.

        Ходы других мест между ходами участника — фолды мест вне дерева или закрытых первым
        вошедшим: в дереве у них решения нет.
        """
        if not on_path:
            return None
        seat = self.players[player].seat_index
        while self._cursor < len(self.acts):
            act = self.acts[self._cursor]
            self._cursor += 1
            if act.seat_index == seat:
                return act
        self.hero_node = at
        return None

    # --- терминалы -------------------------------------------------------------------------

    def _fold(self, winner: int, inv: list[float]) -> int:
        row = [total - put for total, put in zip(self.totals, inv)]
        row[winner] = self.totals[winner] + self.dead + sum(inv) - inv[winner]
        self.nodes.append(Terminal("fold", [row], None))
        return len(self.nodes) - 1

    def _showdown(self, kind: str, a: int, b: int, inv: list[float]) -> int:
        if kind == "checkdown":
            self.flags.add("postflop_checkdown")
        pair = (min(a, b), max(a, b))
        stake = min(inv[a], inv[b])
        others = sum(inv) - inv[a] - inv[b]
        rows = []
        for winner, loser in (pair, pair[::-1]):
            row = [total - put for total, put in zip(self.totals, inv)]
            row[winner] = self.totals[winner] + stake + self.dead + others
            row[loser] = self.totals[loser] - stake
            rows.append(row)
        self.nodes.append(Terminal(kind, rows, pair))
        return len(self.nodes) - 1


def _put(inv: list[float], player: int, to: float) -> list[float]:
    after = list(inv)
    after[player] = to
    return after


def chip_payoffs(tree: Tree) -> list[numpy.ndarray | None]:
    """По узлам дерева: у терминала — матрица `(исходы, участники)`, у решения — `None`.

    Выплата — стек участника после раздачи, BB, как `pushfold_game.chip_outcomes`.
    """
    return [
        numpy.array(node.rows, dtype=numpy.float64) if isinstance(node, Terminal) else None
        for node in tree.nodes
    ]


def icm_payoffs(
    tree: Tree, node: DecisionNode, context: TournamentContext, bounties: bool
) -> list[numpy.ndarray | None]:
    """То же в долларах модели поля: один пакетный вызов ICM на всё дерево (спека D27).

    Стол, поле и лесенка — как в `pushfold_game.icm_outcomes`: места вне дерева со своими
    стеками, выбывший — приз места `playersLeft`. При `bounties=True` победитель олл-ина, у
    проигравшего в котором не осталось фишек, получает наличные за его голову; у вскрытия без
    ставок голов нет — никто не выбывает (`with_bounties`).
    """
    seats = sorted(node.seats, key=lambda seat: seat.seat_index)
    field_count = node.players_left - len(seats)
    one = icm_field.field_stack(
        node.players_left,
        context.average_stack_bb,
        [seat.stack_bb for seat in seats],
        field_count,
    )
    protected = context.protected_ladder(node.players_left)
    ladder = context.ladder() if protected is None else protected
    busted = ladder.prize(node.players_left)
    places = [[seat.seat_index for seat in seats].index(p.seat_index) for p in tree.players]

    def expand(row: list[float]) -> list[float]:
        after = {p.seat_index: stack for p, stack in zip(tree.players, row)}
        return [after.get(seat.seat_index, seat.stack_bb) for seat in seats]

    terminals = [n for n in tree.nodes if isinstance(n, Terminal)]
    tables = [expand(row) for terminal in terminals for row in terminal.rows]
    equities, _ = icm_field.table_equities_batch(tables, field_count, one, ladder)

    values: list[numpy.ndarray | None] = []
    at = 0
    for n in tree.nodes:
        if not isinstance(n, Terminal):
            values.append(None)
            continue
        matrix = numpy.empty((len(n.rows), len(tree.players)))
        for r, row in enumerate(n.rows):
            for p, place in enumerate(places):
                matrix[r, p] = equities[at, place] if row[p] > 0 else busted
            at += 1
        values.append(matrix)
    return with_bounties(tree, values) if bounties else values


def with_bounties(
    tree: Tree, payoffs: list[numpy.ndarray | None]
) -> list[numpy.ndarray | None]:
    """Выплаты `payoffs` плюс наличные за головы: ICM на стеках исходов не пересчитывается.

    Победитель олл-ина, у проигравшего в котором не осталось фишек, получает
    `knockout_cash` его ценника. Сфолдившему по линии ценник не обязателен, и на ветке, где он
    выбывает, голова без ценника не платится.
    """
    values: list[numpy.ndarray | None] = []
    for n, matrix in zip(tree.nodes, payoffs, strict=True):
        if not isinstance(n, Terminal) or n.kind != "allin":
            values.append(matrix)
            continue
        matrix = matrix.copy()
        for r, row in enumerate(n.rows):
            winner, loser = n.pair if r == 0 else n.pair[::-1]
            price = tree.players[loser].bounty_usd
            if row[loser] == 0 and price is not None:
                matrix[r, winner] += bounty.knockout_cash(price)
        values.append(matrix)
    return values
