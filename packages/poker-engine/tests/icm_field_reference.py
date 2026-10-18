"""Эталон сверки: `icm_field.table_equities` плана 3 на чистом Python.

Тело перенесено дословно из `src/poker_engine/icm_field.py` (main, f5aa774)
до перевода модели на `numpy` (план 5, Задача 1, спека D27 §4). В пакете
этой реализации больше нет: она живёт здесь только как эталон, с которым
сверяется быстрый расчёт (`test_icm_field_speed.py`).
"""

from __future__ import annotations

from poker_engine.icm_field import _validate
from poker_engine.ladder import PayoutLadder


def reference_table_equities(
    table: list[float],
    field_count: int,
    field_stack: float,
    ladder: PayoutLadder,
) -> tuple[list[float], float]:
    """Эквити каждого места за столом и суммарное эквити всего поля.

    table — стеки за столом в любых единицах; модель инвариантна к их масштабу.
    field_count — сколько игроков осталось вне стола.
    field_stack — стек одного игрока поля (средний), не суммарный. При
    пустом поле не читается.
    """
    _validate(table, field_count, field_stack)

    seats = len(table)
    stacks = [float(s) for s in table]
    one = float(field_stack) if field_count else 0.0

    subsets = 1 << seats
    full = subsets - 1
    chips = [0.0] * subsets
    taken = [0] * subsets
    for mask in range(1, subsets):
        low = mask & -mask
        rest = mask ^ low
        chips[mask] = chips[rest] + stacks[low.bit_length() - 1]
        taken[mask] = taken[rest] + 1

    # Приз зависит только от номера места, а мест не больше t + F: лесенка
    # опрашивается один раз на место, а не на каждое из 2^t × (F+1) состояний.
    prizes = [ladder.prize(place) for place in range(1, seats + field_count + 1)]

    reach = [[0.0] * (field_count + 1) for _ in range(subsets)]
    reach[0][0] = 1.0
    seat_equity = [0.0] * seats
    field_equity = 0.0

    # Маски обходятся по возрастанию, а `k` внутри маски — тоже: переходы
    # ведут только в `mask | bit > mask` и в `k + 1`, поэтому к моменту
    # обхода состояние уже собрало всю вероятность, что в него входит.
    for mask in range(full):
        row = reach[mask]
        seats_gone = taken[mask]
        # Фишки живых — сумма оставшихся стеков, а не `total − chips(S)`:
        # вычитание теряло бы мелкий стек рядом с крупными до нуля или ниже.
        # Сумма положительных строго больше нуля, пока за столом кто-то жив.
        table_left = chips[full ^ mask]
        for k in range(field_count + 1):
            probability = row[k]
            # Только ускорение: нулевая вероятность ничего не переносит,
            # поэтому снос проверки — эквивалентный мутант. Нули здесь не
            # редкость: на большом поле хвосты вероятностей уходят в underflow.
            if probability == 0.0:
                continue
            left = field_count - k
            share = probability / (table_left + left * one)
            prize = prizes[seats_gone + k]
            for seat in range(seats):
                bit = 1 << seat
                if mask & bit:
                    continue
                step = share * stacks[seat]
                seat_equity[seat] += step * prize
                reach[mask | bit][k] += step
            if left:
                step = share * left * one
                field_equity += step * prize
                row[k + 1] += step

    # Стол выбыл целиком. Ряд `full` цикл выше не обходит, поэтому
    # `reach[full][k]` — вероятность, что последний игрок стола занял место
    # `t + k`: при разных `k` события несовместны. Дальше выбирать не из
    # кого — поле занимает места `t + k + 1 .. t + F` все до одного, и ему
    # достаётся весь хвост лесенки. Хвост копится с конца, без деления на
    # нулевые фишки состояния, где не осталось никого.
    row = reach[full]
    tail = 0.0
    for k in range(field_count - 1, -1, -1):
        tail += prizes[seats + k]
        field_equity += row[k] * tail

    return seat_equity, field_equity
