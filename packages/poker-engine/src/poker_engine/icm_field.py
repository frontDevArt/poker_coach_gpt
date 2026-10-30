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

Расчёт идёт на `numpy` (спека D27): состояния одной диагонали
`|S| + k = d` друг от друга не зависят и обрабатываются одной векторной
операцией, диагоналей `t + F`. Пакетный вызов считает за тот же проход
много наборов стеков с общим полем и лесенкой — исходы одной подыгры.
Прежняя реализация на чистом Python — эталон сверки в
`tests/icm_field_reference.py`.

Модель Malmuth-Harville сохраняется: вероятность занять следующее место
пропорциональна стеку. Её известное смещение (завышение второго места
для крупного стека) здесь не лечится — оно помечается флагом `mh_bias`
в ответе `analyze`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy

from ._checks import check_integer, check_non_negative, check_positive
from .ladder import PayoutLadder

__all__ = [
    "MAX_TABLE_SEATS",
    "PressureUndefined",
    "bubble_factor",
    "field_stack",
    "hero_equity",
    "pressure",
    "risk_premium",
    "table_equities",
    "table_equities_batch",
]

# Стоимость растёт как 2^t. Замер на машине пользователя (план 5, Задача 1),
# поле 490, лучший из семи: одиночный вызов — 8 мест 0.024 с, 9 — 0.031 с,
# 10 — 0.043 с; пакет из 20 наборов — 0.092, 0.176 и 0.338 с. Чистый Python
# плана 3 стоил 0.23, 0.53 и 1.18 с за одиночный вызов. Каждое место сверх
# удваивает и время, и память диагонали: одиннадцать дали бы ~0.7 с на
# пакет подыгры, а советник всего префлопа зовёт ICM на порядок чаще, чем
# push/fold. Столов больше чем на десять мест не бывает, поэтому потолок
# здесь. Это единственный предел в расчётном пути ICM.
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
    seats, field = _solve(
        numpy.asarray([table], dtype=float), field_count, field_stack, ladder
    )
    return seats[0].tolist(), float(field[0])


def table_equities_batch(
    tables: Sequence[Sequence[float]],
    field_count: int,
    field_stack: float,
    ladder: PayoutLadder,
) -> tuple[numpy.ndarray, numpy.ndarray]:
    """Эквити мест `(B, t)` и поля `(B,)` для `B` наборов стеков за один проход.

    Поле и лесенка у всех наборов общие, наборы — одной длины `t`: так
    устроены исходы одной подыгры, они различаются только стеками стола.
    Стек 0 здесь допустим — это выбывший в исходе. Он остаётся местом стола,
    но верхних мест не занимает: эквити по столу у него ноль, остальные
    делят места `1..t − z + F` (`z` — число нулевых стеков в наборе), как
    если бы выбывших не было. Призы мест выбывания добавляет вызывающий.
    Публичный `table_equities` нулевой стек по-прежнему отвергает.
    """
    if len(tables) == 0:
        raise ValueError("пакет столов пуст")
    seats = len(tables[0])
    for index, table in enumerate(tables):
        if len(table) != seats:
            raise ValueError(
                f"наборы стеков разной длины: в наборе 0 мест {seats}, "
                f"в наборе {index} — {len(table)}"
            )
    _check_seat_count(seats)
    for index, table in enumerate(tables):
        for seat, stack in enumerate(table):
            check_non_negative(stack, f"стек на месте {seat} в наборе {index}")
        if not any(stack > 0 for stack in table):
            raise ValueError(f"в наборе {index} нет ни одного положительного стека")
    _check_field(field_count, field_stack)
    return _solve(numpy.asarray(tables, dtype=float), field_count, field_stack, ladder)


