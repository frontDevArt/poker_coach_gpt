"""Инварианты схемы раздачи и её валидатора.

Каждое правило из раздела 7 спеки имеет здесь свой тест. Базовый узел
корректен; каждый тест ломает ровно одно и проверяет, что валидатор это
ловит — с различающим `match=`, потому что гарды модуля взаимно затеняют
друг друга (снесёшь один — отказ придёт от следующего по ходу).
"""

import re

import pytest

from poker_engine.handstate import (
    assign_positions,
    context_from_dict,
    node_from_dict,
    payout_ladder,
    validate_hand,
)
from poker_engine.types import Position

CONTEXT = {
    "payouts": [
        {"from": 1, "to": 1, "amount": 1090.51},
        {"from": 2, "to": 2, "amount": 840.37},
        {"from": 3, "to": 3, "amount": 648.01},
        {"from": 4, "to": 6, "amount": 400.0},
    ],
    "placesPaid": 165,
    "entrants": 1107,
    "playersLeft": 782,
    "lateRegOpen": True,
    "seatsPerTable": 8,
    "averageStackBb": 50.5,
}


def _seat(index, stack, *, hero=False, in_hand=True, invested=0.0, vpip=25.0, hands=60):
    return {
        "seatIndex": index,
        "name": f"p{index}",
        "stackBb": stack,
        "investedBb": invested,
        "inHand": in_hand,
        "isHero": hero,
        "vpip": vpip,
        "vpipHands": hands,
    }


def _node(**overrides):
    base = {
        "street": "preflop",
        "level": 13,
        "blinds": {"sb": 700, "bb": 1400, "ante": 175},
        "heroRank": 90,
        "playersLeft": 496,
        "seats": [
            _seat(0, 72.2),
            _seat(1, 66.1),
            _seat(2, 94.4),
            _seat(3, 35.3),
            _seat(4, 23.2, invested=7.3),
            _seat(5, 39.2),
            _seat(6, 35.7),
            _seat(7, 63.3, hero=True),
        ],
        "buttonSeat": 4,
        "heroCards": ["Jh", "Th"],
        "board": [],
        "potBb": 9.4,
        "toCallBb": 7.3,
        "raiseToBb": 14.5,
    }
    base.update(overrides)
    return base


def _validate(nodes):
    validate_hand(
        context_from_dict(CONTEXT), [node_from_dict(raw) for raw in nodes]
    )


def test_valid_hand_passes():
    _validate([_node()])


def test_button_seat_gets_the_button_position():
    positions = assign_positions(node_from_dict(_node()))
    assert positions[4] == Position.BTN


def test_positions_run_clockwise_from_the_button():
    positions = assign_positions(node_from_dict(_node()))
    assert positions[5] == Position.SB
    assert positions[6] == Position.BB


def test_positions_are_unique_and_complete():
    positions = assign_positions(node_from_dict(_node()))
    assert len(set(positions.values())) == 8


def test_board_size_must_match_the_street():
    with pytest.raises(ValueError, match="карт на доске"):
        _validate([_node(street="flop", board=["8c", "2s"])])


def test_unknown_street_is_rejected():
    with pytest.raises(ValueError, match="неизвестная улица"):
        _validate([_node(street="showdown")])


def test_exactly_one_hero_is_required():
    seats = _node()["seats"]
    seats[0]["isHero"] = True
    with pytest.raises(ValueError, match="героев в узле должно быть ровно один"):
        _validate([_node(seats=seats)])


def test_hero_must_be_in_the_hand():
    seats = _node()["seats"]
    seats[7]["inHand"] = False
    with pytest.raises(ValueError, match="герой помечен как выбывший"):
        _validate([_node(seats=seats)])


def test_button_seat_must_exist():
    with pytest.raises(ValueError, match="кнопки нет среди мест"):
        _validate([_node(buttonSeat=99)])


def test_seat_indices_must_be_unique():
    seats = _node()["seats"]
    seats[1]["seatIndex"] = 0
    with pytest.raises(ValueError, match="места за столом повторяются"):
        _validate([_node(seats=seats)])


