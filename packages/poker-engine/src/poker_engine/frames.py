"""Кадр раздачи — то, что модель-тренер переписала с экрана (спека тренера §6.1).

Форма узла та же, что у `analyze` и `advise`, плюс две вещи, которые снимают арифметику с
модели: единица кадра (`unit`: `bb` по умолчанию или `chips` — фишки делятся на `blinds.bb` без
округления) и банк «середина» (`potCenter*` — движок прибавляет вложенное улицы). Кадр хранится
как пришёл; здесь из него строится новый словарь узла, вход не меняется.
"""

from __future__ import annotations

import math

from ._checks import check_positive
from .handstate import (
    _as_bool,
    _as_float,
    _as_int,
    _as_optional_dict,
    _as_optional_float,
    _present,
)

UNITS = ("bb", "chips")
_SUFFIX = {"bb": "Bb", "chips": "Chips"}
# Поля кадра в единицах стека: на узле и на каждом месте.
_NODE_FIELDS = ("pot", "potCenter", "toCall", "raiseTo")
_SEAT_FIELDS = ("stack", "invested")


def node_payload(raw: dict) -> dict:
    """Кадр → узел в BB: единицы переведены, банк «середина» сложен с вложенным улицы."""
    if not isinstance(raw, dict):
        raise ValueError(f"кадр должен быть объектом, получено {raw!r}")
    unit = raw["unit"] if _present(raw, "unit") else "bb"
    if unit not in UNITS:
        raise ValueError(f"единица кадра должна быть bb или chips, получено {unit!r}")
    # Места, которые не объекты, и места без списка — забота `node_from_dict`: здесь они идут
    # дальше как есть, и отказ придёт с его текстом.
    raw_seats = raw.get("seats")
    seats = [s for s in raw_seats if isinstance(s, dict)] if isinstance(raw_seats, list) else []
    other = _SUFFIX["chips" if unit == "bb" else "bb"]
    for where, fields in ((raw, _NODE_FIELDS), *((seat, _SEAT_FIELDS) for seat in seats)):
        for field in fields:
            if f"{field}{other}" in where:
                raise ValueError(f"поле {field}{other} не для кадра в {unit}")

    node = {key: value for key, value in raw.items() if key != "unit"}
    if unit == "chips":
        bb = _big_blind(raw, "кадр в фишках без большого блайнда: нужно blinds.bb > 0")
        _to_big_blinds(node, _NODE_FIELDS, bb)
        if isinstance(raw_seats, list):
            node["seats"] = [
                _to_big_blinds(dict(seat), _SEAT_FIELDS, bb) if isinstance(seat, dict) else seat
                for seat in raw_seats
            ]

    if "potCenterBb" in node:
        if "potBb" in node:
            raise ValueError("в кадре два банка: нужен полный или середина, не оба")
        if _present(node, "potCenterBb"):
            invested = sum(
                _as_float(seat, "investedBb") if _present(seat, "investedBb") else 0.0
                for seat in node.get("seats") or []
                if isinstance(seat, dict)
            )
            node["potBb"] = _as_float(node, "potCenterBb") + invested
        del node["potCenterBb"]
    return node


def context_payload(raw: dict, last_frame: dict | None, first_frame: dict | None = None) -> dict:
    """Контекст → форма `analyze`: средний стек в BB из того, что есть в контексте.

    Порядок (спека лобби §6):

    1. Есть `averageStackBb` или `averageStackChips` — `averageStackChips` делится на
       `blinds.bb` последнего кадра, остальное как пришло, источник не ставится. Средний стек —
       с экрана лобби, а не со стола: его единица от единицы кадра не зависит, и `blinds` нужен
       у кадра в любых единицах. Без кадра (`coach start`) проверяется только само число.
    2. Иначе есть `startingStackChips` и кадр: при закрытой поздней регистрации средний стек —
       `startingStackChips × entrants / playersLeft / bb` последнего кадра (источник `lobby`), при
       открытой — средний `stackBb + investedBb` по местам первого кадра (источник `table`).
       Без кадра, а при открытой регистрации — без первого кадра, вывода нет: средний стек
       остаётся неизвестным до шага.
    3. `startingStackChips`, если он есть, проверяется всегда, нужен он для вывода или нет.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"поле 'context' должно быть объектом, получено {raw!r}")
    starting = None
    if _present(raw, "startingStackChips"):
        starting = _as_float(raw, "startingStackChips")
        check_positive(starting, "стартовый стек")
    if "averageStackChips" not in raw:
        context = dict(raw)
        if starting is not None and not _present(raw, "averageStackBb"):
            _derive_average_stack(context, starting, last_frame, first_frame)
        return context
    if "averageStackBb" in raw:
        raise ValueError("в контексте два средних стека: нужен в BB или в фишках, не оба")
    context = {key: value for key, value in raw.items() if key != "averageStackChips"}
    if not _present(raw, "averageStackChips"):
        if starting is not None:
            _derive_average_stack(context, starting, last_frame, first_frame)
        return context
    chips = _as_float(raw, "averageStackChips")
    check_positive(chips, "средний стек")
    if last_frame is not None:
        bb = _big_blind(
            last_frame, "средний стек в фишках без большого блайнда: нужно blinds.bb > 0 в кадре"
        )
        context["averageStackBb"] = chips / bb
    return context


def _derive_average_stack(
    context: dict, starting: float, last_frame: dict | None, first_frame: dict | None
) -> None:
    """Средний стек в BB из стартового стека; результат и источник ложатся в `context`."""
    if _as_bool(context, "lateRegOpen"):
        if first_frame is None:
            return
        seats = node_payload(first_frame).get("seats")
        if not isinstance(seats, list) or not seats:
            raise ValueError("средний стек по столу: в первом кадре нет мест")
        total = sum(
            _as_float(seat, "stackBb") + _as_optional_float(seat, "investedBb", 0.0)
            for seat in seats
        )
        context["averageStackBb"] = total / len(seats)
        context["averageStackSource"] = "table"
        return
    if last_frame is None:
        return
    bb = _big_blind(
        last_frame,
        "средний стек из стартового стека без большого блайнда: нужно blinds.bb > 0 в кадре",
    )
    left = _as_int(last_frame, "playersLeft")
    check_positive(left, "остаток игроков")
    context["averageStackBb"] = starting * _as_int(context, "entrants") / left / bb
    context["averageStackSource"] = "lobby"


def _big_blind(frame: dict, text: str) -> float:
    blinds = _as_optional_dict(frame, "blinds") if isinstance(frame, dict) else {}
    try:
        bb = float(blinds["bb"])
    except (KeyError, TypeError, ValueError):
        raise ValueError(text) from None
    # Сравнение в одну сторону: нечисло проваливает его, а не проходит.
    if not 0 < bb < math.inf:
        raise ValueError(text)
    return bb


def _to_big_blinds(target: dict, fields: tuple[str, ...], bb: float) -> dict:
    """Поля `*Chips` в `target` → `*Bb`, поделённые на `bb`; `null` остаётся `null`."""
    for field in fields:
        key = f"{field}Chips"
        if key in target:
            value = _as_float(target, key) / bb if _present(target, key) else None
            del target[key]
            target[f"{field}Bb"] = value
    return target
