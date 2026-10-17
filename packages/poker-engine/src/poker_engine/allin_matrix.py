"""Эквити олл-ина на префлопе: 169 стартовых классов против 169.

Данные лежат в `data/allin_matrix.json` и порождаются `scripts/gen_allin_matrix.py`. Они
вычислены этим же движком (`phevaluator`), а не взяты из чужих таблиц: конвенция репозитория
запрещает числа из памяти.

Две таблицы, обе в порядке `hand_classes()`:

- `equity_matrix()[a, b]` — доля банка класса `a` против класса `b` при олл-ине на префлопе,
  ничья пополам. Monte-Carlo, стратифицированный по парам комбинаций: каждая совместимая пара
  получает одинаковое число ранаутов, случайны только пять карт доски. Стандартная ошибка
  клетки не больше `STANDARD_ERROR` (≈0.0035 при 20 000 ранаутов на клетку). Диагональ — ровно
  0.5 по симметрии.
- `weight_matrix()[a, b]` — точное число упорядоченных пар (комбинация `a`, комбинация `b`)
  без общих карт. Оно учитывает блокеры: `AKs` против `AA` даёт 4 × 3 пар, а не 4 × 6.

Блокеры между тремя и более игроками не учитываются: у каждой пары игроков своя таблица, и
карты третьего игрока веса пары не меняют. Это стандартное упрощение Nash-калькуляторов
(спека плана 4, §5.5); пометки в ответе оно не требует.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy

from .equity import FULL_DECK, RANKS
from .preflop import hand_classes
from .ranges import parse_range

_DATA = Path(__file__).parent / "data" / "allin_matrix.json"

CLASSES: tuple[str, ...] = tuple(hand_classes())
_INDEX = {name: index for index, name in enumerate(CLASSES)}
_COMBOS = tuple(
    tuple(frozenset((combo[:2], combo[2:])) for combo in parse_range(name)) for name in CLASSES
)


@lru_cache(maxsize=1)
def _load() -> dict:
    with _DATA.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if tuple(data["classes"]) != CLASSES:
        raise ValueError("порядок классов в allin_matrix.json не совпадает с hand_classes()")
    return data


def _read_only(array: numpy.ndarray) -> numpy.ndarray:
    array.flags.writeable = False
    return array


@lru_cache(maxsize=1)
def equity_matrix() -> numpy.ndarray:
    """`(169, 169)`: доля банка класса строки против класса столбца."""
    return _read_only(numpy.array(_load()["equity"], dtype=numpy.float64))


@lru_cache(maxsize=1)
def weight_matrix() -> numpy.ndarray:
    """`(169, 169)`: число совместимых пар комбинаций двух классов."""
    return _read_only(numpy.array(_load()["weight"], dtype=numpy.int64))


STANDARD_ERROR: float = _load()["standardError"]


def class_index(name: str) -> int:
    """Позиция класса в `CLASSES`."""
    try:
        return _INDEX[name]
    except KeyError:
        raise ValueError(f"неизвестный класс руки: {name!r}") from None


def combos_of(name: str) -> int:
    """Число комбинаций класса: 6 у пары, 4 у одномастной, 12 у разномастной."""
    return len(_COMBOS[class_index(name)])


def _check_cards(cards: list[str]) -> None:
    if len(cards) != 2 or cards[0] == cards[1]:
        raise ValueError(f"нужно ровно две разные карты: {cards!r}")
    for card in cards:
        if card not in FULL_DECK:
            raise ValueError(f"неизвестная карта: {card!r}")


def class_of(cards: list[str]) -> str:
    """Класс двух конкретных карт: `["Jh", "Th"]` → `"JTs"`. Порядок карт не важен."""
    _check_cards(cards)
    high, low = sorted(cards, key=lambda card: RANKS.index(card[0]), reverse=True)
    if high[0] == low[0]:
        return high[0] + low[0]
    return high[0] + low[0] + ("s" if high[1] == low[1] else "o")


def hand_weights(cards: list[str]) -> numpy.ndarray:
    """`(169,)`: сколько комбинаций каждого класса не пересекаются с картами `cards`."""
    _check_cards(cards)
    held = set(cards)
    return numpy.array(
        [sum(1 for combo in combos if not combo & held) for combos in _COMBOS],
        dtype=numpy.int64,
    )
