"""Факты объяснения `why` и их печать (спека тренера §8).

Факт — `{"key", "value", "display"}`: `value` — число или строка из ответа советника, `display` —
готовая печать по виду значения. Модель-тренер пишет текст только из `display`: числа в тексте,
которых нет в печати фактов, линтер (§9) отвергает. Поэтому печать — одна на пакет и живёт здесь:

- `bb` — стек и размер, `{:.1f} BB`;
- `ev_bb` — EV в BB со знаком, два знака: `+0.35 BB`;
- `usd` — доллары со знаком, два знака: `+$0.14`;
- `pct` — доля как проценты, один знак: `15.0%`;
- `int` — целое; `text` — строка как есть.

Здесь же — факты, общие для советников: узел (банк, колл, требуемая эквити), отказ (причины) и
итог улицы (форма §7.3 спеки тренера: линия и диапазоны или причина).
"""

from __future__ import annotations

from . import allin_matrix, potodds
from .handstate import DecisionNode

KINDS = ("bb", "ev_bb", "usd", "pct", "int", "text")

# Слова действий в печати линии и действия с размером.
WORDS = {
    "fold": "фолд",
    "check": "чек",
    "call": "колл",
    "limp": "лимп",
    "raise": "рейз",
    "allin": "олл-ин",
}


def fact(key: str, value, kind: str) -> dict:
    """Факт с готовой печатью `value` по виду `kind`."""
    return {"key": key, "value": value, "display": display(value, kind)}


def display(value, kind: str) -> str:
    """Печать значения по виду (правила — в шапке модуля)."""
    if kind == "bb":
        return f"{value:.1f} BB"
    if kind == "ev_bb":
        return f"{_signed(value):+.2f} BB"
    if kind == "usd":
        amount = _signed(value)
        return f"{'-' if amount < 0 else '+'}${abs(amount):.2f}"
    if kind == "pct":
        return f"{_zero(round(100 * value, 1)):.1f}%"
    if kind == "int":
        return str(int(value))
    if kind == "text":
        return str(value)
    raise ValueError(f"вид факта должен быть одним из {', '.join(KINDS)}, получено {kind!r}")


def _signed(value: float) -> float:
    # Округление до печати: −0.004 печатается `+0.00`, а не `-0.00`.
    return _zero(round(value, 2))


def _zero(value: float) -> float:
    return value + 0.0  # −0.0 → 0.0


def action_text(action: str, size: float | None) -> str:
    """Действие с размером: `рейз до 2.0 BB`, `олл-ин 8.0 BB`, `фолд`."""
    word = WORDS[action]
    if size is None:
        return word
    if action == "allin":
        return f"{word} {display(size, 'bb')}"
    return f"{word} до {display(size, 'bb')}"


def line_text(line: list[dict]) -> str:
    """Линия строкой: добровольные действия по порядку (`UTG рейз до 2.0 BB, BB колл до 2.0 BB`).

    Фолды не печатаются — их видно по тому, кто не вошёл. Пустая строка — до героя все
    сфолдили или он первым в банк.
    """
    return ", ".join(
        f"{act['position']} {action_text(act['action'], act.get('toBb'))}"
        for act in line
        if act["action"] != "fold"
    )


def share_within(classes: dict[str, float], within: dict[str, float]) -> float | None:
    """Доля диапазона `within`, которую занимают частоты `classes`, взвешенно по комбинациям.

    `within` — частоты классов, дошедших до узла (`reach`); `classes` — стратегия узла по классам
    (`byAction`). `None` — диапазон пуст: долю посчитать не из чего.
    """
    total = sum(freq * allin_matrix.combos_of(name) for name, freq in within.items())
    if total == 0:
        return None
    part = sum(
        freq * classes.get(name, 0.0) * allin_matrix.combos_of(name)
        for name, freq in within.items()
    )
    return part / total


def node_facts(node: DecisionNode, answer: dict) -> list[dict]:
    """Банк и колл узла; требуемая эквити — если в ответе есть колл (`potodds`)."""
    facts = [fact("potBb", node.pot_bb, "bb")]
    if node.to_call_bb > 0:
        facts.append(fact("toCallBb", node.to_call_bb, "bb"))
    callable_ = answer.get("spot") == "facing_allin" or any(
        option.get("action") == "call" for option in answer.get("actions", [])
    )
    if callable_ and node.to_call_bb > 0:
        call = min(node.to_call_bb, node.hero.stack_bb)
        facts.append(fact("requiredEquity", potodds.required_equity(node.pot_bb, call), "pct"))
    return facts


def refusal(answer: dict) -> list[dict]:
    """Отказ советников — факты-причины, по одной на советника, тексты как в ответе."""
    return [
        fact(f"reason.{entry['advisor']}", entry["reason"], "text")
        for entry in answer["notApplicable"]
    ]


def street(summary: dict) -> list[dict]:
    """Итог улицы (§7.3): линия и диапазоны участников либо причина, почему итога нет."""
    name = summary["street"]
    if "reason" in summary:
        return [fact(f"{name}.reason", summary["reason"], "text")]
    facts = [fact(f"{name}.line", line_text(summary["line"]), "text")]
    for entry in summary["ranges"]:
        at = f"{name}.{entry['position']}"
        facts += [
            fact(f"{at}.role", entry["role"], "text"),
            fact(f"{at}.stackBb", entry["stackBb"], "bb"),
            fact(f"{at}.reachPct", entry["reachPct"], "pct"),
        ]
    return facts
