"""Инварианты сквозного разбора.

Проверяется состав ответа и его согласованность с частями движка, а не
конкретные значения ICM или эквити — они предмет тестов своих модулей.
"""

import copy
import json
import re

import pytest

from poker_engine import analyze as analyze_module
from poker_engine.analyze import analyze
from poker_engine.icm_field import bubble_factor, hero_equity, risk_premium
from poker_engine.ladder import PayoutLadder
from poker_engine.potodds import required_equity
from poker_engine.types import Position


@pytest.fixture
def run_analyze(analyze_context, analyze_node):
    """Разбор плановой раздачи с правками — по умолчанию на финальном столе.

    Умолчание `playersLeft=6, heroRank=6` — поля вне стола нет: шесть мест
    и шесть живых. Тесту, которому нужно поле, передавать `playersLeft`
    явно; базовый ответ на неправленой фикстуре живёт в
    `analyze_base_result`. `context` и `node` подменяют фикстуры целиком,
    `overrides` правят узел.
    """

    def call(*, context=None, node=None, **overrides):
        base = copy.deepcopy(node if node is not None else analyze_node)
        base.update(playersLeft=6, heroRank=6)
        base.update(overrides)
        return analyze(
            context if context is not None else analyze_context,
            [base],
            trials=2_000,
            seed=11,
        )

    return call


def test_hero_position_comes_from_the_button(analyze_base_result):
    # 6-max, кнопка на месте 4: 5 — SB, 6 — BB, герой на месте 7 — UTG.
    assert analyze_base_result["heroPosition"] == Position.UTG.value


def test_villain_is_the_player_who_invested_most(analyze_base_result):
    assert analyze_base_result["villainPosition"] == Position.BTN.value


def test_villain_is_chosen_by_investment_before_stack(run_analyze, analyze_node):
    seats = copy.deepcopy(analyze_node["seats"])
    seats[0]["inHand"] = True
    seats[1]["inHand"] = True
    result = run_analyze(seats=seats)
    # Место 4 вложило 7.3 BB против нуля у мест 2 и 3, хотя его стек
    # (23.2 BB) — самый маленький из троих.
    assert result["villainPosition"] == Position.BTN.value
    assert result["effectiveStackBb"] == pytest.approx(23.2)


def test_equal_investments_are_broken_by_the_bigger_stack(run_analyze, analyze_node):
    seats = copy.deepcopy(analyze_node["seats"])
    seats[0]["inHand"] = True
    seats[0]["investedBb"] = 7.3
    result = run_analyze(seats=seats)
    # Места 2 и 4 вложили поровну; место 2 держит 94.4 BB против 23.2 BB.
    # Кнопка на месте 4, по кругу за ней 5, 6, 7, и место 2 — пятое: HJ.
    assert result["villainPosition"] == Position.HJ.value
    assert result["effectiveStackBb"] == pytest.approx(63.3)


def test_effective_stack_is_the_smaller_of_the_two(analyze_base_result):
    # Соперник на кнопке держит 23.2 BB, герой 63.3 BB.
    assert analyze_base_result["effectiveStackBb"] == pytest.approx(23.2)


def test_required_equity_matches_the_pot_odds_module(analyze_base_result):
    assert analyze_base_result["requiredEquity"] == pytest.approx(
        required_equity(9.4, 7.3)
    )


def test_no_call_means_no_required_equity(run_analyze):
    assert "requiredEquity" not in run_analyze(toCallBb=0.0, raiseToBb=None)


def test_icm_equity_is_within_the_prize_pool(analyze_base_result):
    # Поле 490 человек, фонд описан до шестого места. Эквити героя — доля
    # фонда: положительна и меньше первого приза.
    assert 0 < analyze_base_result["icm"]["heroEquity"] < 1090.51


def test_equity_shares_sum_to_one(analyze_base_result):
    equity = analyze_base_result["equity"]
    assert equity["hero"] + equity["villain"] == pytest.approx(1.0)
    # Доли не взаимозаменяемы: JhTh против верхних 25% комбинаций —
    # андердог, потому что в этих 25% сидят все старшие пары и тузы.
    assert equity["hero"] < equity["villain"]


def test_range_source_is_vpip_when_the_sample_suffices(analyze_base_result):
    assert analyze_base_result["equity"]["rangeSource"] == "vpip"


