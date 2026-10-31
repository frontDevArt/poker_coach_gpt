"""Советник push/fold: лучший ответ конкретной руки героя против равновесия соперников.

Узел — спот `first_in` или `facing_allin` (`pushfold_game.read_spot`). Подыгра решается
дважды: по фишкам и по ICM модели поля (с головами, если турнир PKO). Совет даёт ICM: герой
сравнивает EV активного действия и фолда своей комбинации против равновесных стратегий
соперников (спека плана 4, §5.7); фишечное решение — для объяснения ICM-поправки.

Модуль целиком удовлетворяет протоколу советника (`name`, `applies`, `advise`), поэтому
`name` — атрибут модуля в нижнем регистре.

**Уточнения формы ответа против спеки §6.2** (решения плана 4, Задача 4):

- `ev.icm` и `ev.chip` называют активное действие спота: `allinUsd`/`allinBb` в `first_in`,
  `callUsd`/`callBb` в `facing_allin`; плюс `foldUsd`/`foldBb` и `marginUsd`/`marginBb` —
  активное минус фолд;
- `action` — активное при `marginUsd > 0`, иначе `fold`;
- `sizeBb` — `stackBb + investedBb` героя в `first_in`; в `facing_allin` — меньшее из
  `stackBb + investedBb` олл-инщика и героя минус `investedBb` героя. При `fold` ключа нет;
- `nash` — по блоку на решение, у каждого свои единицы: `icm.exploitabilityUsd`,
  `chip.exploitabilityBb` и число итераций;
- `ranges.opponents` — все участники подыгры, кроме героя, по порядку хода: открывающий —
  `role: "shover"`, отвечающие — `"caller"`;
- `effectiveStackBb` — эффективный стек спота: в `first_in` меньшее из стека героя и
  наибольшего стека после него, в `facing_allin` — из стеков олл-инщика и героя (стеки — с
  вложенным, спека §4).

**Против текста спеки §8** (решения плана): `fold_as_walk` ставится и в `facing_allin`, когда
после олл-инщика есть кто-то, кроме `BB`: фолд олл-инщика в равновесии тоже моделируется
уходом банка к `BB`. `close_spot` — по безразличию `|marginUsd| ≤ eps` ICM-решения, а не по
частоте смешанной стратегии: средние fictitious play почти никогда не дают ровно 0 и 1.

**Решения при реализации (Фаза 4):**

- допуск ICM-решения — `EPS_CHIP_BB` в долларах по цене фишки участников (`icm_eps_usd`), а
  не `EPS_ICM_SHARE × деньги в игре` плана. Доля от призов в 25–40 раз грубее фишечного
  допуска (фикстура плана 3: 0.0038 $ против 0.00015 $), ICM-решение останавливалось на 40
  шагах против 200, и диапазоны коллеров расходились с фишечными на 0.016 — шум сходимости
  выдавался бы за ICM-поправку. Константа `EPS_ICM_SHARE` из `nash.py` удалена;
- `ranges.opponents[].classes` — частоты ICM-равновесия, округлённые до `CLASS_FREQ_STEP`;
  класс, округлившийся в ноль, опускается. Средние fictitious play не обнуляются никогда
  (стартовые 0.5 убывают как `1/t²`), и без округления в словаре были бы все 169 классов;
- `ranges.opponents[].stackBb` — `stackBb` места, как во входе (у олл-инщика 0);
- головы: ICM на стеках исходов считается один раз, наличные за головы добавляет
  `pushfold_game.with_bounties`. `ev.bountyUsd` — `marginUsd` с головами минус `marginUsd`
  без них при тех же стратегиях соперников (равновесие с головами не перерешивается).
"""

from __future__ import annotations

import numpy

from . import allin_matrix, nash
from .explain import WORDS, action_text, display, fact
from .hand import Hand
from .handstate import DecisionNode, TournamentContext, assign_positions
from .pushfold_game import (
    Outcomes,
    Spot,
    chip_outcomes,
    icm_outcomes,
    read_spot,
    with_bounties,
)

name = "pushfold"

# Разрешение частот в `ranges.opponents[].classes`: точнее fictitious play не сходится.
CLASS_FREQ_STEP = 0.01

_ACTIVE = {"first_in": "allin", "facing_allin": "call"}


def applies(hand: Hand) -> str | None:
    """`None`, если последний узел — спот push/fold, иначе причина отказа."""
    spot = read_spot(hand.nodes[-1])
    return spot if isinstance(spot, str) else None


