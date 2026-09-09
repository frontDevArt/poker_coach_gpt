import pytest

from poker_engine.icm import bubble_factor, icm_equities, risk_premium


def test_two_players_analytic():
    # P(1-й) = 75/100. EV1 = 0.75*70 + 0.25*30 = 60. EV2 = 40.
    result = icm_equities(stacks=[75, 25], payouts=[70, 30])
    assert result == pytest.approx([60.0, 40.0])


def test_three_players_analytic():
    result = icm_equities(stacks=[50, 30, 20], payouts=[50, 30, 20])
    assert result == pytest.approx(
        [38.392857142857146, 32.75, 28.857142857142854]
    )


def test_sum_of_equities_equals_prize_pool():
    payouts = [500, 300, 200, 100]
    result = icm_equities(stacks=[120, 45, 80, 15], payouts=payouts)
    assert sum(result) == pytest.approx(sum(payouts))


def test_equal_stacks_split_prize_pool_evenly():
    result = icm_equities(stacks=[100, 100, 100], payouts=[50, 30, 20])
    assert result == pytest.approx([100 / 3, 100 / 3, 100 / 3])


def test_winner_take_all_is_linear_in_chips():
    # Единственная выплата -> ICM вырождается в долю фишек.
    result = icm_equities(stacks=[50, 30, 20], payouts=[100, 0, 0])
    assert result == pytest.approx([50.0, 30.0, 20.0])


def test_payouts_shorter_than_field_are_padded_with_zeros():
    result = icm_equities(stacks=[50, 30, 20], payouts=[100])
    assert result == pytest.approx([50.0, 30.0, 20.0])


def test_rejects_more_payouts_than_players():
    with pytest.raises(ValueError):
        icm_equities(stacks=[50, 50], payouts=[50, 30, 20])


def test_rejects_nonpositive_stack():
    with pytest.raises(ValueError):
        icm_equities(stacks=[50, 0], payouts=[100])


def test_bubble_factor_is_one_under_winner_take_all():
    # Без лесенки выплат риска сверх фишкового нет.
    bf = bubble_factor(
        stacks=[50, 30, 20], payouts=[100, 0, 0], hero=0, villain=1
    )
    assert bf == pytest.approx(1.0)


def test_bubble_factor_exceeds_one_with_ladder():
    bf = bubble_factor(
        stacks=[50, 30, 20], payouts=[50, 30, 20], hero=0, villain=1
    )
    assert bf > 1.0


def test_risk_premium_is_zero_under_winner_take_all():
    rp = risk_premium(
        stacks=[50, 30, 20], payouts=[100, 0, 0], hero=0, villain=1
    )
    assert rp == pytest.approx(0.0, abs=1e-9)


def test_risk_premium_positive_with_ladder():
    rp = risk_premium(
        stacks=[50, 30, 20], payouts=[50, 30, 20], hero=0, villain=1
    )
    assert rp > 0.0


def test_bubble_factor_heads_up_survives_single_player_branch():
    # Выигрыш олл-ина в хедз-апе оставляет одного игрока — вырожденная
    # ветка, на которой наивная реализация падает.
    bf = bubble_factor(stacks=[60, 40], payouts=[70, 30], hero=0, villain=1)
    assert bf > 0.0


def test_negative_hero_index_is_rejected():
    # Отрицательный индекс не должен молча оборачиваться Python-семантикой
    # индексации и отвечать за другого игрока.
    with pytest.raises(ValueError):
        bubble_factor(stacks=[50, 30, 20], payouts=[50, 30, 20], hero=-1, villain=1)


def test_risk_premium_with_degenerate_payouts_raises():
    # Нулевые выплаты не меняют ICM-эквити героя при любом исходе олл-ина,
    # risk premium неопределён — должен упасть ValueError, а не ZeroDivisionError.
    with pytest.raises(ValueError):
        risk_premium(stacks=[10, 10], payouts=[0, 0], hero=0, villain=1)


@pytest.mark.parametrize(
    "stacks, payouts, hero, villain",
    [
        ([50, 30, 20], [50, 50, 50], 1, 2),
        ([100, 90, 80, 70], [25, 25, 25, 25], 0, 3),
        ([13, 17, 19, 23, 29, 31], [10, 10, 10, 10, 10, 10], 0, 5),
    ],
)
def test_flat_payout_ladder_is_exactly_degenerate(stacks, payouts, hero, villain):
    # На полностью плоской лесенке (сателлиты) win и lose равны математически,
    # но приходят к значению разными ветвями рекурсии и расходятся на ~1e-15.
    # Точное сравнение float это ловит как false negative — риск-премия и
    # bubble factor обязаны быть ровно 0 и 1, а не мусор от округления.
    rp = risk_premium(stacks, payouts, hero, villain)
    bf = bubble_factor(stacks, payouts, hero, villain)
    assert rp == pytest.approx(0.0, abs=1e-9)
    assert bf == pytest.approx(1.0)


def test_bubble_and_risk_premium_hold_at_realistic_field_size():
    # 8 игроков, 5 оплачиваемых мест — реалистичная лесенка для 9-max,
    # где bust-and-recurse логика реально задействуется.
    stacks = [300, 250, 200, 150, 120, 100, 80, 50]
    payouts = [400, 250, 150, 100, 50]
    bf = bubble_factor(stacks=stacks, payouts=payouts, hero=0, villain=1)
    rp = risk_premium(stacks=stacks, payouts=payouts, hero=0, villain=1)
    assert bf > 1.0
    assert rp > 0.0
