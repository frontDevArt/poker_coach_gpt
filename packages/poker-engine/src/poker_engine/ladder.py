"""Лесенка выплат, адресуемая настоящим местом в турнире.

Реальная лесенка GG — 144 оплачиваемых места, описанные шестнадцатью
интервалами. Список призов по местам не материализуется ни наружу, ни
внутри: приз ищется двоичным поиском по интервалам (спека §4.4), поэтому
память не зависит от `places_paid`.

Тексты отказов взяты дословно из `handstate._validate_context`: там те же
нарушения уже установили пользовательский контракт, и одно нарушение
обязано давать одно сообщение. Пока живут две модели места — здешняя
1-based и 0-based `handstate.payout_ladder`; вторую удаляет Задача 4
плана `docs/superpowers/plans/2026-09-12-icm-field-model.md`, она же
переводит ладдер-блок `_validate_context` на этот класс.

Монотонность призов к худшим местам класс не проверяет: расчёту по
лесенке она безразлична, и проверка остаётся у `handstate`.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Sequence

from ._checks import check_integer, check_positive

__all__ = ["PayoutLadder"]


class PayoutLadder:
    def __init__(
        self, intervals: Sequence[tuple[int, int, float]], places_paid: int
    ) -> None:
        check_integer(places_paid, "размер призовой зоны")
        check_positive(places_paid, "размер призовой зоны")
        if not intervals:
            raise ValueError("лесенка выплат пуста")
        self._places_paid = places_paid
        self._starts: list[int] = []
        self._ends: list[int] = []
        self._amounts: list[float] = []
        covered = 0
        total = 0.0
        for first, last, amount in sorted(intervals, key=lambda i: i[0]):
            check_integer(first, "номер места")
            check_integer(last, "номер места")
            if first < 1 or last < first:
                raise ValueError(
                    f"неверный интервал мест в выплатах: {first}–{last}"
                )
            check_positive(amount, f"приз за место {first}")
            # Уже принятые интервалы отсортированы и не пересекаются, поэтому
            # первый кандидат на пересечение — тот, чей конец не левее начала
            # нового. Место печатается то же, что у `handstate`: наименьшее
            # из общих.
            at = bisect_left(self._ends, first)
            if at < len(self._ends) and self._starts[at] <= last:
                raise ValueError(
                    f"интервалы выплат пересекаются на месте "
                    f"{max(first, self._starts[at])}"
                )
            if last > places_paid:
                raise ValueError(
                    f"выплаты описаны до места {last}, а призовых мест "
                    f"{places_paid}"
                )
            self._starts.append(first)
            self._ends.append(last)
            self._amounts.append(amount)
            covered += last - first + 1
            total += amount * (last - first + 1)
        self._covered = covered
        self._total = total

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
        """Приз за место. Места вне описанных интервалов платят ноль."""
        check_integer(place, "номер места")
        check_positive(place, "номер места")
        at = bisect_right(self._starts, place) - 1
        if at >= 0 and place <= self._ends[at]:
            return self._amounts[at]
        return 0.0

    def total(self) -> float:
        """Сумма призов по всем покрытым местам. Считана в конструкторе:
        бюджет двух секунд (Задача 8) не терпит O(places_paid) на вызов."""
        return self._total
