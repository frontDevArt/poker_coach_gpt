"""Подыгра push/fold из узла скриншота: кто в ней играет, чем она кончается, что стоит исход.

Узел — момент перед решением героя на префлопе. Подыгра начинается с первого игрока, который
ещё может открыть банк (спека плана 4, §5.1): в споте `first_in` это герой, в споте
`facing_allin` — соперник, уже пошедший олл-ин. Отвечающие — все в раздаче после
открывающего по порядку хода. У каждого два действия: открывающий — олл-ин или фолд,
отвечающий — колл или фолд; первый колл закрывает действие (без оверколлов, §5.4).

Исходы — `steal` (все сфолдили, банк открывающему), `walk` (открывающий сфолдил, банк
большому блайнду) и по паре `win`/`lose` на каждого отвечающего: открывающий выиграл или
проиграл олл-ин против него. Места вне подыгры (`bystanders`) ни в одном исходе не меняются.

**Мёртвые деньги.** Всё, что лежит в банке, но не вложено участниками подыгры: анте и
вложения сфолдивших. Распознавание даёт `potBb` и `investedBb` с округлением до
`ROUNDING_STEP_BB`, поэтому банк чуть меньше суммы вложений — шум округления: в пределах
шага на место недостача обнуляется, глубже — ошибка ввода. При обнулённой недостаче
сохранение фишек в исходах выполняется для стеков с вложенными, а не с прочитанным банком.

**`fold_as_walk`.** Фолд героя в споте `first_in` — исход `walk`: банк забирает большой
блайнд, остальные не меняются. Полная модель продолжила бы раздачу без героя; советник
помечает упрощение (спека §5.2). В споте `facing_allin` ряд `walk` тоже строится, но
равновесию не нужен: открывающий уже в олл-ине и сфолдить не может.

**Почему ICM только на исходах (D3).** У олл-инщика `stackBb == 0`, и `analyze` такой узел
отвергает: эквити «сейчас» при неразыгранном банке не определено. Подыгре оно не нужно —
ICM считается на стеках после раздачи, а там стек олл-инщика определён: банк ему, возврат
излишка или ноль и выбывание. Выбывший получает приз места `playersLeft`.

**Стек поля (D23).** Стек игрока поля — `icm_field.field_stack` по стекам **до** раздачи,
как в `analyze`: `playersLeft × средний − Σ stackBb`. Фишки банка и вложенное за столом в
`Σ stackBb` не входят и приписываются полю — смещение `банк / F` на игрока поля, на фикстуре
плана 3 около 0.02 BB. Формула общая с `analyze` ради согласия двух ответов; не чинится.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import bounty, icm_field
from .handstate import (
    ROUNDING_STEP_BB,
    DecisionNode,
    Seat,
    TournamentContext,
    assign_positions,
)
from .types import Position, positions_for

# Калибровочная константа спеки §4.1, а не результат расчёта: выше этого эффективного стека
# у героя есть рейз и лимп, и модель «только олл-ин или фолд» врёт.
PUSHFOLD_MAX_BB = 12.0

_NOT_ALL_IN = "банк открыт не олл-ином: это не спот push/fold"


@dataclass(frozen=True)
class Spot:
    """Подыгра push/fold. `players[0]` — открывающий, дальше отвечающие по порядку хода.

    `totals` — `stackBb + investedBb` каждого участника, `dead_bb` — банк минус вложения
    участников, `bb_at` — индекс большого блайнда в `players` (ему банк в исходе `walk`).
    """

    kind: str
    players: list[Seat]
    hero_at: int
    bb_at: int
    totals: list[float]
    dead_bb: float
    bystanders: list[Seat]


@dataclass(frozen=True)
class Outcomes:
    """Выплаты участникам в порядке `Spot.players` по каждому исходу.

    `win[k]` — открывающий выиграл олл-ин против `players[k + 1]`, `lose[k]` — проиграл.
    """

    steal: list[float]
    walk: list[float]
    win: list[list[float]]
    lose: list[list[float]]


def read_spot(node: DecisionNode) -> Spot | str:
    """Спот push/fold из узла или причина, почему это не он.

    Предусловие: узел прошёл `validate_hand`. Проверки идут в порядке таблицы плана 4
    (Задача 2): первая сработавшая причина и есть ответ.
    """
    if node.street != "preflop":
        return "push/fold советует только на префлопе"
    hero = node.hero
    if hero.stack_bb == 0:
        return "герой уже в олл-ине: решения нет"

    positions = assign_positions(node)
    order = positions_for(len(node.seats))
    seats = sorted(node.seats, key=lambda seat: order.index(positions[seat.seat_index]))
    hero_turn = seats.index(hero)
    before = [seat for seat in seats[:hero_turn] if seat.in_hand]

    if positions[hero.seat_index] is Position.BB and not before:
        return "все сфолдили до большого блайнда: решения нет"
    if any(seat.stack_bb > 0 for seat in before):
        return _NOT_ALL_IN
    # Олл-инщик перед героем — единственный, кому позволено вложить больше блайнда.
    for seat in seats:
        if seat not in before and not _posted_at_most_a_blind(seat, positions[seat.seat_index]):
            return _NOT_ALL_IN
    if len(before) > 1:
        return "олл-инов перед героем больше одного: мультипот вне модели"

    if before:
        opener = before[0]
        if opener.invested_bb <= hero.invested_bb:
            return "к коллу ничего: олл-ин не больше вложенного героем"
        kind = "facing_allin"
    else:
        opener = hero
        kind = "first_in"

    responders = [seat for seat in seats[seats.index(opener) + 1 :] if seat.in_hand]
    for seat in responders:
        if seat.stack_bb == 0:
            return f"место {seat.seat_index} уже в олл-ине с блайнда: вне модели"
    players = [opener, *responders]
    bystanders = [seat for seat in seats if seat not in players]
    for seat in bystanders:
        if seat.stack_bb == 0:
            return f"на месте {seat.seat_index} стек 0 вне раздачи: ICM не определён"
    big_blind = [at for at, seat in enumerate(players) if positions[seat.seat_index] is Position.BB]
    if not big_blind:
        return "большой блайнд не в раздаче: спот не распознан"

    totals = [seat.stack_bb + seat.invested_bb for seat in players]
    if kind == "first_in":
        effective = min(totals[0], max(totals[1:]))
        if effective > PUSHFOLD_MAX_BB:
            return (
                f"эффективный стек {effective:.1f} BB выше порога push/fold "
                f"{PUSHFOLD_MAX_BB:.0f} BB"
            )

    return Spot(
        kind=kind,
        players=players,
        hero_at=players.index(hero),
        bb_at=big_blind[0],
        totals=totals,
        dead_bb=_dead_money(node, players),
        bystanders=bystanders,
    )


def _posted_at_most_a_blind(seat: Seat, position: Position) -> bool:
    """`SB` вложил меньше большого блайнда, `BB` — не больше, остальные — ничего."""
    if position is Position.SB:
        return seat.invested_bb < 1.0
    if position is Position.BB:
        return seat.invested_bb <= 1.0
    return seat.invested_bb == 0


def _dead_money(node: DecisionNode, players: list[Seat]) -> float:
    invested = sum(seat.invested_bb for seat in node.seats)
    loose = node.pot_bb - invested
    if loose < -ROUNDING_STEP_BB * len(node.seats):
        raise ValueError(
            f"банк меньше суммы вложений мест: {node.pot_bb:.1f} BB против {invested:.1f} BB"
        )
    folded = sum(seat.invested_bb for seat in node.seats if seat not in players)
    return max(loose, 0.0) + folded


def chip_outcomes(spot: Spot) -> Outcomes:
    """Выплата по фишкам — стек участника после раздачи, BB."""
    return Outcomes(
        steal=_collect(spot, 0),
        walk=_collect(spot, spot.bb_at),
        win=[_showdown(spot, 0, j) for j in range(1, len(spot.players))],
        lose=[_showdown(spot, j, 0) for j in range(1, len(spot.players))],
    )


def _collect(spot: Spot, winner: int) -> list[float]:
    """Все остальные сфолдили: `winner` забирает банк, остальные теряют вложенное."""
    row = [seat.stack_bb for seat in spot.players]
    row[winner] = spot.totals[winner] + spot.dead_bb + sum(
        seat.invested_bb for at, seat in enumerate(spot.players) if at != winner
    )
    return row


def _showdown(spot: Spot, winner: int, loser: int) -> list[float]:
    """Олл-ин двоих: каждый ставит `stake`, излишок сверх него остаётся владельцу."""
    totals = spot.totals
    stake = min(totals[winner], totals[loser])
    others = sum(
        seat.invested_bb for at, seat in enumerate(spot.players) if at not in (winner, loser)
    )
    row = [seat.stack_bb for seat in spot.players]
    row[winner] = spot.dead_bb + others + 2 * stake + (totals[winner] - stake)
    row[loser] = totals[loser] - stake
    return row


def _table(spot: Spot) -> list[Seat]:
    return sorted([*spot.players, *spot.bystanders], key=lambda seat: seat.seat_index)


def _expand(spot: Spot, row: list[float]) -> list[float]:
    """Стеки участников → стеки всех мест стола по возрастанию `seatIndex`."""
    after = {seat.seat_index: stack for seat, stack in zip(spot.players, row)}
    return [after.get(seat.seat_index, seat.stack_bb) for seat in _table(spot)]


def outcome_stacks(spot: Spot) -> dict[str, list[float] | list[list[float]]]:
    """Стеки всех мест стола (по возрастанию `seatIndex`) по каждому исходу; выбывший — 0."""
    chips = chip_outcomes(spot)
    return {
        "steal": _expand(spot, chips.steal),
        "walk": _expand(spot, chips.walk),
        "win": [_expand(spot, row) for row in chips.win],
        "lose": [_expand(spot, row) for row in chips.lose],
    }


def icm_outcomes(
    spot: Spot,
    node: DecisionNode,
    context: TournamentContext,
    bounties: bool,
) -> Outcomes:
    """Выплата по ICM — эквити участника в долларах на модели поля после исхода.

    Один вызов `table_equities` на исход, `2m + 2` на подыгру с `m` отвечающими. При
    `bounties=True` победитель нокаута получает сверх ICM наличные за голову выбитого.
    """
    seats = _table(spot)
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
    places = [[seat.seat_index for seat in seats].index(p.seat_index) for p in spot.players]

    def value(row: list[float]) -> list[float]:
        table = _expand(spot, row)
        alive = [at for at, stack in enumerate(table) if stack > 0]
        equities, _ = icm_field.table_equities(
            [table[at] for at in alive], field_count, one, ladder
        )
        by_place = dict(zip(alive, equities))
        return [by_place.get(place, busted) for place in places]

    chips = chip_outcomes(spot)
    responders = range(1, len(spot.players))
    plain = Outcomes(
        steal=value(chips.steal),
        walk=value(chips.walk),
        win=[value(chips.win[j - 1]) for j in responders],
        lose=[value(chips.lose[j - 1]) for j in responders],
    )
    return with_bounties(spot, plain) if bounties else plain


def with_bounties(spot: Spot, outcomes: Outcomes) -> Outcomes:
    """Выплаты `outcomes` плюс наличные за голову победителю каждого нокаута.

    Нокаут — исход `win`/`lose`, в котором у проигравшего не осталось фишек. Отдельно от
    `icm_outcomes`, чтобы советник считал ICM на стеках исходов один раз и для ответа с
    головами, и для ответа без них (план 4, Задача 4).
    """
    chips = chip_outcomes(spot)

    def showdown(payout: list[float], row: list[float], winner: int, loser: int) -> list[float]:
        payout = list(payout)
        price = spot.players[loser].bounty_usd
        if row[loser] == 0 and price is not None:
            payout[winner] += bounty.knockout_cash(price)
        return payout

    responders = range(1, len(spot.players))
    return Outcomes(
        steal=list(outcomes.steal),
        walk=list(outcomes.walk),
        win=[showdown(outcomes.win[j - 1], chips.win[j - 1], 0, j) for j in responders],
        lose=[showdown(outcomes.lose[j - 1], chips.lose[j - 1], j, 0) for j in responders],
    )