def test_too_many_seats_are_rejected():
    seats = [_seat(i, 30.0) for i in range(10)]
    seats[0]["isHero"] = True
    with pytest.raises(ValueError, match="максимум"):
        _validate([_node(seats=seats, buttonSeat=0)])


def test_negative_stack_is_rejected():
    seats = _node()["seats"]
    seats[2]["stackBb"] = -1.0
    with pytest.raises(ValueError, match=re.escape("стек на месте 2 не может быть отрицательным")):
        _validate([_node(seats=seats)])


def test_empty_pot_is_rejected():
    with pytest.raises(ValueError, match=re.escape("банк должен быть > 0")):
        _validate([_node(potBb=0.0)])


def test_negative_call_is_rejected():
    with pytest.raises(ValueError, match=re.escape("размер колла не может быть отрицательным")):
        _validate([_node(toCallBb=-1.0)])


def test_raise_must_exceed_the_call():
    with pytest.raises(ValueError, match="рейз не превышает сумму колла"):
        _validate([_node(toCallBb=7.3, raiseToBb=5.0)])


def test_hero_rank_cannot_exceed_the_field():
    with pytest.raises(ValueError, match="ранг героя"):
        _validate([_node(heroRank=500, playersLeft=496)])


def test_card_outside_the_deck_is_rejected():
    # Источник схемы — vision-модель; "Xz" это не гипотеза.
    with pytest.raises(ValueError, match="неизвестная карта"):
        _validate([_node(heroCards=["Jh", "Xz"])])


def test_board_card_outside_the_deck_is_rejected():
    with pytest.raises(ValueError, match="неизвестная карта"):
        _validate([_node(street="flop", board=["8c", "2s", "9x"])])


def test_hero_must_hold_exactly_two_cards():
    with pytest.raises(ValueError, match="у героя должно быть 2 карты"):
        _validate([_node(heroCards=["Jh"])])


def test_duplicate_card_between_hand_and_board_is_rejected():
    with pytest.raises(ValueError, match="карта встречается дважды"):
        _validate([_node(street="flop", board=["Jh", "2s", "9d"], potBb=9.4)])


def test_duplicate_card_inside_the_board_is_rejected():
    with pytest.raises(ValueError, match="карта встречается дважды"):
        _validate([_node(street="flop", board=["8c", "8c", "9d"])])


def test_streets_must_advance():
    first = _node()
    second = _node(street="preflop", potBb=10.0)
    with pytest.raises(ValueError, match="улицы не идут по порядку"):
        _validate([first, second])


def test_board_must_extend_the_previous_board():
    first = _node(street="flop", board=["8c", "2s", "9d"], potBb=5.9)
    second = _node(street="turn", board=["8c", "2s", "Qd", "4c"], potBb=12.0)
    with pytest.raises(ValueError, match="доска не продолжает предыдущую улицу"):
        _validate([first, second])


def test_hero_cards_cannot_change_mid_hand():
    first = _node()
    second = _node(street="flop", board=["8c", "2s", "9d"], heroCards=["Ah", "Kh"])
    with pytest.raises(ValueError, match="карты героя изменились"):
        _validate([first, second])


def test_a_folded_player_cannot_return():
    seats = _node()["seats"]
    seats[0]["inHand"] = False
    first = _node(seats=seats)
    second = _node(street="flop", board=["8c", "2s", "9d"])
    with pytest.raises(ValueError, match="вернулся в раздачу после фолда"):
        _validate([first, second])


def test_chips_must_be_conserved_between_nodes():
    first = _node()
    second = _node(street="flop", board=["8c", "2s", "9d"], potBb=900.0)
    with pytest.raises(ValueError, match="фишки не сходятся между улицами"):
        _validate([first, second])


def test_rounding_between_nodes_is_tolerated():
    # Клиент печатает стеки с точностью 0.1 BB; сумма по восьми местам
    # может разойтись на эту величину без всякой ошибки распознавания.
    first = _node()
    seats = _node()["seats"]
    seats[0]["stackBb"] = 72.1
    second = _node(street="flop", board=["8c", "2s", "9d"], seats=seats, potBb=9.5)
    _validate([first, second])


