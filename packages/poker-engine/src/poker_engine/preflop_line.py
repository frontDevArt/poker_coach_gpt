"""Линия префлопа по кадрам раздачи и спот, в котором решает герой (спека плана 5, §4–§5).

Кадр — узел решения героя. Первый кадр префлопа показывает всё, что сделали до героя: каждое
место перед ним по порядку хода сходило один раз, и его вложенное сверх блайнда и есть
действие. Между двумя кадрами действовали герой и все, кто ходит после него, по кругу до
героя: прирост вложенного — ставка, выбывание из раздачи — фолд. Место, сходившее между
кадрами дважды, видно только итогом; в линиях двоих так не бывает — второй ход требует
третьего игрока, а это мультипот и отказ.

Ставка размечается против максимума вложенного до неё: выше — рейз (мин-рейз до 2.0 при
максимуме 1.0 тоже рейз), иначе колл, а колл 1 BB до первого рейза — лимп, в том числе
доставка малого блайнда. Стек 0 — олл-ин; олл-ин выше максимума поднимает его, как рейз.

Спот читается по линии (таблица §4 спеки), отказ — первая сработавшая причина. `history` линию
не задаёт: её задают кадры (§5.2). Лимп героя — только с `SB` первым в банк (спека модели колла
§7): за ним споты `vs_iso` (`BB` изолировал не олл-ином) и `vs_allin_after_limp`; лимп не с `SB` и
колл героя — отказ `HERO_FLAT`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .handstate import ROUNDING_STEP_BB, DecisionNode, Seat, assign_positions
from .pushfold_game import Spot, read_spot
from .types import Position, positions_for

# Ставки печатаются с шагом `ROUNDING_STEP_BB`: «равно максимуму» — в пределах полушага.
_SAME_BB = ROUNDING_STEP_BB / 2

_VOLUNTARY = frozenset({"limp", "call", "raise", "allin"})

NOT_PREFLOP = "советник префлопа работает только на префлопе"
HERO_ALL_IN = "герой уже в олл-ине: решения нет"
PUSHFOLD_SPOT = "спот push/fold: отвечает советник pushfold"
MULTIWAY = "в банк до героя вошли двое и больше: мультипот вне модели"
AMBIGUOUS = "линия неоднозначна: нужен кадр предыдущего решения героя"
FIVE_BET = "5-бет не олл-ином: вне дерева префлопа"
BIG_BLIND_WALK = "все сфолдили до большого блайнда: решения нет"
HERO_FLAT = "герой вошёл в банк лимпом или коллом: линия вне дерева префлопа"


@dataclass(frozen=True)
class Act:
    """Одно действие линии: место, действие и вложенное «до» после него (у фолда — `None`)."""

    seat_index: int
    action: str
    to_bb: float | None


@dataclass(frozen=True)
class Line:
    """Линия префлопа до решения героя.

    `players` — корень дерева первым (первый добровольно вошедший, а если таких нет — герой),
    дальше по порядку хода все, кто ещё в раздаче или вкладывал на префлопе; места — из
    последнего кадра. `opponent_at` — соперник, против которого решает герой, `None` в `open`.
    """

    kind: str
    acts: list[Act]
    players: list[Seat]
    hero_at: int
    opponent_at: int | None


def read_line(nodes: list[DecisionNode]) -> Line | str:
    """Линия по кадрам раздачи или причина отказа.

    Предусловие: узлы прошли `validate_hand`, разбирается последний. Улицы не убывают, поэтому
    при последнем узле на префлопе на префлопе и все.
    """
    found = _read(nodes)
    return found if isinstance(found, str) else found[0]


def read_closed_line(preflop_nodes: list[DecisionNode], next_node: DecisionNode) -> Line | str:
    """Линия префлопа целиком — до последнего действия улицы — или причина отказа `read_line`.

    Кадры префлопа дают линию до последнего решения героя; что сделали после него герой и
    остальные, видно по первому кадру следующей улицы (спека тренера §7.3): вложенное места на
    префлопе — его стек на старте раздачи минус стек на старте следующей улицы, а до флопа дошли
    те, кто в раздаче там. Каждое место между кадрами ходит не больше раза, как и между двумя
    кадрами префлопа. Чек виден только тем, что вложенное не выросло: его делает `BB` в банке без
    рейза. Предусловие: `preflop_nodes` и `next_node` — подряд идущие кадры одной раздачи,
    прошедшей `validate_hand`.
    """
    found = _read(preflop_nodes)
    if isinstance(found, str):
        return found
    line, walk, cycle, positions = found
    last = {seat.seat_index: seat for seat in preflop_nodes[-1].seats}
    closing = _closing(preflop_nodes, next_node)
    for seat in cycle:
        index = seat.seat_index
        if index in closing and last[index].in_hand:
            before = len(walk.acts)
            walk.step(last[index].invested_bb, closing[index])
            if (
                len(walk.acts) == before
                and closing[index].in_hand
                and walk._level == 0
                and positions[index] is Position.BB
            ):
                walk._add(Act(index, "check", None))
    return replace(line, acts=list(walk.acts))


def flop_players(preflop_nodes: list[DecisionNode], next_node: DecisionNode) -> list[int]:
    """Места, дошедшие до следующей улицы, по местам кадра. Предусловие — как у
    `read_closed_line`."""
    return [index for index, seat in _closing(preflop_nodes, next_node).items() if seat.in_hand]


def _closing(preflop_nodes: list[DecisionNode], next_node: DecisionNode) -> dict[int, Seat]:
    """Место → оно же на исходе префлопа: вложенное за улицу, стек на старте следующей и в
    раздаче ли оно там.

    До следующей улицы дошёл тот, кто в раздаче на её кадре, и тот, кто уравнял наибольшее
    вложенное префлопа: место, сфолдившее на флопе до героя, на его кадре уже вне раздачи, а на
    префлопе фолда у него не было.
    """
    began = {seat.seat_index: seat.stack_bb + seat.invested_bb for seat in preflop_nodes[0].seats}
    starts = {seat.seat_index: seat.stack_bb + seat.invested_bb for seat in next_node.seats}
    put = {index: began[index] - start for index, start in starts.items() if index in began}
    top = max(put.values())
    return {
        seat.seat_index: replace(
            seat,
            stack_bb=starts[seat.seat_index],
            invested_bb=put[seat.seat_index],
            in_hand=seat.in_hand or put[seat.seat_index] > top - _SAME_BB,
        )
        for seat in next_node.seats
        if seat.seat_index in put
    }


def _read(nodes: list[DecisionNode]):
    """`read_line` и то, что нужно дочитать линию до конца улицы: обход, круг хода от героя
    и позиции мест."""
    node = nodes[-1]
    if node.street != "preflop":
        return NOT_PREFLOP
    hero = node.hero
    if hero.stack_bb == 0:
        return HERO_ALL_IN
    if isinstance(read_spot(node), Spot):
        return PUSHFOLD_SPOT

    positions = assign_positions(node)
    order = positions_for(len(node.seats))
    seats = sorted(node.seats, key=lambda seat: order.index(positions[seat.seat_index]))
    blinds = {
        seat.seat_index: _blind(positions[seat.seat_index]) for seat in seats
    }

    first = {seat.seat_index: seat for seat in nodes[0].seats}
    if first[hero.seat_index].invested_bb > blinds[hero.seat_index] + _SAME_BB:
        return AMBIGUOUS

    walk = _Walk()
    hero_turn = [seat.seat_index for seat in seats].index(hero.seat_index)
    for seat in seats[:hero_turn]:
        walk.step(blinds[seat.seat_index], first[seat.seat_index])
    cycle = seats[hero_turn:] + seats[:hero_turn]
    for earlier, later in zip(nodes, nodes[1:]):
        was = {seat.seat_index: seat for seat in earlier.seats}
        now = {seat.seat_index: seat for seat in later.seats}
        for seat in cycle:
            index = seat.seat_index
            if index in was and index in now and was[index].in_hand:
                walk.step(was[index].invested_bb, now[index])

    entrants = {
        act.seat_index
        for act in walk.acts
        if act.action in _VOLUNTARY and act.seat_index != hero.seat_index
    }
    if len(entrants) > 1:
        return MULTIWAY
    kind = _kind(walk, hero, positions[hero.seat_index])
    if kind not in _KINDS:
        return kind

    voluntary = [act.seat_index for act in walk.acts if act.action in _VOLUNTARY]
    root = voluntary[0] if voluntary else hero.seat_index
    start = [seat.seat_index for seat in seats].index(root)
    players = [
        seat
        for seat in seats[start:] + seats[:start]
        if seat.in_hand or seat.invested_bb > 0
    ]
    at = [seat.seat_index for seat in players]
    line = Line(
        kind=kind,
        acts=list(walk.acts),
        players=players,
        hero_at=at.index(hero.seat_index),
        opponent_at=at.index(entrants.pop()) if entrants else None,
    )
    return line, walk, cycle, positions


_KINDS = frozenset(
    {
        "open",
        "vs_open",
        "vs_3bet",
        "vs_4bet",
        "vs_allin_after_raise",
        "vs_limp",
        "vs_iso",
        "vs_allin_after_limp",
    }
)


def _blind(position: Position) -> float:
    if position is Position.SB:
        return 0.5
    if position is Position.BB:
        return 1.0
    return 0.0


class _Walk:
    """Обход действий по порядку хода: линия и номер рейза после каждого действия."""

    def __init__(self) -> None:
        self.acts: list[Act] = []
        self.levels: list[int] = []
        self._top = 1.0
        self._level = 0

    def step(self, was_bb: float, seat: Seat) -> None:
        """Место с вложенным `was_bb` до хода; в `seat` — оно же после хода."""
        to = seat.invested_bb
        if to > was_bb + _SAME_BB:
            if to > self._top + _SAME_BB:
                self._top = to
                self._level += 1
                action = "allin" if seat.stack_bb == 0 else "raise"
            elif seat.stack_bb == 0:
                action = "allin"
            else:
                action = "limp" if self._level == 0 else "call"
            self._add(Act(seat.seat_index, action, to))
        if not seat.in_hand:
            self._add(Act(seat.seat_index, "fold", None))

    def _add(self, act: Act) -> None:
        self.acts.append(act)
        self.levels.append(self._level)


def _kind(walk: _Walk, hero: Seat, position: Position) -> str:
    """Спот по линии с не больше чем одним вошедшим соперником, или причина отказа."""
    mine = [at for at, act in enumerate(walk.acts) if act.seat_index == hero.seat_index]
    theirs = [
        at
        for at, act in enumerate(walk.acts)
        if act.seat_index != hero.seat_index and act.action in _VOLUNTARY
    ]
    if not mine:
        if not theirs:
            return BIG_BLIND_WALK if position is Position.BB else "open"
        action = walk.acts[theirs[-1]].action
        if action == "raise":
            return "vs_open"
        if action == "limp":
            return "vs_limp"
        # Олл-ин до первого решения героя — спот `facing_allin` советника `pushfold`
        # при любом стеке (спека §4), даже если сам `pushfold` узел не взял.
        return PUSHFOLD_SPOT
    if walk.acts[mine[-1]].action == "limp" and position is Position.SB:
        # Первым в банк: лимп после чужого лимпа — два вошедших, отказ `MULTIWAY` выше.
        if theirs and theirs[-1] > mine[-1]:
            reply = walk.acts[theirs[-1]].action
            return "vs_allin_after_limp" if reply == "allin" else "vs_iso"
    if walk.acts[mine[-1]].action != "raise":
        return HERO_FLAT
    reply = walk.acts[theirs[-1]].action
    if reply == "allin":
        return "vs_allin_after_raise"
    level = walk.levels[mine[-1]]
    if level == 1:
        return "vs_3bet"
    if level == 2:
        return "vs_4bet"
    return FIVE_BET
