"""Подыгра push/fold из узла скриншота: спот, исходы, выплаты (план 4, Задача 2)."""

from __future__ import annotations

import pytest

from conftest import _context, pushfold_facing_allin_node, pushfold_first_in_node
from poker_engine import bounty, icm_field
from poker_engine.handstate import context_from_dict, node_from_dict, validate_hand
from poker_engine.pushfold_game import (
    PUSHFOLD_MAX_BB,
    Spot,
    chip_outcomes,
    icm_outcomes,
    outcome_stacks,
    read_spot,
    with_bounties,
)


def _seat(raw: dict, index: int) -> dict:
    return next(seat for seat in raw["seats"] if seat["seatIndex"] == index)


def _spot(raw: dict) -> Spot:
    node = node_from_dict(raw)
    validate_hand(context_from_dict(_context()), [node])
    spot = read_spot(node)
    assert isinstance(spot, Spot), spot
    return spot


def _refusal(raw: dict) -> str:
    node = node_from_dict(raw)
    validate_hand(context_from_dict(_context()), [node])
    reason = read_spot(node)
    assert isinstance(reason, str), reason
    return reason


def _all_rows(outcomes: dict) -> list[list[float]]:
    return [outcomes["steal"], outcomes["walk"], *outcomes["win"], *outcomes["lose"]]


def _hu_node() -> dict:
    """Хедз-ап: кнопка — `SB` (место 4, герой, 8 BB), `BB` — место 7, без анте."""
    raw = pushfold_first_in_node()
    raw["seats"] = [seat for seat in raw["seats"] if seat["seatIndex"] in (4, 7)]
    _seat(raw, 4).update(stackBb=8.0, investedBb=0.5, isHero=True)
    _seat(raw, 7).update(stackBb=20.0, investedBb=1.0, isHero=False)
    raw.update(potBb=1.5, toCallBb=0.5)
    return raw


# --- распознавание -------------------------------------------------------------------------


def test_fixtures_are_valid_hands():
    context = context_from_dict(_context())
    for raw in (pushfold_first_in_node(), pushfold_facing_allin_node()):
        validate_hand(context, [node_from_dict(raw)])


def test_first_in_starts_with_the_hero_and_everyone_after_him_responds(pushfold_first_in):
    spot = _spot(pushfold_first_in)
    assert spot.kind == "first_in"
    assert [seat.seat_index for seat in spot.players] == [7, 2, 3, 4, 5, 6]
    assert spot.hero_at == 0 and spot.players[0].is_hero
    assert spot.bb_at == 5
    assert spot.bystanders == []
    assert spot.totals == [10.0, 94.4, 35.3, 23.2, 39.7, 36.7]
    # Банк 2.25 минус вложения участников 1.5 — анте.
    assert spot.dead_bb == pytest.approx(0.75, abs=1e-12)


def test_facing_allin_starts_with_the_all_in_player(pushfold_facing_allin):
    spot = _spot(pushfold_facing_allin)
    assert spot.kind == "facing_allin"
    assert [seat.seat_index for seat in spot.players] == [2, 4, 5, 6]
    assert spot.hero_at == 1 and spot.players[1].is_hero
    assert spot.bb_at == 3
    assert sorted(seat.seat_index for seat in spot.bystanders) == [3, 7]
    assert spot.totals == [9.0, 30.0, 39.7, 36.7]
    assert spot.dead_bb == pytest.approx(0.75, abs=1e-12)


def test_heads_up_small_blind_is_first_in_with_one_responder():
    spot = _spot(_hu_node())
    assert spot.kind == "first_in"
    assert [seat.seat_index for seat in spot.players] == [4, 7]
    assert (spot.hero_at, spot.bb_at) == (0, 1)
    assert spot.dead_bb == pytest.approx(0.0, abs=1e-12)


def test_dead_money_includes_what_folded_seats_put_in(pushfold_facing_allin):
    # Сфолдивший `SB`: его 0.5 BB лежат в банке, но он не участник подыгры.
    raw = pushfold_facing_allin
    _seat(raw, 5)["inHand"] = False
    spot = _spot(raw)
    assert [seat.seat_index for seat in spot.players] == [2, 4, 6]
    assert spot.dead_bb == pytest.approx(0.75 + 0.5, abs=1e-12)


