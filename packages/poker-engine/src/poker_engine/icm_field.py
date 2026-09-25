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

import math

from ._checks import check_integer, check_non_negative, check_positive
from .ladder import PayoutLadder

__all__ = [
    "MAX_TABLE_SEATS",
    "PressureUndefined",
    "bubble_factor",
    "hero_equity",
    "pressure",
    "risk_premium",
    "table_equities",
]

# Стоимость растёт как 2^t. Замеры прототипа на этой машине: 8 мест —
# 0.23 с, 9 — 0.53 с, 10 — 1.18 с за вызов. Одиннадцать не оставляют
# места под бюджет двух секунд на весь разбор, поэтому потолок здесь.
# Это единственный предел в расчётном пути ICM.
MAX_TABLE_SEATS = 10

# Порог безубыточности олл-ина в фишках. При двустороннем олл-ине на
# эффективный стек `e` герой со стеком `s` выигрывает `e` и проигрывает
# `e`: порог `(s − (s − e)) / ((s + e) − (s − e)) = e / 2e` тождественно
# равен 1/2. `icm.py` вычислял это выражение каждый раз; здесь оно
# записано константой, чтобы не делать вид, что оно от чего-то зависит.
_CHIP_THRESHOLD = 0.5


class PressureUndefined(ValueError):
    """Исход олл-ина не двигает деньги героя так, чтобы давление имело смысл.

    Не ошибка ввода, а свойство лесенки: `analyze` сообщает о нём пометкой
    `icm_pressure_undefined` и продолжает разбор. Остальные отказы
    `risk_premium` и `bubble_factor` — обычный `ValueError`: это ошибки
    вызова, и прятать их за той же пометкой нельзя. Подкласс, а не новый
    тип: CLI ловит `ValueError`, и тексты остаются контрактом.
    """


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


def hero_equity(
    table: list[float],
    field_count: int,
    field_stack: float,
    ladder: PayoutLadder,
    hero: int,
) -> float:
    """ICM-эквити одного места за столом."""
    _check_seat(table, hero, "hero")
    seats, _ = table_equities(table, field_count, field_stack, ladder)
    return seats[hero]


def risk_premium(
    table: list[float],
    field_count: int,
    field_stack: float,
    ladder: PayoutLadder,
    hero: int,
    villain: int,
) -> float:
    """Насколько выше должно быть эквити героя из-за денежной лесенки.

    Разница между порогом безубыточности в деньгах и в фишках.
    Ноль при winner-take-all, положительно при лесенке выплат.
    """
    return _risk_premium_from(
        *_branches(table, field_count, field_stack, ladder, hero, villain)
    )


def bubble_factor(
    table: list[float],
    field_count: int,
    field_stack: float,
    ladder: PayoutLadder,
    hero: int,
    villain: int,
) -> float:
    """Во сколько раз проигрыш дороже выигрыша в деньгах против фишек.

    1.0 — денежная лесенка не давит (winner-take-all).
    Больше 1.0 — герой рискует деньгами сильнее, чем фишками.
    """
    return _bubble_factor_from(
        *_branches(table, field_count, field_stack, ladder, hero, villain)
    )


def pressure(
    table: list[float],
    field_count: int,
    field_stack: float,
    ladder: PayoutLadder,
    hero: int,
    villain: int,
) -> tuple[float, float, float]:
    """Эквити героя сейчас, риск-премия и bubble factor за один проход.

    Три ветви ICM (сейчас, выигрыш, проигрыш) считаются один раз: по
    отдельности `hero_equity`, `risk_premium` и `bubble_factor` дали бы
    семь вызовов `table_equities` на разбор вместо трёх (спека плана 3,
    §7.2). Числа и отказы — ровно те же, что у трёх функций порознь:
    неопределённое давление — `PressureUndefined`, прочее — `ValueError`.
    """
    now, win, lose = _branches(table, field_count, field_stack, ladder, hero, villain)
    return now, _risk_premium_from(now, win, lose), _bubble_factor_from(now, win, lose)


