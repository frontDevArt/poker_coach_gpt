"""Советник push/fold: ответ, совет из EV, головы, пометки (план 4, Задача 4).

Фикстуры споток — `conftest.py`: `first_in` (герой `UTG` 8 BB, 6-max, пятеро отвечающих) и
`facing_allin` (`HJ` олл-ин на 9 BB, герой `BTN` 30 BB, за ним `SB` и `BB`). Вариант `SB`
против `BB` строится здесь: все сфолдили до малого блайнда героя.
"""

from __future__ import annotations

import pytest

from conftest import (
    _context,
    _seats_by_index,
    pushfold_facing_allin_node,
    pushfold_first_in_node,
)
from poker_engine import bounty, nash, pushfold
from poker_engine.allin_matrix import CLASSES, class_index, equity_matrix, hand_weights
from poker_engine.hand import Hand
from poker_engine.handstate import context_from_dict, node_from_dict, validate_hand
from poker_engine.nash import Game, opener_ev, range_share, solve
from poker_engine.pushfold_game import chip_outcomes, icm_outcomes, read_spot


def _sb_vs_bb(stack: float = 8.0, cards: list[str] | None = None) -> dict:
    """Все до `SB` сфолдили; герой — `SB` с `stack` BB вместе с блайндом, за ним только `BB`."""
    raw = pushfold_first_in_node()
    seats = _seats_by_index(raw)
    for index in (7, 2, 3, 4):
        seats[index].update(inHand=False, isHero=False)
    seats[5].update(isHero=True, stackBb=stack - 0.5)
    raw.update(toCallBb=0.5)
    if cards is not None:
        raw["heroCards"] = cards
    return raw


def _shove_from_sb(raw: dict) -> dict:
    """`SB` пошёл олл-ин на 9 BB, герой — `BB`: после олл-инщика только `BB`."""
    seats = _seats_by_index(raw)
    for index in (7, 2, 3, 4):
        seats[index].update(inHand=False, isHero=False)
    seats[5].update(stackBb=0.0, investedBb=9.0)
    seats[6].update(isHero=True)
    raw.update(potBb=10.75, toCallBb=8.0)
    return raw


def _priced(raw: dict) -> dict:
    for seat in raw["seats"]:
        seat["bountyUsd"] = 10.0 + seat["seatIndex"]
    return raw


def _advise(raw: dict, context_raw: dict | None = None, history: list | None = None) -> dict:
    context = context_from_dict(_context() if context_raw is None else context_raw)
    nodes = [node_from_dict(raw)]
    validate_hand(context, nodes)
    assert pushfold.applies(Hand(context, nodes)) is None
    return pushfold.advise(Hand(context, nodes), [] if history is None else history)


def _games(raw: dict, context_raw: dict | None = None) -> tuple[Game, Game, float]:
    """ICM- и фишечная подыгры узла без голов и допуск ICM-решения советника."""
    node = node_from_dict(raw)
    spot = read_spot(node)
    context = context_from_dict(_context() if context_raw is None else context_raw)
    chips = chip_outcomes(spot)
    icm = icm_outcomes(spot, node, context, bounties=False)
    responders = len(spot.players) - 1
    return Game(icm, responders), Game(chips, responders), pushfold.icm_eps_usd(chips, icm)


def _cards(raw: dict, cards: list[str]) -> dict:
    raw["heroCards"] = cards
    return raw


@pytest.fixture(scope="module")
def first_in_answer():
    return _advise(pushfold_first_in_node())


@pytest.fixture(scope="module")
def facing_answer():
    return _advise(pushfold_facing_allin_node())


# --- протокол и отказ ------------------------------------------------------------------------


def test_the_module_is_an_advisor():
    assert pushfold.name == "pushfold"
    assert callable(pushfold.applies) and callable(pushfold.advise)


def test_applies_gives_the_spot_refusal_verbatim():
    raw = pushfold_first_in_node()
    raw["street"] = "flop"
    raw["board"] = ["2c", "7d", "Ks"]
    context = context_from_dict(_context())
    node = node_from_dict(raw)
    assert pushfold.applies(Hand(context, [node])) == "push/fold советует только на префлопе"
    assert pushfold.applies(Hand(context, [node])) == read_spot(node)


# --- форма ответа ----------------------------------------------------------------------------


