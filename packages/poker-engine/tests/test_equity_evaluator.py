"""Быстрый оценщик обязан ранжировать руки так же, как эталонный pokerkit."""

import random

from phevaluator import evaluate_cards
from pokerkit import Card, StandardHighHand

from poker_engine.equity import FULL_DECK


def _sign(value):
    return (value > 0) - (value < 0)


def _pokerkit(cards):
    return StandardHighHand.from_game(
        Card.parse("".join(cards[:2])), Card.parse("".join(cards[2:]))
    )


def _phevaluator(cards):
    # Шкала обратная: меньше — сильнее. Минус приводит её к порядку pokerkit.
    return -evaluate_cards(*cards)


def test_the_fast_evaluator_orders_hands_exactly_like_pokerkit():
    rng = random.Random(20260912)
    disagreements = []
    for _ in range(3000):
        left = rng.sample(FULL_DECK, 7)
        right = rng.sample(FULL_DECK, 7)
        fast = _sign(_phevaluator(left) - _phevaluator(right))
        slow_left, slow_right = _pokerkit(left), _pokerkit(right)
        slow = (slow_left > slow_right) - (slow_left < slow_right)
        if fast != slow:
            disagreements.append((left, right))
    assert disagreements == []


def test_the_fast_evaluator_sees_ties_where_pokerkit_does():
    # Случайные пары из независимых колод почти никогда не делят банк, и
    # тест выше проверял бы ничьи вслепую. Здесь соперники делят одну доску:
    # на общей доске ничьи (игра доской, одинаковые кикеры) частые, и
    # `_score_runout` делит банк именно по равенству оценок.
    rng = random.Random(20260925)
    ties = 0
    disagreements = []
    for _ in range(3000):
        cards = rng.sample(FULL_DECK, 9)
        board = cards[4:]
        left, right = cards[:2] + board, cards[2:4] + board
        fast = _sign(_phevaluator(left) - _phevaluator(right))
        slow_left, slow_right = _pokerkit(left), _pokerkit(right)
        slow = (slow_left > slow_right) - (slow_left < slow_right)
        ties += slow == 0
        if fast != slow:
            disagreements.append((left, right))
    assert disagreements == []
    assert ties > 0
