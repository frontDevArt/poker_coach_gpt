"""Онтология стола: позиции, улицы, снимок стола с проверкой сохранения фишек."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum


class Street(IntEnum):
    """Улицы в порядке следования. IntEnum — чтобы работало сравнение."""

    PREFLOP = 0
    FLOP = 1
    TURN = 2
    RIVER = 3


class Position(StrEnum):
    UTG = "UTG"
    UTG1 = "UTG+1"
    MP = "MP"
    LJ = "LJ"
    HJ = "HJ"
    CO = "CO"
    BTN = "BTN"
    SB = "SB"
    BB = "BB"


# Порядок посадки от самой ранней позиции к самой поздней для полного 9-max
# стола. Общее правило для получения списка на `players` игроков — взять
# хвост этого списка длиной `players` (столы меньшего размера отрезают
# ранние позиции с начала). Это правило работает для 3, 4, 5, 7, 8 и 9
# игроков. Оно НЕ работает для 2 и 6 — см. `_POSITION_OVERRIDES` ниже.
_FULL_RING_ORDER: list[Position] = [
    Position.UTG,
    Position.UTG1,
    Position.MP,
    Position.LJ,
    Position.HJ,
    Position.CO,
    Position.BTN,
    Position.SB,
    Position.BB,
]

# Исключения из правила "взять хвост `_FULL_RING_ORDER`".
#
# Это не другой порядок посадки за столом — это другое соглашение об
# именовании самой ранней позиции для этих конкретных размеров стола:
#
#   - 6-max: механический хвост дал бы [LJ, HJ, CO, BTN, SB, BB], но по
#     общепринятому покерному соглашению самая ранняя позиция на 6-max
#     называется UTG, а не LJ (в отличие от 7/8/9-max, где перед HJ есть
#     несколько "средних" позиций и хвостовая позиция действительно LJ).
#   - Хедз-ап (2 игрока): стол вырождается в SB/BB, что не является
#     хвостом `_FULL_RING_ORDER` вообще (там BTN отсутствует).
#
# Не сворачивай это обратно в один общий срез — это тихо сломает
# именование позиций на 6-max.
_POSITION_OVERRIDES: dict[int, list[Position]] = {
    2: [Position.SB, Position.BB],
    6: [
        Position.UTG,
        Position.HJ,
        Position.CO,
        Position.BTN,
        Position.SB,
        Position.BB,
    ],
}


def positions_for(players: int) -> list[Position]:
    """Позиции за столом на `players` игроков.

    GG по умолчанию раздаёт 8-max в MTT. Хедз-ап вырождается в SB/BB.
    """
    if players < 2:
        raise ValueError(f"нужно минимум 2 игрока, получено {players}")
    if players > len(_FULL_RING_ORDER):
        raise ValueError(f"максимум {len(_FULL_RING_ORDER)} игроков, получено {players}")
    if players in _POSITION_OVERRIDES:
        return _POSITION_OVERRIDES[players]
    return _FULL_RING_ORDER[len(_FULL_RING_ORDER) - players:]


class ChipConservationError(ValueError):
    """Сумма стеков и банка не сходится с общим числом фишек в раздаче."""


@dataclass(frozen=True)
class TableSnapshot:
    """Снимок стола в один момент времени.

    `total_chips` — сколько фишек было в раздаче на её старте. Инвариант:
    сумма текущих стеков плюс банк обязана равняться этому числу. Нарушение
    означает ошибку распознавания скриншота или бага в логике.
    """

    stacks: list[int]
    pot: int
    total_chips: int
    tolerance: int = field(default=0)

    def chip_sum(self) -> int:
        return sum(self.stacks) + self.pot

    def is_consistent(self) -> bool:
        return abs(self.chip_sum() - self.total_chips) <= self.tolerance

    def validate(self) -> None:
        if not self.is_consistent():
            raise ChipConservationError(
                f"стеки+банк = {self.chip_sum()}, ожидалось {self.total_chips}"
            )

    def effective_stack(self, hero: int, villain: int) -> int:
        return min(self.stacks[hero], self.stacks[villain])
