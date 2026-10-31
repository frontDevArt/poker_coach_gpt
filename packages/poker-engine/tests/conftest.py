"""Общие данные тестов: корректная раздача, снятая со скриншота."""

import io
import pathlib

import pytest

# скриншоты лобби пользователя (в репозитории их нет): локальные тесты OCR без них пропускаются
LOBBY_SHOTS = pathlib.Path(r"C:\Users\Admin\Documents\Screenshots\lobby\fifty-stack-2026-10-30")


def console_stdin(text):
    """stdin, как его открывает консоль Windows: из пайпа приходят байты UTF-8, а поток — в cp1252.

    `sys.stdin.read()` на таком потоке отдаёт кириллицу мусором; CLI читает `sys.stdin.buffer`.
    """
    return io.TextIOWrapper(
        io.BytesIO(text.encode("utf-8")), encoding="cp1252", errors="surrogateescape"
    )


def _context(seats_per_table=6):
    """Контекст фикстур: стол 6-max; 8/9-max — `seats_per_table` по числу мест (план 6, Задача 6)."""
    return {
        "payouts": [
            {"from": 1, "to": 1, "amount": 1090.51},
            {"from": 2, "to": 2, "amount": 840.37},
            {"from": 3, "to": 3, "amount": 648.01},
            {"from": 4, "to": 6, "amount": 400.0},
        ],
        "placesPaid": 165,
        "entrants": 1107,
        "playersLeft": 782,
        "lateRegOpen": True,
        "seatsPerTable": seats_per_table,
        "averageStackBb": 50.5,
    }


def _node():
    def seat(index, stack, *, hero=False, in_hand=True, invested=0.0):
        return {
            "seatIndex": index,
            "name": f"p{index}",
            "stackBb": stack,
            "investedBb": invested,
            "inHand": in_hand,
            "isHero": hero,
            "vpip": 25.0,
            "vpipHands": 60,
        }

    return {
        "street": "preflop",
        "level": 13,
        "blinds": {"sb": 700, "bb": 1400, "ante": 175},
        "heroRank": 90,
        "playersLeft": 496,
        "seats": [
            seat(2, 94.4, in_hand=False),
            seat(3, 35.3, in_hand=False),
            seat(4, 23.2, invested=7.3),
            seat(5, 39.2, in_hand=False),
            seat(6, 35.7, in_hand=False),
            seat(7, 63.3, hero=True, invested=1.0),
        ],
        "buttonSeat": 4,
        "heroCards": ["Jh", "Th"],
        "board": [],
        "potBb": 9.4,
        "toCallBb": 7.3,
        "raiseToBb": 14.5,
    }


def _seats_by_index(node):
    return {seat["seatIndex"]: seat for seat in node["seats"]}


def pushfold_first_in_node():
    """Спот `first_in` плана 4: стол фикстуры `_node()`, все в раздаче, герой — UTG.

    Кнопка — место 4, значит `SB` — 5, `BB` — 6, `UTG` — 7, `HJ` — 2, `CO` — 3. Банк —
    блайнды и анте по 0.125 BB с шести мест: 0.5 + 1.0 + 0.75 = 2.25. У героя 8 BB —
    порог `PUSHFOLD_MAX_BB` (план 6, Задача 5): спот берёт советник `pushfold`.
    """
    node = _node()
    seats = _seats_by_index(node)
    for seat in node["seats"]:
        seat["inHand"] = True
        seat["investedBb"] = 0.0
        seat["isHero"] = False
    seats[5]["investedBb"] = 0.5
    seats[6]["investedBb"] = 1.0
    seats[7].update(stackBb=8.0, isHero=True)
    node.update(potBb=2.25, toCallBb=1.0, raiseToBb=None)
    return node