# --- отказы: каждая строка таблицы плана -----------------------------------------------------


def test_refuses_postflop(pushfold_first_in):
    raw = pushfold_first_in
    raw.update(street="flop", board=["2c", "7d", "Ks"])
    assert _refusal(raw) == "push/fold советует только на префлопе"


def test_refuses_when_the_hero_is_already_all_in(pushfold_first_in):
    _seat(pushfold_first_in, 7).update(stackBb=0.0, investedBb=10.0)
    pushfold_first_in["potBb"] = 12.25
    assert _refusal(pushfold_first_in) == "герой уже в олл-ине: решения нет"


def test_refuses_a_walk_to_the_big_blind(pushfold_first_in):
    # Review Focus 4: все сфолдили до героя на `BB` — решения нет.
    raw = pushfold_first_in
    for index in (7, 2, 3, 4, 5):
        _seat(raw, index)["inHand"] = False
    _seat(raw, 7)["isHero"] = False
    _seat(raw, 6)["isHero"] = True
    assert _refusal(raw) == "все сфолдили до большого блайнда: решения нет"


def test_refuses_a_limp_before_the_hero(pushfold_first_in):
    raw = pushfold_first_in
    _seat(raw, 7).update(isHero=False, stackBb=9.0, investedBb=1.0)
    _seat(raw, 2)["inHand"] = False
    _seat(raw, 3)["inHand"] = False
    _seat(raw, 4)["isHero"] = True
    raw["potBb"] = 3.25
    assert _refusal(raw) == "банк открыт не олл-ином: это не спот push/fold"


def test_refuses_the_analyze_fixture_where_a_raise_is_not_all_in(analyze_node):
    # Спека §9 п.15: в плановой фикстуре соперник открыл рейзом не в олл-ин.
    assert _refusal(analyze_node) == "банк открыт не олл-ином: это не спот push/fold"


def test_refuses_a_big_blind_that_posted_more_than_a_big_blind(pushfold_first_in):
    # Граница: ровно 1.0 BB — спот (фикстура), на шаг округления больше — уже нет.
    _seat(pushfold_first_in, 6)["investedBb"] = 1.1
    pushfold_first_in["potBb"] = 2.35
    assert _refusal(pushfold_first_in) == "банк открыт не олл-ином: это не спот push/fold"


def test_refuses_a_small_blind_that_completed(pushfold_first_in):
    _seat(pushfold_first_in, 5)["investedBb"] = 1.0
    pushfold_first_in["potBb"] = 2.75
    assert _refusal(pushfold_first_in) == "банк открыт не олл-ином: это не спот push/fold"


def test_refuses_two_all_ins_before_the_hero(pushfold_facing_allin):
    raw = pushfold_facing_allin
    _seat(raw, 3).update(inHand=True, stackBb=0.0, investedBb=35.3)
    raw["potBb"] = 11.25 + 35.3
    assert _refusal(raw) == "олл-инов перед героем больше одного: мультипот вне модели"


def test_refuses_an_all_in_no_bigger_than_the_hero_already_put_in(pushfold_first_in):
    # Review Focus 5: `SB` пошёл олл-ин на 0.8 BB, герой — `BB` с 1.0 BB в банке.
    raw = pushfold_first_in
    for index in (7, 2, 3, 4):
        _seat(raw, index)["inHand"] = False
    _seat(raw, 7)["isHero"] = False
    _seat(raw, 5).update(stackBb=0.0, investedBb=0.8)
    _seat(raw, 6)["isHero"] = True
    raw["potBb"] = 2.55
    assert _refusal(raw) == "к коллу ничего: олл-ин не больше вложенного героем"


def test_refuses_a_responder_all_in_from_the_blind(pushfold_first_in):
    # Review Focus 2: `BB` в олл-ине с блайнда среди отвечающих.
    _seat(pushfold_first_in, 6).update(stackBb=0.0, investedBb=1.0)
    assert _refusal(pushfold_first_in) == "место 6 уже в олл-ине с блайнда: вне модели"


def test_refuses_a_busted_seat_out_of_the_hand(pushfold_facing_allin):
    # Review Focus 3: место 3 сфолдило со стеком 0 — ICM на нём не определён.
    _seat(pushfold_facing_allin, 3)["stackBb"] = 0.0
    assert _refusal(pushfold_facing_allin) == "на месте 3 стек 0 вне раздачи: ICM не определён"


