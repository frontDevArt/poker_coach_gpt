"""Реестр советников и точка входа `advise` (план 4, Задача 5; план 5, Задача 6 — `preflop`)."""

from __future__ import annotations

import re

import pytest

from conftest import _context, _node, pushfold_facing_allin_node, pushfold_first_in_node
from poker_engine import advice, preflop_advisor, pushfold
from poker_engine.advice import advise
from poker_engine.analyze import analyze
from poker_engine.handstate import context_from_dict, node_from_dict
from poker_engine.preflop_line import AMBIGUOUS

_NOT_ALL_IN = "банк открыт не олл-ином: это не спот push/fold"


class _Fake:
    """Второй советник: берёт узел, когда `takes`, и запоминает, что ему передали."""

    def __init__(self, name: str, takes: bool) -> None:
        self.name = name
        self.takes = takes
        self.seen: list = []

    def applies(self, context, nodes):
        return None if self.takes else f"{self.name} не берёт"

    def advise(self, context, nodes, history):
        self.seen.append((context, nodes, history))
        return {"advisor": self.name}


def _direct(raw: dict) -> dict:
    """Ответ `pushfold` в обход реестра — на тех же разобранных данных."""
    context = context_from_dict(_context())
    return pushfold.advise(context, [node_from_dict(raw)], [])


# --- реестр ----------------------------------------------------------------------------------


def test_pushfold_is_registered_first():
    # План 5, Задача 6: `preflop` встаёт после `pushfold` (спека плана 5, §4).
    assert advice.ADVISORS == (pushfold, preflop_advisor)


@pytest.mark.parametrize("make", [pushfold_first_in_node, pushfold_facing_allin_node])
def test_the_registry_gives_the_pushfold_advice(make):
    answer = advise(_context(), [make()], [])
    assert answer["advisor"] == "pushfold"
    assert answer == _direct(make())


def test_a_node_nobody_takes_is_a_refusal_with_reasons():
    # Узел `analyze`: `BTN` открыл рейзом 7.3 BB, не олл-ином; у героя `UTG` вложен 1 BB, а
    # кадра его прошлого решения нет — линия неоднозначна.
    assert advise(_context(), [_node()], []) == {
        "advisor": None,
        "notApplicable": [
            {"advisor": "pushfold", "reason": _NOT_ALL_IN},
            {"advisor": "preflop", "reason": AMBIGUOUS},
        ],
    }


def test_the_reason_comes_from_the_advisor_itself():
    context = context_from_dict(_context())
    assert pushfold.applies(context, [node_from_dict(_node())]) == _NOT_ALL_IN


# --- второй советник регистрацией ------------------------------------------------------------


def test_the_first_advisor_that_takes_the_node_answers(monkeypatch):
    first, second = _Fake("first", takes=True), _Fake("second", takes=True)
    monkeypatch.setattr(advice, "ADVISORS", (first, second))
    assert advise(_context(), [pushfold_first_in_node()], []) == {"advisor": "first"}
    assert len(first.seen) == 1 and second.seen == []


def test_a_refusing_advisor_passes_the_node_on(monkeypatch):
    shy = _Fake("shy", takes=False)
    monkeypatch.setattr(advice, "ADVISORS", (shy, pushfold))
    assert advise(_context(), [pushfold_first_in_node()], []) == _direct(
        pushfold_first_in_node()
    )


def test_a_second_advisor_takes_what_pushfold_refuses(monkeypatch):
    other = _Fake("preflop", takes=True)
    monkeypatch.setattr(advice, "ADVISORS", (pushfold, other))
    assert advise(_context(), [_node()], []) == {"advisor": "preflop"}
    # На своём споте `pushfold` отвечает первым, и его ответ тот же, что без соседа.
    assert advise(_context(), [pushfold_first_in_node()], []) == _direct(
        pushfold_first_in_node()
    )
    assert len(other.seen) == 1


def test_all_refusals_are_listed_in_registry_order(monkeypatch):
    monkeypatch.setattr(advice, "ADVISORS", (pushfold, _Fake("a", False), _Fake("b", False)))
    assert advise(_context(), [_node()], []) == {
        "advisor": None,
        "notApplicable": [
            {"advisor": "pushfold", "reason": _NOT_ALL_IN},
            {"advisor": "a", "reason": "a не берёт"},
            {"advisor": "b", "reason": "b не берёт"},
        ],
    }


def test_the_advisor_gets_parsed_input_and_the_history(monkeypatch):
    fake = _Fake("fake", takes=True)
    monkeypatch.setattr(advice, "ADVISORS", (fake,))
    history = [{"advisor": "pushfold", "action": "allin"}]
    advise(_context(), [pushfold_first_in_node()], history)
    (context, nodes, seen), = fake.seen
    assert context == context_from_dict(_context())
    assert nodes == [node_from_dict(pushfold_first_in_node())]
    assert seen == history


# --- форма входа -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("context", "nodes", "history", "message"),
    [
        (None, [], [], r"^поле 'context' должно быть объектом, получено None$"),
        ({}, {}, [], r"^поле 'nodes' должно быть списком, получено \{\}$"),
        ({}, [5], [], r"^узел решения 0 должен быть объектом, получено 5$"),
        ({}, [], None, r"^поле 'history' должно быть списком, получено None$"),
        ({}, [], [{}, "x"], r"^ответ 1 в истории должен быть объектом, получено 'x'$"),
    ],
)
def test_the_envelope_is_checked_before_parsing(context, nodes, history, message):
    with pytest.raises(ValueError, match=message):
        advise(context, nodes, history)


def test_the_hand_is_validated_as_in_analyze():
    raw = pushfold_first_in_node()
    raw["heroCards"] = ["Ah", "Ah"]
    with pytest.raises(ValueError) as refused:
        advise(_context(), [raw], [])
    with pytest.raises(ValueError, match=f"^{re.escape(str(refused.value))}$"):
        analyze(_context(), [raw])