_KEYS = {
    "advisor",
    "spot",
    "action",
    "heroHand",
    "effectiveStackBb",
    "ev",
    "ranges",
    "nash",
    "flags",
}


def test_first_in_answer_shape(first_in_answer):
    answer = first_in_answer
    assert set(answer) - {"sizeBb"} == _KEYS
    assert answer["advisor"] == "pushfold"
    assert answer["spot"] == "first_in"
    assert answer["action"] in {"allin", "fold"}
    assert answer["heroHand"] == "JTs"
    # Эффективный — стек героя 8 против наибольшего после него (`HJ` 94.4).
    assert answer["effectiveStackBb"] == 8.0
    assert set(answer["ev"]) == {"icm", "chip"}
    assert set(answer["ev"]["icm"]) == {"allinUsd", "foldUsd", "marginUsd"}
    assert set(answer["ev"]["chip"]) == {"allinBb", "foldBb", "marginBb"}
    assert set(answer["nash"]["icm"]) == {"exploitabilityUsd", "iterations"}
    assert set(answer["nash"]["chip"]) == {"exploitabilityBb", "iterations"}
    eps = _games(pushfold_first_in_node())[2]
    assert answer["nash"]["icm"]["exploitabilityUsd"] <= eps
    assert answer["nash"]["chip"]["exploitabilityBb"] <= nash.EPS_CHIP_BB


def test_first_in_opponents_are_the_callers_in_order(first_in_answer):
    opponents = first_in_answer["ranges"]["opponents"]
    assert [(o["seatIndex"], o["position"], o["role"]) for o in opponents] == [
        (2, "HJ", "caller"),
        (3, "CO", "caller"),
        (4, "BTN", "caller"),
        (5, "SB", "caller"),
        (6, "BB", "caller"),
    ]
    assert [o["stackBb"] for o in opponents] == [94.4, 35.3, 23.2, 39.2, 35.7]


def test_facing_allin_answer_shape(facing_answer):
    answer = facing_answer
    assert set(answer) - {"sizeBb"} == _KEYS
    assert answer["spot"] == "facing_allin"
    assert answer["action"] in {"call", "fold"}
    # Эффективный — олл-ин 9 против 30 героя.
    assert answer["effectiveStackBb"] == 9.0
    assert set(answer["ev"]["icm"]) == {"callUsd", "foldUsd", "marginUsd"}
    assert set(answer["ev"]["chip"]) == {"callBb", "foldBb", "marginBb"}
    opponents = answer["ranges"]["opponents"]
    assert [(o["seatIndex"], o["position"], o["role"]) for o in opponents] == [
        (2, "HJ", "shover"),
        (5, "SB", "caller"),
        (6, "BB", "caller"),
    ]
    assert opponents[0]["stackBb"] == 0.0


@pytest.mark.parametrize(
    ("make", "cards", "action", "size"),
    [
        (pushfold_first_in_node, ["Ah", "As"], "allin", 8.0),
        (pushfold_facing_allin_node, ["Ah", "As"], "call", 9.0),
    ],
)
def test_size_follows_the_rule(make, cards, action, size):
    answer = _advise(_cards(make(), cards))
    assert answer["action"] == action
    assert answer["sizeBb"] == size


def test_call_size_is_the_shove_minus_what_the_hero_has_in():
    # Герой — `BB` с 1 BB в банке против олл-ина `SB` на 9: колл 8, не 9.
    answer = _advise(_cards(_shove_from_sb(pushfold_first_in_node()), ["Ah", "As"]))
    assert answer["action"] == "call"
    assert answer["sizeBb"] == 8.0
    assert answer["effectiveStackBb"] == 9.0


def test_call_size_is_capped_by_the_hero_stack():
    # Герой `BTN` с 5 BB против олл-ина на 9: колл — весь стек.
    raw = _cards(pushfold_facing_allin_node(), ["Ah", "As"])
    _seats_by_index(raw)[4]["stackBb"] = 5.0
    answer = _advise(raw)
    assert answer["action"] == "call"
    assert answer["sizeBb"] == 5.0
    assert answer["effectiveStackBb"] == 5.0


@pytest.mark.parametrize("make", [pushfold_first_in_node, pushfold_facing_allin_node])
def test_fold_has_no_size(make):
    answer = _advise(_cards(make(), ["7h", "2c"]))
    assert answer["action"] == "fold"
    assert "sizeBb" not in answer