def test_small_vpip_sample_is_reported_as_default(run_analyze, analyze_node):
    seats = copy.deepcopy(analyze_node["seats"])
    seats[2]["vpipHands"] = 4  # соперник, место 4
    result = run_analyze(seats=seats)
    assert result["equity"]["rangeSource"] == "default"
    assert "vpip_default" in result["flags"]


def test_hero_equity_belongs_to_the_hero_seat(run_analyze, analyze_node):
    # ICM-эквити строго растёт со стеком при прочих равных: тот же стол,
    # но героем назначено самое крупное место (94.4 BB вместо 63.3 BB),
    # обязан дать герою большую долю призового фонда.
    folded = copy.deepcopy(analyze_node["seats"])
    for seat in folded:
        seat["inHand"] = False
    small = copy.deepcopy(folded)
    small[5]["inHand"] = True
    big = copy.deepcopy(folded)
    big[5]["isHero"] = False
    big[0]["isHero"] = True
    big[0]["inHand"] = True
    quiet = {"toCallBb": 0.0, "raiseToBb": None}
    with_small_stack = run_analyze(seats=small, **quiet)
    with_big_stack = run_analyze(seats=big, **quiet)
    assert (
        with_big_stack["icm"]["heroEquity"] > with_small_stack["icm"]["heroEquity"]
    )


def test_risk_premium_is_reported_for_a_head_to_head_spot(analyze_base_result):
    # Лесенка выплат убывает от места к месту, значит давление ICM есть:
    # проигрыш стоит дороже выигрыша, а порог эквити выше чипового.
    pressure = analyze_base_result["riskPremium"]
    assert pressure["bubbleFactor"] > 1.0
    assert pressure["riskPremium"] > 0.0


def test_prize_ladder_out_of_reach_leaves_icm_pressure_undefined(
    run_analyze, analyze_context
):
    # Финальный стол из шести, а платят только за места 20-25: они уже
    # вручены выбывшим, достижимые места ничего не стоят, деньги не на
    # кону, и давление ICM не определено. Это не ошибка ввода, а отсутствие
    # давления — разбор обязан продолжиться с пометкой.
    context = copy.deepcopy(analyze_context)
    context["payouts"] = [{"from": 20, "to": 25, "amount": 400.0}]
    result = run_analyze(context=context)
    assert result["icm"]["heroEquity"] == 0.0
    assert "riskPremium" not in result
    assert "icm_pressure_undefined" in result["flags"]
    assert "equity" in result


def test_open_late_registration_is_flagged(analyze_base_result):
    assert "late_reg_open" in analyze_base_result["flags"]


def test_mh_bias_is_always_flagged(analyze_base_result, run_analyze):
    assert "mh_bias" in analyze_base_result["flags"]
    assert "mh_bias" in run_analyze()["flags"]


def test_preflop_advice_is_flagged_as_not_computed(analyze_base_result):
    # Ф2 (Nash push/fold) ещё нет: рекомендация действия на префлопе
    # расчётом не является и обязана это сообщать.
    assert "no_pushfold" in analyze_base_result["flags"]


def test_postflop_is_not_flagged_as_missing_pushfold(analyze_context, analyze_node):
    # Финальный стол в обоих узлах: тест про улицу, а не про поле.
    preflop = copy.deepcopy(analyze_node)
    preflop.update(playersLeft=6, heroRank=6)
    flop = copy.deepcopy(preflop)
    flop.update(
        street="flop",
        board=["8c", "2s", "9d"],
        toCallBb=0.0,
        raiseToBb=None,
    )
    result = analyze(analyze_context, [preflop, flop], trials=2_000, seed=11)
    assert "no_pushfold" not in result["flags"]


def test_hand_with_no_active_opponent_skips_head_to_head_numbers(
    run_analyze, analyze_node
):
    seats = copy.deepcopy(analyze_node["seats"])
    seats[2]["inHand"] = False  # единственный соперник, место 4
    result = run_analyze(seats=seats, toCallBb=0.0, raiseToBb=None)
    assert "equity" not in result
    assert "riskPremium" not in result
    assert "icm" in result


