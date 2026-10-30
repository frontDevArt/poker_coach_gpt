"""Факты объяснения `why` и их печать (план 6, Задача 7).

Спека тренера §8, инвариант 8 §12: каждое `display` — печать своего `value` по правилу вида;
набор ключей на каждом споте `preflop` и `pushfold`; отказ — факты-причины. `ranges.hero.reach`
ответа `preflop` (§7.2) — пара тестов.
"""

import re

import pytest

from conftest import (
    _context,
    _node,
    preflop_frame,
    preflop_open,
    preflop_vs_3bet,
    preflop_vs_4bet,
    preflop_vs_allin_after_raise,
    preflop_vs_limp,
    preflop_vs_open,
    pushfold_facing_allin_node,
    pushfold_first_in_node,
)
from poker_engine import allin_matrix, explain, preflop_advisor, pushfold
from poker_engine.advice import advise, why
from poker_engine.explain import display, fact
from poker_engine.handstate import node_from_dict

# Вид печати по ключу факта: точный ключ или его хвост после последней точки.
_KIND = {
    "action": "text",
    "sizeBb": "bb",
    "baseAction": "text",
    "vsBaseUsd": "usd",
    "vsBaseBb": "ev_bb",
    "secondAction": "text",
    "vsSecondUsd": "usd",
    "vsSecondBb": "ev_bb",
    "chipBestAction": "text",
    "bountyUsd": "usd",
    "heroReachPct": "pct",
    "effectiveStackBb": "bb",
    "line": "text",
    "marginUsd": "usd",
    "marginBb": "ev_bb",
    "heroIcmPct": "pct",
    "heroChipPct": "pct",
    "heroHandFreqIcm": "pct",
    "heroHandFreqChip": "pct",
    "potBb": "bb",
    "toCallBb": "bb",
    "requiredEquity": "pct",
    "role": "text",
    "stackBb": "bb",
    "reachPct": "pct",
    "icmPct": "pct",
    "chipPct": "pct",
    "reason": "text",
}
_PREFIX_KIND = {"heroRange": "pct", "heroHandFreq": "pct", "flag": "text", "reason": "text"}


def _kind(key):
    head, _, tail = key.rpartition(".")
    if key in _KIND:
        return _KIND[key]
    if head.split(".")[0] in _PREFIX_KIND and head.count(".") == 0:
        return _PREFIX_KIND[head]
    return _KIND[tail]


def _assert_printed(facts):
    for item in facts:
        assert set(item) == {"key", "value", "display"}
        assert item["display"] == display(item["value"], _kind(item["key"])), item


def _bounties(frames):
    for raw in frames:
        for seat in raw["seats"]:
            seat["bountyUsd"] = 10.0 + seat["seatIndex"]
    return frames


# --- печать ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "kind", "printed"),
    [
        (2.0, "bb", "2.0 BB"),
        (30.333 / 1.4, "bb", "21.7 BB"),
        (0.354, "ev_bb", "+0.35 BB"),
        (-1.256, "ev_bb", "-1.26 BB"),
        (-0.004, "ev_bb", "+0.00 BB"),
        (0.14, "usd", "+$0.14"),
        (-1.5, "usd", "-$1.50"),
        (-0.001, "usd", "+$0.00"),
        (0.15, "pct", "15.0%"),
        (1.0, "pct", "100.0%"),
        (0.44444, "pct", "44.4%"),
        (-0.0001, "pct", "0.0%"),
        (3, "int", "3"),
        ("рейз до 2.0 BB", "text", "рейз до 2.0 BB"),
    ],
)
def test_the_print_rules(value, kind, printed):
    assert fact("x", value, kind) == {"key": "x", "value": value, "display": printed}


def test_an_unknown_kind_is_refused():
    with pytest.raises(ValueError, match=re.escape("вид факта должен быть одним из")):
        display(1.0, "chips")


def test_an_action_with_its_size():
    assert explain.action_text("raise", 2.0) == "рейз до 2.0 BB"
    assert explain.action_text("allin", 8.0) == "олл-ин 8.0 BB"
    assert explain.action_text("fold", None) == "фолд"


# --- preflop ---------------------------------------------------------------------------------


SPOTS = {
    "open": preflop_open,
    "vs_open": preflop_vs_open,
    "vs_limp": preflop_vs_limp,
    "vs_3bet": preflop_vs_3bet,
    "vs_4bet": preflop_vs_4bet,
    "vs_allin_after_raise": preflop_vs_allin_after_raise,
    "vs_open_pko": lambda: _bounties(preflop_vs_open()),
}


