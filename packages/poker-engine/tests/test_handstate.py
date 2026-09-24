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
    validate_hand,
)
from poker_engine.types import Position, positions_for

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
    assert set(positions.values()) == set(positions_for(8))
    # Место 7 (герой) — самая ранняя позиция за столом на 8-max: сдвиг
    # опорной точки на один шаг сместил бы её на соседнюю позицию незаметно
    # для одной только проверки множества.
    assert positions[7] == Position.UTG1


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
    # Клиент печатает стеки с точностью 0.1 BB: место 0 "похудело" на 0.1 BB
    # между скриншотами без компенсации в банке — это и есть расхождение,
    # а не то же число, разложенное на минус здесь и плюс там.
    first = _node()
    seats = _node()["seats"]
    seats[0]["stackBb"] = 72.1
    second = _node(street="flop", board=["8c", "2s", "9d"], seats=seats)
    _validate([first, second])


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


def test_payouts_listed_from_the_worst_place_are_accepted():
    # Порядок интервалов во входе — порядок распознавания, а не мест:
    # монотонность сравнивает призы по возрастанию места, а не по списку.
    reversed_order = dict(CONTEXT)
    reversed_order["payouts"] = list(reversed(CONTEXT["payouts"]))
    validate_hand(context_from_dict(reversed_order), [node_from_dict(_node())])


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


def test_the_context_ladder_covers_the_described_places():
    # Лесенка контекста — `PayoutLadder` по тем же интервалам: 1-based
    # место, интервал 4–6 платит одинаково, глубже описанного — ноль, а
    # покрытых мест шесть при призовой зоне в 165.
    ladder = context_from_dict(CONTEXT).ladder()
    assert ladder.prize(1) == pytest.approx(1090.51)
    assert ladder.prize(4) == ladder.prize(6) == pytest.approx(400.0)
    assert ladder.prize(7) == 0.0
    assert ladder.places_covered == 6
    assert ladder.places_paid == 165
    assert not ladder.is_complete


def _rejected_with(text, **changes):
    broken = dict(CONTEXT)
    broken.update(changes)
    with pytest.raises(ValueError, match="^" + re.escape(text)):
        validate_hand(context_from_dict(broken), [node_from_dict(_node())])


# Приоритет отказов после перевода ладдер-блока на `PayoutLadder` (долг
# D17, решение Задачи 4): конструктор неделим, монотонность и
# `entrants < players_left` встают после него. Меняется ровно три класса
# пар, и одна пара обязана сохраниться; каждый вход нарушает два правила.
RISING = [
    {"from": 1, "to": 1, "amount": 100.0},
    {"from": 2, "to": 2, "amount": 200.0},
]


def test_a_broken_later_interval_beats_rising_prizes():
    # Раньше монотонность ловилась на втором интервале, до третьего.
    _rejected_with(
        "неверный интервал мест в выплатах: 4–3",
        payouts=RISING + [{"from": 4, "to": 3, "amount": 50.0}],
    )


def test_a_zero_prize_zone_beats_rising_prizes():
    _rejected_with("размер призовой зоны должен быть > 0", payouts=RISING, placesPaid=0)


def test_a_ladder_deeper_than_the_prize_zone_beats_rising_prizes():
    _rejected_with(
        "выплаты описаны до места 2, а призовых мест 1", payouts=RISING, placesPaid=1
    )


def test_a_zero_prize_zone_beats_entrants_below_players_left():
    _rejected_with("размер призовой зоны должен быть > 0", entrants=100, placesPaid=0)


def test_a_ladder_deeper_than_the_prize_zone_beats_entrants_below_players_left():
    _rejected_with(
        "выплаты описаны до места 6, а призовых мест 3", entrants=100, placesPaid=3
    )


def test_rising_prizes_still_beat_entrants_below_players_left():
    # Эта пара обязана сохраниться: обе проверки у `handstate`, и
    # монотонность по-прежнему раньше.
    _rejected_with(
        "выплата за более низкое место больше, чем за высокое",
        payouts=RISING,
        entrants=100,
    )


def test_context_without_the_average_stack_is_accepted():
    # Поле `averageStackBb` необязательно: оно нужно только, чтобы населить
    # поле вне стола, и `analyze` знает, когда именно. Валидатор
    # раздачи требовать его не вправе — на финальном столе его нет и не
    # должно быть.
    quiet = dict(CONTEXT)
    del quiet["averageStackBb"]
    context = context_from_dict(quiet)
    assert context.average_stack_bb is None
    validate_hand(context, [node_from_dict(_node())])