def test_refuses_a_big_blind_out_of_the_hand_before_acting(pushfold_first_in):
    _seat(pushfold_first_in, 6)["inHand"] = False
    assert _refusal(pushfold_first_in) == "большой блайнд не в раздаче: спот не распознан"


def test_refuses_an_effective_stack_above_the_threshold(pushfold_first_in):
    _seat(pushfold_first_in, 7)["stackBb"] = 15.0
    assert _refusal(pushfold_first_in) == (
        "эффективный стек 15.0 BB выше порога push/fold 12 BB"
    )


def test_effective_stack_is_capped_by_the_biggest_responder(pushfold_first_in):
    # У героя 30, но больше 11.5 за ним ни у кого нет: эффективный стек 11.5.
    raw = pushfold_first_in
    _seat(raw, 7)["stackBb"] = 30.0
    for index in (2, 3, 4, 5, 6):
        _seat(raw, index)["stackBb"] = 10.5
    assert _spot(raw).kind == "first_in"
    _seat(raw, 2)["stackBb"] = 12.5
    assert _refusal(raw) == "эффективный стек 12.5 BB выше порога push/fold 12 BB"


def test_effective_stack_at_the_threshold_is_still_push_fold(pushfold_first_in):
    _seat(pushfold_first_in, 7)["stackBb"] = PUSHFOLD_MAX_BB
    assert _spot(pushfold_first_in).kind == "first_in"


def test_threshold_does_not_apply_facing_an_all_in(pushfold_facing_allin):
    # Олл-ин на 15 BB против героя с 30: формула `first_in` дала бы эффективный 15 > 12.
    raw = pushfold_facing_allin
    _seat(raw, 2)["investedBb"] = 15.0
    raw.update(potBb=17.25, toCallBb=15.0)
    spot = _spot(raw)
    assert spot.kind == "facing_allin"
    assert min(spot.totals[0], max(spot.totals[1:])) > PUSHFOLD_MAX_BB


# --- мёртвые деньги (Review Focus 1) ---------------------------------------------------------


def test_pot_short_by_rounding_zeroes_the_dead_money(pushfold_first_in):
    # Вложено 1.5 BB, банк 1.0: недостача 0.5 в пределах 0.1 BB × 6 мест.
    pushfold_first_in["potBb"] = 1.0
    assert _spot(pushfold_first_in).dead_bb == 0.0


def test_pot_far_below_the_investments_is_an_error(pushfold_first_in):
    pushfold_first_in["potBb"] = 0.8
    node = node_from_dict(pushfold_first_in)
    with pytest.raises(
        ValueError, match=r"^банк меньше суммы вложений мест: 0\.8 BB против 1\.5 BB$"
    ):
        read_spot(node)


# --- исходы по фишкам ------------------------------------------------------------------------


@pytest.mark.parametrize("make", [pushfold_first_in_node, pushfold_facing_allin_node])
def test_every_outcome_conserves_chips(make):
    # Инвариант 8: сумма стеков после раздачи — стеки до неё плюс банк.
    raw = make()
    spot = _spot(raw)
    before = sum(seat["stackBb"] for seat in raw["seats"]) + raw["potBb"]
    outcomes = outcome_stacks(spot)
    m = len(spot.players) - 1
    assert len(outcomes["win"]) == len(outcomes["lose"]) == m
    for row in _all_rows(outcomes):
        assert len(row) == len(raw["seats"])
        assert sum(row) == pytest.approx(before, abs=1e-9)


@pytest.mark.parametrize("make", [pushfold_first_in_node, pushfold_facing_allin_node])
def test_bystanders_keep_their_stacks_in_every_outcome(make):
    raw = make()
    spot = _spot(raw)
    seats = sorted(raw["seats"], key=lambda seat: seat["seatIndex"])
    outcomes = outcome_stacks(spot)
    for seat in spot.bystanders:
        at = [s["seatIndex"] for s in seats].index(seat.seat_index)
        for row in _all_rows(outcomes):
            assert row[at] == seat.stack_bb


