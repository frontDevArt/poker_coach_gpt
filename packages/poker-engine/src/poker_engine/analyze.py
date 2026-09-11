"""Сквозной разбор состояния, снятого со скриншота.

Одна функция на всё: принимает турнирный контекст и список узлов решения,
возвращает всё, что движок способен посчитать, плюс список пометок о том,
что расчётом не является. Это единственная точка, которую вызывает
приложение.

Ключи, которых посчитать нельзя, в ответе отсутствуют. Заполнять их
нулями значило бы выдавать незнание за число.

Ключи ответа — camelCase, в отличие от остальных подкоманд CLI
(`required_equity` и прочие snake_case). Это намеренно: форма ответа
`analyze` — контракт с приложением на TypeScript, а ключи старых команд
уже отгружены скиллам и закреплены их тестами. Унификация сломала бы
одну из двух сторон и ничего не добавила бы.
"""

from __future__ import annotations

from .equity import equity_vs_range
from .field import reduce_field
from .handstate import (
    DecisionNode,
    Seat,
    assign_positions,
    context_from_dict,
    node_from_dict,
    payout_ladder,
    validate_hand,
)
from .icm import bubble_factor, icm_equities, risk_premium
from .potodds import required_equity
from .profiles import range_for_vpip

MAX_FIELD_NODES = 15


def analyze(
    context_raw: dict,
    nodes_raw: list[dict],
    trials: int = 10_000,
    seed: int | None = None,
) -> dict:
    """Разбор раздачи: контекст турнира плюс узлы решения — по одному на скриншот.

    Разбирается последний узел: он и есть момент, на который отвечает герой,
    остальные нужны валидатору как история.

    Размер поля для свёртки берётся из `node.players_left`, а не из
    `context.players_left`: узел — снимок разбираемого момента, контекст
    снят раньше и живёт дольше (в фикстурах плана это 496 против 782).
    Расхождение между ними — норма, а не ошибка ввода, поэтому `handstate`
    их намеренно не сверяет.
    """
    if not isinstance(nodes_raw, list):
        raise ValueError(
            f"поле 'nodes' должно быть списком, получено {nodes_raw!r}"
        )

    context = context_from_dict(context_raw)
    nodes = [node_from_dict(raw) for raw in nodes_raw]
    validate_hand(context, nodes)

    node = nodes[-1]
    positions = assign_positions(node)
    hero = node.hero
    villain = _pick_villain(node)

    result: dict = {
        "street": node.street,
        "heroPosition": positions[hero.seat_index].value,
        "flags": [],
    }

    seats = sorted(node.seats, key=lambda seat: seat.seat_index)
    hero_index = next(i for i, seat in enumerate(seats) if seat.is_hero)
    field = reduce_field(
        [seat.stack_bb for seat in seats],
        hero_index,
        node.players_left,
        context.average_stack_bb,
        max_nodes=MAX_FIELD_NODES,
    )
    ladder = payout_ladder(context, places=len(field))
    result["icm"] = {
        "heroEquity": icm_equities(field, ladder)[hero_index],
        "fieldNodes": len(field),
    }
    # `mh_bias` безусловна: Malmuth-Harville применяется всегда.
    # `reduced_field` — только когда свёртка правда была: на финальном
    # столе поле равно столу, число точное, и пометка о приближении
    # соврала бы. `flags` — канал честности ответа, флаг, который иногда
    # ложь, обесценивает весь канал.
    result["flags"].append("mh_bias")
    if len(field) > len(seats):
        result["flags"].append("reduced_field")
    if context.late_reg_open:
        result["flags"].append("late_reg_open")
    if node.street == "preflop":
        result["flags"].append("no_pushfold")

    if node.to_call_bb > 0:
        result["requiredEquity"] = required_equity(node.pot_bb, node.to_call_bb)

    if villain is None:
        return result

    villain_index = next(
        i for i, seat in enumerate(seats) if seat.seat_index == villain.seat_index
    )
    result["villainPosition"] = positions[villain.seat_index].value
    result["effectiveStackBb"] = min(hero.stack_bb, villain.stack_bb)

    # `risk_premium` и `bubble_factor` отказываются считать, когда исход
    # олл-ина не двигает ICM-эквити героя (winner-take-all, нулевые выплаты
    # вне свёрнутой лесенки). Это не ошибка ввода, а отсутствие давления
    # лесенки — сообщаем пометкой, а не падением всего разбора.
    try:
        result["riskPremium"] = {
            "riskPremium": risk_premium(field, ladder, hero_index, villain_index),
            "bubbleFactor": bubble_factor(field, ladder, hero_index, villain_index),
        }
    except ValueError:
        result["flags"].append("icm_pressure_undefined")

    combos, used_default = range_for_vpip(villain.vpip, villain.vpip_hands)
    shares = equity_vs_range(
        "".join(node.hero_cards), combos, node.board, trials=trials, seed=seed
    )
    result["equity"] = {
        "hero": shares[0],
        "villain": shares[1],
        "rangeSource": "default" if used_default else "vpip",
    }
    if used_default:
        result["flags"].append("vpip_default")

    return result


def _pick_villain(node: DecisionNode) -> Seat | None:
    """Соперник, на чьё действие отвечает герой.

    Соглашение, а не расчёт: берётся активный оппонент с наибольшим
    вложением на текущей улице, при равенстве — с наибольшим стеком.
    Скриншот не хранит порядок ходов, поэтому определить последнего
    агрессора точнее нечем.
    """
    rivals = [seat for seat in node.seats if seat.in_hand and not seat.is_hero]
    if not rivals:
        return None
    return max(rivals, key=lambda seat: (seat.invested_bb, seat.stack_bb))
