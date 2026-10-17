"""Общие данные тестов: корректная раздача, снятая со скриншота."""

import pytest


def _context():
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
        "seatsPerTable": 6,
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
    блайнды и анте по 0.125 BB с шести мест: 0.5 + 1.0 + 0.75 = 2.25.
    """
    node = _node()
    seats = _seats_by_index(node)
    for seat in node["seats"]:
        seat["inHand"] = True
        seat["investedBb"] = 0.0
        seat["isHero"] = False
    seats[5]["investedBb"] = 0.5
    seats[6]["investedBb"] = 1.0
    seats[7].update(stackBb=10.0, isHero=True)
    node.update(potBb=2.25, toCallBb=1.0, raiseToBb=None)
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
