"""Инварианты сквозного разбора.

Проверяется состав ответа и его согласованность с частями движка, а не
конкретные значения ICM или эквити — они предмет тестов своих модулей.
"""

import copy
import json

import pytest

from poker_engine.analyze import analyze
from poker_engine.potodds import required_equity
from poker_engine.types import Position


@pytest.fixture
def run_analyze(analyze_context, analyze_node):
    def call(**overrides):
        node = copy.deepcopy(analyze_node)
        node.update(overrides)
        return analyze(analyze_context, [node], trials=2_000, seed=11)

    return call


def test_hero_position_comes_from_the_button(run_analyze):
    assert run_analyze()["heroPosition"] == Position.UTG1.value


def test_villain_is_the_player_who_invested_most(run_analyze):
    assert run_analyze()["villainPosition"] == Position.BTN.value


def test_villain_is_chosen_by_investment_before_stack(run_analyze, analyze_node):
    seats = copy.deepcopy(analyze_node["seats"])
    seats[0]["inHand"] = True
    seats[1]["inHand"] = True
    result = run_analyze(seats=seats)
    # Место 4 вложило 7.3 BB против нуля у мест 0 и 1, хотя его стек
    # (23.2 BB) — самый маленький из троих.
    assert result["villainPosition"] == Position.BTN.value
    assert result["effectiveStackBb"] == pytest.approx(23.2)


def test_equal_investments_are_broken_by_the_bigger_stack(run_analyze, analyze_node):
    seats = copy.deepcopy(analyze_node["seats"])
    seats[0]["inHand"] = True
    seats[0]["investedBb"] = 7.3
    result = run_analyze(seats=seats)
    # Места 0 и 4 вложили поровну; место 0 держит 72.2 BB против 23.2 BB.
    # Кнопка на месте 4, значит место 0 — четвёртое по кругу после неё, MP.
    assert result["villainPosition"] == Position.MP.value
    assert result["effectiveStackBb"] == pytest.approx(63.3)


def test_effective_stack_is_the_smaller_of_the_two(run_analyze):
    # Соперник на кнопке держит 23.2 BB, герой 63.3 BB.
    assert run_analyze()["effectiveStackBb"] == pytest.approx(23.2)


def test_required_equity_matches_the_pot_odds_module(run_analyze):
    result = run_analyze()
    assert result["requiredEquity"] == pytest.approx(required_equity(9.4, 7.3))


def test_no_call_means_no_required_equity(run_analyze):
    assert "requiredEquity" not in run_analyze(toCallBb=0.0, raiseToBb=None)


def test_icm_equity_is_within_the_prize_pool(run_analyze):
    assert 0 < run_analyze()["icm"]["heroEquity"] < 1090.51


def test_field_is_reduced_not_taken_whole(run_analyze):
    # 496 игроков против 8 мест: стол сохраняется поимённо, остальное поле
    # занимает все оставшиеся узлы до предела, то есть ровно 8 + 7 = 15.
    assert run_analyze()["icm"]["fieldNodes"] == 15


def test_equity_shares_sum_to_one(run_analyze):
    equity = run_analyze()["equity"]
    assert equity["hero"] + equity["villain"] == pytest.approx(1.0)
    # Доли не взаимозаменяемы: JhTh против верхних 25% комбинаций —
    # андердог, потому что в этих 25% сидят все старшие пары и тузы.
    assert equity["hero"] < equity["villain"]


def test_range_source_is_vpip_when_the_sample_suffices(run_analyze):
    assert run_analyze()["equity"]["rangeSource"] == "vpip"


def test_small_vpip_sample_is_reported_as_default(run_analyze, analyze_node):
    seats = copy.deepcopy(analyze_node["seats"])
    seats[4]["vpipHands"] = 4
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
    small[7]["inHand"] = True
    big = copy.deepcopy(folded)
    big[7]["isHero"] = False
    big[2]["isHero"] = True
    big[2]["inHand"] = True
    quiet = {"toCallBb": 0.0, "raiseToBb": None}
    with_small_stack = run_analyze(seats=small, **quiet)
    with_big_stack = run_analyze(seats=big, **quiet)
    assert (
        with_big_stack["icm"]["heroEquity"] > with_small_stack["icm"]["heroEquity"]
    )