def test_invalid_hand_is_rejected_before_any_computation(analyze_context, analyze_node):
    # Вход нарушает сразу два правила: банк нулевой (валидатор раздачи) и
    # поле больше стола без среднего стека (гард `analyze` ниже по ходу).
    # Побеждать обязан валидатор — иначе пользователь получил бы отказ про
    # поле на раздаче, которую движок и разбирать не должен был. Одного
    # нулевого банка для этого мало: тест остался бы зелёным, даже если
    # перенести `validate_hand` в самый конец `analyze`.
    context = copy.deepcopy(analyze_context)
    del context["averageStackBb"]
    broken = copy.deepcopy(analyze_node)
    broken["potBb"] = 0.0
    with pytest.raises(ValueError, match="банк должен быть > 0"):
        analyze(context, [broken], trials=2_000, seed=11)


def test_nodes_must_be_a_list(analyze_context, analyze_node):
    # Источник данных — vision-модель: одиночный узел вместо списка от неё
    # реален, и итерация по ключам словаря дала бы отказ про отсутствующее
    # поле вместо отказа про форму `nodes`.
    with pytest.raises(ValueError, match="поле 'nodes' должно быть списком"):
        analyze(analyze_context, analyze_node, trials=2_000, seed=11)


def test_context_must_be_an_object(analyze_node):
    # Скаляр вместо объекта: без гарда `_require` падал бы внутренним
    # TypeError («argument of type 'int' is not iterable»).
    with pytest.raises(ValueError, match="поле 'context' должно быть объектом"):
        analyze(5, [analyze_node], trials=2_000, seed=11)


def test_every_node_must_be_an_object(analyze_context, analyze_node):
    with pytest.raises(ValueError, match="узел решения 1 должен быть объектом"):
        analyze(analyze_context, [analyze_node, None], trials=2_000, seed=11)


def test_a_final_table_is_analysed_without_the_average_stack(
    run_analyze, analyze_context
):
    # Средний стек нужен только, чтобы населить поле: на финальном столе
    # поля нет, и разбор обязан состояться без него.
    context = copy.deepcopy(analyze_context)
    del context["averageStackBb"]
    result = run_analyze(context=context)
    assert result["icm"]["heroEquity"] > 0.0


def test_a_field_without_the_average_stack_is_rejected(
    analyze_context, analyze_node
):
    # А пока поле больше стола, отсутствие среднего стека — отказ с русским
    # текстом, а не арифметика на `None`.
    context = copy.deepcopy(analyze_context)
    del context["averageStackBb"]
    with pytest.raises(
        ValueError,
        match=re.escape(
            "нужен средний стек: игроков (496) больше, чем за столом (6), "
            "и поле нечем населить"
        ),
    ):
        analyze(context, [analyze_node], trials=2_000, seed=11)


def test_an_average_stack_below_the_table_is_rejected(run_analyze, analyze_context):
    # Стол держит 291.1 BB, живых восемь: при среднем 30 BB на двоих в поле
    # остаётся 240 − 291.1 < 0 фишек. Противоречие в данных, а не поле из
    # отрицательных стеков.
    context = copy.deepcopy(analyze_context)
    context["averageStackBb"] = 30.0
    with pytest.raises(
        ValueError,
        match="^средний стек не согласован со стеками за столом: "
        "на остальное поле не остаётся фишек$",
    ):
        run_analyze(context=context, playersLeft=8, heroRank=8)


def test_an_average_stack_that_leaves_the_field_no_chips_is_rejected(
    run_analyze, analyze_context, analyze_node
):
    # Граница: средний стек ровно такой, что вся фишка турнира — за столом.
    # Поле из двоих без фишек — то же противоречие, что и в минус. Средний
    # стек — сумма стола, делённая на восемь: деление и умножение на
    # степень двойки точны, и остаток поля выходит ровно нулём.
    context = copy.deepcopy(analyze_context)
    context["averageStackBb"] = sum(seat["stackBb"] for seat in analyze_node["seats"]) / 8
    with pytest.raises(ValueError, match="^средний стек не согласован"):
        run_analyze(context=context, playersLeft=8, heroRank=8)