def advise(hand: Hand, history: list[dict]) -> dict:
    """Совет на последнем узле. Предусловие — `applies` вернул `None`; `history` не читается:
    после олл-ина героя решений в раздаче больше нет."""
    context, node = hand.context, hand.nodes[-1]
    spot = read_spot(node)
    responders = len(spot.players) - 1
    pko = any(seat.bounty_usd is not None for seat in node.seats)

    plain = icm_outcomes(spot, node, context, bounties=False)
    icm_game = nash.Game(with_bounties(spot, plain) if pko else plain, responders)
    chip_game = nash.Game(chip_outcomes(spot), responders)
    icm_eps = icm_eps_usd(chip_game.outcomes, plain)
    by_icm = nash.solve(icm_game, icm_eps, nash.MAX_ITERATIONS)
    by_chip = nash.solve(chip_game, nash.EPS_CHIP_BB, nash.MAX_ITERATIONS)

    hero_class = allin_matrix.class_of(node.hero_cards)
    weights = allin_matrix.hand_weights(node.hero_cards)
    equity = allin_matrix.equity_matrix()[allin_matrix.class_index(hero_class)]

    def hero_ev(game: nash.Game, equilibrium: nash.Equilibrium) -> tuple[float, float]:
        if spot.hero_at == 0:
            return nash.opener_ev(game, equilibrium.call, weights, equity)
        return nash.responder_ev(
            game, equilibrium.push, equilibrium.call, spot.hero_at, weights, equity
        )

    active_usd, fold_usd = hero_ev(icm_game, by_icm)
    active_bb, fold_bb = hero_ev(chip_game, by_chip)
    margin_usd = active_usd - fold_usd
    word = _ACTIVE[spot.kind]
    action = word if margin_usd > 0 else "fold"

    result: dict = {"advisor": name, "spot": spot.kind, "action": action}
    if action != "fold":
        result["sizeBb"] = _size(spot)
    result["heroHand"] = hero_class
    result["effectiveStackBb"] = _effective(spot)

    ev: dict = {
        "icm": {f"{word}Usd": active_usd, "foldUsd": fold_usd, "marginUsd": margin_usd},
        "chip": {f"{word}Bb": active_bb, "foldBb": fold_bb, "marginBb": active_bb - fold_bb},
    }
    if pko:
        plain_active, plain_fold = hero_ev(nash.Game(plain, responders), by_icm)
        ev["bountyUsd"] = margin_usd - (plain_active - plain_fold)
    result["ev"] = ev

    index = allin_matrix.class_index(hero_class)
    hero_icm, hero_chip = _row(by_icm, spot.hero_at), _row(by_chip, spot.hero_at)
    positions = assign_positions(node)
    result["ranges"] = {
        "hero": {
            "icmPct": nash.range_share(hero_icm),
            "chipPct": nash.range_share(hero_chip),
            "handFreqIcm": float(hero_icm[index]),
            "handFreqChip": float(hero_chip[index]),
        },
        "opponents": [
            {
                "seatIndex": seat.seat_index,
                "position": positions[seat.seat_index].value,
                "role": "shover" if at == 0 else "caller",
                "stackBb": seat.stack_bb,
                "icmPct": nash.range_share(_row(by_icm, at)),
                "chipPct": nash.range_share(_row(by_chip, at)),
                "classes": _classes(_row(by_icm, at)),
            }
            for at, seat in enumerate(spot.players)
            if at != spot.hero_at
        ],
    }
    result["nash"] = {
        "icm": {"exploitabilityUsd": by_icm.exploitability, "iterations": by_icm.iterations},
        "chip": {"exploitabilityBb": by_chip.exploitability, "iterations": by_chip.iterations},
    }
    result["flags"] = _flags(context, node, spot, pko, abs(margin_usd) <= icm_eps, by_icm, by_chip)
    return result


def icm_eps_usd(chips: Outcomes, icm: Outcomes) -> float:
    """Допуск ICM-решения: `EPS_CHIP_BB` в долларах по цене фишки участников подыгры.

    Цена — их ICM-эквити на исходе `steal`, делённое на их фишки там же: в `steal` нет
    нокаутов, и голов в нём нет. При одном призе ICM-выплаты пропорциональны фишкам, и обе
    игры с допусками решаются одинаково (инвариант 6 спеки на ответе).
    """
    return nash.EPS_CHIP_BB * sum(icm.steal) / sum(chips.steal)


def _size(spot: Spot) -> float:
    if spot.kind == "first_in":
        return spot.totals[0]
    hero = spot.players[spot.hero_at]
    return min(spot.totals[0], spot.totals[spot.hero_at]) - hero.invested_bb


