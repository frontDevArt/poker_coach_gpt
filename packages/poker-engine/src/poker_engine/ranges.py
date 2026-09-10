"""Диапазоны рук: разбор нотации в конкретные комбинации.

Поддерживаются четыре формы токена, разделённых запятыми:

    AA      пара                     6 комбинаций
    AKs     одномастная              4
    AKo     разномастная            12
    AK      обе                     16
    AsKh    конкретная комбинация    1

Суффикс `+` расширяет токен вверх: у пары растёт ранг (`TT+` = TT..AA),
у двух рангов подтягивается младшая карта (`ATs+` = ATs, AJs, AQs, AKs).
К конкретной комбинации `+` неприменим.
"""

from __future__ import annotations

from itertools import combinations

from .equity import RANKS, SUITS, _parse_cards


def parse_range(text: str) -> list[str]:
    """Комбинации диапазона: отсортированный список строк вида "AsKh"."""
    combos: set[str] = set()
    for token in (t.strip() for t in text.split(",")):
        if not token:
            raise ValueError(f"пустой элемент в диапазоне: {text!r}")
        combos |= _expand(token)
    return sorted(combos)


def _combo(first_card: str, second_card: str) -> str:
    """Каноническая запись комбинации.

    Порядок карт фиксирован лексикографической сортировкой строк, а не
    рангом — это НЕ покерный порядок (ASCII: 2..9 < A < J < K < Q < T),
    только способ получить одну устойчивую форму для set/dedup. Эту
    строку нельзя показывать пользователю как «старшая карта первая».
    """
    first_card, second_card = sorted((first_card, second_card))
    return first_card + second_card


def _expand(token: str) -> set[str]:
    plus = token.endswith("+")
    body = token[:-1] if plus else token

    if len(body) == 4 and body[1] in SUITS and body[3] in SUITS:
        if plus:
            raise ValueError(f"'+' неприменим к конкретной комбинации: {token!r}")
        first, second = _parse_cards(body, expected=2, label="комбинация")
        if first == second:
            raise ValueError(f"дубль карты в комбинации: {token!r}")
        return {_combo(first, second)}

    if len(body) not in (2, 3):
        raise ValueError(f"нераспознанный элемент диапазона: {token!r}")

    high, low = body[0], body[1]
    if high not in RANKS or low not in RANKS:
        raise ValueError(f"неизвестный ранг в элементе: {token!r}")

    suitedness = body[2] if len(body) == 3 else None
    if suitedness not in (None, "s", "o"):
        raise ValueError(f"нераспознанный модификатор: {token!r}")

    hi, lo = RANKS.index(high), RANKS.index(low)
    if hi < lo:
        raise ValueError(f"старший ранг должен идти первым: {token!r}")

    if hi == lo:
        if suitedness is not None:
            raise ValueError(f"пара не может быть {suitedness!r}: {token!r}")
        ranks = range(hi, len(RANKS)) if plus else [hi]
        return {c for r in ranks for c in _pair_combos(r)}

    lows = range(lo, hi) if plus else [lo]
    out: set[str] = set()
    for low_rank in lows:
        out |= _two_rank_combos(hi, low_rank, suitedness)
    return out


def _pair_combos(rank: int) -> set[str]:
    letter = RANKS[rank]
    return {_combo(letter + a, letter + b) for a, b in combinations(SUITS, 2)}


def _two_rank_combos(hi: int, lo: int, suitedness: str | None) -> set[str]:
    high, low = RANKS[hi], RANKS[lo]
    out: set[str] = set()
    for a in SUITS:
        for b in SUITS:
            same = a == b
            if suitedness == "s" and not same:
                continue
            if suitedness == "o" and same:
                continue
            out.add(_combo(high + a, low + b))
    return out
