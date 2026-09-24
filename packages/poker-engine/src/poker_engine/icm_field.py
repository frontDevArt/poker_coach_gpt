"""ICM на реальном поле: стол поимённо, остальные — счётчиком.

За столом игроки различимы, их `t` штук. Остальные `F` игроков поля
неразличимы: у каждого средний стек. Неразличимых не нужно перебирать —
достаточно считать, сколько их уже финишировало.

Состояние: подмножество `S` мест стола, занявших верхние места, плюс
счётчик `k` финишировавших из поля. Разыгрываемое место — `|S| + k + 1`,
и это настоящее место в турнире, а не номер узла: приз берётся из
лесенки по нему, без обрезания и без грубых ступеней.

Раздаются места `1..t + F` — те, что ещё разыгрывают живые. Места глубже
уже достались выбывшим, поэтому сумма эквити стола и поля равна сумме
лесенки по местам `1..t + F`, а это `ladder.total()`, когда живых не
меньше, чем покрытых мест.

Стоимость: `2^t × (F+1)` состояний по `t+1` переходов. Экспонента — от
числа мест за столом, а не от размера поля: поле входит линейно,
множителем `F + 1`. Поле в тысячу человек стоит вдесятеро дороже, чем в
сто, а не в `2^900` раз — но всё-таки вдесятеро, и на ранней стадии
большого турнира эта статья бюджета заметна.

Модель Malmuth-Harville сохраняется: вероятность занять следующее место
пропорциональна стеку. Её известное смещение (завышение второго места
для крупного стека) здесь не лечится — оно помечается флагом `mh_bias`
в ответе `analyze`.
"""

from __future__ import annotations

from ._checks import check_integer, check_non_negative, check_positive
from .ladder import PayoutLadder

__all__ = ["MAX_TABLE_SEATS", "table_equities"]

# Стоимость растёт как 2^t. Замеры прототипа на этой машине: 8 мест —
# 0.23 с, 9 — 0.53 с, 10 — 1.18 с за вызов. Одиннадцать не оставляют
# места под бюджет двух секунд на весь разбор, поэтому потолок здесь.
# Это единственный предел в расчётном пути ICM.
MAX_TABLE_SEATS = 10


def table_equities(
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


def _validate(table: list[float], field_count: int, field_stack: float) -> None:
    if not table:
        raise ValueError("за столом нет игроков")
    if len(table) > MAX_TABLE_SEATS:
        raise ValueError(
            f"мест за столом ({len(table)}) больше предела {MAX_TABLE_SEATS}: "
            f"перебор растёт как 2^t и не укладывается в бюджет разбора"
        )
    for index, stack in enumerate(table):
        check_positive(stack, f"стек на месте {index}")
    check_integer(field_count, "размер поля")
    check_non_negative(field_count, "размер поля")
    if field_count > 0:
        check_positive(field_stack, "стек игрока поля")
