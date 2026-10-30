"""Советники и точка входа `advise` (спека плана 4, §7).

Конвейер не знает об улицах: вход разбирается и проверяется так же, как в `analyze`, затем
реестр `ADVISORS` опрашивается по порядку, и отвечает первый советник, взявший узел. Если
не взял никто, ответ — отказ со всеми причинами: это не ошибка, `ValueError` остаётся для
битого входа.

Новый советник (весь префлоп — этап 4, постфлоп — этап 6) встаёт строкой в `ADVISORS`: ни
этот модуль, ни `pushfold` при этом не меняются.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from . import preflop_advisor, pushfold
from .hand import Hand
from .handstate import context_from_dict, node_from_dict, validate_hand

__all__ = ["ADVISORS", "STREET_CLOSERS", "Advisor", "advise"]


class Advisor(Protocol):
    """Советник: `name`, `applies` — `None` или причина отказа, `advise` — ответ.

    `hand` приходит разобранной и проверенной (спека тренера §7.1); `history` — прошлые ответы
    `advise` в этой раздаче, по порядку.
    """

    name: str

    def applies(self, hand: Hand) -> str | None: ...

    def advise(self, hand: Hand, history: list[dict]) -> dict: ...


ADVISORS: tuple[Advisor, ...] = (pushfold, preflop_advisor)

# Итог улицы считает её советник: улица → функция `Hand → итог` (спека тренера §7.1, §7.3).
STREET_CLOSERS: dict[str, Callable[[Hand], dict]] = {}


def advise(context_raw: dict, nodes_raw: list[dict], history_raw: list[dict]) -> dict:
    """Совет первого советника реестра, взявшего последний узел, или отказ с причинами.

    Форма входа проверяется до разбора: `context` — объект, `nodes` — список объектов, тексты
    — как у `analyze` (гарды формы конверта, а не `_checks`: вынести их в общую функцию
    нельзя без правки `analyze`). `history` — список объектов.
    """
    if not isinstance(context_raw, dict):
        raise ValueError(f"поле 'context' должно быть объектом, получено {context_raw!r}")
    if not isinstance(nodes_raw, list):
        raise ValueError(f"поле 'nodes' должно быть списком, получено {nodes_raw!r}")
    for number, raw in enumerate(nodes_raw):
        if not isinstance(raw, dict):
            raise ValueError(f"узел решения {number} должен быть объектом, получено {raw!r}")
    if not isinstance(history_raw, list):
        raise ValueError(f"поле 'history' должно быть списком, получено {history_raw!r}")
    for number, raw in enumerate(history_raw):
        if not isinstance(raw, dict):
            raise ValueError(f"ответ {number} в истории должен быть объектом, получено {raw!r}")

    context = context_from_dict(context_raw)
    nodes = [node_from_dict(raw) for raw in nodes_raw]
    validate_hand(context, nodes)
    hand = Hand(context, nodes)

    refusals = []
    for advisor in ADVISORS:
        reason = advisor.applies(hand)
        if reason is None:
            return advisor.advise(hand, history_raw)
        refusals.append({"advisor": advisor.name, "reason": reason})
    return {"advisor": None, "notApplicable": refusals}