def test_payouts_deeper_than_the_prize_zone_are_rejected():
    # Противоречие в самих данных: выплата за место, которое турнир не
    # оплачивает. Принять его значит считать ICM с призами, которых нет, —
    # `heroEquity` завысится, и ни одна пометка об этом не скажет.
    broken = dict(CONTEXT)
    broken["placesPaid"] = 3
    with pytest.raises(
        ValueError,
        match=re.escape("выплаты описаны до места 6, а призовых мест 3"),
    ):
        validate_hand(context_from_dict(broken), [node_from_dict(_node())])


def test_prize_zone_wider_than_the_payouts_is_allowed():
    # Обратное соотношение — норма реального турнира: лобби платит за 165
    # мест, а на скриншоте видны выплаты только за первые шесть.
    validate_hand(context_from_dict(dict(CONTEXT)), [node_from_dict(_node())])


def test_a_string_instead_of_a_boolean_is_rejected():
    # `bool("false")` истинно: без гарда место, объявленное сфолдившим,
    # молча вернулось бы в раздачу, а ответ остался бы правдоподобным.
    seats = [_seat(i, 50.0, hero=(i == 7)) for i in range(8)]
    seats[0]["inHand"] = "false"
    with pytest.raises(
        ValueError, match=re.escape("поле 'inHand' должно быть true или false")
    ):
        node_from_dict(_node(seats=seats))


def test_a_number_instead_of_a_boolean_is_rejected():
    broken = dict(CONTEXT)
    broken["lateRegOpen"] = 0
    with pytest.raises(
        ValueError, match=re.escape("поле 'lateRegOpen' должно быть true или false")
    ):
        context_from_dict(broken)


def test_vpip_out_of_range_is_rejected():
    # Правило живёт в `profiles`, но проверяется валидатором: иначе отказ
    # придёт из `range_for_vpip` в самом конце `analyze`, после всего ICM.
    seats = [_seat(i, 50.0, hero=(i == 7)) for i in range(8)]
    seats[0]["vpip"] = 150.0
    with pytest.raises(ValueError, match=re.escape("VPIP вне диапазона 0..100: 150.0")):
        _validate([_node(seats=seats)])


def test_negative_vpip_sample_is_rejected():
    seats = [_seat(i, 50.0, hero=(i == 7)) for i in range(8)]
    seats[0]["vpipHands"] = -1
    with pytest.raises(
        ValueError, match=re.escape("число раздач не может быть отрицательным")
    ):
        _validate([_node(seats=seats)])


def test_a_prize_zone_of_zero_places_is_rejected():
    broken = dict(CONTEXT)
    broken["placesPaid"] = 0
    with pytest.raises(
        ValueError, match=re.escape("размер призовой зоны должен быть > 0")
    ):
        validate_hand(context_from_dict(broken), [node_from_dict(_node())])


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
    with pytest.raises(ValueError, match=re.escape("DecisionNode.hero вызывать только после")):
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


def test_assign_positions_on_six_max_uses_the_shortened_order():
    # 6-max — вторая ловушка именования: механический хвост дал бы LJ на
    # самой ранней позиции, но соглашение требует UTG (types.py).
    six_max = _node(
        seats=[
            _seat(0, 30.0),
            _seat(1, 30.0),
            _seat(2, 30.0),
            _seat(3, 30.0),
            _seat(4, 30.0),
            _seat(5, 30.0, hero=True),
        ],
        buttonSeat=2,
    )
    positions = assign_positions(node_from_dict(six_max))
    assert set(positions.values()) == set(positions_for(6))
    assert positions[2] == Position.BTN
    assert positions[5] == Position.UTG


def test_assign_positions_raises_a_named_precondition_error_without_the_button():
    # `assign_positions` вызывается только после `validate_hand`, но если это
    # предусловие нарушено, отказ обязан называть себя, а не течь наружу как
    # внутренний `StopIteration`.
    node = node_from_dict(
        _node(seats=[_seat(0, 10.0), _seat(1, 10.0, hero=True)], buttonSeat=4)
    )
    with pytest.raises(
        ValueError, match=re.escape("assign_positions вызывать только после")
    ):
        assign_positions(node)