def test_uncovered_surplus_goes_back_to_the_bigger_stack(pushfold_facing_allin):
    spot = _spot(pushfold_facing_allin)
    chips = chip_outcomes(spot)
    hero = spot.hero_at  # отвечающий `players[1]`, его ряды — `win[0]` и `lose[0]`
    # Герой выиграл: 30 своих, 9 олл-инщика, блайнды 1.5 и анте 0.75.
    assert chips.lose[0][hero] == pytest.approx(30.0 + 9.0 + 1.5 + 0.75, abs=1e-12)
    assert chips.lose[0][0] == 0.0
    # Герой проиграл: накрыт излишек 30 − 9, он не выбывает.
    assert chips.win[0][hero] == pytest.approx(30.0 - 9.0 + 0.0, abs=1e-12)
    assert chips.win[0][0] == pytest.approx(9.0 + 9.0 + 1.5 + 0.75, abs=1e-12)


def test_steal_and_walk_give_the_whole_pot(pushfold_first_in):
    spot = _spot(pushfold_first_in)
    chips = chip_outcomes(spot)
    assert chips.steal[0] == pytest.approx(10.0 + 2.25, abs=1e-12)
    assert chips.steal[1:] == [seat.stack_bb for seat in spot.players[1:]]
    # Фолд героя: банк большому блайнду, герой ничего не вкладывал.
    assert chips.walk[spot.bb_at] == pytest.approx(35.7 + 2.25, abs=1e-12)
    assert chips.walk[0] == 10.0


def test_a_blind_responder_who_loses_keeps_the_rest_of_his_total(pushfold_first_in):
    # Герой 10 против `BB` 35.7 + 1.0: `BB` теряет 10 из своих 36.7.
    spot = _spot(pushfold_first_in)
    chips = chip_outcomes(spot)
    k = spot.bb_at - 1
    assert chips.win[k][spot.bb_at] == pytest.approx(36.7 - 10.0, abs=1e-12)
    assert chips.lose[k][0] == 0.0


# --- исходы по ICM ---------------------------------------------------------------------------


