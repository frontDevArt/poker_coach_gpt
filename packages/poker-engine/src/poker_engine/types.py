"""Онтология стола: позиции и улицы."""

from __future__ import annotations

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
# хвост этого списка длиной `players` (отрезаны только самые ранние позиции,
# остальной порядок не меняется). Это правило работает для 3, 4, 5, 7, 8 и 9
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
#
# Значения — кортежи, а не списки: `positions_for` всегда возвращает
# свежесозданный список (`list(...)`), так что этот модульный константный
# словарь остаётся действительно неизменяемым и не может быть случайно
# испорчен вызывающим кодом, мутирующим ранее полученный результат.
_POSITION_OVERRIDES: dict[int, tuple[Position, ...]] = {
    2: (Position.SB, Position.BB),
    6: (
        Position.UTG,
        Position.HJ,
        Position.CO,
        Position.BTN,
        Position.SB,
        Position.BB,
    ),
}


def positions_for(players: int) -> list[Position]:
    """Позиции за столом на `players` игроков.

    GG по умолчанию раздаёт 8-max в MTT. Хедз-ап вырождается в SB/BB.

    Всегда возвращает свежий список — безопасно мутировать результат,
    не затрагивая внутренние структуры модуля или другие вызовы.
    """
    if players < 2:
        raise ValueError(f"нужно минимум 2 игрока, получено {players}")
    if players > len(_FULL_RING_ORDER):
        raise ValueError(f"максимум {len(_FULL_RING_ORDER)} игроков, получено {players}")
    if players in _POSITION_OVERRIDES:
        return list(_POSITION_OVERRIDES[players])
    return _FULL_RING_ORDER[len(_FULL_RING_ORDER) - players:]
