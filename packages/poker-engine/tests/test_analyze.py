"""Инварианты сквозного разбора.

Проверяется состав ответа и его согласованность с частями движка, а не
конкретные значения ICM или эквити — они предмет тестов своих модулей.
"""

import copy
import json
import math

import pytest

from poker_engine.analyze import MAX_FIELD_NODES, MAX_ICM_PREFIXES, analyze
from poker_engine.potodds import required_equity
from poker_engine.types import Position


@pytest.fixture
def run_analyze(analyze_context, analyze_node):
    def call(**overrides):
        node = copy.deepcopy(analyze_node)
        node.update(overrides)
        return analyze(analyze_context, [node], trials=2_000, seed=11)

    return call


def test_hero_position_comes_from_the_button(analyze_base_result):
    assert analyze_base_result["heroPosition"] == Position.UTG1.value


def test_villain_is_the_player_who_invested_most(analyze_base_result):
    assert analyze_base_result["villainPosition"] == Position.BTN.value


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
    assert 0 < analyze_base_result["icm"]["heroEquity"] < 1090.51


def test_field_is_reduced_not_taken_whole(analyze_base_result):
    # 496 игроков против 8 мест: стол сохраняется поимённо, остальное поле
    # занимает все оставшиеся узлы до предела, то есть ровно 8 + 7 = 15.
    assert analyze_base_result["icm"]["fieldNodes"] == 15


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


def test_risk_premium_is_reported_for_a_head_to_head_spot(analyze_base_result):
    # Лесенка выплат убывает от места к месту, значит давление ICM есть:
    # проигрыш стоит дороже выигрыша, а порог эквити выше чипового.
    pressure = analyze_base_result["riskPremium"]
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


def test_open_late_registration_is_flagged(analyze_base_result):
    assert "late_reg_open" in analyze_base_result["flags"]


def test_reduced_field_and_mh_bias_are_always_flagged(analyze_base_result):
    flags = analyze_base_result["flags"]
    assert "reduced_field" in flags
    assert "mh_bias" in flags


def test_field_equal_to_the_table_is_not_flagged_as_reduced(run_analyze):
    # Финальный стол: 8 мест и 8 оставшихся игроков — схлопывать нечего,
    # ICM считается по полю целиком и приближением не является.
    result = run_analyze(playersLeft=8, heroRank=8)
    assert "reduced_field" not in result["flags"]
    assert result["icm"]["fieldNodes"] == 8


def test_preflop_advice_is_flagged_as_not_computed(analyze_base_result):
    # Ф2 (Nash push/fold) ещё нет: рекомендация действия на префлопе
    # расчётом не является и обязана это сообщать.
    assert "no_pushfold" in analyze_base_result["flags"]


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


def test_context_must_be_an_object(analyze_node):
    # Скаляр вместо объекта: без гарда `_require` падал бы внутренним
    # TypeError («argument of type 'int' is not iterable»).
    with pytest.raises(ValueError, match="поле 'context' должно быть объектом"):
        analyze(5, [analyze_node], trials=2_000, seed=11)


def test_every_node_must_be_an_object(analyze_context, analyze_node):
    with pytest.raises(ValueError, match="узел решения 1 должен быть объектом"):
        analyze(analyze_context, [analyze_node, None], trials=2_000, seed=11)


def test_prizes_deeper_than_the_field_are_flagged_as_truncated(
    analyze_context, analyze_node
):
    # Выплаты доходят до 25-го места, а в модели 15 узлов: призы за места
    # с 16-го по 25-е в расчёт не попали, и ICM-эквити героя занижено.
    #
    # Лесенка нарочно с разрывом (места 7..19 не оплачены): сплошная
    # лесенка до 25-го места дала бы пятнадцать ненулевых мест из
    # пятнадцати, а Malmuth-Harville перебирает упорядоченные префиксы
    # до последней ненулевой выплаты — 15! порядков, то есть тест,
    # который не кончается. Это ровно та цена, из-за которой лесенка и
    # обрезается, и ровно то, о чём обязана сообщать пометка.
    context = copy.deepcopy(analyze_context)
    context["payouts"] = context["payouts"] + [
        {"from": 20, "to": 25, "amount": 100.0}
    ]
    result = analyze(context, [analyze_node], trials=2_000, seed=11)
    assert "ladder_truncated" in result["flags"]


def test_a_dense_prize_ladder_is_rejected_instead_of_hanging(
    analyze_context, analyze_node
):
    # Реальный GG MTT: оплачиваемых мест больше, чем узлов поля, поэтому
    # внутри свёрнутого поля оплачены все пятнадцать. Malmuth-Harville
    # перебирает 15! порядков — это не «долго», это никогда, и отказ
    # обязан прийти до первого расчёта. Тест поэтому мгновенный: гард
    # стоит перед `icm_equities`, считать здесь нечего.
    context = copy.deepcopy(analyze_context)
    context["payouts"] = [{"from": 1, "to": 165, "amount": 400.0}]
    with pytest.raises(
        ValueError, match="оплачиваемых мест внутри свёрнутого поля 15 из 15"
    ):
        analyze(context, [analyze_node], trials=2_000, seed=11)