def test_null_in_a_required_field_is_rejected_like_a_missing_field():
    # Источник — vision-модель: `null` в обязательном поле — тот же отказ,
    # что и отсутствующий ключ, не программная ошибка типа.
    raw = _node()
    raw["buttonSeat"] = None
    with pytest.raises(
        ValueError, match=re.escape("в данных нет обязательного поля 'buttonSeat'")
    ):
        node_from_dict(raw)


def test_garbage_string_in_a_numeric_field_is_rejected():
    raw = _node()
    raw["potBb"] = "n/a"
    with pytest.raises(
        ValueError, match=re.escape("поле 'potBb' должно быть числом")
    ):
        node_from_dict(raw)


def test_garbage_string_in_an_integer_field_is_rejected():
    raw = _node()
    raw["heroRank"] = "n/a"
    with pytest.raises(
        ValueError, match=re.escape("поле 'heroRank' должно быть целым числом")
    ):
        node_from_dict(raw)


# R19: те же гарантии для необязательных числовых полей (`investedBb`, `vpip`,
# `vpipHands` на месте, `level` и `raiseToBb` на узле) — тот же JSON от той же
# vision-модели, отсутствие/`null` не ошибка, а мусор в присутствующем значении
# отвергается тем же русским текстом, что и в обязательных полях.


def test_optional_seat_fields_default_when_absent():
    seats = _node()["seats"]
    del seats[4]["investedBb"]
    del seats[5]["vpip"]
    del seats[6]["vpipHands"]
    node = node_from_dict(_node(seats=seats))
    assert node.seats[4].invested_bb == 0.0
    assert node.seats[5].vpip is None
    assert node.seats[6].vpip_hands is None


def test_optional_seat_fields_default_when_null():
    seats = _node()["seats"]
    seats[4]["investedBb"] = None
    seats[5]["vpip"] = None
    seats[6]["vpipHands"] = None
    node = node_from_dict(_node(seats=seats))
    assert node.seats[4].invested_bb == 0.0
    assert node.seats[5].vpip is None
    assert node.seats[6].vpip_hands is None


def test_garbage_invested_bb_is_rejected():
    seats = _node()["seats"]
    seats[4]["investedBb"] = "n/a"
    with pytest.raises(
        ValueError, match=re.escape("поле 'investedBb' должно быть числом")
    ):
        node_from_dict(_node(seats=seats))


def test_garbage_vpip_is_rejected():
    seats = _node()["seats"]
    seats[5]["vpip"] = "n/a"
    with pytest.raises(ValueError, match=re.escape("поле 'vpip' должно быть числом")):
        node_from_dict(_node(seats=seats))


def test_garbage_vpip_hands_is_rejected():
    seats = _node()["seats"]
    seats[6]["vpipHands"] = "n/a"
    with pytest.raises(
        ValueError, match=re.escape("поле 'vpipHands' должно быть целым числом")
    ):
        node_from_dict(_node(seats=seats))


def test_level_and_raise_to_bb_default_when_absent_or_null():
    raw = _node()
    del raw["raiseToBb"]
    raw["level"] = None
    node = node_from_dict(raw)
    assert node.raise_to_bb is None
    assert node.level == 0


def test_garbage_level_is_rejected():
    raw = _node()
    raw["level"] = "n/a"
    with pytest.raises(
        ValueError, match=re.escape("поле 'level' должно быть целым числом")
    ):
        node_from_dict(raw)


def test_garbage_raise_to_bb_is_rejected():
    raw = _node()
    raw["raiseToBb"] = "n/a"
    with pytest.raises(
        ValueError, match=re.escape("поле 'raiseToBb' должно быть числом")
    ):
        node_from_dict(raw)


# R20 — три остатка, найденные и вынесенные в круге 3: явный `null` в `blinds`
# и `board` бросал английский `TypeError`; `null` в `name` тихо превращался в
# строку "None"; `heroCards` строкой разваливался на символы и отвергался с
# текстом про число карт вместо текста про форму поля. Плюс `board`/`seats`
# проверены на ту же ловушку формы.


def test_blinds_default_to_empty_dict_when_absent_or_null():
    raw = _node()
    del raw["blinds"]
    assert node_from_dict(raw).blinds == {}

    raw2 = _node()
    raw2["blinds"] = None
    assert node_from_dict(raw2).blinds == {}