def _with_extra_seats(node, stacks):
    """Узел, дополненный местами 8, 9, … после `UTG` (место 7): герой остаётся `UTG`.

    Новые места в раздаче, ничего не вложили, ставят анте наравне со всеми: банк растёт на
    0.125 BB за место. Контекст и `playersLeft` прежние.
    """
    for offset, stack in enumerate(stacks):
        node["seats"].append(
            {
                "seatIndex": 8 + offset,
                "name": f"p{8 + offset}",
                "stackBb": stack,
                "investedBb": 0.0,
                "inHand": True,
                "isHero": False,
                "vpip": 25.0,
                "vpipHands": 60,
            }
        )
    node["potBb"] += 0.125 * len(stacks)
    return node


def pushfold_first_in_node_8max():
    """Спот `first_in` плана 4 на 8 местах: герой `UTG`, за ним семь отвечающих."""
    return _with_extra_seats(pushfold_first_in_node(), [28.0, 41.6])


def pushfold_first_in_node_9max():
    """Спот `first_in` плана 4 на 9 местах: герой `UTG`, за ним восемь отвечающих."""
    return _with_extra_seats(pushfold_first_in_node(), [28.0, 41.6, 18.4])


def preflop_open_utg_node(make, depth=25.0):
    """Спот `open` героя `UTG` на столе `make`: у всех `depth` BB до раздачи.

    Стол и вложенное — как у `make` (узел `first_in` плана 4); глубже `PUSHFOLD_MAX_BB` узел
    берёт советник `preflop`. Это деревья замера бюджета Задачи 5 плана 5.
    """
    node = make()
    for seat in node["seats"]:
        seat["stackBb"] = depth - seat["investedBb"]
    return node


def pushfold_facing_allin_node():
    """Спот `facing_allin`: `HJ` (место 2) пошёл олл-ин на 9 BB, `CO` сфолдил, герой — `BTN`.

    `UTG` (место 7) сфолдил первым. Банк — 9 + 0.5 + 1.0 + анте 0.75 = 11.25.
    """
    node = pushfold_first_in_node()
    seats = _seats_by_index(node)
    seats[7].update(stackBb=63.3, isHero=False, inHand=False)
    seats[2].update(stackBb=0.0, investedBb=9.0)
    seats[3]["inHand"] = False
    seats[4].update(stackBb=30.0, isHero=True)
    node.update(potBb=11.25, toCallBb=9.0)
    return node


def preflop_frame(hero, invested=None, folded=(), starting=None):
    """Кадр префлопа на столе `pushfold_first_in_node`: 6-max, у каждого 40 BB до раздачи.

    Кнопка — место 4, ход — `UTG` 7, `HJ` 2, `CO` 3, `BTN` 4, `SB` 5, `BB` 6. `invested` —
    вложенное на улице по местам поверх блайндов 0.5 и 1.0, `folded` — сфолдившие, `starting` —
    стеки до раздачи, отличные от 40. Стек — стартовый минус вложенное, банк — вложенное плюс
    анте 0.75: фишки между кадрами одной раздачи сходятся сами собой.
    """
    put = {5: 0.5, 6: 1.0, **(invested or {})}
    totals = {**{seat: 40.0 for seat in range(2, 8)}, **(starting or {})}
    node = pushfold_first_in_node()
    for seat in node["seats"]:
        index = seat["seatIndex"]
        seat.update(
            investedBb=put.get(index, 0.0),
            stackBb=totals[index] - put.get(index, 0.0),
            inHand=index not in folded,
            isHero=index == hero,
        )
    node.update(
        potBb=sum(put.values()) + 0.75,
        toCallBb=max(put.values()) - put.get(hero, 0.0),
        raiseToBb=None,
    )
    return node


def flop_frame(hero, put, folded, starting=None, bets=None):
    """Кадр флопа на столе `preflop_frame`: `put` — вложенное префлопа по местам поверх блайндов
    0.5 и 1.0, `folded` — вне раздачи на флопе, `bets` — ставки флопа до героя."""
    put = {5: 0.5, 6: 1.0, **put}
    bets = bets or {}
    totals = {**{seat: 40.0 for seat in range(2, 8)}, **(starting or {})}
    frame = preflop_frame(hero, folded=folded, starting=starting)
    for seat in frame["seats"]:
        index = seat["seatIndex"]
        seat.update(
            investedBb=bets.get(index, 0.0),
            stackBb=totals[index] - put.get(index, 0.0) - bets.get(index, 0.0),
        )
    frame.update(
        street="flop",
        board=["8c", "2s", "9d"],
        potBb=sum(put.values()) + 0.75 + sum(bets.values()),
        toCallBb=max(bets.values(), default=0.0) - bets.get(hero, 0.0),
    )
    return frame