def test_a_broken_vpip_is_rejected_before_any_computation(
    analyze_context, analyze_node
):
    # Тот же порядок, что и у остального валидатора: бейдж соперника
    # проверяется до расчёта. Среднего стека здесь нет, и если бы VPIP
    # проверялся только в `range_for_vpip` (последний шаг `analyze`),
    # победило бы сообщение про поле.
    context = copy.deepcopy(analyze_context)
    del context["averageStackBb"]
    seats = copy.deepcopy(analyze_node["seats"])
    seats[2]["vpip"] = 150.0  # соперник, место 4
    node = copy.deepcopy(analyze_node)
    node["seats"] = seats
    with pytest.raises(ValueError, match=re.escape("VPIP вне диапазона 0..100")):
        analyze(context, [node], trials=2_000, seed=11)


def test_a_prize_zone_of_zero_places_is_rejected(analyze_context, analyze_node):
    # `placesPaid` виден в ответе только через пометку `ladder_incomplete`,
    # и мусорное значение исказило бы её молча — вместе с единственным
    # сообщением о том, что `heroEquity` занижено.
    context = copy.deepcopy(analyze_context)
    context["placesPaid"] = 0
    with pytest.raises(ValueError, match="размер призовой зоны должен быть > 0"):
        analyze(context, [analyze_node], trials=2_000, seed=11)


def test_all_in_opponent_is_rejected_before_the_icm(run_analyze, analyze_node):
    # Известное ограничение, а не дефект разбора (спека плана 3, §11.1):
    # место с нулевым стеком проходит `validate_hand`, но модель ICM не
    # знает, куда деть вложенное выбывающим. Тест пинит, что отказ остаётся
    # русским и адресным и приходит раньше `icm_field`, у которого свой
    # текст про стек называл бы позицию в списке.
    #
    # Места нарочно перенумерованы с двойки: `validate_hand` требует от
    # `seatIndex` только уникальности, а на скриншоте номера идут с
    # пропусками, когда за столом есть пустые места. Здесь виноватый стек
    # соперника стоит в списке третьим (позиция 2), а называться обязано
    # место 6.
    seats = copy.deepcopy(analyze_node["seats"])
    for seat in seats:
        seat["seatIndex"] += 2
    seats[2]["stackBb"] = 0.0
    with pytest.raises(ValueError, match="^стек на месте 6 должен быть > 0"):
        run_analyze(seats=seats, buttonSeat=6)


def test_the_answer_is_the_field_model_of_the_whole_tournament(
    analyze_base_result, analyze_node
):
    # Согласованность с `icm_field`, а не число из памяти: стол по номерам
    # мест, герой — место 7 (позиция 5), соперник — место 4 (позиция 2),
    # поле — 490 игроков, делящих фишки турнира без стола поровну.
    table = [seat["stackBb"] for seat in analyze_node["seats"]]
    field_count = 496 - len(table)
    field_stack = (496 * 50.5 - sum(table)) / field_count
    ladder = PayoutLadder(
        [(1, 1, 1090.51), (2, 2, 840.37), (3, 3, 648.01), (4, 6, 400.0)],
        places_paid=165,
    )
    args = (table, field_count, field_stack, ladder, 5)
    assert analyze_base_result["icm"]["heroEquity"] == pytest.approx(hero_equity(*args))
    pressure = analyze_base_result["riskPremium"]
    assert pressure["riskPremium"] == pytest.approx(risk_premium(*args, 2))
    assert pressure["bubbleFactor"] == pytest.approx(bubble_factor(*args, 2))


def test_the_answer_no_longer_claims_a_truncated_ladder(analyze_base_result):
    # Лесенка берётся по настоящему месту целиком, поле не сворачивается:
    # обеим пометкам больше нечего сообщать.
    assert "ladder_truncated" not in analyze_base_result["flags"]
    assert "reduced_field" not in analyze_base_result["flags"]


def test_a_homogeneous_field_is_flagged(analyze_base_result):
    assert "field_homogeneous" in analyze_base_result["flags"]


def test_a_final_table_has_no_field_and_is_not_flagged(run_analyze):
    # Умолчание фикстуры — playersLeft=6 при шести местах: поля вне стола
    # нет, допущения об однородности тоже, и пометка соврала бы.
    result = run_analyze()
    assert "field_homogeneous" not in result["flags"]
    assert result["icm"]["playersLeft"] == result["icm"]["tableSeats"] == 6


def test_a_ladder_shorter_than_places_paid_is_flagged(analyze_base_result):
    # Фикстура описывает места 1-6 при placesPaid=165.
    assert "ladder_incomplete" in analyze_base_result["flags"]


