"""Инварианты свёртки поля.

Проверяется сохранение того, от чего зависит ICM: суммы фишек, доли
героя в ней и его индекса. Точных значений ICM здесь нет — они предмет
`test_icm.py`.
"""

import pytest

from poker_engine.field import SCALE, reduce_field

TABLE = [72.2, 66.1, 94.4, 35.3, 23.2, 39.2, 35.7, 63.3]
HERO = 7

# Сумма стола: 72.2+66.1+94.4+35.3+23.2+39.2+35.7+63.3 = 429.4 BB,
# то есть 53.675 BB в среднем на восьмерых. Обе величины используются
# ниже как производные от TABLE, а не как отдельно вспомненные числа.
TABLE_TOTAL = 429.4
TABLE_AVERAGE = TABLE_TOTAL / len(TABLE)


def test_hero_stack_survives_scaling():
    reduced = reduce_field(TABLE, HERO, players_left=782, average_stack_bb=50.5)
    assert reduced[HERO] == round(TABLE[HERO] * SCALE)


def test_table_stacks_come_first_and_in_order():
    reduced = reduce_field(TABLE, HERO, players_left=782, average_stack_bb=50.5)
    assert reduced[: len(TABLE)] == [round(stack * SCALE) for stack in TABLE]


def test_node_count_is_capped():
    reduced = reduce_field(
        TABLE, HERO, players_left=782, average_stack_bb=50.5, max_nodes=15
    )
    assert len(reduced) <= 15


def test_total_chips_are_preserved():
    players_left, average = 782, 50.5
    reduced = reduce_field(TABLE, HERO, players_left, average)
    expected = players_left * average * SCALE
    # Допуск — округление каждого узла до 0.1 BB.
    assert sum(reduced) == pytest.approx(expected, abs=len(reduced))


def test_hero_share_of_chips_is_preserved():
    players_left, average = 782, 50.5
    reduced = reduce_field(TABLE, HERO, players_left, average)
    share = reduced[HERO] / sum(reduced)
    expected = TABLE[HERO] / (players_left * average)
    assert share == pytest.approx(expected, rel=1e-3)


def test_field_equal_to_the_table_is_left_alone():
    reduced = reduce_field(
        TABLE, HERO, players_left=len(TABLE), average_stack_bb=TABLE_AVERAGE
    )
    assert reduced == [round(stack * SCALE) for stack in TABLE]


def test_every_stack_is_a_positive_integer():
    reduced = reduce_field(TABLE, HERO, players_left=782, average_stack_bb=50.5)
    assert all(isinstance(stack, int) and stack > 0 for stack in reduced)


def test_field_smaller_than_the_table_is_rejected():
    # 3 игрока при столе на 8 — противоречие в исходных данных.
    # `match` обязателен: остальные отказы `reduce_field` — тоже
    # ValueError, и без текста тест не отличил бы их от нужного.
    with pytest.raises(ValueError, match="осталось игроков"):
        reduce_field(TABLE, HERO, players_left=3, average_stack_bb=50.5)


def test_average_inconsistent_with_the_table_is_rejected():
    # Стол держит больше фишек, чем всё поле по среднему стеку:
    # 10 * 1.0 = 10.0 против 429.4 за столом.
    # `match` обязателен: без этого гарда отрицательный остаток дошёл бы
    # до шкалы и упёрся в отсечку по 0.1 BB — отказ по другой причине.
    with pytest.raises(ValueError, match="не остаётся фишек"):
        reduce_field(TABLE, HERO, players_left=10, average_stack_bb=1.0)


def test_hero_index_outside_the_table_is_rejected():
    # Верхняя граница: индекс, равный числу мест, — уже вне стола.
    with pytest.raises(ValueError, match="индекс героя вне стола"):
        reduce_field(TABLE, len(TABLE), players_left=782, average_stack_bb=50.5)


def test_cap_below_table_size_is_rejected():
    # `match` берёт «меньше числа мест за столом», а не «предел узлов»:
    # последнее встречается и в сообщении соседнего гарда про нехватку
    # места под остальное поле.
    with pytest.raises(ValueError, match="меньше числа мест за столом"):
        reduce_field(
            TABLE, HERO, players_left=782, average_stack_bb=50.5, max_nodes=4
        )


def test_stack_below_the_printed_precision_is_rejected():
    # 0.04 BB — меньше половины деления шкалы 0.1 BB: round(0.4) = 0,
    # то есть узел с нулём фишек. 2 * 25.02 = 50.04 = 0.04 + 50.0, поле
    # сходится со столом, поэтому сработать может только отсечка
    # по точности.
    with pytest.raises(ValueError, match="не представим"):
        reduce_field([0.04, 50.0], 0, players_left=2, average_stack_bb=25.02)


# --- Границы гардов: по значению с каждой стороны отсечки ------------------


