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
        "seatsPerTable": 8,
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
            seat(0, 72.2, in_hand=False),
            seat(1, 66.1, in_hand=False),
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


@pytest.fixture
def analyze_context():
    return _context()


@pytest.fixture
def analyze_node():
    return _node()


@pytest.fixture(scope="module")
def analyze_base_result():
    """Разбор плановой фикстуры без единой правки, посчитанный один раз на модуль.

    Один вызов `analyze` на этих данных считает ICM по 15 узлам семь раз
    (сам расчёт плюс по три ветви в `risk_premium` и `bubble_factor`) и
    стоит десятки секунд. Тесты, которым нужен именно базовый ответ,
    берут его отсюда и только читают: словарь общий на модуль, и правка
    его в одном тесте испортила бы остальные. Тестам, меняющим вход,
    остаётся фикстура `run_analyze`, считающая заново.
    """
    from poker_engine.analyze import analyze

    return analyze(_context(), [_node()], trials=2_000, seed=11)
