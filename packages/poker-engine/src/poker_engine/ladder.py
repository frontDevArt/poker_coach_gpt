"""Лесенка выплат, адресуемая настоящим местом в турнире.

Реальная лесенка GG — 144 оплачиваемых места, описанные шестнадцатью
интервалами. Список призов по местам не материализуется ни наружу, ни
внутри: приз ищется двоичным поиском по интервалам (спека §4.4), поэтому
память не зависит от `places_paid`.

Форма строки лесенки — контракт вызывающего кода, а не пользовательский
ввод: `intervals` — последовательность троек `(first, last, amount)` с
целыми 1-based местами включительно и числовым призом. Тройки собирает
пакет (с Задачи 4 — из `TournamentContext.payouts`, где `handstate`
уже привёл поля к числам), поэтому строка не той длины или приз строкой
— программная ошибка, и класс не заводит на неё пользовательского
текста: наружу уходит сырой `ValueError`/`TypeError` распаковки или
сравнения. Гард `check_integer` на границах интервала стоит там же по той
же причине — он ловит конструкцию, а не ввод.

Тексты отказов взяты дословно из `handstate._validate_context`: там те же
нарушения уже установили пользовательский контракт, и одно нарушение
обязано давать одно сообщение. Порядок гардов тоже повторяет
`_validate_context`: пустота, затем интервалы, затем `places_paid` и
глубина лесенки — Задача 4 переводит ладдер-блок валидатора на этот
класс, и приоритет сообщений на данных, нарушающих сразу два правила,
обязан остаться прежним. Пока живут две модели места — здешняя
1-based и 0-based `handstate.payout_ladder`; вторую удаляет Задача 4
плана `docs/superpowers/plans/2026-09-12-icm-field-model.md`.

Монотонность призов к худшим местам класс не проверяет: расчёту по
лесенке она безразлична, и проверка остаётся у `handstate`.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence

from ._checks import check_integer, check_positive

__all__ = ["PayoutLadder"]


class PayoutLadder:
    def __init__(
        self, intervals: Sequence[tuple[int, int, float]], places_paid: int
    ) -> None:
        if not intervals:
            raise ValueError("лесенка выплат пуста")
        self._starts: list[int] = []
        self._ends: list[int] = []
        self._amounts: list[float] = []
        covered = 0
        total = 0.0
        for first, last, amount in sorted(intervals, key=lambda i: i[0]):
            check_integer(first, "номер места в выплатах")
            check_integer(last, "номер места в выплатах")
            if first < 1 or last < first:
                raise ValueError(
                    f"неверный интервал мест в выплатах: {first}–{last}"
                )
            check_positive(amount, f"приз за место {first}")
            # Со скриншота приз мог распознаться целым; `prize` и `total`
            # обещают float, и обещание держится здесь, а не на выходе.
            amount = float(amount)
            # Инвариант, на котором стоит весь класс: `_starts` и `_ends`
            # строго возрастают. Интервалы обходятся по возрастанию `first`,
            # `first <= last` проверено выше, а новый принимается, только
            # если начинается правее конца последнего принятого. Отсюда же
            # гард пересечения: у каждого принятого start <= first, конец
            # самый правый — у хвоста, и если он не левее `first`, хвост
            # накрывает само место `first`. Правую границу нового интервала
            # проверять незачем, наименьшее из общих мест всегда `first`.
            # На возрастании `_ends` держится и `bisect_right` в `prize`.
            if self._ends and first <= self._ends[-1]:
                raise ValueError(
                    f"интервалы выплат пересекаются на месте {first}"
                )
            self._starts.append(first)
            self._ends.append(last)
            self._amounts.append(amount)
            covered += last - first + 1
            total += amount * (last - first + 1)
        check_integer(places_paid, "размер призовой зоны")
        check_positive(places_paid, "размер призовой зоны")
        deepest = max(self._ends)
        if deepest > places_paid:
            raise ValueError(
                f"выплаты описаны до места {deepest}, а призовых мест "
                f"{places_paid}"
            )
        self._places_paid = places_paid
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
        # `==`, а не `>=`, и мутант `>=` эквивалентен: covered > places_paid
        # невозможен, пока живы гарды first >= 1, непересечения и
        # deepest <= places_paid — различные места лежат в 1..places_paid.
        return self._covered == self._places_paid

    def prize(self, place: int) -> float:
        """Приз за место. Места вне описанных интервалов платят ноль —
        и за призовой зоной, и в дырах между интервалами, и до первого
        описанного места. Место меньше 1 отвергается текстом
        `номер места должен быть > 0`, нецелое (в том числе `bool`) —
        `номер места должен быть целым`."""
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