def _effective(spot: Spot) -> float:
    if spot.kind == "first_in":
        return min(spot.totals[0], max(spot.totals[1:]))
    return min(spot.totals[0], spot.totals[spot.hero_at])


def _row(equilibrium: nash.Equilibrium, at: int) -> numpy.ndarray:
    """Частоты активного действия участника `at` подыгры: 0 — пуш, дальше — коллы."""
    return equilibrium.push if at == 0 else equilibrium.call[at - 1]


def _classes(freq: numpy.ndarray) -> dict[str, float]:
    # Делить на число шагов в единице, а не умножать на шаг: 95 / 100 — ближайшее к 0.95
    # число, а 95 × 0.01 — 0.9500000000000001, и в JSON ушёл бы хвост.
    per_unit = round(1 / CLASS_FREQ_STEP)
    steps = numpy.round(freq * per_unit)
    return {
        allin_matrix.CLASSES[at]: float(steps[at] / per_unit)
        for at in range(len(allin_matrix.CLASSES))
        if steps[at] > 0
    }


def _flags(
    context: TournamentContext,
    node: DecisionNode,
    spot: Spot,
    pko: bool,
    close: bool,
    by_icm: nash.Equilibrium,
    by_chip: nash.Equilibrium,
) -> list[str]:
    """Пометки спеки §8; каждая ставится, только когда она правда (правило `analyze`)."""
    flags = _context_flags(context, node, pko)
    if len(spot.players) > 2:
        flags.append("no_overcall")
    if any(at != spot.bb_at for at in range(1, len(spot.players))):
        flags.append("fold_as_walk")
    if close:
        flags.append("close_spot")
    if not (by_icm.converged and by_chip.converged):
        flags.append("nash_not_converged")
    return flags


def _context_flags(context: TournamentContext, node: DecisionNode, pko: bool) -> list[str]:
    """Пометки модели и турнира, общие для советников префлопа, в порядке ответа."""
    flags = ["mh_bias"]
    if node.players_left > len(node.seats):
        flags.append("field_homogeneous")
    if pko:
        flags.append("pko")
    if context.protected_ladder(node.players_left) is not None:
        flags.append("bubble_protection")
    if not context.ladder().is_complete:
        flags.append("ladder_incomplete")
    if context.late_reg_open:
        flags.append("late_reg_open")
    if context.payouts_final is False:
        flags.append("payouts_provisional")
    if context.average_stack_source == "table":
        flags.append("field_from_table")
    return flags


def explain(answer: dict) -> list[dict]:
    """Факты ответа (спека тренера §8): действие и размер, разница с фолдом в долларах и в BB,
    головы, доли и частоты героя, соперники, пометки. Банк, колл и требуемую эквити колла в
    `facing_allin` даёт узел (`explain.node_facts`)."""
    facts = [fact("action", _action_text(answer), "text")]
    if "sizeBb" in answer:
        facts.append(fact("sizeBb", answer["sizeBb"], "bb"))
    ev = answer["ev"]
    facts += [
        fact("marginUsd", ev["icm"]["marginUsd"], "usd"),
        fact("marginBb", ev["chip"]["marginBb"], "ev_bb"),
    ]
    if "bountyUsd" in ev:
        facts.append(fact("bountyUsd", ev["bountyUsd"], "usd"))
    hero = answer["ranges"]["hero"]
    facts += [
        fact("heroIcmPct", hero["icmPct"], "pct"),
        fact("heroChipPct", hero["chipPct"], "pct"),
        fact("heroHandFreqIcm", hero["handFreqIcm"], "pct"),
        fact("heroHandFreqChip", hero["handFreqChip"], "pct"),
    ]
    for opponent in answer["ranges"]["opponents"]:
        at = f"opponent.{opponent['position']}"
        facts += [
            fact(f"{at}.role", opponent["role"], "role"),
            fact(f"{at}.stackBb", opponent["stackBb"], "bb"),
            fact(f"{at}.icmPct", opponent["icmPct"], "pct"),
            fact(f"{at}.chipPct", opponent["chipPct"], "pct"),
        ]
    facts.append(fact("effectiveStackBb", answer["effectiveStackBb"], "bb"))
    facts += [fact(f"flag.{flag}", flag, "text") for flag in answer["flags"]]
    return facts


def _action_text(answer: dict) -> str:
    """Действие с размером. `sizeBb` колла — доплата героя, а не уровень олл-ина (у героя на
    блайнде они расходятся): «колл 8.0 BB», а не «колл до»."""
    if answer["action"] == "call":
        return f"{WORDS['call']} {display(answer['sizeBb'], 'bb')}"
    return action_text(answer["action"], answer.get("sizeBb"))
