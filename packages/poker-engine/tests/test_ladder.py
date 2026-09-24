"""Лесенка выплат: приз берётся по настоящему месту в турнире."""

import tracemalloc

import pytest

from poker_engine.ladder import PayoutLadder


def test_prize_comes_from_the_interval_that_covers_the_place():
    ladder = PayoutLadder([(1, 1, 100.0), (2, 3, 50.0)], places_paid=3)
    assert ladder.prize(1) == 100.0
    assert ladder.prize(2) == 50.0
    assert ladder.prize(3) == 50.0


def test_intervals_may_come_in_any_order():
    # Со скриншота строки приходят как распознались; порядок — не контракт.
    ladder = PayoutLadder([(2, 3, 50.0), (1, 1, 100.0)], places_paid=3)
    assert ladder.prize(1) == 100.0
    assert ladder.prize(3) == 50.0
    assert ladder.is_complete


def test_places_past_the_ladder_pay_nothing():
    ladder = PayoutLadder([(1, 2, 10.0)], places_paid=2)
    assert ladder.prize(3) == 0.0
    assert ladder.prize(100_000) == 0.0


def test_places_inside_the_prize_pool_but_outside_the_intervals_pay_nothing():
    # Недоснятый скриншот: места 7-144 не описаны, платить за них нечем.
    ladder = PayoutLadder([(1, 6, 400.0)], places_paid=144)
    assert ladder.prize(7) == 0.0
    assert ladder.prize(144) == 0.0


def test_total_is_the_sum_over_every_paid_place():
    # 100 за первое плюс 50 за два места = 200.
    ladder = PayoutLadder([(1, 1, 100.0), (2, 3, 50.0)], places_paid=3)
    assert ladder.total() == pytest.approx(200.0)


def test_real_ladder_is_sixteen_lines_for_a_hundred_forty_four_places():
    # Лесенка Mini SUPER SIX Bounty Turbo, 1244 входа, 144 места (спека 4.1).
    ladder = PayoutLadder(
        [
            (1, 1, 1098.45), (2, 2, 1097.86), (3, 3, 832.02), (4, 4, 630.55),
            (5, 5, 476.41), (6, 6, 361.05), (7, 7, 273.62), (8, 8, 163.54),
            (9, 10, 122.37), (11, 13, 91.55), (14, 18, 68.50), (19, 26, 51.25),
            (27, 39, 38.35), (40, 59, 28.69), (60, 92, 21.46), (93, 144, 16.06),
        ],
        places_paid=144,
    )
    assert ladder.is_complete
    assert ladder.places_covered == 144
    assert ladder.prize(144) == 16.06
    assert ladder.prize(145) == 0.0


def test_partial_coverage_is_visible_and_is_not_an_error():
    # Пользователь снял только первый экран лобби: описаны места 1-6 из 144.
    ladder = PayoutLadder([(1, 6, 400.0)], places_paid=144)
    assert ladder.places_covered == 6
    assert ladder.is_complete is False


def test_adjacent_intervals_cover_the_whole_prize_pool():
    # 3 места плюс 1 место = 4 покрытых из 4 оплачиваемых.
    ladder = PayoutLadder([(1, 3, 10.0), (4, 4, 5.0)], places_paid=4)
    assert ladder.places_covered == 4
    assert ladder.is_complete


def test_a_complete_ladder_always_pays_something():
    # Все призы > 0 по гарду, значит полная лесенка не может стоить ноль:
    # 144 места по 1.0 = 144.0.
    ladder = PayoutLadder([(1, 144, 1.0)], places_paid=144)
    assert ladder.is_complete
    assert ladder.total() == pytest.approx(144.0)


def test_memory_does_not_scale_with_places_paid():
    # Список на places_paid + 1 элементов дал бы здесь ~160 МБ; двоичный
    # поиск по интервалам держит память на числе интервалов — у одного
    # интервала это сотни байт. Потолок 100 КБ абсолютный: на три порядка
    # выше честной постройки и на три порядка ниже регрессии, поэтому шум
    # аллокатора его не задевает. Окно одно: прогревочная постройка
    # забирает одноразовые аллокации, `reset_peak` их отсекает.
    tracemalloc.start()
    try:
        PayoutLadder([(1, 6, 400.0)], places_paid=10)
        tracemalloc.reset_peak()
        ladder = PayoutLadder([(1, 6, 400.0)], places_paid=20_000_000)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak <= 100_000
    assert ladder.prize(10_000_000) == 0.0


