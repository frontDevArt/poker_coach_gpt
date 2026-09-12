"""Лесенка выплат, адресуемая настоящим местом в турнире.

Реальная лесенка GG — 144 оплачиваемых места, описанные двенадцатью
интервалами. Наружу список призов по местам не отдаётся никогда: он
материализуется внутри ради `prize` за O(1) и там же остаётся.

Предусловие конструктора: интервалы не пересекаются и призы не растут к
худшим местам. Это уже проверено `handstate._validate_context`, и второй
гард на то же условие здесь не заводится — два текста на одно нарушение
разошлись бы молча (конвенция «общие гарды только в `_checks.py`»).
"""

from __future__ import annotations

from ._checks import check_positive


class PayoutLadder:
    def __init__(
        self, intervals: list[tuple[int, int, float]], places_paid: int
    ) -> None:
        # «размер», а не «число»: шаблон `_checks` собирается как
        # «{name} должен быть > 0» и требует мужского рода.
        check_positive(places_paid, "размер лесенки выплат")
        self._places_paid = places_paid
        self._prizes = [0.0] * (places_paid + 1)  # индекс 0 не используется
        covered = 0
        for first, last, amount in intervals:
            check_positive(first, "номер места")
            if last < first:
                raise ValueError(
                    f"интервал выплат {first}–{last} идёт в обратную сторону"
                )
            if last > places_paid:
                raise ValueError(
                    f"интервал выплат {first}–{last} выходит за {places_paid} "
                    f"оплачиваемых мест"
                )
            for place in range(first, last + 1):
                self._prizes[place] = amount
                covered += 1
        self._covered = covered

    @property
    def places_paid(self) -> int:
        return self._places_paid

    @property
    def places_covered(self) -> int:
        return self._covered

    @property
    def is_complete(self) -> bool:
        return self._covered == self._places_paid

    def prize(self, place: int) -> float:
        """Приз за место. Места глубже лесенки платят ноль."""
        check_positive(place, "номер места")
        if place > self._places_paid:
            return 0.0
        return self._prizes[place]

    def total(self) -> float:
        return sum(self._prizes)