def test_payout_ladder_expands_ranges():
    # Интервал 4–6 разворачивается в три одинаковых места.
    ladder = payout_ladder(context_from_dict(CONTEXT), places=12)
    assert ladder[0] == pytest.approx(1090.51)
    assert ladder[3] == pytest.approx(400.0)
    assert ladder[5] == pytest.approx(400.0)


def test_payout_ladder_pads_unpaid_places_with_zero():
    ladder = payout_ladder(context_from_dict(CONTEXT), places=15)
    assert len(ladder) == 15
    assert ladder[6] == 0.0
    assert ladder[14] == 0.0


def test_payout_ladder_must_not_increase_with_place():
    ladder = payout_ladder(context_from_dict(CONTEXT), places=12)
    assert ladder == sorted(ladder, reverse=True)


def test_overlapping_payout_ranges_are_rejected():
    broken = dict(CONTEXT)
    broken["payouts"] = [
        {"from": 1, "to": 3, "amount": 100.0},
        {"from": 3, "to": 5, "amount": 50.0},
    ]
    with pytest.raises(ValueError, match="интервалы выплат пересекаются"):
        validate_hand(context_from_dict(broken), [node_from_dict(_node())])


def test_field_smaller_than_the_table_is_rejected():
    with pytest.raises(ValueError, match=re.escape("осталось игроков (3) меньше, чем за столом")):
        _validate([_node(playersLeft=3)])


def test_players_left_equal_to_table_size_is_allowed():
    # Граница: ровно столько же игроков, сколько мест за столом, — это
    # финальный стол, а не ошибка распознавания.
    _validate([_node(playersLeft=8, heroRank=1)])


def test_hero_rank_zero_is_rejected():
    # Ранг начинается с 1; 0 — не более слабый герой, а испорченные данные.
    with pytest.raises(ValueError, match=re.escape("ранг героя (0)")):
        _validate([_node(heroRank=0)])


def test_raise_equal_to_call_is_rejected():
    # Рейз обязан превышать колл строго; равенство — это колл, а не рейз.
    with pytest.raises(ValueError, match="рейз не превышает сумму колла"):
        _validate([_node(toCallBb=7.3, raiseToBb=7.3)])


def test_negative_invested_is_rejected():
    seats = _node()["seats"]
    seats[4]["investedBb"] = -1.0
    with pytest.raises(
        ValueError, match=re.escape("вложение на месте 4 не может быть отрицательным")
    ):
        _validate([_node(seats=seats)])


def test_empty_payout_ladder_is_rejected():
    broken = dict(CONTEXT)
    broken["payouts"] = []
    with pytest.raises(ValueError, match="лесенка выплат пуста"):
        validate_hand(context_from_dict(broken), [node_from_dict(_node())])


def test_invalid_payout_interval_is_rejected():
    broken = dict(CONTEXT)
    broken["payouts"] = [{"from": 3, "to": 1, "amount": 100.0}]
    with pytest.raises(ValueError, match="неверный интервал мест в выплатах"):
        validate_hand(context_from_dict(broken), [node_from_dict(_node())])


def test_non_positive_payout_amount_is_rejected():
    broken = dict(CONTEXT)
    broken["payouts"] = [{"from": 1, "to": 1, "amount": 0.0}]
    with pytest.raises(
        ValueError, match=re.escape("приз за место 1 должен быть > 0")
    ):
        validate_hand(context_from_dict(broken), [node_from_dict(_node())])


def test_payout_amount_must_not_increase_for_a_worse_place():
    broken = dict(CONTEXT)
    broken["payouts"] = [
        {"from": 1, "to": 1, "amount": 100.0},
        {"from": 2, "to": 2, "amount": 200.0},
    ]
    with pytest.raises(
        ValueError, match="выплата за более низкое место больше, чем за высокое"
    ):
        validate_hand(context_from_dict(broken), [node_from_dict(_node())])