@pytest.fixture
def icm_calls(monkeypatch):
    calls = []
    original = icm_field.table_equities

    def counted(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(icm_field, "table_equities", counted)
    return calls


@pytest.mark.parametrize("make", [pushfold_first_in_node, pushfold_facing_allin_node])
def test_icm_is_called_once_per_outcome(make, icm_calls):
    raw = make()
    spot = _spot(raw)
    icm_outcomes(spot, node_from_dict(raw), context_from_dict(_context()), bounties=False)
    m = len(spot.players) - 1
    assert len(icm_calls) == 2 * m + 2


@pytest.mark.parametrize("make", [pushfold_first_in_node, pushfold_facing_allin_node])
def test_icm_outcome_matches_a_direct_calculation(make):
    raw = make()
    node = node_from_dict(raw)
    context = context_from_dict(_context())
    spot = _spot(raw)
    icm = icm_outcomes(spot, node, context, bounties=False)
    stacks = outcome_stacks(spot)

    seats = sorted(node.seats, key=lambda seat: seat.seat_index)
    field_count = node.players_left - len(seats)
    one = icm_field.field_stack(
        node.players_left, context.average_stack_bb, [s.stack_bb for s in seats], field_count
    )
    ladder = context.ladder()
    busted_prize = ladder.prize(node.players_left)
    order = [seat.seat_index for seat in seats]

    def direct(row):
        alive = [at for at, stack in enumerate(row) if stack > 0]
        equities, _ = icm_field.table_equities(
            [row[at] for at in alive], field_count, one, ladder
        )
        by_seat = dict(zip(alive, equities))
        return [by_seat.get(order.index(p.seat_index), busted_prize) for p in spot.players]

    assert icm.steal == pytest.approx(direct(stacks["steal"]), abs=1e-12)
    assert icm.walk == pytest.approx(direct(stacks["walk"]), abs=1e-12)
    busts = 0
    for k in range(len(spot.players) - 1):
        assert icm.win[k] == pytest.approx(direct(stacks["win"][k]), abs=1e-12)
        assert icm.lose[k] == pytest.approx(direct(stacks["lose"][k]), abs=1e-12)
        busts += 0.0 in stacks["win"][k] or 0.0 in stacks["lose"][k]
    assert busts  # ряд с выбывшим и его призом проверен


def test_icm_uses_the_protected_ladder_on_the_bubble(pushfold_first_in):
    context_raw = _context()
    context_raw["bubbleRefundUsd"] = 50.0
    node = node_from_dict(pushfold_first_in)
    spot = _spot(pushfold_first_in)
    plain = icm_outcomes(spot, node, context_from_dict(_context()), bounties=False)
    protected = icm_outcomes(spot, node, context_from_dict(context_raw), bounties=False)
    # Герой выбывает в `lose`: на защищённой лесенке он забирает возврат бай-ина.
    assert plain.lose[0][0] == 0.0
    assert protected.lose[0][0] == 50.0


def test_classic_tournament_never_calls_bounty(pushfold_facing_allin, monkeypatch):
    # Часть инварианта 10: без ценников `bounty.py` не вызывается.
    def refuse(*args, **kwargs):
        raise AssertionError("knockout_cash в классическом турнире")

    monkeypatch.setattr(bounty, "knockout_cash", refuse)
    raw = pushfold_facing_allin
    node = node_from_dict(raw)
    spot = _spot(raw)
    context = context_from_dict(_context())
    assert icm_outcomes(spot, node, context, bounties=True) == icm_outcomes(
        spot, node, context, bounties=False
    )


def _priced(raw: dict) -> dict:
    for seat in raw["seats"]:
        seat["bountyUsd"] = 10.0 + seat["seatIndex"]
    return raw


@pytest.mark.parametrize("make", [pushfold_first_in_node, pushfold_facing_allin_node])
def test_knockout_cash_goes_to_the_winner_only(make):
    raw = _priced(make())
    node = node_from_dict(raw)
    spot = _spot(raw)
    context = context_from_dict(_context())
    heads = icm_outcomes(spot, node, context, bounties=True)
    plain = icm_outcomes(spot, node, context, bounties=False)
    chips = chip_outcomes(spot)
    assert heads.steal == plain.steal and heads.walk == plain.walk
    knockouts = 0
    for k in range(len(spot.players) - 1):
        j = k + 1
        for row, winner, loser in ((k, 0, j), (k, j, 0)):
            won = heads.win[row] if winner == 0 else heads.lose[row]
            base = plain.win[row] if winner == 0 else plain.lose[row]
            stacks = chips.win[row] if winner == 0 else chips.lose[row]
            expected = [0.0] * len(spot.players)
            if stacks[loser] == 0.0:
                expected[winner] = bounty.knockout_cash(spot.players[loser].bounty_usd)
                knockouts += 1
            assert [a - b for a, b in zip(won, base)] == pytest.approx(expected, abs=1e-9)
    assert knockouts


# --- D3 --------------------------------------------------------------------------------------


def test_d3_all_in_player_at_zero_builds_outcomes(pushfold_facing_allin):
    # Спека §5.8, инвариант 14: олл-инщик со стеком 0 — не отказ; ICM только на исходах.
    raw = pushfold_facing_allin
    assert _seat(raw, 2)["stackBb"] == 0.0
    node = node_from_dict(raw)
    spot = _spot(raw)
    icm = icm_outcomes(spot, node, context_from_dict(_context()), bounties=False)
    assert icm.steal[0] > 0.0
    assert len(icm.win) == len(icm.lose) == 3



def test_an_opener_who_busts_a_short_responder_takes_the_head():
    # `BTN` с 5 BB короче героя-`UTG` с 10: выиграв олл-ин против него, герой выбивает его.
    # В фикстурах выше открывающий никого не накрывает, и ряды `win` без нокаута.
    raw = _priced(pushfold_first_in_node())
    _seat(raw, 4)["stackBb"] = 5.0
    node = node_from_dict(raw)
    spot = _spot(raw)
    context = context_from_dict(_context())
    plain = icm_outcomes(spot, node, context, bounties=False)
    heads = with_bounties(spot, plain)
    btn = [seat.seat_index for seat in spot.players].index(4)
    assert chip_outcomes(spot).win[btn - 1][btn] == 0.0
    cash = bounty.knockout_cash(spot.players[btn].bounty_usd)
    assert heads.win[btn - 1][0] == pytest.approx(plain.win[btn - 1][0] + cash, abs=1e-12)
    assert heads.lose[btn - 1] == plain.lose[btn - 1]
