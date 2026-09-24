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
from .ladder import PayoutLadder
from .profiles import check_vpip
from .types import Position, positions_for

BOARD_SIZE = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}
# Порядок улиц — ключи `BOARD_SIZE` в порядке вставки (гарантия языка), а не
# второй независимый источник истины: расхождение дало бы `ValueError` от
# `list.index` вместо пользовательского текста.
STREETS = tuple(BOARD_SIZE)

# Клиент печатает стеки с точностью 0.1 BB. Сумма по местам расходится
# на величину порядка этого шага, и это не ошибка распознавания.
ROUNDING_STEP_BB = 0.1


@dataclass(frozen=True)
class Seat:
    """Одно место за столом на одном скриншоте.

    `vpip` — процент 0..100 (как в `profiles.py`), не доля 0..1; `None`,
    когда клиент бейдж не показал. `invested_bb` — уже вложенное этим местом
    в текущую улицу; `DecisionNode.pot_bb` (см. ниже) подразумевается уже
    учитывающим эти вложения, отдельно они к банку не прибавляются.

    `bounty_usd` — ценник головы PKO, как показан над игроком: наличные,
    которые получит выбивший (`bounty.py`). `None` — ценника на экране нет;
    ни одного ценника за столом — классический турнир.
    """

    seat_index: int
    name: str
    stack_bb: float
    invested_bb: float
    in_hand: bool
    is_hero: bool
    vpip: float | None
    vpip_hands: int | None
    bounty_usd: float | None


@dataclass(frozen=True)
class DecisionNode:
    """Один снимок раздачи — одно решение на одном скриншоте.

    `pot_bb` — банк на момент снимка, уже включающий вложения текущей улицы
    (`Seat.invested_bb` по каждому месту); проверка сохранения фишек между
    узлами (`_validate_transition`) складывает только стеки и банк ровно
    поэтому — второй раз вложенное не прибавляется.
    """

    street: str
    level: int
    blinds: dict[str, int]
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
        """Место героя. Предусловие: узел уже прошёл `validate_hand`, который
        гарантирует ровно одного героя — здесь второй гард на то же условие не
        заводится (см. `assign_positions`), а нарушение предусловия называется
        по имени, а не пересказывается вторым пользовательским текстом."""
        for seat in self.seats:
            if seat.is_hero:
                return seat
        raise ValueError(
            "нарушено предусловие: DecisionNode.hero вызывать только после "
            "validate_hand, который гарантирует ровно одного героя в узле"
        )


@dataclass(frozen=True)
class Payout:
    first: int
    last: int
    amount: float


@dataclass(frozen=True)
class TournamentContext:
    """Турнирный контекст раздачи — общий для всех узлов одной раздачи,
    в отличие от `DecisionNode`, который снимается на каждом скриншоте."""

    payouts: list[Payout]
    places_paid: int
    entrants: int
    players_left: int
    late_reg_open: bool
    seats_per_table: int
    # `None` — законное отсутствие: средний стек нужен только, чтобы
    # населить поле вне стола (`analyze._field_stack`), и на финальном
    # столе требовать его означало бы требовать число ни для чего.
    average_stack_bb: float | None

    def ladder(self) -> PayoutLadder:
        """Лесенка выплат контекста. Её гарды — у `PayoutLadder`."""
        return PayoutLadder(
            [(payout.first, payout.last, payout.amount) for payout in self.payouts],
            places_paid=self.places_paid,
        )


