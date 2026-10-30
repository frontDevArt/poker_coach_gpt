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

from . import explain as facts
from . import preflop_advisor, pushfold
from .hand import Hand
from .handstate import DecisionNode, context_from_dict, node_from_dict, validate_hand

__all__ = ["ADVISORS", "STREET_CLOSERS", "Advisor", "advise", "read_hand", "why"]


class Advisor(Protocol):
    """Советник: `name`, `applies` — `None` или причина отказа, `advise` — ответ, `explain` —
    факты ответа (спека тренера §8).

    `hand` приходит разобранной и проверенной (спека тренера §7.1); `history` — прошлые ответы
    `advise` в этой раздаче, по порядку.
    """

    name: str

    def applies(self, hand: Hand) -> str | None: ...

    def advise(self, hand: Hand, history: list[dict]) -> dict: ...

    def explain(self, answer: dict) -> list[dict]: ...


ADVISORS: tuple[Advisor, ...] = (pushfold, preflop_advisor)

# Итог улицы считает её советник: улица → функция `Hand → итог` (спека тренера §7.1, §7.3).
# Советник постфлопа добавит строку сюда и в `ADVISORS` и прочтёт диапазоны префлопа из
# `Hand.street_summary("preflop")`.
STREET_CLOSERS: dict[str, Callable[[Hand], dict]] = {"preflop": preflop_advisor.close_street}


def advise(context_raw: dict, nodes_raw: list[dict], history_raw: list[dict]) -> dict:
    """Совет первого советника реестра, взявшего последний узел, или отказ с причинами.

    Форма входа проверяется до разбора: `context` — объект, `nodes` — список объектов, тексты
    — как у `analyze` (гарды формы конверта, а не `_checks`: вынести их в общую функцию
    нельзя без правки `analyze`). `history` — список объектов.
    """
    _check_envelope(context_raw, nodes_raw)
    if not isinstance(history_raw, list):
        raise ValueError(f"поле 'history' должно быть списком, получено {history_raw!r}")
    for number, raw in enumerate(history_raw):
        if not isinstance(raw, dict):
            raise ValueError(f"ответ {number} в истории должен быть объектом, получено {raw!r}")
    hand = _parse(context_raw, nodes_raw)

    refusals = []
    for advisor in ADVISORS:
        reason = advisor.applies(hand)
        if reason is None:
            return advisor.advise(hand, history_raw)
        refusals.append({"advisor": advisor.name, "reason": reason})
    return {"advisor": None, "notApplicable": refusals}


def read_hand(context_raw: dict, nodes_raw: list[dict]) -> Hand:
    """Раздача из конверта `advise` (без `history`): те же проверки формы и `validate_hand`."""
    _check_envelope(context_raw, nodes_raw)
    return _parse(context_raw, nodes_raw)


def why(answer: dict, node: DecisionNode) -> list[dict]:
    """Факты ответа `advise` на узле `node`: советника — его `explain` и факты узла; отказ —
    причины (спека тренера §8)."""
    if answer["advisor"] is None:
        return facts.refusal(answer)
    advisor = next(advisor for advisor in ADVISORS if advisor.name == answer["advisor"])
    return [*advisor.explain(answer), *facts.node_facts(node, answer)]


def _check_envelope(context_raw: dict, nodes_raw: list[dict]) -> None:
    if not isinstance(context_raw, dict):
        raise ValueError(f"поле 'context' должно быть объектом, получено {context_raw!r}")
    if not isinstance(nodes_raw, list):
        raise ValueError(f"поле 'nodes' должно быть списком, получено {nodes_raw!r}")
    for number, raw in enumerate(nodes_raw):
        if not isinstance(raw, dict):
            raise ValueError(f"узел решения {number} должен быть объектом, получено {raw!r}")


def _parse(context_raw: dict, nodes_raw: list[dict]) -> Hand:
    context = context_from_dict(context_raw)
    nodes = [node_from_dict(raw) for raw in nodes_raw]
    validate_hand(context, nodes)
    return Hand(context, nodes)