def test_empty_table_is_rejected():
    # Без стола нет ни героя, ни точки отсчёта для остального поля.
    with pytest.raises(ValueError, match="за столом нет игроков"):
        reduce_field([], 0, players_left=782, average_stack_bb=50.5)


@pytest.mark.parametrize("bad_stack", [0.0, -5.0])
def test_non_positive_table_stack_is_rejected(bad_stack):
    # Игрок с нулём или отрицанием фишек за столом не сидит: ICM такой
    # узел не примет, и подменять его на «почти ноль» движок не вправе.
    # `match` обязателен: без этого гарда непредставимый стек всё равно
    # упёрся бы в отсечку по 0.1 BB и тест ничего бы не проверял.
    with pytest.raises(ValueError, match="стек на месте 0 должен быть > 0"):
        reduce_field([bad_stack, 50.0], 1, players_left=2, average_stack_bb=25.0)


@pytest.mark.parametrize("bad_average", [0.0, -1.0])
def test_non_positive_average_stack_is_rejected(bad_average):
    # Средний стек — множитель смысла «сколько фишек у всего поля»;
    # неположительный делает общий банк поля нулевым или отрицательным.
    # `match` обязателен: без этого гарда отказ всё равно пришёл бы, но
    # от проверки согласованности — и назвал бы виновным не тот аргумент.
    with pytest.raises(ValueError, match="средний стек должен быть > 0"):
        reduce_field(TABLE, HERO, players_left=782, average_stack_bb=bad_average)


def test_negative_hero_index_is_rejected():
    # -1 — валидный индекс в Python и молча указал бы на последнее место
    # за столом. Нижняя граница проверки обязана это ловить.
    with pytest.raises(ValueError, match="индекс героя"):
        reduce_field(TABLE, -1, players_left=782, average_stack_bb=50.5)


def test_cap_equal_to_table_size_leaves_no_room_for_the_rest():
    # Предел ровно по числу мест за столом не мал сам по себе, но при
    # непустом остальном поле схлопывать его некуда — отдельная ветка.
    with pytest.raises(ValueError, match="нет места"):
        reduce_field(
            TABLE, HERO, players_left=782, average_stack_bb=50.5, max_nodes=len(TABLE)
        )


def test_cap_equal_to_table_size_is_fine_when_the_table_is_the_field():
    # Обратная сторона той же границы: остального поля нет, узлов ровно
    # столько, сколько мест — отказывать не за что.
    reduced = reduce_field(
        TABLE,
        HERO,
        players_left=len(TABLE),
        average_stack_bb=TABLE_AVERAGE,
        max_nodes=len(TABLE),
    )
    assert reduced == [round(stack * SCALE) for stack in TABLE]


def test_average_leaving_exactly_zero_for_the_rest_is_rejected():
    # 4 * 10.0 = 40.0 фишек у поля, 10.0 + 30.0 = 40.0 уже за столом:
    # на двух оставшихся игроков остаётся ровно ноль. Это не «мало
    # фишек», а противоречие в исходных данных, и граница здесь строгая.
    with pytest.raises(ValueError, match="не остаётся фишек"):
        reduce_field([10.0, 30.0], 0, players_left=4, average_stack_bb=10.0)


def test_seat_labels_name_the_seat_instead_of_the_list_position():
    # Список стеков анонимен, и без подписей отказ называет позицию в
    # списке. Совпадает она с номером места только при нумерации подряд
    # от нуля; за столом бывают пустые места, и `seatIndex` со скриншота
    # идёт с пропусками. Подписи `[3, 7]` требуют «места 7», а позиция
    # виноватого стека — 1: числа различны, поэтому тест не слепой.
    with pytest.raises(ValueError, match="стек на месте 7 должен быть > 0"):
        reduce_field(
            [10.0, 0.0],
            0,
            players_left=2,
            average_stack_bb=5.0,
            seat_labels=[3, 7],
        )


def test_seat_labels_of_the_wrong_length_are_rejected():
    # Короткий список подписей молча оставил бы часть стеков без проверки:
    # `zip` обрывается по кратчайшему, и нулевой стек последнего места
    # прошёл бы гард насквозь.
    with pytest.raises(ValueError, match="подписей мест"):
        reduce_field(
            [10.0, 20.0],
            0,
            players_left=2,
            average_stack_bb=15.0,
            seat_labels=[3],
        )


def test_smallest_printable_stack_is_accepted():
    # 0.1 BB — минимум, который печатает клиент, и ровно 1 узел шкалы.
    # Отсечка «меньше 0.1 BB» обязана быть строгой, иначе легальный
    # стек короткого игрока отвергается. 2 * 25.05 = 50.1 = 0.1 + 50.0.
    reduced = reduce_field([0.1, 50.0], 0, players_left=2, average_stack_bb=25.05)
    assert reduced == [1, 500]
