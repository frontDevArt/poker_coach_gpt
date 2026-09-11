"""Свёртка турнирного поля до размера, посильного Malmuth-Harville.

`icm_equities` перебирает упорядоченные префиксы игроков; на поле из
сотен человек это не считается. Стеки за столом сохраняются поимённо,
остальное поле схлопывается в несколько узлов «средний игрок» так, что
общая сумма фишек и доля героя в ней сохраняются с точностью до
округления каждого узла до 0.1 BB.

Стеки приходят в BB, потому что клиент печатает их так, а `icm_equities`
принимает целые. ICM инвариантен к общему масштабу стеков, поэтому BB
умножаются на 10 — это ровно та точность, которая напечатана на экране.
Инвариантность закреплена тестом в `tests/test_icm.py`.
"""

from __future__ import annotations

from ._checks import check_positive

SCALE = 10


def reduce_field(
    table_stacks_bb: list[float],
    hero_index: int,
    players_left: int,
    average_stack_bb: float | None,
    max_nodes: int = 15,
    seat_labels: list[int] | None = None,
) -> list[int]:
    """Стеки поля в десятых долях BB: стол как есть, остальные схлопнуты.

    Индекс героя не меняется — стол всегда идёт первым.

    `average_stack_bb` нужен только для схлопывания остального поля: когда
    игроков ровно столько же, сколько за столом, схлопывать нечего, и
    `None` здесь законен. Переданное значение проверяется в любом случае —
    неучастие в расчёте не делает ноль или минус осмысленным вводом.

    `seat_labels` — номера мест за столом в том же порядке, что стеки.
    Нужны только сообщениям об ошибках: список стеков анонимен, и без
    подписей отказ называет позицию в списке. Совпадает она с номером
    места лишь когда места пронумерованы подряд от нуля, а вызывающий
    вправе передать любые уникальные номера — за столом бывают пустые
    места, и `seatIndex` со скриншота идёт с пропусками. Тогда
    пользователю называлось бы место, которого он на экране не видел.
    """
    if not table_stacks_bb:
        raise ValueError("за столом нет игроков")
    if not 0 <= hero_index < len(table_stacks_bb):
        raise ValueError(f"индекс героя вне стола: {hero_index}")
    if seat_labels is not None and len(seat_labels) != len(table_stacks_bb):
        raise ValueError(
            f"подписей мест ({len(seat_labels)}) не столько, сколько стеков "
            f"({len(table_stacks_bb)})"
        )
    labels = range(len(table_stacks_bb)) if seat_labels is None else seat_labels
    for seat, stack in zip(labels, table_stacks_bb):
        check_positive(stack, f"стек на месте {seat}")
    if players_left < len(table_stacks_bb):
        raise ValueError(
            f"осталось игроков ({players_left}) меньше, чем за столом "
            f"({len(table_stacks_bb)})"
        )
    if average_stack_bb is not None:
        check_positive(average_stack_bb, "средний стек")
    if max_nodes < len(table_stacks_bb):
        raise ValueError(
            f"предел узлов ({max_nodes}) меньше числа мест за столом "
            f"({len(table_stacks_bb)})"
        )

    stacks = list(table_stacks_bb)
    rest_players = players_left - len(table_stacks_bb)

    if rest_players > 0:
        if max_nodes == len(table_stacks_bb):
            raise ValueError("нет места под остальное поле: увеличьте предел узлов")
        if average_stack_bb is None:
            raise ValueError(
                f"нужен средний стек: игроков ({players_left}) больше, чем за "
                f"столом ({len(table_stacks_bb)}), и остальное поле нечем "
                f"схлопнуть"
            )
        rest_chips = players_left * average_stack_bb - sum(table_stacks_bb)
        if rest_chips <= 0:
            raise ValueError(
                "средний стек не согласован со стеками за столом: "
                "на остальное поле не остаётся фишек"
            )
        slots = min(rest_players, max_nodes - len(table_stacks_bb))
        stacks.extend([rest_chips / slots] * slots)

    scaled = [round(stack * SCALE) for stack in stacks]
    if any(stack < 1 for stack in scaled):
        raise ValueError("стек меньше 0.1 BB не представим")
    return scaled