def _expected_preflop_keys(answer):
    """Ключи фактов `preflop` по правилам §8 — независимо от `explain`."""
    actions = answer["actions"]
    best = [option["action"] for option in actions].index(answer["action"])
    keys = {"action", "secondAction", "vsSecondUsd", "vsSecondBb", "heroReachPct", "effectiveStackBb"}
    if "sizeBb" in answer:
        keys.add("sizeBb")
    if best != 0:
        keys |= {"baseAction", "vsBaseUsd", "vsBaseBb"}
    chip = max(range(len(actions)), key=lambda at: (actions[at]["evBb"], -at))
    if chip != best:
        keys.add("chipBestAction")
    if "bountyUsd" in answer:
        keys.add("bountyUsd")
    hero = answer["ranges"]["hero"]
    keys |= {f"heroRange.{kind}" for kind in hero["byAction"]}
    mixed = [kind for kind, freq in hero["handFreq"].items() if freq >= 0.005]
    if len(mixed) > 1:
        keys |= {f"heroHandFreq.{kind}" for kind in mixed}
    for opponent in answer["ranges"]["opponents"]:
        keys |= {f"opponent.{opponent['position']}.{tail}" for tail in ("role", "stackBb", "reachPct")}
    if any(act["action"] != "fold" for act in answer["line"]):
        keys.add("line")
    keys |= {f"flag.{flag}" for flag in answer["flags"]}
    return keys


@pytest.fixture(scope="module", params=list(SPOTS))
def preflop_answer(request):
    frames = SPOTS[request.param]()
    history = [advise(_context(), frames[:at], []) for at in range(1, len(frames))]
    return frames, advise(_context(), frames, history)


def test_preflop_facts_print_their_values(preflop_answer):
    _, answer = preflop_answer
    _assert_printed(preflop_advisor.explain(answer))


def test_preflop_fact_keys(preflop_answer):
    _, answer = preflop_answer
    facts = preflop_advisor.explain(answer)
    keys = [item["key"] for item in facts]
    assert len(keys) == len(set(keys))
    assert set(keys) == _expected_preflop_keys(answer)


def test_preflop_fact_values(preflop_answer):
    _, answer = preflop_answer
    facts = {item["key"]: item["value"] for item in preflop_advisor.explain(answer)}
    actions = answer["actions"]
    best = [option["action"] for option in actions].index(answer["action"])
    others = [option for at, option in enumerate(actions) if at != best]
    runner = max(others, key=lambda option: option["evUsd"])
    assert facts["vsSecondUsd"] == actions[best]["evUsd"] - runner["evUsd"] >= 0
    assert facts["vsSecondBb"] == actions[best]["evBb"] - runner["evBb"]
    if best != 0:
        assert facts["vsBaseUsd"] == actions[best]["evUsd"] - actions[0]["evUsd"]
    for kind, classes in answer["ranges"]["hero"]["byAction"].items():
        combos = sum(freq * allin_matrix.combos_of(name) for name, freq in classes.items())
        assert facts[f"heroRange.{kind}"] == pytest.approx(combos / 1326)
    # Доли действий героя — весь диапазон: в сумме 1 с точностью округления частот — до
    # полушага 0.005 на класс на каждое действие узла.
    shares = [value for key, value in facts.items() if key.startswith("heroRange.")]
    assert sum(shares) == pytest.approx(1.0, abs=0.005 * len(answer["actions"]))


def test_preflop_pko_has_the_bounty_fact():
    answer = advise(_context(), _bounties(preflop_vs_open()), [])
    facts = {item["key"]: item for item in preflop_advisor.explain(answer)}
    assert facts["bountyUsd"]["value"] == answer["bountyUsd"]


# --- ranges.hero.reach -----------------------------------------------------------------------


def test_the_hero_reach_on_open_is_every_hand():
    answer = advise(_context(), preflop_open(), [])
    hero = answer["ranges"]["hero"]
    assert hero["reach"] == dict.fromkeys(allin_matrix.CLASSES, 1.0)
    assert hero["reachPct"] == pytest.approx(1.0)