def test_payout_amounts_may_tie_between_places():
    # Равные призовые за соседние места — законная плоская лесенка, не отказ.
    tied = dict(CONTEXT)
    tied["payouts"] = [
        {"from": 1, "to": 1, "amount": 100.0},
        {"from": 2, "to": 2, "amount": 100.0},
    ]
    validate_hand(context_from_dict(tied), [node_from_dict(_node())])


def test_entrants_below_players_left_is_rejected():
    broken = dict(CONTEXT)
    broken["entrants"] = 100
    with pytest.raises(
        ValueError,
        match=re.escape("осталось игроков (782) больше, чем входов (100)"),
    ):
        validate_hand(context_from_dict(broken), [node_from_dict(_node())])


def test_entrants_equal_to_players_left_is_allowed():
    # Граница: на последнем столе входов ровно столько же, сколько осталось.
    equal = dict(CONTEXT)
    equal["entrants"] = CONTEXT["playersLeft"]
    validate_hand(context_from_dict(equal), [node_from_dict(_node())])


def test_non_positive_average_stack_is_rejected():
    broken = dict(CONTEXT)
    broken["averageStackBb"] = 0.0
    with pytest.raises(ValueError, match=re.escape("средний стек должен быть > 0")):
        validate_hand(context_from_dict(broken), [node_from_dict(_node())])


def test_tolerance_at_the_rounding_boundary_is_allowed():
    # Восемь мест, шаг округления 0.1 BB на место -> допуск ровно 0.8 BB.
    # Расхождение, в точности равное допуску, ещё не является отказом:
    # строгое неравенство в проверке (`>`, не `>=`) обязано пропустить его.
    seats = [_seat(i, 0.0, hero=(i == 7)) for i in range(8)]
    first = _node(seats=seats, potBb=0.9)
    second = _node(
        street="flop", board=["8c", "2s", "9d"], seats=seats, potBb=0.1
    )
    _validate([first, second])


def test_tolerance_scales_with_the_larger_of_the_two_seat_counts():
    # Если между узлами число мест меняется, допуск обязан считаться по
    # большему из двух столов, а не по меньшему: иначе достоверное
    # расхождение в пределах допуска на полном столе ложно бракуется после
    # того, как часть мест пропала из списка.
    first = _node()
    seats_short = [
        _seat(4, 20.0),
        _seat(7, 60.0, hero=True),
    ]
    second = _node(
        street="flop",
        board=["8c", "2s", "9d"],
        seats=seats_short,
        buttonSeat=4,
        potBb=358.3,
    )
    _validate([first, second])


def test_validate_hand_rejects_an_empty_node_list():
    with pytest.raises(ValueError, match="в раздаче нет ни одного узла решения"):
        validate_hand(context_from_dict(CONTEXT), [])


def test_missing_required_field_is_rejected():
    # Источник — vision-модель: пропавшее поле в JSON от Nuxt это ровно тот
    # отказ, который обслуживает `_require`, а не программная ошибка.
    raw = _node()
    del raw["buttonSeat"]
    with pytest.raises(
        ValueError, match=re.escape("в данных нет обязательного поля 'buttonSeat'")
    ):
        node_from_dict(raw)


def test_decision_node_hero_returns_the_hero_seat():
    # Не первое место, а именно то, что помечено `isHero` — герой в фикстуре
    # сидит последним (место 7).
    node = node_from_dict(_node())
    assert node.hero.seat_index == 7


def test_decision_node_hero_raises_when_nobody_is_marked_as_hero():
    seats = [dict(seat, isHero=False) for seat in _node()["seats"]]
    node = node_from_dict(_node(seats=seats))
    with pytest.raises(ValueError, match="в узле нет героя"):
        node.hero


def test_assign_positions_on_heads_up_uses_the_small_blind_as_the_button():
    # На хедз-апе `positions_for` не содержит BTN вообще (SB и есть кнопка).
    heads_up = _node(
        seats=[_seat(0, 50.0), _seat(1, 50.0, hero=True)],
        buttonSeat=0,
    )
    positions = assign_positions(node_from_dict(heads_up))
    assert positions[0] == Position.SB
    assert positions[1] == Position.BB