def test_a_complete_ladder_is_not_flagged(run_analyze, analyze_context):
    # Те же выплаты, но призовая зона ровно по ним: пометка сравнивает
    # покрытые места с `placesPaid`, а не с чем-то ещё.
    context = copy.deepcopy(analyze_context)
    context["placesPaid"] = 6
    result = run_analyze(context=context)
    assert "ladder_incomplete" not in result["flags"]


def test_an_incomplete_ladder_out_of_reach_is_flagged_but_costs_nothing(
    run_analyze, analyze_context
):
    # Финальный стол из шести, выплаты за места 1-6, призовая зона 165:
    # места 7-165 уже вручены выбывшим. Пометка — про вход (лобби снято не
    # целиком) и стоит, но число от неё не страдает: то же эквити, что и
    # при призовой зоне ровно по выплатам.
    complete = copy.deepcopy(analyze_context)
    complete["placesPaid"] = 6
    flagged = run_analyze()
    exact = run_analyze(context=complete)
    assert "ladder_incomplete" in flagged["flags"]
    assert flagged["icm"]["heroEquity"] == exact["icm"]["heroEquity"]


def test_a_deeper_ladder_is_computed_instead_of_refused(run_analyze, analyze_context):
    # Лесенка на все 165 мест при поле из 490: раньше это падало с
    # «перебор Malmuth-Harville такого размера не считается».
    context = copy.deepcopy(analyze_context)
    context["payouts"] = [
        {"from": 1, "to": 1, "amount": 1090.51},
        {"from": 2, "to": 2, "amount": 840.37},
        {"from": 3, "to": 3, "amount": 648.01},
        {"from": 4, "to": 6, "amount": 400.0},
        {"from": 7, "to": 12, "amount": 250.0},
        {"from": 13, "to": 40, "amount": 120.0},
        {"from": 41, "to": 165, "amount": 60.0},
    ]
    result = run_analyze(context=context, playersLeft=496, heroRank=90)
    assert result["icm"]["heroEquity"] > 0.0
    assert "ladder_incomplete" not in result["flags"]
    assert "riskPremium" in result


def test_the_field_size_reported_is_the_whole_tournament(analyze_base_result):
    assert analyze_base_result["icm"]["playersLeft"] == 496
    assert analyze_base_result["icm"]["tableSeats"] == 6


def test_only_undefined_pressure_is_turned_into_a_flag(run_analyze, monkeypatch):
    # Пометка `icm_pressure_undefined` — про свойство лесенки. Любой другой
    # отказ из `risk_premium` — ошибка вызова, и прятать её под пометкой
    # нельзя: разбор обязан упасть с ней (долг D4). Из настоящего входа
    # такой отказ недостижим, поэтому он подложен.
    def broken(*args):
        raise ValueError("чужой отказ")

    monkeypatch.setattr(analyze_module, "risk_premium", broken)
    with pytest.raises(ValueError, match="^чужой отказ$"):
        run_analyze()


def test_result_is_json_serialisable(analyze_base_result):
    json.dumps(analyze_base_result)


# --- PKO: ценники голов со стола (Задача 6) ---------------------------------
#
# На финальном столе `run_analyze` живы шесть мест фикстуры: 2 (94.4), 3 (35.3),
# 4 (23.2, вложил 7.3 — соперник), 5 (39.2), 6 (35.7), 7 (63.3, герой, вложил
# 1.0). Призы мест 1-6 по лесенке фикстуры — 1090.51 + 840.37 + 648.01 +
# 3 × 400 = 3778.89.

FINAL_TABLE_PRIZES = 1090.51 + 840.37 + 648.01 + 3 * 400.0


def bounty_node(base, prices, **stacks):
    """Узел с ценниками голов.

    `prices` — словарь `seatIndex -> цена в долларах`, передаётся позиционно:
    номера мест целые, а через `**kwargs` целые ключи не проходят. Место без
    цены в словаре остаётся без ценника. `stacks` — правка стеков вида
    `seat4=5.0`.
    """
    node = copy.deepcopy(base)
    node["seats"] = [
        {**seat, "bountyUsd": prices.get(seat["seatIndex"])}
        for seat in node["seats"]
    ]
    for key, stack in stacks.items():
        index = int(key.removeprefix("seat"))
        for seat in node["seats"]:
            if seat["seatIndex"] == index:
                seat["stackBb"] = stack
    return node


