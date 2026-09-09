"""Эквити рук: полный перебор при дорисованной доске, иначе Monte-Carlo.

Сплиты делятся поровну между выигравшими, поэтому сумма эквити всегда 1.
Генератор случайных чисел засеивается явно — результат воспроизводим,
иначе тесты и разборы плавали бы от прогона к прогону.
"""

from __future__ import annotations

import random
from itertools import combinations

from pokerkit import Card, StandardHighHand

from ._checks import check_amount

RANKS = "23456789TJQKA"
SUITS = "cdhs"
FULL_DECK: list[str] = [r + s for r in RANKS for s in SUITS]


def hand_equity(
    hands: list[str],
    board: list[str],
    trials: int = 10_000,
    seed: int | None = None,
) -> list[float]:
    """Доля банка, которую в среднем забирает каждая рука.

    hands — строки вида "AsKd" по две карты.
    board — уже открытые карты, от нуля до пяти.
    trials — число прогонов Monte-Carlo. Игнорируется, если доска полная
        либо остаётся не больше одной карты (в этих случаях перебор точный).
    """
    parsed = [_parse_cards(h, expected=2, label="рука") for h in hands]
    parsed_board = _parse_board(board)
    _check_duplicates([c for hand in parsed for c in hand] + parsed_board)

    if len(parsed) < 2:
        raise ValueError("нужно минимум две руки")

    known = {c for hand in parsed for c in hand} | set(parsed_board)
    deck = [c for c in FULL_DECK if c not in known]
    need = 5 - len(parsed_board)

    wins = [0.0] * len(parsed)

    if need == 0:
        _score_runout(parsed, parsed_board, wins)
        total = 1
    elif need <= 1:
        # Полный перебор дешевле выборки, когда осталась одна карта.
        runouts = list(combinations(deck, need))
        for extra in runouts:
            _score_runout(parsed, parsed_board + list(extra), wins)
        total = len(runouts)
    else:
        check_amount(trials, "trials")
        rng = random.Random(seed)
        for _ in range(trials):
            extra = rng.sample(deck, need)
            _score_runout(parsed, parsed_board + extra, wins)
        total = trials

    return [w / total for w in wins]


def _score_runout(
    hands: list[list[str]], board: list[str], wins: list[float]
) -> None:
    scores = [_best_hand(hand + board) for hand in hands]
    best = max(scores)
    winners = [i for i, s in enumerate(scores) if s == best]
    share = 1.0 / len(winners)
    for i in winners:
        wins[i] += share


def _best_hand(cards: list[str]) -> StandardHighHand:
    """Лучшая пятикарточная комбинация из семи карт."""
    return max(
        StandardHighHand(Card.parse("".join(combo)))
        for combo in combinations(cards, 5)
    )


def _parse_cards(text: str, expected: int, label: str) -> list[str]:
    cards = [text[i : i + 2] for i in range(0, len(text), 2)]
    if len(cards) != expected:
        raise ValueError(f"{label} '{text}': ожидалось {expected} карт, вышло {len(cards)}")
    for c in cards:
        if c not in FULL_DECK:
            raise ValueError(f"неизвестная карта '{c}' в '{text}'")
    return cards


def _parse_board(board: list[str]) -> list[str]:
    if len(board) > 5:
        raise ValueError(f"на доске не может быть больше 5 карт, получено {len(board)}")
    for c in board:
        if c not in FULL_DECK:
            raise ValueError(f"неизвестная карта на доске: '{c}'")
    return list(board)


def _check_duplicates(cards: list[str]) -> None:
    seen: set[str] = set()
    for c in cards:
        if c in seen:
            raise ValueError(f"карта '{c}' встречается дважды")
        seen.add(c)