# --- совет следует из EV ---------------------------------------------------------------------


@pytest.mark.parametrize("make", [pushfold_first_in_node, pushfold_facing_allin_node])
@pytest.mark.parametrize("cards", [["Ah", "As"], ["Jh", "Th"], ["7h", "2c"]])
def test_advice_follows_the_icm_margin(make, cards):
    answer = _advise(_cards(make(), cards))
    word = "allin" if answer["spot"] == "first_in" else "call"
    icm, chip = answer["ev"]["icm"], answer["ev"]["chip"]
    assert icm["marginUsd"] == icm[f"{word}Usd"] - icm["foldUsd"]
    assert chip["marginBb"] == chip[f"{word}Bb"] - chip["foldBb"]
    assert (answer["action"] == word) == (icm["marginUsd"] > 0)


def test_on_the_bubble_icm_overrules_chips():
    # 170 живых, платят 165, призы до 165-го места: колл `87s` против олл-ина 9 BB выгоден
    # по фишкам и убыточен по ICM. Совет — фолд: его даёт ICM, фишки — для объяснения.
    context_raw = _context()
    context_raw["payouts"][-1] = {"from": 4, "to": 165, "amount": 20.0}
    raw = _cards(pushfold_facing_allin_node(), ["8h", "7h"])
    raw.update(playersLeft=170, heroRank=50)
    answer = _advise(raw, context_raw)
    assert answer["ev"]["chip"]["marginBb"] > 0 > answer["ev"]["icm"]["marginUsd"]
    assert answer["action"] == "fold"
    hero = answer["ranges"]["hero"]
    assert hero["handFreqChip"] > 0.5 > hero["handFreqIcm"]


def test_effective_stack_is_against_the_deepest_behind():
    # `BTN` с 5 BB короче героя, но за героем есть стеки глубже: эффективный — 8, не 5.
    raw = pushfold_first_in_node()
    _seats_by_index(raw)[4]["stackBb"] = 5.0
    assert _advise(raw)["effectiveStackBb"] == 8.0


def test_opener_fold_is_the_walk(first_in_answer):
    # Фолд героя-открывающего — исход `walk`: по фишкам у `UTG` остаётся его стек.
    assert first_in_answer["ev"]["chip"]["foldBb"] == 8.0


# --- диапазоны -------------------------------------------------------------------------------


def test_hero_range_comes_from_the_icm_equilibrium(first_in_answer):
    game, _, eps = _games(pushfold_first_in_node())
    equilibrium = solve(game, eps)
    hero = first_in_answer["ranges"]["hero"]
    assert hero["icmPct"] == range_share(equilibrium.push)
    assert hero["handFreqIcm"] == equilibrium.push[class_index("JTs")]
    callers = first_in_answer["ranges"]["opponents"]
    assert callers[-1]["icmPct"] == range_share(equilibrium.call[-1])
    # Частоты классов — с шагом CLASS_FREQ_STEP; округлившиеся в ноль опущены.
    step = pushfold.CLASS_FREQ_STEP
    expected = {}
    for name in CLASSES:
        steps = round(float(equilibrium.call[-1][class_index(name)]) / step)
        if steps > 0:
            expected[name] = steps * step
    assert callers[-1]["classes"] == pytest.approx(expected, abs=1e-12)
    assert 0 < len(expected) < 169
    # Округлено и в JSON: `0.95`, а не `0.9500000000000001` (находка 5 ревью Задачи 4).
    for opponent in callers:
        assert all(len(repr(freq)) <= 4 for freq in opponent["classes"].values())


def test_chip_side_comes_from_the_chip_equilibrium(first_in_answer):
    # `ev.chip` и `chipPct` — из фишечного решения, а не из ICM: на пузыре знаки совпадают,
    # на одном призе совпадают равновесия, и подмена иначе не видна.
    _, game, _ = _games(pushfold_first_in_node())
    equilibrium = solve(game, nash.EPS_CHIP_BB)
    row = equity_matrix()[class_index("JTs")]
    allin, fold = opener_ev(game, equilibrium.call, hand_weights(["Jh", "Th"]), row)
    chip = first_in_answer["ev"]["chip"]
    assert (chip["allinBb"], chip["foldBb"]) == pytest.approx((allin, fold), abs=1e-12)
    hero = first_in_answer["ranges"]["hero"]
    assert hero["chipPct"] == range_share(equilibrium.push)
    assert hero["handFreqChip"] == equilibrium.push[class_index("JTs")]
    callers = first_in_answer["ranges"]["opponents"]
    for k, caller in enumerate(callers):
        assert caller["chipPct"] == range_share(equilibrium.call[k])


