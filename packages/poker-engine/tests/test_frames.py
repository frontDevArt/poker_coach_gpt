"""Кадр раздачи: единицы, банк «середина», перевод в форму узла (план 6, Задача 6).

Спека тренера §6.1, инварианты 1–2 §12; Review Focus 4 плана 6. Кадр в BB — форма узла `analyze`
как есть; кадр в фишках делится на `blinds.bb` без округления.
"""

import copy
import re

import pytest

from conftest import _context, preflop_frame, preflop_vs_open
from poker_engine.frames import context_payload, node_payload
from poker_engine.handstate import context_from_dict, node_from_dict, validate_hand

BB = 1400

_TOP = ("pot", "toCall", "raiseTo")
_SEAT = ("stack", "invested")


def _in_chips(raw, bb=BB):
    """Кадр `raw` в BB, переписанный в фишки: каждое поле `*Bb` → `*Chips`, умноженное на `bb`."""
    chips = copy.deepcopy(raw)
    chips["unit"] = "chips"
    chips["blinds"] = {"sb": bb // 2, "bb": bb, "ante": bb // 8}
    for key in _TOP:
        value = chips.pop(f"{key}Bb", None)
        if value is not None:
            chips[f"{key}Chips"] = value * bb
    for seat in chips["seats"]:
        for key in _SEAT:
            seat[f"{key}Chips"] = seat.pop(f"{key}Bb") * bb
    return chips


def _validate(raws, context=None):
    validate_hand(
        context_from_dict(context or _context()), [node_from_dict(node_payload(r)) for r in raws]
    )


# --- единицы ---------------------------------------------------------------------------------


def test_a_frame_in_big_blinds_is_the_node_as_is():
    raw = preflop_vs_open()[0]
    assert node_payload(raw) == raw
    assert node_payload({**raw, "unit": "bb"}) == raw


def test_a_frame_in_chips_is_the_frame_in_big_blinds_divided():
    # Инвариант 1: значения в BB — фишки, поделённые на `blinds.bb`, без округления.
    chips = {
        **_in_chips(preflop_vs_open()[0]),
        "potChips": 4900,
        "toCallChips": 2800,
        "raiseToChips": 6300,
    }
    chips["seats"][0]["stackChips"] = 30333
    bb = copy.deepcopy(chips)
    del bb["unit"]
    for key in _TOP:
        bb[f"{key}Bb"] = bb.pop(f"{key}Chips") / BB
    for seat in bb["seats"]:
        for key in _SEAT:
            seat[f"{key}Bb"] = seat.pop(f"{key}Chips") / BB
    assert node_payload(chips) == bb
    assert node_from_dict(node_payload(chips)) == node_from_dict(bb)


def test_chips_are_divided_without_rounding():
    # Review Focus 4: `blinds.bb = 1400`, стек 30333 — 21.666… BB, не 21.7; валидатор проходит
    # в своём допуске.
    raw = _in_chips(preflop_vs_open()[0])
    hero = next(seat for seat in raw["seats"] if seat["isHero"])
    hero["stackChips"] = 30333
    assert next(s for s in node_payload(raw)["seats"] if s["isHero"])["stackBb"] == 30333 / 1400
    _validate([raw])


def test_a_null_raise_in_chips_stays_null():
    raw = _in_chips(preflop_vs_open()[0])
    raw["raiseToChips"] = None
    assert node_from_dict(node_payload(raw)).raise_to_bb is None


def test_a_series_in_chips_passes_like_the_series_in_big_blinds():
    _validate([_in_chips(raw) for raw in preflop_vs_open()])


@pytest.mark.parametrize(
    ("unit", "where", "key"),
    [
        ("bb", "top", "potChips"),
        ("bb", "seat", "stackChips"),
        ("bb", "top", "potCenterChips"),
        ("chips", "top", "toCallBb"),
        ("chips", "seat", "investedBb"),
        ("chips", "top", "potCenterBb"),
    ],
)
def test_mixed_units_are_refused(unit, where, key):
    raw = preflop_vs_open()[0] if unit == "bb" else _in_chips(preflop_vs_open()[0])
    target = raw if where == "top" else raw["seats"][2]
    target[key] = 1.0
    with pytest.raises(ValueError, match=f"^поле {key} не для кадра в {unit}$"):
        node_payload(raw)


@pytest.mark.parametrize(
    "blinds", [None, {"sb": 700}, {"sb": 700, "bb": 0}, {"sb": 700, "bb": -1400}, {"bb": "x"}]
)
def test_a_frame_in_chips_needs_the_big_blind(blinds):
    raw = _in_chips(preflop_vs_open()[0])
    if blinds is None:
        del raw["blinds"]
    else:
        raw["blinds"] = blinds
    with pytest.raises(
        ValueError, match=re.escape("кадр в фишках без большого блайнда: нужно blinds.bb > 0")
    ):
        node_payload(raw)


def test_an_unknown_unit_is_refused():
    with pytest.raises(ValueError, match="^единица кадра должна быть bb или chips, получено 'usd'$"):
        node_payload({**preflop_vs_open()[0], "unit": "usd"})


def test_a_chip_field_must_be_a_number():
    raw = _in_chips(preflop_vs_open()[0])
    raw["seats"][1]["stackChips"] = "много"
    with pytest.raises(ValueError, match="^поле 'stackChips' должно быть числом, получено 'много'$"):
        node_payload(raw)


def test_a_frame_must_be_an_object():
    with pytest.raises(ValueError, match=re.escape("кадр должен быть объектом, получено [1]")):
        node_payload([1])


def test_the_frame_is_not_changed():
    # Кадры хранятся как пришли (спека тренера §5.1): перевод строит новый словарь.
    raw = _in_chips(preflop_vs_open()[0])
    raw["potCenterChips"] = raw.pop("potChips") - 700
    before = copy.deepcopy(raw)
    node_payload(raw)
    assert raw == before


# --- банк ------------------------------------------------------------------------------------


@pytest.mark.parametrize("unit", ["bb", "chips"])
def test_the_pot_center_plus_the_street_investment_is_the_full_pot(unit):
    # Инвариант 2: `UTG` открыл до 2.0, блайнды 0.5 и 1.0, анте 0.75 — полный банк 4.25, на
    # середине — анте 0.75; вложенное улицы — 3.5.
    raw = preflop_vs_open()[0]
    if unit == "chips":
        raw = _in_chips(raw)
    pot, center = ("potBb", "potCenterBb") if unit == "bb" else ("potChips", "potCenterChips")
    scale = 1 if unit == "bb" else BB
    assert raw[pot] == pytest.approx(4.25 * scale)
    centered = {key: value for key, value in raw.items() if key != pot}
    centered[center] = 0.75 * scale
    assert node_payload(centered)["potBb"] == pytest.approx(node_payload(raw)["potBb"])
    assert center not in node_payload(centered)


def test_the_pot_center_counts_a_seat_without_investment_as_zero():
    raw = preflop_frame(3, folded={7, 2})
    for seat in raw["seats"]:
        if seat["investedBb"] == 0.0:
            del seat["investedBb"]
    raw["potCenterBb"] = raw.pop("potBb") - 1.5
    assert node_payload(raw)["potBb"] == pytest.approx(2.25)


@pytest.mark.parametrize("unit", ["bb", "chips"])
def test_two_pots_are_refused(unit):
    raw = preflop_vs_open()[0] if unit == "bb" else _in_chips(preflop_vs_open()[0])
    raw["potCenterBb" if unit == "bb" else "potCenterChips"] = 1.0
    with pytest.raises(
        ValueError, match=re.escape("в кадре два банка: нужен полный или середина, не оба")
    ):
        node_payload(raw)


# --- контекст --------------------------------------------------------------------------------


def test_a_context_in_big_blinds_is_as_is():
    assert context_payload(_context(), preflop_vs_open()[0]) == _context()


def test_the_average_stack_in_chips_is_divided_by_the_big_blind_of_the_last_frame():
    raw = {**_context(), "averageStackChips": 70700}
    del raw["averageStackBb"]
    payload = context_payload(raw, _in_chips(preflop_vs_open()[0]))
    assert payload["averageStackBb"] == 70700 / 1400
    assert "averageStackChips" not in payload


def test_a_frame_in_big_blinds_still_gives_the_big_blind():
    # Средний стек — с экрана лобби, единица кадра ему не указ: `blinds` есть и у кадра в BB.
    raw = {**_context(), "averageStackChips": 70700}
    del raw["averageStackBb"]
    assert context_payload(raw, preflop_vs_open()[0])["averageStackBb"] == 50.5


def test_two_average_stacks_are_refused():
    raw = {**_context(), "averageStackChips": 70700}
    with pytest.raises(
        ValueError,
        match=re.escape("в контексте два средних стека: нужен в BB или в фишках, не оба"),
    ):
        context_payload(raw, preflop_vs_open()[0])


def test_the_average_stack_in_chips_needs_the_big_blind():
    raw = {**_context(), "averageStackChips": 70700}
    del raw["averageStackBb"]
    frame = preflop_vs_open()[0]
    del frame["blinds"]
    with pytest.raises(
        ValueError,
        match=re.escape("средний стек в фишках без большого блайнда: нужно blinds.bb > 0 в кадре"),
    ):
        context_payload(raw, frame)


# --- средний стек из стартового стека (план D40, Задача 1) --------------------------------------


def test_average_stack_from_starting_stack_after_late_reg():
    raw = {**_context(), "startingStackChips": 50000, "entrants": 2351, "lateRegOpen": False}
    raw.pop("averageStackBb")
    frame = {**preflop_vs_open()[0], "playersLeft": 802, "unit": "bb"}
    frame["blinds"] = {"sb": 2500, "bb": 5000, "ante": 600}
    payload = context_payload(raw, frame, first_frame=frame)
    assert payload["averageStackBb"] == pytest.approx(50000 * 2351 / 802 / 5000)
    assert payload["averageStackSource"] == "lobby"


def test_late_reg_hand_with_final_lobby_uses_table():
    first = preflop_vs_open()[0]
    raw = {**_context(), "startingStackChips": 50000, "lateRegOpen": True, "payoutsFinal": True}
    raw.pop("averageStackBb")
    payload = context_payload(raw, preflop_vs_open()[-1], first_frame=first)
    seats = node_payload(first)["seats"]
    expected = sum(s["stackBb"] + s.get("investedBb", 0.0) for s in seats) / len(seats)
    assert payload["averageStackBb"] == pytest.approx(expected)
    assert payload["averageStackSource"] == "table"


def test_explicit_average_stack_wins_over_starting_stack():
    raw = {**_context(), "averageStackBb": 50.5, "startingStackChips": 50000}
    payload = context_payload(raw, preflop_vs_open()[0], first_frame=preflop_vs_open()[0])
    assert payload["averageStackBb"] == 50.5 and "averageStackSource" not in payload


def test_explicit_average_stack_in_chips_wins_over_starting_stack():
    raw = {**_context(), "averageStackChips": 70700, "startingStackChips": 50000}
    raw.pop("averageStackBb")
    frame = _in_chips(preflop_vs_open()[0])
    payload = context_payload(raw, frame, first_frame=frame)
    assert payload["averageStackBb"] == pytest.approx(70700 / frame["blinds"]["bb"])
    assert "averageStackSource" not in payload


def test_late_reg_open_without_first_frame_derives_nothing():
    raw = {**_context(), "startingStackChips": 50000, "lateRegOpen": True}
    raw.pop("averageStackBb")
    payload = context_payload(raw, preflop_vs_open()[0])
    assert "averageStackBb" not in payload and "averageStackSource" not in payload


def test_starting_stack_without_frame_derives_nothing():
    raw = {**_context(), "startingStackChips": 50000, "lateRegOpen": False}
    raw.pop("averageStackBb")
    payload = context_payload(raw, None)
    assert "averageStackBb" not in payload and "averageStackSource" not in payload


def test_starting_stack_must_be_positive():
    with pytest.raises(ValueError, match="стартовый стек должен быть > 0"):
        context_payload({**_context(), "startingStackChips": 0}, None)


def test_starting_stack_is_checked_even_when_not_needed():
    raw = {**_context(), "startingStackChips": -5}
    with pytest.raises(ValueError, match="стартовый стек должен быть > 0"):
        context_payload(raw, preflop_vs_open()[0], first_frame=preflop_vs_open()[0])


def test_table_average_is_the_same_for_a_first_frame_in_chips():
    first = preflop_vs_open()[0]
    raw = {**_context(), "startingStackChips": 50000, "lateRegOpen": True}
    raw.pop("averageStackBb")
    last = preflop_vs_open()[-1]
    in_bb = context_payload(raw, last, first_frame=first)["averageStackBb"]
    in_chips = context_payload(raw, last, first_frame=_in_chips(first))["averageStackBb"]
    assert in_chips == pytest.approx(in_bb)


@pytest.mark.parametrize("null_field", ["averageStackChips", "averageStackBb"])
def test_a_null_average_stack_is_derived_from_the_starting_stack(null_field):
    raw = {**_context(), "startingStackChips": 50000, "lateRegOpen": False, null_field: None}
    if null_field == "averageStackChips":
        raw.pop("averageStackBb")
    frame = {**preflop_vs_open()[0], "playersLeft": 802, "blinds": {"sb": 2500, "bb": 5000}}
    payload = context_payload(raw, frame, first_frame=frame)
    assert payload["averageStackBb"] == pytest.approx(50000 * raw["entrants"] / 802 / 5000)
    assert payload["averageStackSource"] == "lobby"
    assert "averageStackChips" not in payload


def test_starting_stack_without_a_big_blind_is_refused():
    raw = {**_context(), "startingStackChips": 50000, "lateRegOpen": False}
    raw.pop("averageStackBb")
    frame = {key: value for key, value in preflop_vs_open()[0].items() if key != "blinds"}
    with pytest.raises(ValueError, match=re.escape("средний стек из стартового стека без большого блайнда")):
        context_payload(raw, frame, first_frame=frame)


def test_starting_stack_with_no_players_left_is_refused():
    raw = {**_context(), "startingStackChips": 50000, "lateRegOpen": False}
    raw.pop("averageStackBb")
    frame = {**preflop_vs_open()[0], "playersLeft": 0, "blinds": {"sb": 2500, "bb": 5000}}
    with pytest.raises(ValueError, match="остаток игроков должен быть > 0"):
        context_payload(raw, frame, first_frame=frame)


def test_table_average_of_a_first_frame_with_no_seats_is_refused():
    raw = {**_context(), "startingStackChips": 50000, "lateRegOpen": True}
    raw.pop("averageStackBb")
    first = {**preflop_vs_open()[0], "seats": []}
    with pytest.raises(ValueError, match="в первом кадре нет мест"):
        context_payload(raw, preflop_vs_open()[-1], first_frame=first)
