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

from ._checks import check_positive
from .bounty import knockout_cash, own_bounty_growth, required_equity_with_bounty
from .equity import equity_vs_range
from .handstate import (
    DecisionNode,
    Seat,
    TournamentContext,
    assign_positions,
    context_from_dict,
    node_from_dict,
    validate_hand,
)
from .icm_field import PressureUndefined, bubble_factor, hero_equity, risk_premium
from .ladder import PayoutLadder
from .potodds import required_equity
from .profiles import range_for_vpip


def analyze(
    context_raw: dict,
    nodes_raw: list[dict],
    trials: int = 10_000,
    seed: int | None = None,
) -> dict:
    """Разбор раздачи: контекст турнира плюс узлы решения — по одному на скриншот.

    Разбирается последний узел: он и есть момент, на который отвечает герой,
    остальные нужны валидатору как история.

    ICM считается моделью «стол поимённо + однородное поле» (`icm_field`):
    места за столом различимы, остальные `players_left − мест за столом`
    игроков поля неразличимы и держат средний стек турнира за вычетом
    стола. Место в этой модели — настоящее место в турнире, и приз берётся
    из лесенки по нему целиком, без обрезания.

    Размер поля берётся из `node.players_left`, а не из
    `context.players_left`: узел — снимок разбираемого момента, контекст
    снят раньше и живёт дольше (в фикстурах плана это 496 против 782).
    Расхождение между ними — норма, а не ошибка ввода, поэтому `handstate`
    их намеренно не сверяет.

    `trials` — число прогонов Monte-Carlo для эквити против диапазона,
    `seed` — сид его генератора. Ответ воспроизводим ровно при
    фиксированном `seed`; без него доли эквити меняются от вызова к
    вызову в пределах точности выборки. На ICM и пот-оддсы оба
    параметра не влияют — те считаются точно.

    Пометка `ladder_incomplete` означает, что интервалы выплат покрывают
    меньше мест, чем `placesPaid`: призы за непокрытые места модель
    считает нулевыми. Недоснятый скриншот лобби или кривое распознавание —
    не повод молчать. Пометка — про вход, а не про число: `heroEquity`
    занижено, только если среди непокрытых есть места не глубже
    `playersLeft`. Места глубже уже вручены выбывшим и в расчёт не входят,
    и на финальном столе с выплатами за места 1–6 из 165 число точное, а
    пометка всё равно стоит.

    PKO узнаётся по ценникам голов (`Seat.bounty_usd`), а не по настройке:
    есть хоть один — пометка `pko`, и при определённом сопернике ответ
    получает блок `bounty`. Он лежит отдельно от `icm` и ни с чем не
    складывается: деньги лесенки и деньги голов — два разных куска, и
    пользователь обязан видеть, что тянет решение (спека плана 3, §8.2).
    Уже взятые баунти в расчёт не входят никогда: они на балансе. Без
    ценников `bounty.py` не вызывается вовсе.

    Защита на баббле (`bubbleRefundUsd` в контексте) — возврат бай-ина за
    вылет вне денег — входит в ICM призом за места `placesPaid + 1 ..
    playersLeft` (`TournamentContext.protected_ladder`, там же допущение о
    границах бабла). Применена — пометка `bubble_protection` и блок
    `bubbleProtection`: размер возврата, места, которым он платится, и
    риск-премия без него. `ladder_incomplete` и цена блайнда в блоке
    `bounty` считаются по лесенке лобби: возврат платит рум, а не фонд.

    Известное ограничение: соперник в олл-ине (стек 0 BB) разбору не
    поддаётся — раздача отвергается сообщением про стек на его месте
    (`seatIndex`, как на скриншоте). Как учитывать уже вложенные в банк
    фишки выбывающего — решение о модели ICM (спека плана 3, §11.1), и
    оно не принято.

    `effectiveStackBb` — минимум из остаточных стеков героя и соперника;
    уже вложенное в банк в него не входит (`Seat.invested_bb` учтено в
    `pot_bb`, см. `DecisionNode`). Это соглашение, а не расчёт: сколько
    фишек реально на кону, зависит от того, кто кому отвечает.

    Форма входа проверяется до разбора: `context` — объект, `nodes` —
    список объектов. Источник данных — vision-модель, и `null` либо
    число вместо узла от неё так же реальны, как объект вместо списка;
    без этих гардов наружу протекал бы внутренний `TypeError` вместо
    русского сообщения.
    """
    if not isinstance(context_raw, dict):
        raise ValueError(
            f"поле 'context' должно быть объектом, получено {context_raw!r}"
        )
    if not isinstance(nodes_raw, list):
        raise ValueError(
            f"поле 'nodes' должно быть списком, получено {nodes_raw!r}"
        )
    for number, raw in enumerate(nodes_raw):
        if not isinstance(raw, dict):
            raise ValueError(
                f"узел решения {number} должен быть объектом, получено {raw!r}"
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
    hero_index = seats.index(hero)
    # Ноль не доходит до расчёта: стек 0 BB проходит `validate_hand`
    # (олл-ин соперника), но модель не знает, куда деть его вложенное.
    # Отказ называет `seatIndex`, а не позицию в списке: номера со
    # скриншота идут с пропусками, когда за столом есть пустые места, и
    # `icm_field` назвал бы не то место.
    for seat in seats:
        check_positive(seat.stack_bb, f"стек на месте {seat.seat_index}")
    table = [seat.stack_bb for seat in seats]

    # `prizes` — лесенка лобби; `ladder` — та, по которой считается ICM: с
    # защитой на баббле это `prizes`, удлинённая возвратом бай-ина за места
    # вне денег (`TournamentContext.protected_ladder`).
    prizes = context.ladder()
    protected = context.protected_ladder(node.players_left)
    ladder = prizes if protected is None else protected
    field_count = node.players_left - len(table)
    field_stack = _field_stack(node, context, table, field_count)

    result["icm"] = {
        "heroEquity": hero_equity(table, field_count, field_stack, ladder, hero_index),
        "playersLeft": node.players_left,
        "tableSeats": len(table),
    }
    # `mh_bias` безусловна: Malmuth-Harville применяется всегда.
    # `field_homogeneous` — только когда поле вне стола правда есть: на
    # финальном столе поле пусто, допущения об однородности нет, и флаг
    # соврал бы. `flags` — канал честности ответа, флаг, который иногда
    # ложь, обесценивает весь канал.
    result["flags"].append("mh_bias")
    if field_count > 0:
        result["flags"].append("field_homogeneous")
    # Полнота — о лесенке лобби. По значению это то же, что полнота
    # удлинённой (интервал возврата покрывает ровно места, на которые
    # удлинена зона, и дыру внутри призовой зоны не закрывает), но пометка
    # про вход и читается по входу.
    if not prizes.is_complete:
        result["flags"].append("ladder_incomplete")
    if context.late_reg_open:
        result["flags"].append("late_reg_open")
    if node.street == "preflop":
        result["flags"].append("no_pushfold")
    if protected is not None:
        result["flags"].append("bubble_protection")
        result["bubbleProtection"] = {
            "refundUsd": context.bubble_refund_usd,
            "places": {"from": context.places_paid + 1, "to": node.players_left},
        }
    is_pko = any(seat.bounty_usd is not None for seat in seats)
    if is_pko:
        result["flags"].append("pko")

    if node.to_call_bb > 0:
        result["requiredEquity"] = required_equity(node.pot_bb, node.to_call_bb)

    if villain is None:
        return result

    villain_index = seats.index(villain)
    result["villainPosition"] = positions[villain.seat_index].value
    result["effectiveStackBb"] = min(hero.stack_bb, villain.stack_bb)

    # Неопределённое давление (winner-take-all, деньги вне достижимых мест,
    # лесенка, награждающая вылет) — не ошибка ввода, а свойство лесенки:
    # сообщаем пометкой, а не падением всего разбора. Ловится только
    # `PressureUndefined`: прочие отказы этих функций — ошибки вызова, и
    # под пометкой они бы спрятались (долг D4).
    try:
        result["riskPremium"] = _pressure(
            table, field_count, field_stack, ladder, hero_index, villain_index
        )
    except PressureUndefined:
        result["flags"].append("icm_pressure_undefined")
    # Обе риск-премии — с возвратом и без: пользователь обязан видеть, что
    # именно смягчило давление (спека §6). Неопределённое давление без
    # возврата — то же свойство лесенки, что и в основном расчёте: ключа
    # тогда нет, а пометка `icm_pressure_undefined` остаётся про основной.
    if protected is not None:
        try:
            result["bubbleProtection"]["riskPremiumWithoutRefund"] = _pressure(
                table, field_count, field_stack, prizes, hero_index, villain_index
            )
        except PressureUndefined:
            pass

    if is_pko:
        result["bounty"] = _bounty_block(
            node, hero, villain, prizes, sum(table) + field_count * field_stack
        )

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


def _field_stack(
    node: DecisionNode,
    context: TournamentContext,
    table: list[float],
    field_count: int,
) -> float:
    """Стек одного игрока поля: средний по турниру за вычетом стола.

    Считается из среднего стека, а не берётся им: средний стек включает
    стол, а поле — это турнир без стола.
    """
    if field_count <= 0:
        return 0.0
    if context.average_stack_bb is None:
        raise ValueError(
            f"нужен средний стек: игроков ({node.players_left}) больше, чем за "
            f"столом ({len(table)}), и поле нечем населить"
        )
    chips = node.players_left * context.average_stack_bb - sum(table)
    if chips <= 0:
        raise ValueError(
            "средний стек не согласован со стеками за столом: "
            "на остальное поле не остаётся фишек"
        )
    return chips / field_count


def _pressure(
    table: list[float],
    field_count: int,
    field_stack: float,
    ladder: PayoutLadder,
    hero: int,
    villain: int,
) -> dict:
    """Риск-премия и bubble factor героя против соперника на лесенке `ladder`."""
    return {
        "riskPremium": risk_premium(
            table, field_count, field_stack, ladder, hero, villain
        ),
        "bubbleFactor": bubble_factor(
            table, field_count, field_stack, ladder, hero, villain
        ),
    }


def _bounty_block(
    node: DecisionNode,
    hero: Seat,
    villain: Seat,
    ladder: PayoutLadder,
    chips_in_play: float,
) -> dict:
    """Головы PKO: что можно выиграть и что потерять в этой раздаче.

    Ценники обоим гарантирует `handstate`: в PKO он обязателен у героя и у
    каждого в раздаче. Наличные за нокаут — показанный ценник соперника
    целиком (`bounty.py`, спека §5.2).

    `bbValueUsd` — доллары за большой блайнд: деньги, которые ещё
    разыгрываются, делённые на фишки в игре. Разыгрываются призы мест
    `1..playersLeft` — те, что глубже, уже вручены выбывшим, и сумма всей
    лесенки на глубоком ITM завысила бы цену блайнда. `ladder` — лесенка
    лобби, без возврата бай-ина на баббле: он не из фонда и от фишек не
    зависит. Фишки в игре — стол
    плюс поле ровно в той модели, по которой считан ICM. Если лесенка не
    знает ни одного приза в пределах `playersLeft`, цену блайнда считать
    нечем, и ключей `bbValueUsd` и `requiredEquityWithBounty` нет.

    Голова засчитывается в порог, только если нокаут в этой раздаче
    возможен: колл героя накрывает остаток соперника (правило
    `required_equity_with_bounty`) и у героя фишек не меньше, чем у
    соперника вместе с вложенным. Иначе порог — обычный пот-оддс.
    Колл против олл-ина (остаток 0 BB) пока до сюда не доходит —
    ограничение ICM, см. docstring `analyze`.
    """
    block: dict = {
        "villainPriceUsd": villain.bounty_usd,
        "knockoutCashUsd": knockout_cash(villain.bounty_usd),
        "ownPriceGrowthUsd": own_bounty_growth(villain.bounty_usd),
        "heroPriceAtRiskUsd": hero.bounty_usd,
    }
    in_play = min(node.players_left, ladder.places_paid)
    money_in_play = sum(ladder.prize(place) for place in range(1, in_play + 1))
    if money_in_play <= 0:
        return block
    bb_value = money_in_play / chips_in_play
    block["bbValueUsd"] = bb_value
    if node.to_call_bb > 0:
        can_bust = (
            hero.stack_bb + hero.invested_bb
            >= villain.stack_bb + villain.invested_bb
        )
        block["requiredEquityWithBounty"] = (
            required_equity_with_bounty(
                node.pot_bb,
                node.to_call_bb,
                villain.stack_bb,
                villain.bounty_usd,
                bb_value,
            )
            if can_bust
            else required_equity(node.pot_bb, node.to_call_bb)
        )
    return block


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