def test_the_hero_reach_after_the_open_is_the_raise_of_step_one():
    # `BTN` 3-бет до 6.0 — размер правила (3 × 2.0 в позиции): дерево шага 2 то же, что шага 1,
    # и `reach` героя — ровно его частоты рейза на шаге 1.
    frames = [
        preflop_frame(3, folded={7, 2}),
        preflop_frame(3, {3: 2.0, 4: 6.0}, folded={7, 2, 5, 6}),
    ]
    one = advise(_context(), frames[:1], [])
    two = advise(_context(), frames, [one])
    assert two["spot"] == "vs_3bet"
    assert two["ranges"]["hero"]["reach"] == one["ranges"]["hero"]["byAction"]["raise"]
    assert two["ranges"]["hero"]["reachPct"] == pytest.approx(
        explain.range_share(one["ranges"]["hero"]["byAction"]["raise"]), abs=0.005
    )


# --- pushfold --------------------------------------------------------------------------------


PUSHFOLD = {
    "first_in": pushfold_first_in_node,
    "facing_allin": pushfold_facing_allin_node,
    "first_in_pko": lambda: _bounties([pushfold_first_in_node()])[0],
}


@pytest.mark.parametrize("name", list(PUSHFOLD))
def test_pushfold_facts(name):
    answer = advise(_context(), [PUSHFOLD[name]()], [])
    facts = pushfold.explain(answer)
    _assert_printed(facts)
    keys = {item["key"] for item in facts}
    expected = {
        "action",
        "marginUsd",
        "marginBb",
        "heroIcmPct",
        "heroChipPct",
        "heroHandFreqIcm",
        "heroHandFreqChip",
        "effectiveStackBb",
        *(f"flag.{flag}" for flag in answer["flags"]),
        *(
            f"opponent.{o['position']}.{tail}"
            for o in answer["ranges"]["opponents"]
            for tail in ("role", "stackBb", "icmPct", "chipPct")
        ),
    }
    if "sizeBb" in answer:
        expected.add("sizeBb")
    if "bountyUsd" in answer["ev"]:
        expected.add("bountyUsd")
    assert keys == expected
    assert ("bountyUsd" in keys) == name.endswith("pko")


# --- узел и отказ ----------------------------------------------------------------------------


def test_the_node_facts_of_a_call_against_an_all_in():
    # Банк 11.25, колл 9 — требуемая эквити 9 / 20.25 = 44.4%.
    raw = pushfold_facing_allin_node()
    answer = advise(_context(), [raw], [])
    facts = {item["key"]: item for item in why(answer, node_from_dict(raw))}
    assert facts["potBb"]["value"] == 11.25
    assert facts["toCallBb"]["display"] == "9.0 BB"
    assert facts["requiredEquity"]["value"] == pytest.approx(9 / 20.25)
    assert facts["requiredEquity"]["display"] == "44.4%"


def test_no_required_equity_without_a_call():
    # `CO` против открытия `UTG` — не закрывающий: колла в дереве нет (D30).
    frames = preflop_vs_open()
    answer = advise(_context(), frames, [])
    assert "call" not in [option["action"] for option in answer["actions"]]
    keys = {item["key"] for item in why(answer, node_from_dict(frames[-1]))}
    assert {"potBb", "toCallBb"} <= keys and "requiredEquity" not in keys


def test_a_refusal_gives_its_reasons():
    answer = advise(_context(), [_node()], [])
    assert answer["advisor"] is None
    assert why(answer, node_from_dict(_node())) == [
        fact(f"reason.{entry['advisor']}", entry["reason"], "text")
        for entry in answer["notApplicable"]
    ]


def test_the_summary_facts():
    summary = {
        "street": "preflop",
        "line": [
            {"seatIndex": 3, "position": "CO", "action": "raise", "toBb": 2.0},
            {"seatIndex": 4, "position": "BTN", "action": "fold"},
            {"seatIndex": 6, "position": "BB", "action": "call", "toBb": 2.0},
        ],
        "ranges": [
            {"seatIndex": 3, "position": "CO", "role": "opener", "isHero": True,
             "stackBb": 38.0, "reach": {}, "reachPct": 0.3},
        ],
    }
    assert explain.street(summary) == [
        fact("preflop.line", "CO рейз до 2.0 BB, BB колл до 2.0 BB", "text"),
        fact("preflop.CO.role", "opener", "text"),
        fact("preflop.CO.stackBb", 38.0, "bb"),
        fact("preflop.CO.reachPct", 0.3, "pct"),
    ]
    assert explain.street({"street": "preflop", "reason": "нет"}) == [
        fact("preflop.reason", "нет", "text")
    ]