def test_risk_premium_is_reported_for_a_head_to_head_spot(run_analyze):
    # Лесенка выплат убывает от места к месту, значит давление ICM есть:
    # проигрыш стоит дороже выигрыша, а порог эквити выше чипового.
    pressure = run_analyze()["riskPremium"]
    assert pressure["bubbleFactor"] > 1.0
    assert pressure["riskPremium"] > 0.0


def test_prize_ladder_out_of_reach_leaves_icm_pressure_undefined(
    analyze_context, analyze_node
):
    # Все выплаты глубже свёрнутого поля: лесенка внутри расчёта нулевая,
    # деньги не на кону, и давление ICM не определено. Это не ошибка ввода,
    # а отсутствие давления — разбор обязан продолжиться с пометкой.
    context = copy.deepcopy(analyze_context)
    context["payouts"] = [{"from": 20, "to": 25, "amount": 400.0}]
    result = analyze(context, [analyze_node], trials=2_000, seed=11)
    assert "riskPremium" not in result
    assert "icm_pressure_undefined" in result["flags"]
    assert "equity" in result


def test_open_late_registration_is_flagged(run_analyze):
    assert "late_reg_open" in run_analyze()["flags"]


def test_reduced_field_and_mh_bias_are_always_flagged(run_analyze):
    flags = run_analyze()["flags"]
    assert "reduced_field" in flags
    assert "mh_bias" in flags


def test_field_equal_to_the_table_is_not_flagged_as_reduced(run_analyze):
    # Финальный стол: 8 мест и 8 оставшихся игроков — схлопывать нечего,
    # ICM считается по полю целиком и приближением не является.
    result = run_analyze(playersLeft=8, heroRank=8)
    assert "reduced_field" not in result["flags"]
    assert result["icm"]["fieldNodes"] == 8


def test_preflop_advice_is_flagged_as_not_computed(run_analyze):
    # Ф2 (Nash push/fold) ещё нет: рекомендация действия на префлопе
    # расчётом не является и обязана это сообщать.
    assert "no_pushfold" in run_analyze()["flags"]


def test_postflop_is_not_flagged_as_missing_pushfold(analyze_context, analyze_node):
    flop = copy.deepcopy(analyze_node)
    flop.update(
        street="flop",
        board=["8c", "2s", "9d"],
        toCallBb=0.0,
        raiseToBb=None,
    )
    result = analyze(analyze_context, [analyze_node, flop], trials=2_000, seed=11)
    assert "no_pushfold" not in result["flags"]


def test_hand_with_no_active_opponent_skips_head_to_head_numbers(
    run_analyze, analyze_node
):
    seats = copy.deepcopy(analyze_node["seats"])
    seats[4]["inHand"] = False
    result = run_analyze(seats=seats, toCallBb=0.0, raiseToBb=None)
    assert "equity" not in result
    assert "riskPremium" not in result
    assert "icm" in result


def test_invalid_hand_is_rejected_before_any_computation(analyze_context, analyze_node):
    broken = copy.deepcopy(analyze_node)
    broken["potBb"] = 0.0
    with pytest.raises(ValueError, match="банк должен быть > 0"):
        analyze(analyze_context, [broken], trials=2_000, seed=11)


def test_nodes_must_be_a_list(analyze_context, analyze_node):
    # Источник данных — vision-модель: одиночный узел вместо списка от неё
    # реален, и итерация по ключам словаря дала бы отказ про отсутствующее
    # поле вместо отказа про форму `nodes`.
    with pytest.raises(ValueError, match="поле 'nodes' должно быть списком"):
        analyze(analyze_context, analyze_node, trials=2_000, seed=11)


def test_result_is_json_serialisable(run_analyze):
    json.dumps(run_analyze())