# Все места стола с ценником: соперник и герой — по аргументам, прочие по 1.50.
def priced(villain, hero):
    prices = {2: 1.50, 3: 1.50, 5: 1.50, 6: 1.50}
    prices.update({4: villain, 7: hero})
    return prices


def test_a_table_without_prices_is_not_a_pko(analyze_base_result):
    assert "pko" not in analyze_base_result["flags"]
    assert "bounty" not in analyze_base_result


def test_a_classic_table_never_touches_the_bounty_module(run_analyze, monkeypatch):
    # Инвариант 11 спеки: без единого ценника ни одна функция `bounty.py`
    # при разборе не вызывается.
    def forbidden(*args, **kwargs):
        raise AssertionError("классика дошла до bounty.py")

    for name in ("knockout_cash", "own_bounty_growth", "required_equity_with_bounty"):
        monkeypatch.setattr(analyze_module, name, forbidden)
    result = run_analyze()
    assert "bounty" not in result


def test_prices_on_the_table_make_it_a_pko(run_analyze, analyze_node):
    result = run_analyze(node=bounty_node(analyze_node, priced(1.50, 1.50)))
    assert "pko" in result["flags"]


def test_a_pko_without_a_villain_is_still_a_pko(run_analyze, analyze_node):
    # Все сфолдили до героя: головы на кону нет, блока нет, но турнир — PKO,
    # и пометка про турнир остаётся правдой (спека §5.1).
    node = bounty_node(analyze_node, {7: 1.50})
    for seat in node["seats"]:
        seat["inHand"] = seat["isHero"]
    result = run_analyze(node=node)
    assert "pko" in result["flags"]
    assert "bounty" not in result


def test_the_cash_for_a_knockout_is_the_price_shown(run_analyze, analyze_node):
    result = run_analyze(node=bounty_node(analyze_node, priced(2.25, 1.50)))
    assert result["bounty"]["villainPriceUsd"] == pytest.approx(2.25)
    assert result["bounty"]["knockoutCashUsd"] == pytest.approx(2.25)
    assert result["bounty"]["ownPriceGrowthUsd"] == pytest.approx(1.125)


def test_the_hero_own_price_is_reported_as_at_risk(run_analyze, analyze_node):
    result = run_analyze(node=bounty_node(analyze_node, priced(1.50, 3.00)))
    assert result["bounty"]["heroPriceAtRiskUsd"] == pytest.approx(3.00)


def test_a_bb_costs_the_money_still_in_play_over_the_chips_in_play(
    run_analyze, analyze_node, analyze_context
):
    # Лесенка на все 165 мест, но живы шестеро: места 7-165 уже вручены
    # выбывшим, и в цене большого блайнда их призов нет.
    context = copy.deepcopy(analyze_context)
    context["payouts"].append({"from": 7, "to": 165, "amount": 10.0})
    result = run_analyze(context=context, node=bounty_node(analyze_node, priced(1.50, 1.50)))
    table = 94.4 + 35.3 + 23.2 + 39.2 + 35.7 + 63.3
    assert result["bounty"]["bbValueUsd"] == pytest.approx(FINAL_TABLE_PRIZES / table)


def test_a_bb_costs_the_prize_pool_over_the_tournament_chips_with_a_field(
    run_analyze, analyze_node
):
    # Поле из 490: фишек в игре — стол плюс поле, то есть 496 × средний стек.
    result = run_analyze(
        node=bounty_node(analyze_node, priced(1.50, 1.50)), playersLeft=496, heroRank=90
    )
    assert result["bounty"]["bbValueUsd"] == pytest.approx(
        FINAL_TABLE_PRIZES / (496 * 50.5)
    )


def test_a_bounty_lowers_the_required_equity(run_analyze, analyze_node):
    # У соперника за спиной 5.0 BB — меньше колла 7.3: колл героя его
    # накрывает, нокаут возможен в этой раздаче. Голова идёт в банк
    # наличными, переведёнными в большие блайнды.
    result = run_analyze(node=bounty_node(analyze_node, priced(5.00, 1.50), seat4=5.0))
    block = result["bounty"]
    table = 94.4 + 35.3 + 5.0 + 39.2 + 35.7 + 63.3
    assert block["bbValueUsd"] == pytest.approx(FINAL_TABLE_PRIZES / table)
    extra = block["knockoutCashUsd"] / block["bbValueUsd"]
    assert block["requiredEquityWithBounty"] == pytest.approx(7.3 / (9.4 + extra + 7.3))
    assert block["requiredEquityWithBounty"] < result["requiredEquity"]