def test_chip_and_icm_ranges_are_both_reported(first_in_answer, facing_answer):
    for answer in (first_in_answer, facing_answer):
        hero = answer["ranges"]["hero"]
        assert set(hero) == {"icmPct", "chipPct", "handFreqIcm", "handFreqChip"}
        assert all(0.0 <= value <= 1.0 for value in hero.values())


def test_winner_take_all_makes_icm_and_chip_ranges_agree():
    # Инвариант 6 на ответе: один приз, без голов и защиты — ICM пропорционален фишкам.
    # Допуск ICM-решения — фишечный в долларах, поэтому обе игры решаются шаг в шаг.
    context_raw = _context()
    context_raw.update(payouts=[{"from": 1, "to": 1, "amount": 1000.0}], placesPaid=1)
    answer = _advise(pushfold_first_in_node(), context_raw)
    assert answer["nash"]["icm"]["iterations"] == answer["nash"]["chip"]["iterations"]
    hero = answer["ranges"]["hero"]
    assert hero["icmPct"] == pytest.approx(hero["chipPct"], abs=1e-9)
    assert hero["handFreqIcm"] == pytest.approx(hero["handFreqChip"], abs=1e-9)
    for opponent in answer["ranges"]["opponents"]:
        assert opponent["icmPct"] == pytest.approx(opponent["chipPct"], abs=1e-9)


# --- классика, защита, головы ----------------------------------------------------------------


@pytest.mark.parametrize("make", [pushfold_first_in_node, pushfold_facing_allin_node])
def test_classic_tournament_has_no_bounty_part(make, monkeypatch):
    # Инвариант 10: без ценников нет `ev.bountyUsd`, нет `pko`, `bounty.py` не вызывается.
    def refuse(*args, **kwargs):
        raise AssertionError("knockout_cash в классическом турнире")

    monkeypatch.setattr(bounty, "knockout_cash", refuse)
    answer = _advise(make())
    assert "bountyUsd" not in answer["ev"]
    assert "pko" not in answer["flags"]


@pytest.mark.parametrize("make", [pushfold_first_in_node, pushfold_facing_allin_node])
def test_zero_protection_is_no_protection(make):
    # Инвариант 11: `bubbleRefundUsd = 0` — ответ ключ в ключ как без поля.
    context_raw = _context()
    context_raw["bubbleRefundUsd"] = 0.0
    assert _advise(make(), context_raw) == _advise(make())


def test_a_covering_call_earns_the_head():
    # Герой 30 BB накрывает олл-ин 9 BB: выиграв колл, он выбивает и берёт голову.
    answer = _advise(_priced(pushfold_facing_allin_node()))
    assert "pko" in answer["flags"]
    assert answer["ev"]["bountyUsd"] > 0


def test_a_call_that_does_not_cover_earns_no_head():
    # Герой 5 BB против олл-ина 9 BB: выигрыш не выбивает олл-инщика, головы нет.
    raw = _priced(pushfold_facing_allin_node())
    _seats_by_index(raw)[4]["stackBb"] = 5.0
    answer = _advise(raw)
    assert "pko" in answer["flags"]
    assert answer["ev"]["bountyUsd"] == 0.0


# --- пометки ---------------------------------------------------------------------------------


def test_mh_bias_is_always_set(first_in_answer, facing_answer):
    # Malmuth-Harville применяется всегда: пары «не ставится» у этой пометки нет.
    assert first_in_answer["flags"][0] == "mh_bias"
    assert facing_answer["flags"][0] == "mh_bias"


def test_field_homogeneous_only_with_a_field(first_in_answer):
    assert "field_homogeneous" in first_in_answer["flags"]
    raw = pushfold_first_in_node()
    raw.update(playersLeft=6, heroRank=3)  # финальный стол: поля вне стола нет
    assert "field_homogeneous" not in _advise(raw)["flags"]