def _solve(
    stacks: numpy.ndarray,
    field_count: int,
    field_stack: float,
    ladder: PayoutLadder,
) -> tuple[numpy.ndarray, numpy.ndarray]:
    """Обход состояний `(S, k)` по диагоналям `d = |S| + k`, векторно.

    Каждый переход увеличивает `|S| + k` ровно на единицу, поэтому
    состояния одной диагонали друг от друга не зависят, а всё, что в них
    входит, приходит с предыдущей. Диагональ хранится одним массивом по
    маскам: для маски `S` это вероятность состояния `(S, d − |S|)`, ноль,
    где такой `k` вне `0..F`. Разыгрываемое место на диагонали одно —
    `d + 1`, приз тоже один.

    Знаменатель — фишки живых: сумма стеков вне `S` (а не `total − chips(S)`,
    вычитание теряло бы мелкий стек рядом с крупными) плюс `F − k` стеков
    поля. Где он ноль, живых нет, и состояние ничего не переносит: так
    кончается каждая ветвь, без деления на ноль. Отдельного хвоста для
    поля после выбывания стола, как в эталоне плана 3, здесь нет — ряд
    «стол выбыл» обходится тем же циклом: всё, что в нём есть, уходит полю
    шагом за шагом, по одному месту на диагональ. Выбывший в исходе (стек 0)
    не выбирается ни разу и в `S` не попадает.

    Порядок суммирования другой, чем в эталоне, поэтому сверка с ним — с
    допуском, а не на равенство.
    """
    batch, seats = stacks.shape
    one = float(field_stack) if field_count else 0.0
    subsets = 1 << seats
    masks = numpy.arange(subsets)
    # outside[m, i] — место i ещё не в S = m, то есть живо.
    outside = ((masks[:, None] & (1 << numpy.arange(seats))[None, :]) == 0).astype(float)
    taken = (seats - outside.sum(axis=1).astype(int))[:, None]
    # Массивы диагонали — (маска, набор): пакет последней осью, чтобы срезы
    # по биту ниже шли непрерывными блоками хотя бы по длине пакета.
    # Фишки живых за столом для каждой маски — сумма стеков вне S.
    table_left = outside @ stacks.T

    prizes = [ladder.prize(place) for place in range(1, seats + field_count + 1)]

    # Вероятность выбора, взвешенная призом, копится по маскам, а суммы по
    # местам берутся один раз в конце: место i занимает место d + 1 из
    # каждой маски, где его ещё нет, с вероятностью share × stack_i. Так же
    # копится вклад поля.
    weighted = numpy.zeros((subsets, batch))
    field_weighted = numpy.zeros((subsets, batch))
    current = numpy.zeros((subsets, batch))
    current[0] = 1.0
    share = numpy.zeros_like(current)
    scratch = numpy.empty_like(current)
    # Перенос «место i занимает место d + 1»: маска без бита i переходит в
    # маску с ним. В разбиении индекса маски на (старшие, бит i, младшие)
    # это перенос из среза «бит 0» в срез «бит 1» с весом stack_i. Срезы —
    # виды на буферы, они строятся один раз на вызов.
    moves = []
    for seat in range(seats):
        shape = (subsets >> (seat + 1), 2, 1 << seat, batch)
        moves.append(
            (
                share.reshape(shape)[:, 0],
                current.reshape(shape)[:, 1],
                scratch.reshape(shape)[:, 0],
                stacks[:, seat],
            )
        )
    for diagonal, prize in enumerate(prizes):
        # Фишки игроков поля, ещё живых в состоянии (S, d − |S|): (F − k) × one.
        # Где такой `k` вне `0..F`, состояние недостижимо и несёт ровно ноль:
        # маска не может набрать больше мест, чем разыграно, а из `k = F`
        # поле не переносит ничего (`left = 0`). Поэтому значение `left` там
        # не важно, важно лишь не поделить ноль на ноль.
        left = (field_count - diagonal + taken) * one
        denominator = table_left + left
        if seats <= diagonal <= field_count:
            # Середина: у каждой маски `k` лежит в 0..F, а знаменатель строго
            # положителен — `F − k >= |S|`, ноль только у пустой маски при
            # d = F, а у неё за столом все фишки. Проверка не нужна. Ветка —
            # только ускорение: общий путь ниже дал бы то же, поэтому мутант
            # «середины нет» эквивалентен.
            numpy.divide(current, denominator, out=share)
        else:
            share.fill(0.0)
            numpy.divide(current, denominator, out=share, where=denominator > 0)
        numpy.multiply(share, prize, out=scratch)
        weighted += scratch
        # Поле занимает место d + 1: та же маска, k + 1.
        numpy.multiply(share, left, out=current)
        numpy.multiply(current, prize, out=scratch)
        field_weighted += scratch
        for origin, target, step, stack in moves:
            numpy.multiply(origin, stack, out=step)
            target += step

    field_equity = field_weighted.sum(axis=0)
    seat_mass = (outside.T @ weighted).T
    return seat_mass * stacks, field_equity


def field_stack(
    players_left: int,
    average_stack_bb: float | None,
    table: list[float],
    field_count: int,
) -> float:
    """Стек одного игрока поля: средний по турниру за вычетом стола.

    Считается из среднего стека, а не берётся им: средний стек включает
    стол, а поле — это турнир без стола. Фишки банка и вложенное за столом
    в `table` не входят и приписываются полю (долг D23 плана 4).
    """
    if field_count <= 0:
        return 0.0
    if average_stack_bb is None:
        raise ValueError(
            f"нужен средний стек: игроков ({players_left}) больше, чем за "
            f"столом ({len(table)}), и поле нечем населить"
        )
    chips = players_left * average_stack_bb - sum(table)
    if chips <= 0:
        raise ValueError(
            "средний стек не согласован со стеками за столом: "
            "на остальное поле не остаётся фишек"
        )
    return chips / field_count


def _validate(table: list[float], field_count: int, field_stack: float) -> None:
    _check_seat_count(len(table))
    for index, stack in enumerate(table):
        check_positive(stack, f"стек на месте {index}")
    _check_field(field_count, field_stack)


def _check_seat_count(seats: int) -> None:
    if seats == 0:
        raise ValueError("за столом нет игроков")
    if seats > MAX_TABLE_SEATS:
        raise ValueError(
            f"мест за столом ({seats}) больше предела {MAX_TABLE_SEATS}: "
            f"перебор растёт как 2^t и не укладывается в бюджет разбора"
        )


def _check_field(field_count: int, field_stack: float) -> None:
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
    # Размер стола — раньше места: у пустого стола диапазона `[0, -1]` нет, и отказ называет
    # пустой стол текстом `table_equities` (D13).
    _check_seat_count(len(table))
    if not 0 <= seat < len(table):
        raise ValueError(f"{name}={seat} вне диапазона игроков [0, {len(table) - 1}]")