def test_place_below_one_is_rejected_by_prize():
    ladder = PayoutLadder([(1, 1, 5.0)], places_paid=1)
    with pytest.raises(ValueError, match="номер места должен быть > 0"):
        ladder.prize(0)


def test_fractional_place_is_rejected_by_prize():
    ladder = PayoutLadder([(1, 1, 5.0)], places_paid=1)
    with pytest.raises(ValueError, match="номер места должен быть целым"):
        ladder.prize(2.5)


def test_non_positive_places_paid_is_rejected():
    with pytest.raises(ValueError, match="размер призовой зоны должен быть > 0"):
        PayoutLadder([(1, 1, 5.0)], places_paid=0)


def test_fractional_places_paid_is_rejected():
    with pytest.raises(ValueError, match="размер призовой зоны должен быть целым"):
        PayoutLadder([(1, 1, 5.0)], places_paid=2.5)


def test_empty_ladder_is_rejected():
    with pytest.raises(ValueError, match="лесенка выплат пуста"):
        PayoutLadder([], places_paid=144)


def test_interval_outside_places_paid_is_rejected():
    with pytest.raises(
        ValueError, match="выплаты описаны до места 150, а призовых мест 144"
    ):
        PayoutLadder([(140, 150, 10.0)], places_paid=144)


def test_backwards_interval_is_rejected():
    with pytest.raises(
        ValueError, match="неверный интервал мест в выплатах: 10–3"
    ):
        PayoutLadder([(10, 3, 10.0)], places_paid=144)


def test_interval_starting_below_place_one_is_rejected():
    with pytest.raises(
        ValueError, match="неверный интервал мест в выплатах: 0–3"
    ):
        PayoutLadder([(0, 3, 10.0)], places_paid=144)


def test_fractional_interval_bound_is_rejected():
    # Текст отличается от «номер места» в `prize`: там кривой запрос
    # пользователя, здесь — кривая строка лесенки, и путать их нечего.
    # Гардов на этот текст два — на `first` и на `last`, — и различает их
    # только значение, поэтому оно пинится вместе с текстом.
    with pytest.raises(
        ValueError, match="номер места в выплатах должен быть целым, получено 1.5$"
    ):
        PayoutLadder([(1.5, 3, 10.0)], places_paid=144)
    with pytest.raises(
        ValueError, match="номер места в выплатах должен быть целым, получено 2.5$"
    ):
        PayoutLadder([(1, 2.5, 10.0)], places_paid=144)


def test_non_positive_prize_is_rejected():
    with pytest.raises(ValueError, match="приз за место 1 должен быть > 0"):
        PayoutLadder([(1, 1, -500.0)], places_paid=1)
    with pytest.raises(ValueError, match="приз за место 1 должен быть > 0"):
        PayoutLadder([(1, 144, 0.0)], places_paid=144)


def test_overlapping_intervals_are_rejected():
    # Места 2-3 описаны дважды: считать их пришлось бы дважды.
    with pytest.raises(
        ValueError, match="интервалы выплат пересекаются на месте 2"
    ):
        PayoutLadder([(1, 3, 10.0), (2, 4, 5.0)], places_paid=4)


def test_overlap_names_the_lowest_place_described_twice():
    # Принятые интервалы 1-3 и 5-12; новый 10-20 пересекается с 5-12
    # начиная с места 10 — как и считает `handstate._validate_context`.
    with pytest.raises(
        ValueError, match="интервалы выплат пересекаются на месте 10"
    ):
        PayoutLadder(
            [(1, 3, 10.0), (10, 20, 5.0), (5, 12, 7.0)], places_paid=20
        )


def test_boolean_places_paid_is_rejected():
    # `isinstance(True, int)` истинно: без отдельного гарда на bool
    # places_paid=True прошёл бы за призовую зону в одно место, и
    # is_complete на односегментной лесенке сказал бы True.
    with pytest.raises(ValueError, match="размер призовой зоны должен быть целым"):
        PayoutLadder([(1, 1, 5.0)], places_paid=True)