def test_no_credit_for_a_head_the_call_does_not_take(run_analyze, analyze_node):
    # У соперника за спиной 23.2 BB, колл 7.3 его не накрывает — головы в
    # этой раздаче на кону нет, порог обычный.
    result = run_analyze(node=bounty_node(analyze_node, priced(5.00, 1.50)))
    assert result["bounty"]["requiredEquityWithBounty"] == result["requiredEquity"]


def test_no_credit_when_the_hero_cannot_cover_the_villain(run_analyze, analyze_node):
    # Колл накрывает остаток соперника (5.0 < 7.3), но у героя 8.0 + 1.0
    # вложенных против 5.0 + 7.3 у соперника: выбить его герой не может,
    # голову не засчитывать. Стек героя больше остатка соперника — сравнивать
    # надо с вложенным, иначе голова засчиталась бы.
    node = bounty_node(analyze_node, priced(5.00, 1.50), seat4=5.0, seat7=8.0)
    result = run_analyze(node=node)
    assert result["bounty"]["requiredEquityWithBounty"] == result["requiredEquity"]


def test_no_threshold_when_there_is_nothing_to_call(run_analyze, analyze_node):
    # Колла нет — нет и порога, ни обычного, ни с головой; остальной блок на месте.
    node = bounty_node(analyze_node, priced(5.00, 1.50), seat4=5.0)
    result = run_analyze(node=node, toCallBb=0.0)
    assert "requiredEquity" not in result
    assert "requiredEquityWithBounty" not in result["bounty"]
    assert "bbValueUsd" in result["bounty"]


def test_no_bb_value_when_no_prize_is_left_in_play(
    run_analyze, analyze_node, analyze_context
):
    # Лобби снято только с 7-го места, живы шестеро: денег, которые ещё
    # разыгрываются, лесенка не знает. Цену блайнда посчитать нечем — ключей
    # нет, а не ноль и не отказ всего разбора.
    context = copy.deepcopy(analyze_context)
    context["payouts"] = [{"from": 7, "to": 165, "amount": 10.0}]
    result = run_analyze(
        context=context, node=bounty_node(analyze_node, priced(5.00, 1.50), seat4=5.0)
    )
    assert "ladder_incomplete" in result["flags"]
    assert result["bounty"]["knockoutCashUsd"] == pytest.approx(5.00)
    assert "bbValueUsd" not in result["bounty"]
    assert "requiredEquityWithBounty" not in result["bounty"]


def test_a_price_on_the_villain_but_not_on_the_hero_is_rejected(
    run_analyze, analyze_node
):
    with pytest.raises(ValueError, match="ценник героя не прочитан"):
        run_analyze(node=bounty_node(analyze_node, {4: 1.50}))


def test_a_negative_price_is_rejected(run_analyze, analyze_node):
    with pytest.raises(
        ValueError, match="^ценник на месте 4 не может быть отрицательным: -1.0$"
    ):
        run_analyze(node=bounty_node(analyze_node, priced(-1.0, 1.50)))


def test_the_two_halves_of_equity_stay_separate(run_analyze, analyze_node):
    """Инварианты 10 и «раздельно» спеки (§5.3, §8.2).

    Эквити в лесенке не зависит от ценников голов ни в одну сторону: это
    два разных куска денег, и складывать их в одно число запрещено. При
    выросших вдвое ценниках `icm` обязано остаться тем же, а меняться
    обязан только блок `bounty`. Уже взятых баунти в контракте нет: ответ
    зависит только от того, что висит на экране сейчас.
    """
    cheap = run_analyze(node=bounty_node(analyze_node, priced(1.50, 1.50)))
    rich = run_analyze(node=bounty_node(analyze_node, priced(3.00, 3.00)))
    assert rich["icm"] == cheap["icm"]
    assert rich["bounty"]["knockoutCashUsd"] > cheap["bounty"]["knockoutCashUsd"]