def _present(raw, key: str) -> bool:
    """Есть ли у поля значение, и объект ли вообще то, у чего его спрашивают.

    Единственная точка, где проверяется форма контейнера. Список объектов
    приходит от vision-модели, и `null` либо число внутри `seats` или
    `payouts` от неё так же реальны, как испорченное поле: без этой проверки
    `key not in raw` бросал бы английский `TypeError: argument of type
    'NoneType' is not a container`, который `cli.main` не ловит — наружу
    уходил бы трейсбек вместо разбираемого ответа с ключом `error`.

    Проверка стоит здесь, а не в разборе каждого списка, потому что дефект
    один на весь слой: любое будущее вложение получает её даром.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"ожидался объект с полем {key!r}, получено {raw!r}")
    return key in raw and raw[key] is not None


def _require(raw: dict, key: str):
    """Значение обязательного поля. `None` — то же нарушение, что и его отсутствие:
    источник данных — vision-модель, и не увидевшая поле модель и увидевшая в нём
    пустоту дают пользователю одну и ту же причину не доверять скриншоту.
    """
    if not _present(raw, key):
        raise ValueError(f"в данных нет обязательного поля {key!r}")
    return raw[key]


def _as_int(raw: dict, key: str) -> int:
    """Обязательное поле как целое число. Мусор (не число, дробь с текстом и т.п.)
    — тот же класс отказа, что и отсутствующее поле, а не программная ошибка."""
    value = _require(raw, key)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"поле {key!r} должно быть целым числом, получено {value!r}"
        ) from None


def _as_float(raw: dict, key: str) -> float:
    """Обязательное поле как вещественное число, см. `_as_int`."""
    value = _require(raw, key)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"поле {key!r} должно быть числом, получено {value!r}"
        ) from None


def _as_optional_int(raw: dict, key: str, default: int | None = None) -> int | None:
    """Необязательное поле как целое число. Отсутствие ключа и `null` — не
    ошибка, это законное «модель не увидела значение», и обе формы дают
    `default`. Ошибка — только когда поле присутствует, но не число: тот же
    класс отказа, что и мусор в обязательном поле (`_as_int`), поэтому и
    сообщение то же по форме."""
    if not _present(raw, key):
        return default
    value = raw[key]
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"поле {key!r} должно быть целым числом, получено {value!r}"
        ) from None


def _as_optional_float(
    raw: dict, key: str, default: float | None = None
) -> float | None:
    """Необязательное поле как вещественное число, см. `_as_optional_int`."""
    if not _present(raw, key):
        return default
    value = raw[key]
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"поле {key!r} должно быть числом, получено {value!r}"
        ) from None


def _as_bool(raw: dict, key: str) -> bool:
    """Обязательное поле как булево. `bool(...)` здесь неприменим: строка
    `"false"` от vision-модели истинна, и место, объявленное сфолдившим,
    молча вернулось бы в раздачу. Наружу ушёл бы не отказ, а правдоподобный
    неверный ответ — это хуже английского `TypeError`, ради которого писан
    остальной слой разбора."""
    value = _require(raw, key)
    if not isinstance(value, bool):
        raise ValueError(
            f"поле {key!r} должно быть true или false, получено {value!r}"
        )
    return value


def _as_optional_bool(raw: dict, key: str, default: bool = False) -> bool:
    """Необязательное поле как булево, см. `_as_bool`. Отсутствие ключа и
    `null` дают `default`."""
    if not _present(raw, key):
        return default
    value = raw[key]
    if not isinstance(value, bool):
        raise ValueError(
            f"поле {key!r} должно быть true или false, получено {value!r}"
        )
    return value


def _as_list(raw: dict, key: str) -> list:
    """Обязательное поле как список. Форма — часть контракта, а не предмет
    интерпретации: `list(...)` на строке не бросает и молча разваливает её
    на символы, так что `heroCards: "JhTh"` дало бы отказ про число карт, а
    не про испорченную форму поля."""
    value = _require(raw, key)
    if not isinstance(value, list):
        raise ValueError(f"поле {key!r} должно быть списком, получено {value!r}")
    return list(value)


def _as_optional_list(raw: dict, key: str, default: list | None = None) -> list:
    """Необязательное поле как список, см. `_as_list`. Отсутствие ключа и
    `null` дают `default` (пустой список по умолчанию), а не отказ."""
    if not _present(raw, key):
        return list(default) if default is not None else []
    value = raw[key]
    if not isinstance(value, list):
        raise ValueError(f"поле {key!r} должно быть списком, получено {value!r}")
    return list(value)


def _as_optional_dict(raw: dict, key: str, default: dict | None = None) -> dict:
    """Необязательное поле как объект (`dict`). Отсутствие ключа и `null`
    дают `default` (пустой объект по умолчанию); значение другой формы
    (строка, список) отвергается по имени поля вместо того, чтобы `dict(...)`
    либо бросил английский `TypeError` на `None`, либо молча собрал блайнды
    из чужой структуры."""
    if not _present(raw, key):
        return dict(default) if default is not None else {}
    value = raw[key]
    if not isinstance(value, dict):
        raise ValueError(f"поле {key!r} должно быть объектом, получено {value!r}")
    return dict(value)


def context_from_dict(raw: dict) -> TournamentContext:
    payouts = [
        Payout(
            first=_as_int(entry, "from"),
            last=_as_int(entry, "to"),
            amount=_as_float(entry, "amount"),
        )
        for entry in _as_list(raw, "payouts")
    ]
    return TournamentContext(
        payouts=payouts,
        places_paid=_as_int(raw, "placesPaid"),
        entrants=_as_int(raw, "entrants"),
        players_left=_as_int(raw, "playersLeft"),
        late_reg_open=_as_bool(raw, "lateRegOpen"),
        seats_per_table=_as_int(raw, "seatsPerTable"),
        average_stack_bb=_as_optional_float(raw, "averageStackBb"),
    )


def node_from_dict(raw: dict) -> DecisionNode:
    seats = [
        Seat(
            seat_index=_as_int(entry, "seatIndex"),
            name="" if entry.get("name") is None else str(entry["name"]),
            stack_bb=_as_float(entry, "stackBb"),
            invested_bb=_as_optional_float(entry, "investedBb", 0.0),
            in_hand=_as_bool(entry, "inHand"),
            is_hero=_as_optional_bool(entry, "isHero"),
            vpip=_as_optional_float(entry, "vpip"),
            vpip_hands=_as_optional_int(entry, "vpipHands"),
            bounty_usd=_as_optional_float(entry, "bountyUsd"),
        )
        for entry in _as_list(raw, "seats")
    ]
    return DecisionNode(
        street=str(_require(raw, "street")),
        level=_as_optional_int(raw, "level", 0),
        blinds=_as_optional_dict(raw, "blinds"),
        hero_rank=_as_int(raw, "heroRank"),
        players_left=_as_int(raw, "playersLeft"),
        seats=seats,
        button_seat=_as_int(raw, "buttonSeat"),
        hero_cards=_as_list(raw, "heroCards"),
        board=_as_optional_list(raw, "board"),
        pot_bb=_as_float(raw, "potBb"),
        to_call_bb=_as_float(raw, "toCallBb"),
        raise_to_bb=_as_optional_float(raw, "raiseToBb"),
    )


def assign_positions(node: DecisionNode) -> dict[int, Position]:
    """Место за столом → позиция, отсчитанная от кнопки.

    Позиции не подписаны на скриншоте и не называются моделью: порядок
    берётся из `positions_for`, который уже знает неочевидные соглашения
    для 2 и 6 игроков, и разворачивается по кругу от кнопки.

    На хедз-апе (2 места) `positions_for` не включает `BTN` в список: кнопка
    и малый блайнд там — одно и то же место (`types.py`), так что опорной
    позицией берётся `SB` — это переименование того же места, а не новое
    соглашение о посадке.

    Предусловие: узел уже прошёл `validate_hand`. Функция не проверяет
    уникальность `seat_index` — `validate_hand` уже отвергает дубли с
    пользовательским текстом, и дублировать гард здесь означало бы два
    сообщения на одно и то же нарушение. Отсутствующую кнопку `validate_hand`
    тоже отвергает первой; здесь нарушение того же предусловия называется по
    имени функции, а не пересказывается вторым текстом и не всплывает как
    внутренний `StopIteration`.
    """
    seats = sorted(node.seats, key=lambda seat: seat.seat_index)
    n = len(seats)
    order = positions_for(n)  # len(order) == n по построению positions_for
    try:
        button_at = next(
            i for i, seat in enumerate(seats) if seat.seat_index == node.button_seat
        )
    except StopIteration:
        raise ValueError(
            "нарушено предусловие: assign_positions вызывать только после "
            "validate_hand, который гарантирует кнопку среди мест за столом"
        ) from None
    anchor = Position.BTN if Position.BTN in order else Position.SB
    anchor_at = order.index(anchor)
    positions: dict[int, Position] = {}
    for offset in range(n):
        seat_index = seats[(button_at + offset) % n].seat_index
        positions[seat_index] = order[(anchor_at + offset) % n]
    return positions


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
    # Пустота, интервалы, призы, пересечения, `places_paid` и глубина
    # лесенки — у `PayoutLadder`, с теми же текстами: одно нарушение — одно
    # сообщение, и одна реализация на пакет.
    #
    # Конструктор неделим, поэтому две проверки, которые раньше стояли
    # между его гардами, встают после него (решение Задачи 4, долг D17):
    # монотонность — отдельным проходом, когда интервалы уже проверены,
    # упорядочены и не пересекаются; `entrants < players_left` — последней.
    # Приоритет гардов класса между собой прежний; меняется он ровно в трёх
    # парах, и каждая запинена в `tests/test_handstate.py`.
    context.ladder()
    previous_amount: float | None = None
    for payout in sorted(context.payouts, key=lambda p: p.first):
        if previous_amount is not None and payout.amount > previous_amount:
            raise ValueError("выплата за более низкое место больше, чем за высокое")
        previous_amount = payout.amount
    if context.entrants < context.players_left:
        raise ValueError(
            f"осталось игроков ({context.players_left}) больше, чем входов "
            f"({context.entrants})"
        )
    # Отсутствие среднего стека проверяет не валидатор, а `analyze`:
    # обязателен он ровно тогда, когда поле больше стола, и это знает тот,
    # кто поле населяет. Здесь проверяется только переданное значение.
    if context.average_stack_bb is not None:
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
        # Бейдж соперника проверяется здесь, а не откладывается до
        # `range_for_vpip`: тот вызывается в самом конце `analyze`, уже
        # после ICM, и мусорный процент стоил бы пользователю полного
        # расчёта перед отказом. Правило одно на пакет — в `profiles`.
        check_vpip(seat.vpip, seat.vpip_hands)

    _validate_prices(node)

    check_positive(node.pot_bb, "банк")
    check_non_negative(node.to_call_bb, "размер колла")
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


def _validate_prices(node: DecisionNode) -> None:
    """Ценники голов PKO: признак турнира — их наличие (спека плана 3, §5.1).

    Сначала мусор в прочитанном, потом пропуски. Ценник обязателен у
    героя — без него неизвестно, что он теряет при вылете, — и у каждого,
    кто в раздаче: без ценника соперника порог колла посчитался бы без
    головы, и наружу ушло бы правдоподобное неверное число вместо отказа.
    Сфолдившему ценник не нужен: в этой раздаче он не выбывает и не
    выбивает.
    """
    priced = [seat for seat in node.seats if seat.bounty_usd is not None]
    for seat in priced:
        check_non_negative(seat.bounty_usd, f"ценник на месте {seat.seat_index}")
    if not priced:
        return
    if node.hero.bounty_usd is None:
        raise ValueError(
            "у соперников есть ценники голов, а ценник героя не прочитан: "
            "без него неизвестно, что герой теряет при вылете"
        )
    for seat in node.seats:
        if seat.in_hand and seat.bounty_usd is None:
            raise ValueError(
                f"ценник на месте {seat.seat_index} не прочитан, а у других мест "
                "он есть: без него неизвестно, чего стоит нокаут"
            )


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
