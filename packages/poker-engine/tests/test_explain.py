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
from poker_engine.lint import numbers

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
    "role": "role",
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


@pytest.mark.parametrize(
    ("role", "word"),
    [
        ("opener", "открывший"),
        ("3bettor", "3-беттор"),
        ("4bettor", "4-беттор"),
        ("limper", "лимпер"),
        ("shover", "олл-инщик"),
        ("responder", "отвечающий"),
        ("caller", "отвечающий"),
    ],
)
def test_a_role_is_printed_as_a_word(role, word):
    # Код роли в печати — след `3` или `4` линтеру (D35); слово — не число.
    assert fact("x.role", role, "role") == {"key": "x.role", "value": role, "display": word}
    assert numbers(word) == []


def test_every_role_of_the_advisors_has_a_word():
    assert set(explain.ROLES) == {
        *preflop_advisor._RAISE_ROLES, "limper", "shover", "responder", "caller"
    }


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
    # Доля действия — в диапазоне героя, дошедшем до узла (`reach`), взвешенно по комбинациям.
    reach = answer["ranges"]["hero"]["reach"]
    total = sum(freq * allin_matrix.combos_of(name) for name, freq in reach.items())
    for kind, classes in answer["ranges"]["hero"]["byAction"].items():
        part = sum(
            freq * classes.get(name, 0.0) * allin_matrix.combos_of(name)
            for name, freq in reach.items()
        )
        assert facts[f"heroRange.{kind}"] == pytest.approx(part / total)
    # Доли действий героя — весь его диапазон: в сумме 1 с точностью округления частот — до
    # полушага 0.005 на класс на каждое действие узла.
    shares = [value for key, value in facts.items() if key.startswith("heroRange.")]
    assert sum(shares) == pytest.approx(1.0, abs=0.005 * len(answer["actions"]))


def _hand_made_answer(chip_evs):
    """Ответ `preflop`, собранный руками: фолд, рейз до 2.0 и олл-ин 40.0 BB; по ICM лучший — рейз.

    `chip_evs` — `evBb` трёх действий по порядку; `evUsd` — 0, 0.10, 0.05.
    """
    actions = [
        {"action": "fold", "evUsd": 0.0, "evBb": chip_evs[0]},
        {"action": "raise", "toBb": 2.0, "evUsd": 0.10, "evBb": chip_evs[1]},
        {"action": "allin", "toBb": 40.0, "evUsd": 0.05, "evBb": chip_evs[2]},
    ]
    hero = {"byAction": {}, "reach": {}, "handFreq": {"raise": 1.0}, "reachPct": 1.0}
    return {
        "action": "raise",
        "sizeBb": 2.0,
        "actions": actions,
        "ranges": {"hero": hero, "opponents": []},
        "effectiveStackBb": 40.0,
        "line": [],
        "flags": [],
    }


@pytest.mark.parametrize(
    ("chip_evs", "printed"),
    [
        ((0.0, 0.2, 0.5), "олл-ин 40.0 BB"),
        ((0.3, 0.2, 0.1), "фолд"),
        ((0.0, 0.2, 0.1), None),
        # Равенство `evBb` — к раннему действию, как у совета: лучшее по фишкам — тот же рейз.
        ((0.0, 0.2, 0.2), None),
    ],
)
def test_the_chip_best_action_is_a_fact_only_when_it_differs(chip_evs, printed):
    # ICM-поправка (спека тренера §8): лучшее по фишкам называется, только когда оно другое.
    facts = preflop_advisor.explain(_hand_made_answer(chip_evs))
    assert {item["key"]: item["display"] for item in facts}.get("chipBestAction") == printed


def test_preflop_pko_has_the_bounty_fact():
    answer = advise(_context(), _bounties(preflop_vs_open()), [])
    facts = {item["key"]: item for item in preflop_advisor.explain(answer)}
    assert facts["bountyUsd"]["value"] == answer["bountyUsd"]