def test_blinds_of_the_wrong_shape_is_rejected():
    raw = _node()
    raw["blinds"] = "sb700bb1400"
    with pytest.raises(
        ValueError, match=re.escape("поле 'blinds' должно быть объектом")
    ):
        node_from_dict(raw)


def test_board_defaults_to_empty_list_when_absent_or_null():
    raw = _node()
    del raw["board"]
    assert node_from_dict(raw).board == []

    raw2 = _node()
    raw2["board"] = None
    assert node_from_dict(raw2).board == []


def test_board_of_the_wrong_shape_is_rejected():
    raw = _node(street="flop")
    raw["board"] = "8c2s9d"
    with pytest.raises(
        ValueError, match=re.escape("поле 'board' должно быть списком")
    ):
        node_from_dict(raw)

    raw2 = _node(street="flop")
    raw2["board"] = {"flop": ["8c", "2s", "9d"]}
    with pytest.raises(
        ValueError, match=re.escape("поле 'board' должно быть списком")
    ):
        node_from_dict(raw2)


def test_name_defaults_to_empty_string_when_absent_or_null():
    # "None" в выводе Task 7 выглядел бы как настоящее имя игрока.
    seats = _node()["seats"]
    del seats[0]["name"]
    seats[1]["name"] = None
    node = node_from_dict(_node(seats=seats))
    assert node.seats[0].name == ""
    assert node.seats[1].name == ""


def test_hero_cards_as_a_bare_string_is_rejected_by_shape_not_by_count():
    raw = _node()
    raw["heroCards"] = "JhTh"
    with pytest.raises(
        ValueError, match=re.escape("поле 'heroCards' должно быть списком")
    ):
        node_from_dict(raw)


def test_seats_as_a_bare_string_is_rejected_by_shape():
    raw = _node()
    raw["seats"] = "ab"
    with pytest.raises(
        ValueError, match=re.escape("поле 'seats' должно быть списком")
    ):
        node_from_dict(raw)


def test_seats_as_a_dict_is_rejected_by_shape():
    raw = _node()
    raw["seats"] = {"0": {"seatIndex": 0}}
    with pytest.raises(
        ValueError, match=re.escape("поле 'seats' должно быть списком")
    ):
        node_from_dict(raw)


def test_payouts_as_a_bare_string_is_rejected_by_shape():
    # Тот же класс, что и у `seats`: без проверки формы строка/dict проваливаются
    # в разбор элементов и дают "нет обязательного поля 'from'" — верное
    # исключение, неверная причина.
    broken = dict(CONTEXT)
    broken["payouts"] = "1,1,1090.51"
    with pytest.raises(
        ValueError, match=re.escape("поле 'payouts' должно быть списком")
    ):
        context_from_dict(broken)


def test_payouts_as_a_dict_is_rejected_by_shape():
    broken = dict(CONTEXT)
    broken["payouts"] = {"1": {"from": 1, "to": 1, "amount": 1090.51}}
    with pytest.raises(
        ValueError, match=re.escape("поле 'payouts' должно быть списком")
    ):
        context_from_dict(broken)


def test_a_seat_that_is_not_an_object_is_rejected_by_shape():
    # Список правильной формы с испорченным элементом. Проверка формы самого
    # списка сюда не достаёт, а разбор элемента спрашивал у `None` наличие
    # ключа и получал английский `TypeError`, который `cli.main` не ловит:
    # наружу уходил трейсбек вместо ответа с ключом `error`.
    raw = _node()
    raw["seats"] = [None] + raw["seats"][1:]
    with pytest.raises(
        ValueError, match=re.escape("ожидался объект с полем 'seatIndex'")
    ):
        node_from_dict(raw)


def test_a_payout_that_is_not_an_object_is_rejected_by_shape():
    # Тот же класс, что и у места: испорчен элемент, а не список.
    broken = dict(CONTEXT)
    broken["payouts"] = [5]
    with pytest.raises(ValueError, match=re.escape("ожидался объект с полем 'from'")):
        context_from_dict(broken)


# --- ценники голов PKO (план 3, Задача 6) ------------------------------------


def _priced_seats(prices):
    """Места базового узла с ценниками: `prices` — `seatIndex -> доллары`."""
    seats = _node()["seats"]
    for seat in seats:
        seat["bountyUsd"] = prices.get(seat["seatIndex"])
    return seats


def test_a_price_defaults_to_none_when_absent_or_null():
    seats = _node()["seats"]
    seats[3]["bountyUsd"] = None
    node = node_from_dict(_node(seats=seats))
    assert node.seats[3].bounty_usd is None
    assert node.seats[4].bounty_usd is None