def _risk_premium_from(now: float, win: float, lose: float) -> float:
    if math.isclose(win, lose, abs_tol=1e-9):
        # Плоская лесенка выплат (сателлиты): win и lose равны математически,
        # но приходят к значению разными ветвями перебора и расходятся на
        # ~1e-15 — точное сравнение (win == lose) это пропускает.
        # Если деньги реально на кону (now != 0), лесенка не давит и risk
        # premium определён — ровно 0. Если все достижимые места стоят
        # ноль, деньги не на кону вовсе, и это остаётся неопределённым.
        if not math.isclose(now, 0.0, abs_tol=1e-9):
            return 0.0
        raise PressureUndefined(
            "исход олл-ина не меняет ICM-эквити героя, risk premium не определён"
        )
    money_threshold = (now - lose) / (win - lose)
    return money_threshold - _CHIP_THRESHOLD


def _bubble_factor_from(now: float, win: float, lose: float) -> float:
    if math.isclose(win, now, abs_tol=1e-9) and not math.isclose(now, 0.0, abs_tol=1e-9):
        # Плоская лесенка (сателлиты): win и now совпадают математически,
        # но расходятся на ~1e-15 — без допуска это ловится как
        # money_up <= 0. Деньги при этом на кону (now != 0), давления нет,
        # bubble factor определён — ровно 1.0.
        return 1.0
    money_up = win - now
    if money_up <= 0 or math.isclose(money_up, 0.0, abs_tol=1e-9):
        raise PressureUndefined(
            "выигрыш не увеличивает ICM-эквити, bubble factor не определён"
        )
    # Фишковое отношение (проигранное к выигранному) тождественно равно 1:
    # при двустороннем олл-ине на кону одинаковые фишки в обе стороны.
    # `icm.py` делил на него явно; здесь деление на единицу опущено.
    return (now - lose) / money_up


def _branches(
    table: list[float],
    field_count: int,
    field_stack: float,
    ladder: PayoutLadder,
    hero: int,
    villain: int,
) -> tuple[float, float, float]:
    """Эквити героя сейчас, после выигрыша и после проигрыша олл-ина.

    Гарды и их порядок — как в `icm._icm_branches`: места, различие,
    эффективный стек, и только потом гарды `table_equities`. Поэтому
    соперник со стеком 0 получает текст про эффективный стек, а не про
    стек места.
    """
    _check_seat(table, hero, "hero")
    _check_seat(table, villain, "villain")
    if hero == villain:
        raise ValueError("hero и villain должны различаться")
    stake = min(table[hero], table[villain])
    if stake <= 0:
        raise ValueError("эффективный стек равен нулю")

    now = table_equities(table, field_count, field_stack, ladder)[0][hero]

    won = list(table)
    won[hero] += stake
    won[villain] -= stake
    win = _equity_after(won, field_count, field_stack, ladder, hero)

    lost = list(table)
    lost[hero] -= stake
    lost[villain] += stake
    lose = _equity_after(lost, field_count, field_stack, ladder, hero)

    return now, win, lose


def _equity_after(
    table: list[float],
    field_count: int,
    field_stack: float,
    ladder: PayoutLadder,
    hero: int,
) -> float:
    """Эквити героя после олл-ина, в котором один из двоих мог вылететь.

    Место в этой модели абсолютное, поэтому лесенку сдвигать не нужно (в
    отличие от `icm._equity_with_busts`, индексировавшего выплаты позицией
    среди выживших). Вылетевший занимает последнее место среди всех, кто
    ещё в турнире, а места выше не меняются: достаточно убрать его со стола
    и посчитать заново. `min` в `_branches` возвращает один из двух стеков
    как есть, поэтому вылетевший получает ровно ноль, без погрешности.
    """
    if table[hero] <= 0:
        # Живые — остальные за столом, всё поле и сам герой: его место
        # последнее из них.
        alive = sum(1 for stack in table if stack > 0)
        return ladder.prize(alive + field_count + 1)
    seats = [index for index, stack in enumerate(table) if stack > 0]
    shrunk = [table[index] for index in seats]
    equities, _ = table_equities(shrunk, field_count, field_stack, ladder)
    return equities[seats.index(hero)]


def _check_seat(table: list[float], seat: int, name: str) -> None:
    if not 0 <= seat < len(table):
        raise ValueError(f"{name}={seat} вне диапазона игроков [0, {len(table) - 1}]")