def test_a_mid_sized_field_beyond_the_budget_is_also_rejected(
    analyze_context, analyze_node
):
    # Поле из двенадцати узлов и восемь оплачиваемых мест — 19.9 млн
    # префиксов: меньше, чем 15!, но всё равно за потолком. Порог
    # проверяется по стоимости перебора, а не по числу мест самому по
    # себе: восемь мест из восьми стоили бы 40 320 и считались бы.
    context = copy.deepcopy(analyze_context)
    context["payouts"] = context["payouts"][:3] + [
        {"from": 4, "to": 8, "amount": 400.0}
    ]
    node = copy.deepcopy(analyze_node)
    node.update(playersLeft=12, heroRank=12)
    with pytest.raises(
        ValueError, match="оплачиваемых мест внутри свёрнутого поля 8 из 12"
    ):
        analyze(context, [node], trials=2_000, seed=11)


def test_the_ladder_at_the_budget_edge_is_still_computed(analyze_base_result):
    # Плановая фикстура платит за шесть мест из пятнадцати — 3.6 млн
    # префиксов против потолка в 4 млн, последняя переносимая глубина.
    # Разбор обязан состояться, а не быть отвергнут заодно с плотными.
    assert analyze_base_result["icm"]["fieldNodes"] == 15
    assert analyze_base_result["icm"]["heroEquity"] > 0


def test_the_prefix_budget_is_never_hit_exactly():
    # Гард сравнивает стоимость перебора строгим `>`, и `>` отличается от
    # `>=` ровно на одном входе — дающем ровно `MAX_ICM_PREFIXES`
    # префиксов. Такого входа не существует: число префиксов — падающий
    # факториал `perm(узлы, места)` при узлах не больше `MAX_FIELD_NODES`,
    # и значения 4 000 000 он не принимает (ближайшее снизу — 3 991 680
    # при двенадцати узлах и семи местах). Проверять сам выбор знака
    # поэтому нечем, и мутация `>` → `>=` тестами не убивается.
    #
    # Тест пинит причину этой безразличности, а не сам знак: подвиньте
    # константу на достижимое число — например на 3 603 600, ровно
    # стоимость плановой фикстуры, — и граница станет значимой, а разбор,
    # который сегодня считается, начнёт молча отвергаться.
    attainable = {
        math.perm(nodes, paid)
        for nodes in range(1, MAX_FIELD_NODES + 1)
        for paid in range(nodes + 1)
    }
    assert MAX_ICM_PREFIXES not in attainable


def test_a_prize_range_crossing_the_field_edge_is_flagged(
    analyze_context, analyze_node
):
    # Финальный стол: 8 мест и 8 узлов, свёртки нет. Интервал выплат
    # 6..12 начинается внутри поля, а кончается за ним — обрезана часть
    # лесенки, и это тот же случай, что и целиком выпавший приз.
    context = copy.deepcopy(analyze_context)
    context["payouts"] = context["payouts"][:3] + [
        {"from": 4, "to": 5, "amount": 400.0},
        {"from": 6, "to": 12, "amount": 200.0},
    ]
    node = copy.deepcopy(analyze_node)
    node.update(playersLeft=8, heroRank=8)
    result = analyze(context, [node], trials=2_000, seed=11)
    assert "ladder_truncated" in result["flags"]


def test_a_prize_range_ending_at_the_field_edge_is_not_truncated(
    analyze_context, analyze_node
):
    # Финальный стол: 8 мест, 8 узлов, и последняя оплачиваемая позиция —
    # ровно восьмая. Граница включительная: лесенка помещается в модель
    # целиком, обрезать нечего.
    context = copy.deepcopy(analyze_context)
    context["payouts"] = context["payouts"][:3] + [
        {"from": 4, "to": 8, "amount": 400.0}
    ]
    node = copy.deepcopy(analyze_node)
    node.update(playersLeft=8, heroRank=8)
    result = analyze(context, [node], trials=2_000, seed=11)
    assert "ladder_truncated" not in result["flags"]


def test_ladder_inside_the_field_is_not_flagged_as_truncated(analyze_base_result):
    # В плановой фикстуре призы кончаются на шестом месте из пятнадцати:
    # обрезать нечего, и пометка соврала бы.
    assert "ladder_truncated" not in analyze_base_result["flags"]


def test_all_in_opponent_is_rejected_by_the_field_reduction(run_analyze, analyze_node):
    # Известное ограничение, а не дефект разбора: место с нулевым стеком
    # проходит `validate_hand`, но `reduce_field` требует положительных
    # стеков. Как вернуть в ICM уже вложенные выбывающим фишки — решение
    # о модели, оно этой задачей не принимается; тест пинит, что отказ
    # остаётся русским и адресным.
    seats = copy.deepcopy(analyze_node["seats"])
    seats[4]["stackBb"] = 0.0
    with pytest.raises(ValueError, match="стек на месте 4 должен быть > 0"):
        run_analyze(seats=seats)


def test_result_is_json_serialisable(analyze_base_result):
    json.dumps(analyze_base_result)