def test_a_price_is_read_from_the_seat():
    node = node_from_dict(_node(seats=_priced_seats({4: 2.25, 7: 1.50})))
    assert node.seats[4].bounty_usd == 2.25
    assert node.seats[7].bounty_usd == 1.50


def test_garbage_price_is_rejected():
    seats = _node()["seats"]
    seats[4]["bountyUsd"] = "n/a"
    with pytest.raises(ValueError, match=re.escape("поле 'bountyUsd' должно быть числом")):
        node_from_dict(_node(seats=seats))


def test_a_table_where_everyone_in_hand_has_a_price_passes():
    # Вне раздачи ценник не нужен: сфолдивший не выбывает и не выбивает.
    everyone_in_hand = {index: 1.50 for index in range(8)}
    _validate([_node(seats=_priced_seats(everyone_in_hand))])
    seats = _priced_seats(everyone_in_hand)
    for seat in seats:
        seat["inHand"] = seat["seatIndex"] in (4, 7)
        if not seat["inHand"]:
            seat["bountyUsd"] = None
    _validate([_node(seats=seats)])


def test_a_negative_price_is_rejected():
    everyone = {index: 1.50 for index in range(8)}
    everyone[2] = -0.5
    with pytest.raises(
        ValueError, match="^ценник на месте 2 не может быть отрицательным: -0.5$"
    ):
        _validate([_node(seats=_priced_seats(everyone))])


def test_a_price_on_a_rival_without_one_on_the_hero_is_rejected():
    everyone_but_hero = {index: 1.50 for index in range(7)}
    with pytest.raises(
        ValueError,
        match=(
            "^у соперников есть ценники голов, а ценник героя не прочитан: "
            "без него неизвестно, что герой теряет при вылете$"
        ),
    ):
        _validate([_node(seats=_priced_seats(everyone_but_hero))])


def test_a_player_in_the_hand_without_a_price_on_a_priced_table_is_rejected():
    # Без ценника соперника порог колла посчитался бы без головы — правдоподобное
    # неверное число вместо отказа.
    everyone_but_seat_4 = {index: 1.50 for index in range(8) if index != 4}
    with pytest.raises(
        ValueError,
        match=(
            "^ценник на месте 4 не прочитан, а у других мест он есть: "
            "без него неизвестно, чего стоит нокаут$"
        ),
    ):
        _validate([_node(seats=_priced_seats(everyone_but_seat_4))])


def test_the_negative_price_is_named_before_the_missing_hero_price():
    # Оба нарушения сразу: сначала мусор в прочитанном, потом пропуски.
    prices = {2: -0.5, 4: 1.50}
    with pytest.raises(ValueError, match="^ценник на месте 2 не может быть"):
        _validate([_node(seats=_priced_seats(prices))])


def test_the_missing_hero_price_is_named_before_a_missing_rival_price():
    prices = {2: 1.50}
    with pytest.raises(ValueError, match="ценник героя не прочитан"):
        _validate([_node(seats=_priced_seats(prices))])


# --- защита на баббле (план 3, Задача 7) -------------------------------------


def test_a_bubble_refund_defaults_to_none():
    assert context_from_dict(CONTEXT).bubble_refund_usd is None


def test_a_bubble_refund_is_read_from_the_context():
    protected = dict(CONTEXT)
    protected["bubbleRefundUsd"] = 6.60
    assert context_from_dict(protected).bubble_refund_usd == 6.60


def test_garbage_bubble_refund_is_rejected():
    broken = dict(CONTEXT)
    broken["bubbleRefundUsd"] = "n/a"
    with pytest.raises(
        ValueError, match=re.escape("поле 'bubbleRefundUsd' должно быть числом")
    ):
        context_from_dict(broken)


def test_a_nan_bubble_refund_is_rejected():
    broken = dict(CONTEXT)
    broken["bubbleRefundUsd"] = float("nan")
    with pytest.raises(ValueError, match="^возврат бай-ина не может быть нечислом: nan$"):
        validate_hand(context_from_dict(broken), [node_from_dict(_node())])


def test_a_zero_bubble_refund_is_accepted():
    quiet = dict(CONTEXT)
    quiet["bubbleRefundUsd"] = 0.0
    validate_hand(context_from_dict(quiet), [node_from_dict(_node())])