def test_on_the_first_decision_the_hero_range_is_every_hand():
    # Находка ревью Фазы 8: доля действия — в диапазоне, который герой довёл до узла (`reach`).
    # На первом решении `reach` — все руки, и доля — та же, что по 1326 комбинациям.
    answer = advise(_context(), preflop_open(), [])
    facts = {item["key"]: item["value"] for item in preflop_advisor.explain(answer)}
    for kind, classes in answer["ranges"]["hero"]["byAction"].items():
        everyone = sum(freq * allin_matrix.combos_of(name) for name, freq in classes.items())
        assert facts[f"heroRange.{kind}"] == pytest.approx(everyone / 1326)


def test_an_empty_hero_range_has_no_shares():
    # Герой сыграл линию, которой равновесие не играет: частоты `reach` ниже полушага, диапазон
    # пуст — долей нет, исключения нет (ключа, который посчитать нельзя, нет).
    answer = advise(_context(), preflop_vs_3bet(), [])
    answer["ranges"]["hero"]["reach"] = {}
    keys = {item["key"] for item in preflop_advisor.explain(answer)}
    assert not any(key.startswith("heroRange.") for key in keys)
    assert "heroReachPct" in keys


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
    raised = one["ranges"]["hero"]["byAction"]["raise"]
    share = sum(freq * allin_matrix.combos_of(name) for name, freq in raised.items()) / 1326
    assert two["ranges"]["hero"]["reachPct"] == pytest.approx(share, abs=0.005)


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


@pytest.mark.parametrize("to_call", [30.0, 5.0])
def test_a_short_hero_calls_the_pot_without_the_excess_of_the_all_in(to_call):
    # Герой `BTN` 5 BB против олл-ина `HJ` 30 BB: банк 30 + 0.5 + 1.0 + анте 0.75 = 32.25. Излишек
    # 30 − 5 = 25 вернётся `HJ`: банк до колла 7.25, требуемая эквити 5 / 12.25 = 40.8%. «Call»
    # GG показывает то ставку (30), то стек героя (5) — ответ один.
    raw = pushfold_facing_allin_node()
    seats = {seat["seatIndex"]: seat for seat in raw["seats"]}
    seats[2]["investedBb"] = 30.0
    seats[4]["stackBb"] = 5.0
    raw.update(potBb=32.25, toCallBb=to_call)
    facts = {
        item["key"]: item
        for item in explain.node_facts(node_from_dict(raw), {"spot": "facing_allin"})
    }
    assert facts["requiredEquity"]["value"] == pytest.approx(5 / 12.25)
    assert facts["requiredEquity"]["display"] == "40.8%"


def test_no_required_equity_without_a_call():
    # `CO` против открытия `UTG` — не закрывающий: колла в дереве нет (D30).
    frames = preflop_vs_open()
    answer = advise(_context(), frames, [])
    assert "call" not in [option["action"] for option in answer["actions"]]
    keys = {item["key"] for item in why(answer, node_from_dict(frames[-1]))}
    assert {"potBb", "toCallBb"} <= keys and "requiredEquity" not in keys


def test_no_call_facts_without_a_bet_to_call():
    # `BB` против лимпа `SB`: колла нет — фактов колла и требуемой эквити тоже, `0.0 BB` колла в
    # `why` не ложится.
    frames = [preflop_frame(6, {5: 1.0}, folded={7, 2, 3, 4})]
    answer = advise(_context(), frames, [])
    assert (answer["advisor"], answer["spot"]) == ("preflop", "vs_limp")
    node = node_from_dict(frames[-1])
    assert node.to_call_bb == 0
    keys = {item["key"] for item in why(answer, node)}
    assert "potBb" in keys and not keys & {"toCallBb", "requiredEquity"}


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
        fact("preflop.CO.role", "opener", "role"),
        fact("preflop.CO.stackBb", 38.0, "bb"),
        fact("preflop.CO.reachPct", 0.3, "pct"),
    ]
    assert explain.street(summary)[1]["display"] == "открывший"
    assert explain.street({"street": "preflop", "reason": "нет"}) == [
        fact("preflop.reason", "нет", "text")
    ]