def preflop_open():
    """`open`: `UTG` и `HJ` сфолдили, герой — `CO`."""
    return [preflop_frame(3, folded={7, 2})]


def preflop_vs_open():
    """`vs_open`: `UTG` открыл до 2.0 (мин-рейз), `HJ` сфолдил, герой — `CO`."""
    return [preflop_frame(3, {7: 2.0}, folded={2})]


def preflop_vs_limp():
    """`vs_limp`: `UTG` залимпил, `HJ` и `CO` сфолдили, герой — `BTN`."""
    return [preflop_frame(4, {7: 1.0}, folded={2, 3})]


def preflop_vs_3bet():
    """`vs_3bet` в два кадра: герой `CO` открыл до 2.0, `BTN` — 3-бет до 7.0, блайнды фолд."""
    return [
        preflop_frame(3, folded={7, 2}),
        preflop_frame(3, {3: 2.0, 4: 7.0}, folded={7, 2, 5, 6}),
    ]


def preflop_vs_4bet():
    """`vs_4bet` в два кадра: `UTG` открыл до 2.0, герой `CO` — 3-бет до 6.0, `UTG` — 4-бет 15.0."""
    return [
        preflop_frame(3, {7: 2.0}, folded={2}),
        preflop_frame(3, {7: 15.0, 3: 6.0}, folded={2, 4, 5, 6}),
    ]


def preflop_vs_allin_after_raise():
    """`vs_allin_after_raise`: герой `CO` открыл до 2.0, `BTN` пошёл олл-ин на 40 BB."""
    return [
        preflop_frame(3, folded={7, 2}),
        preflop_frame(3, {3: 2.0, 4: 40.0}, folded={7, 2, 5, 6}),
    ]


@pytest.fixture
def analyze_context():
    return _context()


@pytest.fixture
def analyze_node():
    return _node()


@pytest.fixture(scope="module")
def analyze_base_result():
    """Разбор плановой фикстуры без единой правки, посчитанный один раз на модуль.

    Стол 6-max и поле из 490 игроков. Тесты, которым нужен именно базовый
    ответ, берут его отсюда и только читают: словарь общий на модуль, и правка
    его в одном тесте испортила бы остальные. Тестам, меняющим вход,
    остаётся фикстура `run_analyze`, считающая заново.
    """
    from poker_engine.analyze import analyze

    return analyze(_context(), [_node()], trials=2_000, seed=11)


@pytest.fixture
def pushfold_first_in():
    return pushfold_first_in_node()


@pytest.fixture
def pushfold_facing_allin():
    return pushfold_facing_allin_node()


def heads_up_spot(depth):
    """HU по фишкам без анте: `SB` 0.5 и `BB` 1, у обоих `depth` BB до блайндов.

    `Spot` строится напрямую, без `read_spot`: солвер о пороге push/fold не знает, а
    эталонный чарт идёт до 20 BB.
    """
    from poker_engine.handstate import Seat
    from poker_engine.pushfold_game import Spot

    def seat(index, invested):
        return Seat(
            seat_index=index,
            name=f"p{index}",
            stack_bb=depth - invested,
            invested_bb=invested,
            in_hand=True,
            is_hero=index == 1,
            vpip=None,
            vpip_hands=None,
            bounty_usd=None,
        )

    return Spot(
        kind="first_in",
        players=[seat(1, 0.5), seat(2, 1.0)],
        hero_at=0,
        bb_at=1,
        totals=[float(depth), float(depth)],
        dead_bb=0.0,
        bystanders=[],
    )