def test_pko_only_with_prices(first_in_answer):
    assert "pko" not in first_in_answer["flags"]
    assert "pko" in _advise(_priced(pushfold_first_in_node()))["flags"]


def test_bubble_protection_only_with_a_refund(first_in_answer):
    assert "bubble_protection" not in first_in_answer["flags"]
    context_raw = _context()
    context_raw["bubbleRefundUsd"] = 50.0
    assert "bubble_protection" in _advise(pushfold_first_in_node(), context_raw)["flags"]


def test_ladder_incomplete_only_when_it_is(first_in_answer):
    # Лесенка фикстуры описывает места 1–6 из 165 оплачиваемых.
    assert "ladder_incomplete" in first_in_answer["flags"]
    context_raw = _context()
    context_raw["placesPaid"] = 6
    assert "ladder_incomplete" not in _advise(pushfold_first_in_node(), context_raw)["flags"]


def test_late_reg_open_only_when_it_is(first_in_answer):
    assert "late_reg_open" in first_in_answer["flags"]
    context_raw = _context()
    context_raw["lateRegOpen"] = False
    assert "late_reg_open" not in _advise(pushfold_first_in_node(), context_raw)["flags"]


def test_no_overcall_only_with_more_than_one_responder(first_in_answer, facing_answer):
    assert "no_overcall" in first_in_answer["flags"]
    assert "no_overcall" in facing_answer["flags"]
    assert "no_overcall" not in _advise(_sb_vs_bb())["flags"]
    assert "no_overcall" not in _advise(_shove_from_sb(pushfold_first_in_node()))["flags"]


def test_fold_as_walk_only_with_someone_besides_the_big_blind(first_in_answer, facing_answer):
    assert "fold_as_walk" in first_in_answer["flags"]
    # Решение плана против спеки §8: и в `facing_allin`, когда после олл-инщика не только `BB`.
    assert "fold_as_walk" in facing_answer["flags"]
    assert "fold_as_walk" not in _advise(_sb_vs_bb())["flags"]
    assert "fold_as_walk" not in _advise(_shove_from_sb(pushfold_first_in_node()))["flags"]


def test_close_spot_marks_exactly_the_indifferent_stacks():
    # Перебор стека `SB` с `T2o` шагом 0.1 BB: пометка там и только там, где |маржа| ≤ eps.
    seen = {True: 0, False: 0}
    for tenths in range(45, 56):
        raw = _sb_vs_bb(tenths / 10, ["Th", "2c"])
        answer = _advise(raw)
        close = abs(answer["ev"]["icm"]["marginUsd"]) <= _games(raw)[2]
        assert ("close_spot" in answer["flags"]) == close, tenths
        seen[close] += 1
    assert seen[True] and seen[False]


def test_nash_not_converged_only_when_a_solve_stops_short(first_in_answer, monkeypatch):
    assert "nash_not_converged" not in first_in_answer["flags"]
    monkeypatch.setattr(nash, "MAX_ITERATIONS", 1)
    answer = _advise(pushfold_first_in_node())
    assert "nash_not_converged" in answer["flags"]
    assert answer["nash"]["icm"]["iterations"] == answer["nash"]["chip"]["iterations"] == 1


@pytest.mark.parametrize("short", ["icm", "chip"])
def test_nash_not_converged_when_either_solve_stops_short(short, monkeypatch):
    # Предел в одну итерацию только у одного из двух решений: пометка ставится в обоих случаях.
    real = nash.solve

    def solve_once_for(game, eps, max_iterations):
        is_chip = eps == nash.EPS_CHIP_BB
        return real(game, eps, 1 if is_chip == (short == "chip") else max_iterations)

    monkeypatch.setattr(nash, "solve", solve_once_for)
    answer = _advise(pushfold_first_in_node())
    other = "chip" if short == "icm" else "icm"
    assert answer["nash"][short]["iterations"] == 1
    assert answer["nash"][other]["iterations"] > 1
    assert "nash_not_converged" in answer["flags"]


# --- history и детерминизм -------------------------------------------------------------------


def test_history_is_not_read(first_in_answer):
    assert _advise(pushfold_first_in_node(), history=[{"x": 1}]) == first_in_answer


def test_the_answer_is_deterministic(facing_answer):
    assert _advise(pushfold_facing_allin_node()) == facing_answer
