"""Схема раздачи, снятой со скриншотов, и её детерминированная проверка.

Раздача — это турнирный контекст плюс упорядоченный список узлов решения,
по одному на скриншот. Отдельного механизма истории нет: весь список и
есть история.

Валидатор запускается до любого расчёта. Он ловит то, что физически
невозможно (дубль карты, вернувшийся в раздачу игрок, несходящиеся фишки),
а не то, что маловероятно. Каждое сообщение об ошибке видит пользователь.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._checks import check_non_negative, check_positive
from .equity import FULL_DECK
from .types import Position, positions_for

STREETS = ("preflop", "flop", "turn", "river")
BOARD_SIZE = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}

# Клиент печатает стеки с точностью 0.1 BB. Сумма по местам расходится
# на величину порядка этого шага, и это не ошибка распознавания.
ROUNDING_STEP_BB = 0.1


@dataclass(frozen=True)
class Seat:
    seat_index: int
    name: str
    stack_bb: float
    invested_bb: float
    in_hand: bool
    is_hero: bool
    vpip: float | None
    vpip_hands: int | None


@dataclass(frozen=True)
class DecisionNode:
    street: str
    level: int
    blinds: dict
    hero_rank: int
    players_left: int
    seats: list[Seat]
    button_seat: int
    hero_cards: list[str]
    board: list[str]
    pot_bb: float
    to_call_bb: float
    raise_to_bb: float | None

    @property
    def hero(self) -> Seat:
        for seat in self.seats:
            if seat.is_hero:
                return seat
        raise ValueError("в узле нет героя")


@dataclass(frozen=True)
class Payout:
    first: int
    last: int
    amount: float


@dataclass(frozen=True)
class TournamentContext:
    payouts: list[Payout]
    places_paid: int
    entrants: int
    players_left: int
    late_reg_open: bool
    seats_per_table: int
    average_stack_bb: float


def _require(raw: dict, key: str):
    if key not in raw:
        raise ValueError(f"в данных нет обязательного поля {key!r}")
    return raw[key]


def context_from_dict(raw: dict) -> TournamentContext:
    payouts = [
        Payout(
            first=int(_require(entry, "from")),
            last=int(_require(entry, "to")),
            amount=float(_require(entry, "amount")),
        )
        for entry in _require(raw, "payouts")
    ]
    return TournamentContext(
        payouts=payouts,
        places_paid=int(_require(raw, "placesPaid")),
        entrants=int(_require(raw, "entrants")),
        players_left=int(_require(raw, "playersLeft")),
        late_reg_open=bool(_require(raw, "lateRegOpen")),
        seats_per_table=int(_require(raw, "seatsPerTable")),
        average_stack_bb=float(_require(raw, "averageStackBb")),
    )


def node_from_dict(raw: dict) -> DecisionNode:
    seats = [
        Seat(
            seat_index=int(_require(entry, "seatIndex")),
            name=str(entry.get("name", "")),
            stack_bb=float(_require(entry, "stackBb")),
            invested_bb=float(entry.get("investedBb", 0.0)),
            in_hand=bool(_require(entry, "inHand")),
            is_hero=bool(entry.get("isHero", False)),
            vpip=None if entry.get("vpip") is None else float(entry["vpip"]),
            vpip_hands=(
                None if entry.get("vpipHands") is None else int(entry["vpipHands"])
            ),
        )
        for entry in _require(raw, "seats")
    ]
    raise_to = raw.get("raiseToBb")
    return DecisionNode(
        street=str(_require(raw, "street")),
        level=int(raw.get("level", 0)),
        blinds=dict(raw.get("blinds", {})),
        hero_rank=int(_require(raw, "heroRank")),
        players_left=int(_require(raw, "playersLeft")),
        seats=seats,
        button_seat=int(_require(raw, "buttonSeat")),
        hero_cards=list(_require(raw, "heroCards")),
        board=list(raw.get("board", [])),
        pot_bb=float(_require(raw, "potBb")),
        to_call_bb=float(_require(raw, "toCallBb")),
        raise_to_bb=None if raise_to is None else float(raise_to),
    )


def assign_positions(node: DecisionNode) -> dict[int, Position]:
    """Место за столом → позиция, отсчитанная от кнопки.

    Позиции не подписаны на скриншоте и не называются моделью: порядок
    берётся из `positions_for`, который уже знает неочевидные соглашения
    для 2 и 6 игроков, и разворачивается по кругу от кнопки.
    """
    seats = sorted(node.seats, key=lambda seat: seat.seat_index)
    order = positions_for(len(seats))
    button_at = next(
        i for i, seat in enumerate(seats) if seat.seat_index == node.button_seat
    )
    button_in_order = order.index(Position.BTN)
    shift = button_at - button_in_order
    return {
        seats[(button_in_order + offset + shift) % len(seats)].seat_index: order[
            (button_in_order + offset) % len(order)
        ]
        for offset in range(len(seats))
    }


def payout_ladder(context: TournamentContext, places: int) -> list[float]:
    """Призовые по местам от первого, добитые нулями до `places`."""
    ladder = [0.0] * places
    for payout in context.payouts:
        for place in range(payout.first, payout.last + 1):
            if 1 <= place <= places:
                ladder[place - 1] = payout.amount
    return ladder


def validate_hand(
    context: TournamentContext, nodes: list[DecisionNode]
) -> None:
    """Проверяет раздачу целиком. Бросает `ValueError` при нарушении."""
    if not nodes:
        raise ValueError("в раздаче нет ни одного узла решения")

    _validate_context(context)
    for node in nodes:
        _validate_node(node)
    for earlier, later in zip(nodes, nodes[1:]):
        _validate_transition(earlier, later)


def _validate_context(context: TournamentContext) -> None:
    if not context.payouts:
        raise ValueError("лесенка выплат пуста")
    seen: set[int] = set()
    previous_amount: float | None = None
    for payout in sorted(context.payouts, key=lambda p: p.first):
        if payout.first < 1 or payout.last < payout.first:
            raise ValueError(
                f"неверный интервал мест в выплатах: {payout.first}–{payout.last}"
            )
        check_positive(payout.amount, f"выплата за место {payout.first}")
        places = set(range(payout.first, payout.last + 1))
        if places & seen:
            raise ValueError(
                f"интервалы выплат пересекаются на месте "
                f"{min(places & seen)}"
            )
        seen |= places
        if previous_amount is not None and payout.amount > previous_amount:
            raise ValueError("выплата за более низкое место больше, чем за высокое")
        previous_amount = payout.amount
    if context.entrants < context.players_left:
        raise ValueError(
            f"осталось игроков ({context.players_left}) больше, чем входов "
            f"({context.entrants})"
        )
    check_positive(context.average_stack_bb, "средний стек")


def _validate_node(node: DecisionNode) -> None:
    if node.street not in BOARD_SIZE:
        raise ValueError(f"неизвестная улица: {node.street!r}")
    if len(node.board) != BOARD_SIZE[node.street]:
        raise ValueError(
            f"на улице {node.street} должно быть {BOARD_SIZE[node.street]} карт "
            f"на доске, получено {len(node.board)}"
        )

    indices = [seat.seat_index for seat in node.seats]
    if len(set(indices)) != len(indices):
        raise ValueError("места за столом повторяются")
    # Границы 2..9 и соглашения для 2 и 6 игроков — забота positions_for.
    positions_for(len(node.seats))
    if node.button_seat not in indices:
        raise ValueError(f"кнопки нет среди мест за столом: {node.button_seat}")

    heroes = [seat for seat in node.seats if seat.is_hero]
    if len(heroes) != 1:
        raise ValueError(f"героев в узле должно быть ровно один, найдено {len(heroes)}")
    if not heroes[0].in_hand:
        raise ValueError("герой помечен как выбывший из раздачи")

    for seat in node.seats:
        check_non_negative(seat.stack_bb, f"стек на месте {seat.seat_index}")
        check_non_negative(seat.invested_bb, f"вложение на месте {seat.seat_index}")

    check_positive(node.pot_bb, "банк")
    check_non_negative(node.to_call_bb, "сумма колла")
    if node.raise_to_bb is not None and node.raise_to_bb <= node.to_call_bb:
        raise ValueError("рейз не превышает сумму колла")

    if node.players_left < len(node.seats):
        raise ValueError(
            f"осталось игроков ({node.players_left}) меньше, чем за столом "
            f"({len(node.seats)})"
        )
    if not 1 <= node.hero_rank <= node.players_left:
        raise ValueError(
            f"ранг героя ({node.hero_rank}) вне поля из {node.players_left} игроков"
        )

    # Личность карт проверяется здесь, а не откладывается до equity_vs_range
    # в Task 7: там она всплывёт как ошибка про склейку "JhXz", которой
    # пользователь не писал. Источник — vision-модель, `"Xz"` от неё реален.
    if len(node.hero_cards) != 2:
        raise ValueError(
            f"у героя должно быть 2 карты, получено {len(node.hero_cards)}"
        )
    cards = list(node.hero_cards) + list(node.board)
    for card in cards:
        if card not in FULL_DECK:
            raise ValueError(f"неизвестная карта: {card!r}")
    if len(set(cards)) != len(cards):
        raise ValueError(f"карта встречается дважды: {sorted(cards)}")


def _validate_transition(earlier: DecisionNode, later: DecisionNode) -> None:
    if STREETS.index(later.street) <= STREETS.index(earlier.street):
        raise ValueError(
            f"улицы не идут по порядку: {earlier.street} → {later.street}"
        )
    if list(later.hero_cards) != list(earlier.hero_cards):
        raise ValueError("карты героя изменились внутри раздачи")
    if list(later.board[: len(earlier.board)]) != list(earlier.board):
        raise ValueError("доска не продолжает предыдущую улицу")

    was_in = {seat.seat_index for seat in earlier.seats if seat.in_hand}
    now_in = {seat.seat_index for seat in later.seats if seat.in_hand}
    returned = now_in - was_in
    if returned:
        raise ValueError(f"игрок вернулся в раздачу после фолда: место {min(returned)}")

    before = sum(seat.stack_bb for seat in earlier.seats) + earlier.pot_bb
    after = sum(seat.stack_bb for seat in later.seats) + later.pot_bb
    tolerance = ROUNDING_STEP_BB * max(len(earlier.seats), len(later.seats))
    if abs(before - after) > tolerance:
        raise ValueError(
            f"фишки не сходятся между улицами: было {before:.1f} BB, "
            f"стало {after:.1f} BB"
        )