def test_intervals_touching_on_a_shared_bound_are_rejected():
    # Место 5 описано и последним в первом интервале, и первым во втором:
    # places_covered насчитал бы 5 + 5 = 10 при 9 оплачиваемых местах,
    # и is_complete солгал бы на лесенке с дырой.
    with pytest.raises(
        ValueError, match="интервалы выплат пересекаются на месте 5"
    ):
        PayoutLadder([(1, 5, 10.0), (5, 9, 5.0)], places_paid=9)


def test_total_on_an_incomplete_ladder_counts_only_covered_places():
    # Сняты места 1-6 из 144: 6 x 400 = 2400, а не 144 x 400 и не 400.
    ladder = PayoutLadder([(1, 6, 400.0)], places_paid=144)
    assert ladder.is_complete is False
    assert ladder.total() == pytest.approx(2400.0)


def test_prize_is_a_float_even_for_an_integer_amount():
    # Сигнатура обещает float; со скриншота приз мог распознаться целым.
    ladder = PayoutLadder([(1, 2, 5)], places_paid=2)
    assert isinstance(ladder.prize(1), float)
    assert isinstance(ladder.total(), float)


def test_empty_ladder_outranks_a_broken_prize_pool_size():
    # Нарушены сразу два правила. Приоритет тот же, что у
    # `handstate._validate_context`: пустота лесенки раньше places_paid.
    with pytest.raises(ValueError, match="лесенка выплат пуста"):
        PayoutLadder([], places_paid=0)


def test_a_broken_interval_outranks_a_broken_prize_pool_size():
    # Тот же приоритет: цикл по интервалам раньше гарда places_paid.
    with pytest.raises(
        ValueError, match="неверный интервал мест в выплатах: 10–3"
    ):
        PayoutLadder([(10, 3, 10.0)], places_paid=0)


def test_a_ladder_described_past_the_prize_pool_by_its_last_interval_is_rejected():
    # Глубина лесенки — конец последнего интервала, а не первого: при
    # min вместо max здесь приняли бы места 1 и 3-7 (6 мест) при
    # places_paid=6, и is_complete сказал бы True при непокрытом месте 2
    # и месте 7 вне призовой зоны.
    with pytest.raises(
        ValueError, match="выплаты описаны до места 7, а призовых мест 6"
    ):
        PayoutLadder([(1, 1, 10.0), (3, 7, 5.0)], places_paid=6)


def test_places_above_the_first_described_place_pay_nothing():
    # Снят второй экран лобби: описаны места 9-144. Места 1-8 не описаны,
    # и приз за них — ноль, а не приз ближайшего интервала снизу.
    ladder = PayoutLadder([(9, 144, 16.06)], places_paid=144)
    assert ladder.prize(1) == 0.0
    assert ladder.prize(8) == 0.0
    assert ladder.prize(9) == 16.06


def test_interval_ending_one_place_before_it_starts_is_rejected():
    # Вырожденный интервал 5-4 покрыл бы ноль мест, но лёг бы в список
    # концов и сломал его возрастание, на котором стоят гард пересечения
    # и поиск в `prize`.
    with pytest.raises(
        ValueError, match="неверный интервал мест в выплатах: 5–4"
    ):
        PayoutLadder([(5, 4, 10.0)], places_paid=144)


def test_a_hole_between_intervals_pays_nothing_and_is_not_covered():
    # Места 4-9 не описаны: 3 + 3 = 6 покрытых из 12.
    ladder = PayoutLadder([(1, 3, 10.0), (10, 12, 5.0)], places_paid=12)
    assert ladder.prize(5) == 0.0
    assert ladder.places_covered == 6
    assert ladder.is_complete is False


def test_nested_overlap_names_the_inner_interval_start():
    # 2-3 лежит внутри 1-10. Интервалы обходятся по возрастанию `first`,
    # поэтому первым принят 1-10, и наименьшее место, описанное дважды, —
    # 2, как у `handstate._validate_context` (`min(places & seen)`). При
    # обходе по `last` первым лёг бы 2-3, и отказ назвал бы место 1,
    # описанное один раз. Порядок на входе обратный — сортировка обязана.
    with pytest.raises(
        ValueError, match="интервалы выплат пересекаются на месте 2$"
    ):
        PayoutLadder([(2, 3, 5.0), (1, 10, 10.0)], places_paid=10)
