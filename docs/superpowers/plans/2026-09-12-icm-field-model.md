# Модель поля, настоящая лесенка, PKO и бюджет 2 секунды — план имплементации

> **Режим исполнения — решение пользователя, перекрывает рекомендацию скиллов.**
> Субагенты не используются. Каждая задача исполняется **линейно, отдельным прогоном
> на Opus 5** (не Sonnet, не Haiku). Задачи нарезаны так, чтобы прогон вместе с чтением
> нужных файлов укладывался в 150k контекста. После каждой задачи — отдельный прогон
> ревью; находки ревью возвращаются готовым промптом-задачей на починку, и цикл
> «ревью → починка → ревью» повторяется, пока ревью не выдаст пустой список находок.
> Протокол — в разделе «Цикл исполнения» ниже. Шаги помечены `- [ ]` для отметок.

**Goal:** заменить модель ICM на «стол поимённо + однородное поле», считать по настоящей
лесенке выплат, включить PKO в разбор и уложить `analyze` в две секунды.

**Architecture:** новый расчёт перебирает подмножества мест за столом и счётчик
выбывших из поля (`2^t × (F+1)` состояний) вместо упорядоченных префиксов
(`n!/(n−depth)!`). Место героя становится настоящим местом в турнире, поэтому лесенка
берётся по нему целиком и свёртка поля (`field.reduce_field`) уходит из расчётного пути.
Оценка силы руки переезжает с `pokerkit` на `eval7` (замерено: 1 190 000 оценок в секунду
против 1 934), `pokerkit` остаётся эталоном в тестах.

**Tech Stack:** Python 3.12, pytest, pokerkit 0.7.5 (эталон), eval7 0.1.11 (горячий путь).

**Spec:** `docs/superpowers/specs/2026-09-12-icm-field-model-design.md`

## Global Constraints

Скопировано из спеки и конвенций ядра; требования каждой задачи включают этот раздел.

- **Один коммит на задачу.** Правки по ревью — отдельными `fix(engine): …`.
  Conventional Commits.
- **Валидация живёт в движке, не в CLI.** Тексты `ValueError` — пользовательские
  сообщения; менять существующие нельзя без обновления тестов.
- **Гарды называются по ограничению, не по домену.** Общие — только в `_checks.py`,
  копировать в новые модули нельзя.
- **Имя, передаваемое в `_checks.py`, — существительное мужского рода.** Шаблоны:
  `{name} должен быть > 0`, `{name} не может быть отрицательным`. `номер места` —
  годится, `выплата` — нет.
- **Тест на отказ пинит сообщение через `match=`.** Голый `pytest.raises(ValueError)`
  ловит любой гард, включая не тот.
- **Тесты — аналитические инварианты,** проверяемые на бумаге, а не числа из памяти
  модели.
- **Пометка ставится, только когда она правда.** Флаг, который иногда ложь, обесценивает
  весь канал пометок.
- **Прогон тестов:** `cd packages/poker-engine && .venv/Scripts/python -m pytest`.
  До начала работ: 304 passed.
- **Приёмка всего плана:** `analyze` на эталонной 6-max фикстуре укладывается в 2 секунды,
  и это проверяется тестом (Задача 8).

---

## Цикл исполнения

Для каждой задачи N по порядку:

1. **Прогон реализации.** Новая сессия, Opus 5. Промпт:
   > Прочитай `docs/superpowers/plans/2026-09-12-icm-field-model.md`, раздел
   > «Global Constraints» и «Задача N» целиком. Выполни все шаги Задачи N по порядку,
   > включая коммит. Спека — `docs/superpowers/specs/2026-09-12-icm-field-model-design.md`,
   > читай её разделы, на которые ссылается задача. Ничего за пределами задачи не трогай.

2. **Прогон ревью.** Новая сессия, Opus 5. Промпт:
   > Ревью Задачи N плана `docs/superpowers/plans/2026-09-12-icm-field-model.md`.
   > Смотри `git show HEAD` и текущее состояние затронутых файлов. Проверь по порядку:
   > (1) соответствие спеке `docs/superpowers/specs/2026-09-12-icm-field-model-design.md`;
   > (2) выполнение раздела «Global Constraints» плана;
   > (3) выполнение блока «Приёмка» Задачи N — каждый пункт отдельно, с доказательством;
   > (4) качество кода: мёртвый код, дубли гардов, тесты, которые проходят при сломанной
   > реализации, сообщения об ошибках не по конвенции.
   > Прогони тесты и приведи вывод. Выдай находки списком, каждая — файл, строка, в чём
   > дефект, как чинить. Если находок нет, напиши ровно `НАХОДОК НЕТ`. Ничего не чини сам.

3. **Если ревью выдало находки** — прогон починки. Новая сессия, Opus 5. Промпт
   собирается так:
   > Задача: починить находки ревью по Задаче N плана
   > `docs/superpowers/plans/2026-09-12-icm-field-model.md`.
   > Находки:
   > `<сюда дословно вставляется список находок из шага 2>`
   > По каждой находке: либо почини, либо аргументируй, почему находка неверна — молча
   > пропускать нельзя. Прогони весь тест-сьют. Закоммить одним `fix(engine): …`.

4. **Повтор шага 2** на том же коммите. Цикл, пока ревью не ответит `НАХОДОК НЕТ`.

5. Только после этого — Задача N+1.

После Задачи 8 и её сходимости — финальное ревью всей ветки тем же протоколом, с
областью «вся ветка против спеки целиком», и запись журнала в
`docs/superpowers/state/2026-09-12-icm-field-execution-notes.md`.

---

## Структура файлов

| Файл | Ответственность | Задача |
|---|---|---|
| `src/poker_engine/ladder.py` | **создать.** Лесенка выплат: приз по настоящему месту, сумма, полнота | 1 |
| `src/poker_engine/icm_field.py` | **создать.** Перебор «стол + однородное поле», эквити мест и поля | 2 |
| `src/poker_engine/icm.py` | остаётся эталоном точного перебора; `risk_premium`/`bubble_factor` переезжают в `icm_field.py` | 3 |
| `src/poker_engine/bounty.py` | исправить модель половины | 5 |
| `src/poker_engine/analyze.py` | переключить на новую модель, пометки, PKO-блок, защита на баббле | 4, 6, 7 |
| `src/poker_engine/handstate.py` | ценник баунти у места, компенсация на баббле в контексте | 6, 7 |
| `src/poker_engine/equity.py` | горячий путь на `eval7` | 8 |
| `src/poker_engine/field.py` | уходит из расчётного пути `analyze`; сам модуль и его тесты остаются | 4 |
| `src/poker_engine/cli.py` | `--split` убирается из `bounty-ev` | 5 |

---

## Задача 1: лесенка выплат по настоящему месту

**Files:**
- Create: `src/poker_engine/ladder.py`
- Test: `tests/test_ladder.py`

**Interfaces:**
- Consumes: ничего.
- Produces:
  - `class PayoutLadder` с конструктором
    `PayoutLadder(intervals: list[tuple[int, int, float]], places_paid: int)`,
    где `intervals` — тройки `(first, last, amount)`, места 1-based включительно.
  - `PayoutLadder.prize(place: int) -> float` — приз за место, 0.0 за местами лесенки.
  - `PayoutLadder.total() -> float` — сумма призов по всем оплачиваемым местам.
  - `PayoutLadder.places_covered -> int` — сколько мест покрыто интервалами.
  - `PayoutLadder.is_complete -> bool` — покрыты ли все `places_paid` мест.
  - `PayoutLadder.places_paid -> int`.

**Почему интервалы, а не список призов.** Реальная лесенка — 144 места, описанные
шестнадцатью строками (спека §4.4). Список призов по местам не материализуется ни
наружу, ни внутри: приз ищется двоичным поиском по интервалам, которых меньше двадцати.

**Решения по контракту (прогон A, 2026-09-12).** Ревью Задачи 1 показало, что класс
завёл четыре собственных текста отказа на нарушения, для которых
`handstate._validate_context` уже установил пользовательский контракт, а docstring при
этом утверждал, что дублирования нет. Global Constraint «второй текст на одно нарушение»
нарушен. Принято:

1. **Тексты отказов берутся дословно из `handstate._validate_context`.** Там они уже
   пользовательский контракт (`analyze` и CLI отдают их наружу), а `PayoutLadder`
   никакого контракта пока не установил: класс ещё никем не вызывается.
   Одно нарушение — одно сообщение, поэтому расходиться нечему:

   | Нарушение | Текст | Источник |
   |---|---|---|
   | интервалов нет вовсе | `лесенка выплат пуста` | `handstate.py:379` |
   | место < 1 или интервал задом наперёд | `неверный интервал мест в выплатах: {first}–{last}` | `handstate.py:383` |
   | приз ≤ 0 | `check_positive(amount, f"приз за место {first}")` | `handstate.py:387` |
   | интервалы пересекаются | `интервалы выплат пересекаются на месте {place}` | `handstate.py:391` |
   | интервал глубже призовой зоны | `выплаты описаны до места {last}, а призовых мест {places_paid}` | `handstate.py:415` |
   | `places_paid` ≤ 0 | `check_positive(places_paid, "размер призовой зоны")` | `handstate.py:407` |

   Следствия: гарда «номер места должен быть > 0» в конструкторе больше нет (место < 1
   ловит текст интервала), и этот текст остаётся за одним владельцем — `prize`.
   Падежная кривизна «выходит за 144 оплачиваемых мест» уходит вместе со своим текстом.

2. **Непересечение интервалов класс проверяет** — в отличие от первоначального текста
   задачи. Без этого `places_covered` считает место дважды и `is_complete` лжёт на
   покрытой лесенке; счёт различных мест без гарда требовал бы материализации всех мест.
   Текст взят из `handstate` дословно, поэтому запрет на второй текст соблюдён.
   Проверка монотонности призов (`выплата за более низкое место больше, чем за высокое`)
   остаётся у `handstate`: лесенке она безразлична.

3. **Второй моделью места владеет Задача 4.** Сейчас в пакете две несовместимые модели:
   `handstate.payout_ladder` — 0-based список со скрытой обрезкой по `places`,
   `PayoutLadder` — 1-based с нулём за пределами. Задача 4 снимает последний вызов
   `payout_ladder`, поэтому она же удаляет функцию и переводит ладдер-блок
   `_validate_context` на построение `PayoutLadder` (см. «Что убирается» Задачи 4).
   До Задачи 4 обе модели живут рядом, и docstring каждой ссылается на другую.

4. **Предел `places_paid` не вводится.** Пик 160 МБ на `places_paid=20_000_000` давала
   не отсутствующая граница, а материализация списка на `places_paid + 1` элементов.
   Материализация убрана — аллокации по `places_paid` больше нет, память O(числа
   интервалов), и третья константа предела (журнал: «единый источник предела узлов»)
   не появляется. `places_paid` при этом обязан быть целым: `2.5` раньше давал
   `TypeError` из умножения списка.

5. **Число строк реальной лесенки — шестнадцать, не двенадцать.** «Двенадцать»
   стояло в спеке §4.4, в этой задаче и в имени тест-образца, а в самих данных всегда
   было шестнадцать интервалов. Исправлено во всех трёх местах.

- [ ] **Шаг 1: написать падающий тест**

Создать `tests/test_ladder.py`:

```python
"""Лесенка выплат: приз берётся по настоящему месту в турнире."""

import pytest

from poker_engine.ladder import PayoutLadder


def test_prize_comes_from_the_interval_that_covers_the_place():
    ladder = PayoutLadder([(1, 1, 100.0), (2, 3, 50.0)], places_paid=3)
    assert ladder.prize(1) == 100.0
    assert ladder.prize(2) == 50.0
    assert ladder.prize(3) == 50.0


def test_places_past_the_ladder_pay_nothing():
    ladder = PayoutLadder([(1, 2, 10.0)], places_paid=2)
    assert ladder.prize(3) == 0.0
    assert ladder.prize(100_000) == 0.0


def test_total_is_the_sum_over_every_paid_place():
    # 100 за первое плюс 50 за два места = 200.
    ladder = PayoutLadder([(1, 1, 100.0), (2, 3, 50.0)], places_paid=3)
    assert ladder.total() == pytest.approx(200.0)


def test_real_ladder_is_sixteen_lines_for_a_hundred_forty_four_places():
    # Лесенка Mini SUPER SIX Bounty Turbo, 1244 входа, 144 места (спека 4.1).
    ladder = PayoutLadder(
        [
            (1, 1, 1098.45), (2, 2, 1097.86), (3, 3, 832.02), (4, 4, 630.55),
            (5, 5, 476.41), (6, 6, 361.05), (7, 7, 273.62), (8, 8, 163.54),
            (9, 10, 122.37), (11, 13, 91.55), (14, 18, 68.50), (19, 26, 51.25),
            (27, 39, 38.35), (40, 59, 28.69), (60, 92, 21.46), (93, 144, 16.06),
        ],
        places_paid=144,
    )
    assert ladder.is_complete
    assert ladder.places_covered == 144
    assert ladder.prize(144) == 16.06
    assert ladder.prize(145) == 0.0


def test_partial_coverage_is_visible_and_is_not_an_error():
    # Пользователь снял только первый экран лобби: описаны места 1-6 из 144.
    ladder = PayoutLadder([(1, 6, 400.0)], places_paid=144)
    assert ladder.places_covered == 6
    assert ladder.is_complete is False
    assert ladder.prize(7) == 0.0


def test_place_below_one_is_rejected_by_prize():
    ladder = PayoutLadder([(1, 1, 5.0)], places_paid=1)
    with pytest.raises(ValueError, match="номер места должен быть > 0"):
        ladder.prize(0)


def test_non_positive_places_paid_is_rejected():
    with pytest.raises(ValueError, match="размер призовой зоны должен быть > 0"):
        PayoutLadder([(1, 1, 5.0)], places_paid=0)


def test_interval_outside_places_paid_is_rejected():
    with pytest.raises(
        ValueError, match="выплаты описаны до места 150, а призовых мест 144"
    ):
        PayoutLadder([(140, 150, 10.0)], places_paid=144)
```

Тесты, добивающие мутантов каждого гарда (пустая лесенка, интервал задом наперёд,
место < 1 в интервале, неположительный приз, пересечение, нецелые аргументы,
`is_complete` на неполной лесенке) добавляет прогон починки по находкам ревью — по
одному тесту на гард, каждый с `match=` на свой текст.

- [ ] **Шаг 2: убедиться, что тест падает**

Run: `.venv/Scripts/python -m pytest tests/test_ladder.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'poker_engine.ladder'`

- [ ] **Шаг 3: реализация**

В `src/poker_engine/_checks.py` добавить общий гард целочисленности (общие гарды —
только здесь, конвенция ядра):

```python
def check_integer(value: object, name: str) -> None:
    if not isinstance(value, int):
        raise ValueError(f"{name} должен быть целым, получено {value!r}")
```

Создать `src/poker_engine/ladder.py`:

```python
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
```

- [ ] **Шаг 4: убедиться, что тесты проходят**

Run: `.venv/Scripts/python -m pytest tests/test_ladder.py -v`
Expected: 9 passed

- [ ] **Шаг 5: прогнать весь сьют**

Run: `.venv/Scripts/python -m pytest`
Expected: 304 прежних плюс тесты лесенки, все зелёные.

- [ ] **Шаг 6: коммит**

```bash
git add src/poker_engine/ladder.py tests/test_ladder.py src/poker_engine/_checks.py
git commit -m "feat(engine): лесенка выплат, адресуемая настоящим местом"
```

**Приёмка задачи 1:**
1. `prize` возвращает 0.0 за пределами лесенки, а не бросает.
2. `total` равен сумме по всем покрытым местам, а не по числу интервалов, и не
   пересчитывается на каждый вызов.
3. Ни один текст отказа класса не расходится с `handstate._validate_context`:
   каждый либо дословно оттуда, либо (`номер места`, `должен быть целым`) не имеет там
   аналога. Docstring не утверждает об отсутствии проверок, которые есть.
4. Все сообщения об отказах пинятся через `match=`, и ни один текст не бросается двумя
   разными гардами модуля.
5. `places_covered` считает различные места: пересечение отвергнуто гардом, поэтому
   двойного счёта нет.
6. Память не зависит от `places_paid`: списка на `places_paid + 1` элементов нет.
7. Мутационная приёмка: снос любого гарда `ladder.py` целиком и разворот `==` в
   `is_complete` краснят хотя бы один тест.
8. Весь сьют зелёный.

---

## Задача 2: расчёт «стол поимённо + однородное поле»

**Files:**
- Create: `src/poker_engine/icm_field.py`
- Test: `tests/test_icm_field.py`

**Interfaces:**
- Consumes: `poker_engine.ladder.PayoutLadder` (Задача 1).
- Produces:
  - `MAX_TABLE_SEATS: int = 10`
  - `def table_equities(table: list[float], field_count: int, field_stack: float,
    ladder: PayoutLadder) -> tuple[list[float], float]` — эквити каждого места за столом
    в порядке `table` и **суммарное** эквити всего поля вне стола.

**Модель.** Спека §3. Состояние — подмножество мест стола `S`, уже занявших верхние места,
плюс счётчик `k` выбранных из поля. Разыгрываемое место — `|S| + k + 1`, и это настоящее
место в турнире. Неразличимые игроки поля не перебираются, а считаются.

**Почему потолок 10 мест.** Стоимость растёт как `2^t`. Замеры прототипа: 8 мест — 0.23 с,
9 — 0.53 с, 10 — 1.18 с. Одиннадцать уже не оставляют места под бюджет двух секунд.
`MAX_TABLE_SEATS` — единственный предел в расчётном пути; `MAX_ICM_PREFIXES` из
`analyze.py` убирается в Задаче 4.

- [ ] **Шаг 1: написать падающий тест**

Создать `tests/test_icm_field.py`:

```python
"""Модель «стол поимённо, поле счётчиком»: аналитические инварианты."""

import pytest

from poker_engine.icm import icm_equities
from poker_engine.icm_field import MAX_TABLE_SEATS, table_equities
from poker_engine.ladder import PayoutLadder


def flat_ladder(places, amount, paid=None):
    return PayoutLadder([(1, places, amount)], places_paid=paid or places)


def test_winner_take_all_two_players_is_the_chip_share():
    # Победитель забирает всё: эквити = доля фишек.
    ladder = PayoutLadder([(1, 1, 100.0)], places_paid=1)
    seats, field = table_equities([75.0, 25.0], 0, 0.0, ladder)
    assert seats == pytest.approx([75.0, 25.0])
    assert field == pytest.approx(0.0)


def test_money_is_never_lost():
    # Главный инвариант модели: всё, что раздано, равно сумме лесенки.
    ladder = PayoutLadder(
        [(1, 1, 500.0), (2, 2, 300.0), (3, 5, 100.0)], places_paid=5
    )
    seats, field = table_equities([40.0, 30.0, 20.0], 6, 10.0, ladder)
    assert sum(seats) + field == pytest.approx(ladder.total())


def test_an_empty_field_reproduces_the_exact_enumeration():
    # F = 0: модель обязана совпасть со старым точным перебором.
    stacks = [5000, 3000, 2000, 1500, 900]
    payouts = [500.0, 300.0, 200.0]
    reference = icm_equities(stacks, payouts)
    ladder = PayoutLadder(
        [(1, 1, 500.0), (2, 2, 300.0), (3, 3, 200.0)], places_paid=3
    )
    seats, field = table_equities([float(s) for s in stacks], 0, 0.0, ladder)
    assert field == pytest.approx(0.0)
    assert seats == pytest.approx(reference, abs=1e-12)


def test_equal_stacks_everywhere_split_the_pool_evenly():
    # Шесть за столом плюс четверо в поле, все по 50: каждому десятая доля.
    ladder = flat_ladder(10, 100.0)
    seats, field = table_equities([50.0] * 6, 4, 50.0, ladder)
    assert seats == pytest.approx([100.0] * 6)
    assert field == pytest.approx(400.0)


def test_a_bigger_stack_is_worth_more_but_less_than_proportionally():
    # Неплоская лесенка: доля эквити крупного стека строго меньше доли фишек.
    ladder = PayoutLadder(
        [(1, 1, 500.0), (2, 2, 300.0), (3, 3, 200.0)], places_paid=3
    )
    table = [100.0, 50.0, 50.0]
    seats, field = table_equities(table, 0, 0.0, ladder)
    assert seats[0] > seats[1]
    chip_share = table[0] / sum(table)
    money_share = seats[0] / ladder.total()
    assert money_share < chip_share


def test_scaling_the_ladder_scales_every_equity():
    table, count, stack = [60.0, 40.0, 30.0], 5, 20.0
    base = PayoutLadder([(1, 1, 100.0), (2, 3, 40.0)], places_paid=3)
    big = PayoutLadder([(1, 1, 300.0), (2, 3, 120.0)], places_paid=3)
    seats_base, field_base = table_equities(table, count, stack, base)
    seats_big, field_big = table_equities(table, count, stack, big)
    assert seats_big == pytest.approx([3.0 * x for x in seats_base])
    assert field_big == pytest.approx(3.0 * field_base)


def test_scaling_every_stack_changes_nothing():
    ladder = PayoutLadder([(1, 1, 100.0), (2, 2, 50.0)], places_paid=2)
    small, _ = table_equities([6.0, 4.0, 3.0], 4, 2.0, ladder)
    big, _ = table_equities([600.0, 400.0, 300.0], 4, 200.0, ladder)
    assert big == pytest.approx(small)


def test_a_field_player_is_worth_less_than_a_bigger_table_stack():
    ladder = PayoutLadder([(1, 1, 100.0), (2, 4, 25.0)], places_paid=4)
    seats, field = table_equities([80.0, 20.0], 4, 20.0, ladder)
    per_field_player = field / 4
    assert seats[0] > per_field_player
    assert seats[1] == pytest.approx(per_field_player)


def test_too_many_seats_is_rejected():
    ladder = flat_ladder(1, 10.0)
    table = [10.0] * (MAX_TABLE_SEATS + 1)
    with pytest.raises(ValueError, match="мест за столом"):
        table_equities(table, 0, 0.0, ladder)


def test_empty_table_is_rejected():
    with pytest.raises(ValueError, match="за столом нет игроков"):
        table_equities([], 0, 0.0, flat_ladder(1, 10.0))


def test_non_positive_table_stack_is_rejected():
    with pytest.raises(ValueError, match="стек на месте 1 должен быть > 0"):
        table_equities([10.0, 0.0], 0, 0.0, flat_ladder(2, 10.0))


def test_negative_field_size_is_rejected():
    with pytest.raises(ValueError, match="размер поля не может быть отрицательным"):
        table_equities([10.0], -1, 5.0, flat_ladder(1, 10.0))


def test_a_non_empty_field_needs_a_positive_stack():
    with pytest.raises(ValueError, match="стек игрока поля должен быть > 0"):
        table_equities([10.0], 3, 0.0, flat_ladder(1, 10.0))
```

- [ ] **Шаг 2: убедиться, что тест падает**

Run: `.venv/Scripts/python -m pytest tests/test_icm_field.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'poker_engine.icm_field'`

- [ ] **Шаг 3: реализация**

Создать `src/poker_engine/icm_field.py`:

```python
"""ICM на реальном поле: стол поимённо, остальные — счётчиком.

За столом игроки различимы, их `t` штук. Остальные `F` игроков поля
неразличимы: у каждого средний стек. Неразличимых не нужно перебирать —
достаточно считать, сколько их уже финишировало.

Состояние: подмножество `S` мест стола, занявших верхние места, плюс
счётчик `k` финишировавших из поля. Разыгрываемое место — `|S| + k + 1`,
и это настоящее место в турнире, а не номер узла: приз берётся из
лесенки по нему, без обрезания и без грубых ступеней.

Стоимость: `2^t × (F+1)` состояний по `t+1` переходов. Экспонента — от
числа мест за столом, а не от размера поля, поэтому поле в тысячу
человек считается так же дёшево, как в сто.

Модель Malmuth-Harville сохраняется: вероятность занять следующее место
пропорциональна стеку. Её известное смещение (завышение второго места
для крупного стека) здесь не лечится — оно помечается флагом `mh_bias`
в ответе `analyze`.
"""

from __future__ import annotations

from ._checks import check_non_negative, check_positive
from .ladder import PayoutLadder

# Стоимость растёт как 2^t. Замеры прототипа на этой машине: 8 мест —
# 0.23 с, 9 — 0.53 с, 10 — 1.18 с за вызов. Одиннадцать не оставляют
# места под бюджет двух секунд на весь разбор, поэтому потолок здесь.
# Это единственный предел в расчётном пути ICM.
MAX_TABLE_SEATS = 10


def table_equities(
    table: list[float],
    field_count: int,
    field_stack: float,
    ladder: PayoutLadder,
) -> tuple[list[float], float]:
    """Эквити каждого места за столом и суммарное эквити всего поля.

    table — стеки за столом в любых единицах; модель инвариантна к их масштабу.
    field_count — сколько игроков осталось вне стола.
    field_stack — стек одного игрока поля (средний), не суммарный.
    """
    _validate(table, field_count, field_stack)

    seats = len(table)
    stacks = [float(s) for s in table]
    one = float(field_stack)
    total = sum(stacks) + field_count * one

    subsets = 1 << seats
    chips = [0.0] * subsets
    taken = [0] * subsets
    for mask in range(1, subsets):
        low = mask & -mask
        rest = mask ^ low
        chips[mask] = chips[rest] + stacks[low.bit_length() - 1]
        taken[mask] = taken[rest] + 1

    reach = [[0.0] * (field_count + 1) for _ in range(subsets)]
    reach[0][0] = 1.0
    seat_equity = [0.0] * seats
    field_equity = 0.0

    for mask in range(subsets):
        row = reach[mask]
        seats_gone = taken[mask]
        for k in range(field_count + 1):
            probability = row[k]
            if probability == 0.0:
                continue
            remaining = total - chips[mask] - k * one
            if remaining <= 0.0:
                continue
            prize = ladder.prize(seats_gone + k + 1)
            for seat in range(seats):
                bit = 1 << seat
                if mask & bit:
                    continue
                step = probability * stacks[seat] / remaining
                seat_equity[seat] += step * prize
                reach[mask | bit][k] += step
            left = field_count - k
            if left:
                step = probability * (left * one) / remaining
                field_equity += step * prize
                row[k + 1] += step

    return seat_equity, field_equity


def _validate(table: list[float], field_count: int, field_stack: float) -> None:
    if not table:
        raise ValueError("за столом нет игроков")
    if len(table) > MAX_TABLE_SEATS:
        raise ValueError(
            f"мест за столом ({len(table)}) больше предела {MAX_TABLE_SEATS}: "
            f"перебор растёт как 2^t и не укладывается в бюджет разбора"
        )
    for index, stack in enumerate(table):
        check_positive(stack, f"стек на месте {index}")
    check_non_negative(field_count, "размер поля")
    if field_count > 0:
        check_positive(field_stack, "стек игрока поля")
```

- [ ] **Шаг 4: убедиться, что тесты проходят**

Run: `.venv/Scripts/python -m pytest tests/test_icm_field.py -v`
Expected: 13 passed

Если падает `test_an_empty_field_reproduces_the_exact_enumeration` — это главный сигнал,
что модель разошлась с эталоном; чинить модель, а не допуск.

- [ ] **Шаг 5: прогнать весь сьют**

Run: `.venv/Scripts/python -m pytest`
Expected: 325 passed

- [ ] **Шаг 6: коммит**

```bash
git add src/poker_engine/icm_field.py tests/test_icm_field.py
git commit -m "feat(engine): ICM по столу поимённо и полю счётчиком"
```

**Приёмка задачи 2:**
1. Тест на совпадение с точным перебором при `F = 0` проходит с допуском `1e-12`,
   а не ослабленным.
2. Сумма эквити стола и поля равна `ladder.total()`.
3. `MAX_TABLE_SEATS` объявлен в этом модуле и больше нигде.
4. Перебор по полю идёт счётчиком: `field_count` не появляется в размерности `2^…`.
5. Все четыре отказа пинятся через `match=`, имена в `_checks.py` — мужского рода.
6. 325 тестов зелёные.

---

## Задача 3: риск-премия и bubble factor на новой модели

**Files:**
- Modify: `src/poker_engine/icm_field.py` (дописать три функции)
- Test: `tests/test_icm_field_pressure.py`

**Interfaces:**
- Consumes: `table_equities` (Задача 2), `PayoutLadder` (Задача 1).
- Produces:
  - `def hero_equity(table, field_count, field_stack, ladder, hero: int) -> float`
  - `def risk_premium(table, field_count, field_stack, ladder, hero: int,
    villain: int) -> float`
  - `def bubble_factor(table, field_count, field_stack, ladder, hero: int,
    villain: int) -> float`

**Что упрощается против `icm.py`.** Старый `_equity_with_busts` сдвигал лесенку, потому
что индексировал выплаты позицией среди выживших. В новой модели место абсолютное:
вылетевший занимает последнее место среди всех оставшихся, а места выше не меняются.
Значит достаточно убрать вылетевшего из стола и посчитать заново — никаких сдвигов.

**Что переносится дословно.** Обработка вырожденных лесенок через `math.isclose`
(плоская лесенка сателлита даёт `win == now` с расхождением ~1e-15) и тексты обеих
ошибок — это пользовательский контракт, менять их нельзя. Смотри `icm.py:70-90`
и `icm.py:105-120`.

- [ ] **Шаг 1: написать падающий тест**

Создать `tests/test_icm_field_pressure.py`:

```python
"""Давление лесенки на новой модели поля."""

import pytest

from poker_engine.icm_field import bubble_factor, hero_equity, risk_premium
from poker_engine.ladder import PayoutLadder


def winner_take_all():
    return PayoutLadder([(1, 1, 100.0)], places_paid=1)


def flat(places, amount):
    return PayoutLadder([(1, places, amount)], places_paid=places)


def test_winner_take_all_has_no_ladder_pressure():
    # Единственный приз: деньги линейны по фишкам, давить нечему.
    assert risk_premium([50.0, 50.0, 50.0], 0, 0.0, winner_take_all(), 0, 1) == (
        pytest.approx(0.0, abs=1e-12)
    )
    assert bubble_factor([50.0, 50.0, 50.0], 0, 0.0, winner_take_all(), 0, 1) == (
        pytest.approx(1.0, abs=1e-12)
    )


def test_a_ladder_creates_positive_pressure():
    ladder = PayoutLadder([(1, 1, 500.0), (2, 2, 300.0), (3, 3, 200.0)], places_paid=3)
    assert risk_premium([50.0, 50.0, 50.0], 0, 0.0, ladder, 0, 1) > 0.0
    assert bubble_factor([50.0, 50.0, 50.0], 0, 0.0, ladder, 0, 1) > 1.0


def test_a_flat_ladder_paying_everyone_does_not_press():
    # Сателлит: всем оставшимся платят поровну — исход олл-ина денег не меняет.
    assert risk_premium([40.0, 30.0, 30.0], 0, 0.0, flat(3, 100.0), 0, 1) == (
        pytest.approx(0.0, abs=1e-9)
    )


def test_pressure_is_higher_on_the_bubble_than_deep_in_the_money():
    # Одна и та же раздача: лесенка на 3 места при четверых за столом (бабл)
    # против лесенки на 4 места (все в деньгах).
    table = [50.0, 40.0, 30.0, 20.0]
    bubble = PayoutLadder([(1, 3, 100.0)], places_paid=3)
    in_money = PayoutLadder([(1, 4, 75.0)], places_paid=4)
    assert risk_premium(table, 0, 0.0, bubble, 0, 3) > risk_premium(
        table, 0, 0.0, in_money, 0, 3
    )


def test_scaling_the_ladder_leaves_pressure_untouched():
    table, count, stack = [60.0, 40.0, 30.0], 5, 20.0
    base = PayoutLadder([(1, 1, 100.0), (2, 3, 40.0)], places_paid=3)
    big = PayoutLadder([(1, 1, 115.0), (2, 3, 46.0)], places_paid=3)
    assert risk_premium(table, count, stack, big, 0, 1) == pytest.approx(
        risk_premium(table, count, stack, base, 0, 1)
    )
    assert bubble_factor(table, count, stack, big, 0, 1) == pytest.approx(
        bubble_factor(table, count, stack, base, 0, 1)
    )


def test_hero_equity_matches_the_seat_from_table_equities():
    from poker_engine.icm_field import table_equities

    ladder = PayoutLadder([(1, 1, 100.0), (2, 3, 30.0)], places_paid=3)
    seats, _ = table_equities([50.0, 30.0, 20.0], 4, 25.0, ladder)
    assert hero_equity([50.0, 30.0, 20.0], 4, 25.0, ladder, 1) == pytest.approx(
        seats[1]
    )


def test_hero_and_villain_must_differ():
    with pytest.raises(ValueError, match="hero и villain должны различаться"):
        risk_premium([50.0, 50.0], 0, 0.0, winner_take_all(), 0, 0)


def test_hero_outside_the_table_is_rejected():
    with pytest.raises(ValueError, match=r"hero=5 вне диапазона игроков \[0, 1\]"):
        risk_premium([50.0, 50.0], 0, 0.0, winner_take_all(), 5, 1)


def test_zero_effective_stack_is_rejected():
    with pytest.raises(ValueError, match="эффективный стек равен нулю"):
        risk_premium([50.0, 50.0], 0, 0.0, winner_take_all(), 0, 1, at_risk=0.0)


def test_degenerate_ladder_leaves_risk_premium_undefined():
    # Выплаты нулевые: деньги не на кону вовсе.
    ladder = PayoutLadder([(1, 2, 0.0)], places_paid=2)
    with pytest.raises(
        ValueError, match="исход олл-ина не меняет ICM-эквити героя"
    ):
        risk_premium([50.0, 50.0], 0, 0.0, ladder, 0, 1)
```

- [ ] **Шаг 2: убедиться, что тест падает**

Run: `.venv/Scripts/python -m pytest tests/test_icm_field_pressure.py -v`
Expected: FAIL, `ImportError: cannot import name 'hero_equity'`

- [ ] **Шаг 3: реализация**

Дописать в `src/poker_engine/icm_field.py`:

```python
import math


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
    at_risk: float | None = None,
) -> float:
    """Насколько выше должно быть эквити героя из-за денежной лесенки.

    Ноль при winner-take-all, положительно при лесенке выплат.
    `at_risk` — фишки на кону; по умолчанию эффективный стек пары.
    """
    now, win, lose = _branches(
        table, field_count, field_stack, ladder, hero, villain, at_risk
    )
    if math.isclose(win, lose, abs_tol=1e-9):
        # Плоская лесенка (сателлиты): win и lose равны математически, но
        # приходят к значению разными ветвями и расходятся на ~1e-15.
        # Если деньги реально на кону, лесенка не давит — ровно 0.
        if not math.isclose(now, 0.0, abs_tol=1e-9):
            return 0.0
        raise ValueError(
            "исход олл-ина не меняет ICM-эквити героя, risk premium не определён"
        )
    money_threshold = (now - lose) / (win - lose)
    return money_threshold - 0.5


def bubble_factor(
    table: list[float],
    field_count: int,
    field_stack: float,
    ladder: PayoutLadder,
    hero: int,
    villain: int,
    at_risk: float | None = None,
) -> float:
    """Во сколько раз проигрыш дороже выигрыша в деньгах против фишек."""
    now, win, lose = _branches(
        table, field_count, field_stack, ladder, hero, villain, at_risk
    )
    if math.isclose(win, now, abs_tol=1e-9) and not math.isclose(
        now, 0.0, abs_tol=1e-9
    ):
        return 1.0
    money_up = win - now
    if money_up <= 0 or math.isclose(money_up, 0.0, abs_tol=1e-9):
        raise ValueError(
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
    at_risk: float | None,
) -> tuple[float, float, float]:
    """Эквити героя сейчас, после выигрыша и после проигрыша олл-ина.

    Место в новой модели абсолютное, поэтому вылетевший просто убирается
    со стола: он занимает последнее место среди оставшихся, а места выше
    не сдвигаются. Сдвиг лесенки, который делал `icm._equity_with_busts`,
    здесь не нужен.
    """
    _check_seat(table, hero, "hero")
    _check_seat(table, villain, "villain")
    if hero == villain:
        raise ValueError("hero и villain должны различаться")
    stake = min(table[hero], table[villain]) if at_risk is None else at_risk
    if stake <= 0:
        raise ValueError("эффективный стек равен нулю")

    now = hero_equity(table, field_count, field_stack, ladder, hero)

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
    """Эквити героя после раздачи, в которой кто-то мог вылететь."""
    alive = [(index, stack) for index, stack in enumerate(table) if stack > 0]
    if len(alive) == len(table):
        return hero_equity(table, field_count, field_stack, ladder, hero)

    if table[hero] <= 0:
        # Герой вылетел: его место — последнее среди всех, кто ещё в турнире.
        return ladder.prize(len(alive) + field_count + 1)

    shrunk = [stack for _, stack in alive]
    seat = [index for index, _ in alive].index(hero)
    return hero_equity(shrunk, field_count, field_stack, ladder, seat)


def _check_seat(table: list[float], seat: int, name: str) -> None:
    if not 0 <= seat < len(table):
        raise ValueError(
            f"{name}={seat} вне диапазона игроков [0, {len(table) - 1}]"
        )
```

**Замечание о `risk_premium`.** Фишковый порог всегда ровно `0.5`: при двустороннем
олл-ине на равные фишки герой выигрывает столько же, сколько проигрывает. Старый код в
`icm.py` вычислял это выражением `(stack − lose) / (win − lose)`, которое тождественно
равно `0.5`. Здесь константа записана прямо, с этим комментарием в коде.

- [ ] **Шаг 4: убедиться, что тесты проходят**

Run: `.venv/Scripts/python -m pytest tests/test_icm_field_pressure.py -v`
Expected: 10 passed

- [ ] **Шаг 5: прогнать весь сьют**

Run: `.venv/Scripts/python -m pytest`
Expected: 335 passed

- [ ] **Шаг 6: коммит**

```bash
git add src/poker_engine/icm_field.py tests/test_icm_field_pressure.py
git commit -m "feat(engine): риск-премия и bubble factor на модели поля"
```

**Приёмка задачи 3:**
1. Тексты обеих ошибок совпадают с `icm.py` дословно — это контракт CLI.
2. `_equity_after` не сдвигает лесенку; вылетевший адресуется абсолютным местом.
3. Фишковый порог `0.5` записан константой с объяснением, а не вычисляется впустую.
4. Тест на бабл сравнивает две лесенки при одной раздаче, а не два числа из памяти.
5. 335 тестов зелёные.

---

## Задача 4: переключить `analyze` на новую модель

**Files:**
- Modify: `src/poker_engine/analyze.py`
- Modify: `tests/test_analyze.py`
- Modify: `tests/conftest.py` (эталонная фикстура становится 6-max, см. ниже)

**Interfaces:**
- Consumes: `icm_field.hero_equity`, `icm_field.risk_premium`,
  `icm_field.bubble_factor`, `ladder.PayoutLadder`.
- Produces: `analyze` с новым содержимым `result["icm"]` и новым набором пометок.

**Что убирается из `analyze.py`:**
- `MAX_FIELD_NODES`, `MAX_ICM_PREFIXES` и функция `_icm_prefixes` — вместе с отказом
  «перебор Malmuth-Harville такого размера не считается»;
- вызов `reduce_field` и импорт из `field`;
- вызов `payout_ladder` и импорт `significant_depth`;
- сама функция `handstate.payout_ladder` вместе с её тестами: после этой задачи у
  неё не остаётся вызовов, а держать в пакете вторую модель места (0-based список со
  скрытой обрезкой против 1-based `PayoutLadder`) — приглашение перепутать их.
  Ладдер-блок `handstate._validate_context` переводится на построение
  `PayoutLadder`: интервальные проверки (пусто, интервал задом наперёд, приз ≤ 0,
  пересечение, глубже призовой зоны, `places_paid` ≤ 0) остаются в одной реализации,
  тексты не меняются, у `handstate` остаётся своя только проверка монотонности
  призов. Владение решено прогоном A Задачи 1 (решение 3);
- пометки `ladder_truncated` и `reduced_field`.

`field.py` и `tests/test_field.py` **не удаляются**: модуль перестаёт быть частью
расчётного пути, но остаётся рабочим и покрытым. Удаление — отдельное решение и не
входит в этот план.

**Что появляется:**
- построение `PayoutLadder` из `context.payouts` и `context.places_paid`;
- поле героя считается как `players_left − число мест за столом`;
- пометки `field_homogeneous` и `ladder_incomplete`.

**Эталонная фикстура.** `tests/conftest.py` описывает стол на 8 мест. Приёмка плана
стоит на 6-max — формате турниров пользователя (спека §3.4). Фикстура переводится на
шесть мест: удаляются места 0 и 1, `buttonSeat` остаётся 4, герой остаётся на месте 7,
`seatsPerTable` в контексте становится 6. Числа в тестах, завязанных на конкретные
позиции, пересчитываются в этой же задаче.

**Таблица «входов → мест» в движок не вносится.** Спека §4.4 оставила выбор плану.
Решение: `placesPaid` приходит на входе, как и сейчас. Довод тот же, что и против
зашитого генератора лесенки (§4.1) — таблица снята с одного турнира одного формата, а
ошибаться она будет молча. Проверка полноты лесенки (`ladder_incomplete`) даёт ту же
защиту от кривого распознавания, не внося в движок неподтверждённых данных.

**Фикстура `run_analyze` расширяется.** Сейчас она принимает только правки узла
(`tests/test_analyze.py:33-38`). Тестам этого плана нужно подменять и контекст, поэтому
сигнатура становится `call(*, context=None, node=None, **overrides)`. Умолчание
`playersLeft` меняется с 8 на 6 — по числу мест за новым столом.

- [ ] **Шаг 1: переписать фикстуру под 6-max**

В `tests/conftest.py`, функция `_node`, оставить шесть мест:

```python
        "seats": [
            seat(2, 94.4, in_hand=False),
            seat(3, 35.3, in_hand=False),
            seat(4, 23.2, invested=7.3),
            seat(5, 39.2, in_hand=False),
            seat(6, 35.7, in_hand=False),
            seat(7, 63.3, hero=True, invested=1.0),
        ],
```

В `_context` поменять `"seatsPerTable": 8` на `"seatsPerTable": 6`.

В `tests/test_analyze.py` расширить фикстуру `run_analyze` (строки 33-38):

```python
    def call(*, context=None, node=None, **overrides):
        base = copy.deepcopy(node if node is not None else analyze_node)
        # Умолчание — финальный стол: поля вне стола нет, разбор дешевле.
        # Тесту, которому нужно поле, передавать playersLeft явно.
        base.update(playersLeft=6, heroRank=6)
        base.update(overrides)
        return analyze(
            context if context is not None else analyze_context,
            [base],
            trials=2_000,
            seed=11,
        )

    return call
```

- [ ] **Шаг 2: прогнать тесты и увидеть, что именно отвалилось**

Run: `.venv/Scripts/python -m pytest tests/test_analyze.py -v`
Expected: падают тесты, завязанные на позиции за восьмиместным столом. Выписать их
список — он понадобится на шаге 6.

- [ ] **Шаг 3: написать падающие тесты новой модели**

Добавить в `tests/test_analyze.py`:

```python
def test_hero_equity_is_a_real_share_of_the_prize_pool(analyze_base_result):
    # Поле 496 человек, фонд описан до шестого места. Эквити героя обязано
    # быть положительным и меньше первого приза.
    equity = analyze_base_result["icm"]["heroEquity"]
    assert 0.0 < equity < 1090.51


def test_the_answer_no_longer_claims_a_truncated_ladder(analyze_base_result):
    assert "ladder_truncated" not in analyze_base_result["flags"]
    assert "reduced_field" not in analyze_base_result["flags"]


def test_a_homogeneous_field_is_flagged(analyze_base_result):
    assert "field_homogeneous" in analyze_base_result["flags"]


def test_a_final_table_has_no_field_and_is_not_flagged(run_analyze):
    # Умолчание фикстуры — playersLeft=6 при шести местах: поля вне стола нет.
    assert "field_homogeneous" not in run_analyze()["flags"]


def test_a_ladder_shorter_than_places_paid_is_flagged(analyze_base_result):
    # Фикстура описывает места 1-6 при placesPaid=165.
    assert "ladder_incomplete" in analyze_base_result["flags"]


def test_a_complete_ladder_is_not_flagged(run_analyze, analyze_context):
    context = dict(analyze_context)
    context["placesPaid"] = 6
    result = run_analyze(context=context)
    assert "ladder_incomplete" not in result["flags"]


def test_a_deeper_ladder_is_computed_instead_of_refused(run_analyze, analyze_context):
    # Раньше это падало с «перебор Malmuth-Harville такого размера не считается».
    context = dict(analyze_context)
    context["payouts"] = [
        {"from": 1, "to": 1, "amount": 1090.51},
        {"from": 2, "to": 2, "amount": 840.37},
        {"from": 3, "to": 3, "amount": 648.01},
        {"from": 4, "to": 6, "amount": 400.0},
        {"from": 7, "to": 12, "amount": 250.0},
        {"from": 13, "to": 40, "amount": 120.0},
        {"from": 41, "to": 165, "amount": 60.0},
    ]
    result = run_analyze(context=context)
    assert result["icm"]["heroEquity"] > 0.0
    assert "ladder_incomplete" not in result["flags"]


def test_the_field_size_reported_is_the_whole_tournament(analyze_base_result):
    assert analyze_base_result["icm"]["playersLeft"] == 496
    assert analyze_base_result["icm"]["tableSeats"] == 6
```

- [ ] **Шаг 4: реализация**

В `src/poker_engine/analyze.py` удалить `MAX_FIELD_NODES`, `MAX_ICM_PREFIXES`,
`_icm_prefixes`, импорты `reduce_field`, `payout_ladder`, `significant_depth` и заменить
блок расчёта ICM на:

```python
from .icm_field import bubble_factor, hero_equity, risk_premium
from .ladder import PayoutLadder

    seats = sorted(node.seats, key=lambda seat: seat.seat_index)
    hero_index = seats.index(hero)
    table = [seat.stack_bb for seat in seats]

    ladder = PayoutLadder(
        [(p.first, p.last, p.amount) for p in context.payouts],
        places_paid=context.places_paid,
    )
    field_count = node.players_left - len(table)
    field_stack = _field_stack(node, context, table, field_count)

    result["icm"] = {
        "heroEquity": hero_equity(
            table, field_count, field_stack, ladder, hero_index
        ),
        "playersLeft": node.players_left,
        "tableSeats": len(table),
    }

    # `mh_bias` безусловна: Malmuth-Harville применяется всегда.
    # `field_homogeneous` — только когда поле вне стола правда есть: на
    # финальном столе поле пусто, допущения об однородности нет, и флаг
    # соврал бы. Флаг, который иногда ложь, обесценивает весь канал.
    result["flags"].append("mh_bias")
    if field_count > 0:
        result["flags"].append("field_homogeneous")
    if not ladder.is_complete:
        result["flags"].append("ladder_incomplete")
```

и добавить рядом:

```python
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
```

Вызовы `risk_premium` и `bubble_factor` в блоке `try` ниже переписать на новую
сигнатуру: `risk_premium(table, field_count, field_stack, ladder, hero_index,
villain_index)`.

- [ ] **Шаг 5: убедиться, что новые тесты проходят**

Run: `.venv/Scripts/python -m pytest tests/test_analyze.py -v`
Expected: новые 8 тестов зелёные.

- [ ] **Шаг 6: починить тесты, отвалившиеся на шаге 2**

Пройти по списку из шага 2. Каждый тест либо пересчитать под 6-max, либо, если он
проверял исчезнувшее поведение (`ladder_truncated`, `reduced_field`, отказ по числу
префиксов), удалить с комментарием в сообщении коммита.

- [ ] **Шаг 7: прогнать весь сьют**

Run: `.venv/Scripts/python -m pytest`
Expected: все зелёные, ни одного skip, ни одного xfail.

- [ ] **Шаг 8: коммит**

```bash
git add src/poker_engine/analyze.py tests/test_analyze.py tests/conftest.py
git commit -m "feat(engine): analyze считает ICM по реальному полю и полной лесенке"
```

**Приёмка задачи 4:**
1. Строк `MAX_ICM_PREFIXES`, `MAX_FIELD_NODES`, `_icm_prefixes`, `ladder_truncated`,
   `reduced_field` в `analyze.py` не осталось: `grep` по каждому даёт пусто.
2. `field.py` и `tests/test_field.py` не тронуты.
3. `field_homogeneous` не ставится на финальном столе.
4. Лесенка на 165 мест считается, а не отвергается.
5. Ни один тест не удалён молча — каждое удаление названо в сообщении коммита.
6. Весь сьют зелёный.

---

## Задача 5: исправить модель половины в `bounty.py`

**Files:**
- Modify: `src/poker_engine/bounty.py`
- Modify: `src/poker_engine/cli.py:192-198` (убрать `--split`), `cli.py:85`
- Modify: `tests/test_bounty.py`
- Modify: `packages/poker-engine/README.md`

**Interfaces:**
- Produces:
  - `PROGRESSIVE_SHARE: float = 0.5`
  - `def knockout_cash(bounty: float) -> float` — равно `bounty`.
  - `def own_bounty_growth(bounty: float) -> float` — равно `bounty * PROGRESSIVE_SHARE`.
  - `def bounty_in_chips(bounty: float, chip_value: float) -> float`
  - `def required_equity_with_bounty(pot_before_call, call_amount, villain_stack,
    bounty, chip_value) -> float`

**Что именно неверно сейчас.** Спека §5.2 и §5.5. Число на экране — это наличные,
которые получит выбивший, то есть половина полного баунти игрока (внёс $3.00, показано
$1.50). Текущий код считает `knockout_cash = bounty × 0.5` и занижает ценность нокаута
вдвое.

**`--split` убирается сознательно.** Это ломающее изменение контракта CLI, и оно
намеренное: правильного значения у этого флага нет — доля не настраивается, она следует
из того, что показано на экране. Изменение обязано быть видно в README и тестах.

- [ ] **Шаг 1: переписать тесты под верную модель**

В `tests/test_bounty.py` заменить `test_knockout_split_is_configurable` и
`test_split_reaches_the_threshold` на:

```python
def test_cash_equals_the_price_shown_on_screen():
    # Экран показывает $1.50 — это и есть наличные выбившему (спека 5.2).
    assert knockout_cash(bounty=1.50) == pytest.approx(1.50)


def test_own_price_grows_by_half_of_what_was_taken():
    # Ценник 1.50 плюс половина взятого 1.50 = 2.25 — ровно как на скриншоте.
    assert own_bounty_growth(bounty=1.50) == pytest.approx(0.75)


def test_the_screenshot_arithmetic_reproduces():
    # damdreiQ3 = $2.25: стартовые 1.50 плюс половина одного выбитого новичка.
    assert 1.50 + own_bounty_growth(1.50) == pytest.approx(2.25)
    # LRDAM = $3.00: двое выбитых новичков.
    assert 1.50 + 2 * own_bounty_growth(1.50) == pytest.approx(3.00)


def test_the_bounty_pool_is_conserved():
    # Двое по $3.00 в фонде. A выбивает B: берёт 1.50 наличными, его полный
    # баунти становится 3.00 + 1.50 = 4.50 и достаётся ему при победе.
    pool = 2 * 3.00
    cash = knockout_cash(1.50)
    winner_total = 3.00 + 2 * own_bounty_growth(1.50)
    assert cash + winner_total == pytest.approx(pool)
```

- [ ] **Шаг 2: убедиться, что тесты падают**

Run: `.venv/Scripts/python -m pytest tests/test_bounty.py -v`
Expected: FAIL — `knockout_cash(1.50)` возвращает 0.75, ожидается 1.50.

- [ ] **Шаг 3: реализация**

В `src/poker_engine/bounty.py` заменить шапку и первые три функции:

```python
"""Progressive Knockout: перевод головы в фишки и порог колла с учётом баунти.

Число на экране клиента — это **наличные, которые получит выбивший**, то
есть половина полного баунти игрока: участник вносит $3.00 на голову, а
над ним висит $1.50. При нокауте выбивший получает показанное число
целиком и вдобавок наращивает собственный ценник на его половину.

Проверено сохранением фонда: двое по $3.00, итого $6.00. A выбивает B,
берёт $1.50, его полный баунти становится $4.50 и достаётся ему при
победе. Выплачено $6.00 (спека 2026-09-12, раздел 5.2).

В EV конкретной руки считается только наличная часть: прирост своего
ценника обналичится лишь при последующих нокаутах и здесь не моделируется.
"""

# Доля показанного ценника, которая садится на голову выбившего. Наличные
# при этом равны показанному числу целиком, а не его доле — см. шапку.
PROGRESSIVE_SHARE = 0.5


def knockout_cash(bounty: float) -> float:
    """Наличные, которые герой получает сразу за нокаут.

    Равны показанному на экране числу. Это не половина — половиной оно уже
    является по отношению к полному баунти выбитого.
    """
    _check_bounty(bounty)
    return bounty


def own_bounty_growth(bounty: float) -> float:
    """На сколько вырастет собственный ценник героя после нокаута."""
    _check_bounty(bounty)
    return bounty * PROGRESSIVE_SHARE


def bounty_in_chips(bounty: float, chip_value: float) -> float:
    """Наличные за нокаут, выраженные в фишках."""
    _check_chip_value(chip_value)
    return knockout_cash(bounty) / chip_value
```

В `required_equity_with_bounty` убрать параметр `split`, его проверку `_check_split` и
передачу в `bounty_in_chips`. Удалить `DEFAULT_SPLIT` и `_check_split`, если после этого
они больше нигде не используются.

- [ ] **Шаг 4: убрать `--split` из CLI**

В `src/poker_engine/cli.py` удалить строку `p_b.add_argument("--split", ...)`, строку
`split=args.split,` и импорт `DEFAULT_SPLIT`.

- [ ] **Шаг 5: обновить README**

В `packages/poker-engine/README.md` найти описание `bounty-ev`, убрать `--split` из
примера и добавить строку: «`--bounty` — число, показанное над игроком на экране; оно
и есть наличные за нокаут».

- [ ] **Шаг 6: прогнать весь сьют**

Run: `.venv/Scripts/python -m pytest`
Expected: все зелёные. Если падает тест CLI на `--split` — удалить его, это и есть
намеренное ломающее изменение.

- [ ] **Шаг 7: коммит**

```bash
git add src/poker_engine/bounty.py src/poker_engine/cli.py tests/test_bounty.py \
        README.md
git commit -m "fix(engine): наличные за нокаут равны показанному ценнику, не его половине

Ломающее изменение контракта: --split убран из bounty-ev. Правильного
значения у флага нет — доля следует из того, что показано на экране."
```

**Приёмка задачи 5:**
1. `knockout_cash(1.50)` возвращает `1.50`.
2. Тест на сохранение баунти-фонда проходит и записан как арифметика, а не как
   ожидаемое число.
3. `DEFAULT_SPLIT` и `_check_split` не остались мёртвым кодом.
4. README не упоминает `--split`.
5. Весь сьют зелёный.

---

## Задача 6: PKO в разборе

**Files:**
- Modify: `src/poker_engine/handstate.py` (поле `bounty_usd` у `Seat`, разбор и валидация)
- Modify: `src/poker_engine/analyze.py` (блок `bounty` в ответе, пометка `pko`)
- Modify: `tests/test_handstate.py`, `tests/test_analyze.py`

**Interfaces:**
- Consumes: `bounty.knockout_cash`, `bounty.own_bounty_growth`,
  `bounty.required_equity_with_bounty` (Задача 5).
- Produces: `Seat.bounty_usd: float | None`; ключ `result["bounty"]` в ответе `analyze`.

**Признак PKO — наличие ценников**, а не настройка (спека §5.1). Если ценник есть хоть у
одного места, он обязан быть у героя: без собственного ценника неизвестно, что герой
теряет при вылете.

**Что считается и что не считается.** В решении участвуют ровно две величины: ценник
соперника (можно выиграть) и ценник героя (можно потерять). Уже взятые баунти не
участвуют никогда — они на балансе и от исхода раздачи не зависят (спека §5.3).

**Ценность головы в фишках** требует цены фишки. Она берётся как сумма лесенки, делённая
на общее число фишек в турнире: `ladder.total() / (players_left * average_stack_bb)`.
На финальном столе, где среднего стека может не быть, берётся сумма стеков стола.

- [ ] **Шаг 1: написать падающий тест**

Добавить в `tests/test_analyze.py`:

```python
def bounty_node(base, prices):
    """Узел с ценниками голов.

    `prices` — словарь `seatIndex -> цена в долларах`, передаётся позиционно:
    номера мест целые, а через `**kwargs` целые ключи не проходят.
    """
    node = copy.deepcopy(base)
    node["seats"] = [
        {**seat, "bountyUsd": prices.get(seat["seatIndex"])}
        for seat in node["seats"]
    ]
    return node


def test_a_table_without_prices_is_not_a_pko(analyze_base_result):
    assert "pko" not in analyze_base_result["flags"]
    assert "bounty" not in analyze_base_result


def test_prices_on_the_table_make_it_a_pko(run_analyze, analyze_node):
    result = run_analyze(node=bounty_node(analyze_node, {4: 1.50, 7: 1.50}))
    assert "pko" in result["flags"]


def test_the_cash_for_a_knockout_is_the_price_shown(run_analyze, analyze_node):
    result = run_analyze(node=bounty_node(analyze_node, {4: 2.25, 7: 1.50}))
    assert result["bounty"]["villainPriceUsd"] == pytest.approx(2.25)
    assert result["bounty"]["knockoutCashUsd"] == pytest.approx(2.25)
    assert result["bounty"]["ownPriceGrowthUsd"] == pytest.approx(1.125)


def test_the_hero_own_price_is_reported_as_at_risk(run_analyze, analyze_node):
    result = run_analyze(node=bounty_node(analyze_node, {4: 1.50, 7: 3.00}))
    assert result["bounty"]["heroPriceAtRiskUsd"] == pytest.approx(3.00)


def test_a_bounty_lowers_the_required_equity(run_analyze, analyze_node):
    without = run_analyze()["requiredEquity"]
    with_head = run_analyze(node=bounty_node(analyze_node, {4: 5.00, 7: 1.50}))
    assert with_head["bounty"]["requiredEquityWithBounty"] < without


def test_a_price_on_the_villain_but_not_on_the_hero_is_rejected(
    run_analyze, analyze_node
):
    with pytest.raises(ValueError, match="ценник героя"):
        run_analyze(node=bounty_node(analyze_node, {4: 1.50}))


def test_a_negative_price_is_rejected(run_analyze, analyze_node):
    with pytest.raises(
        ValueError, match="ценник на месте 4 не может быть отрицательным"
    ):
        run_analyze(node=bounty_node(analyze_node, {4: -1.0, 7: 1.50}))


def test_the_two_halves_of_equity_stay_separate(run_analyze, analyze_node):
    """Инварианты 10 и «раздельно» спеки (§5.3, §8.2).

    Эквити в лесенке не зависит от ценников голов ни в одну сторону: это
    два разных куска денег, и складывать их в одно число запрещено. Тест
    сторожит именно это — при выросших вдвое ценниках `icm.heroEquity`
    обязано остаться тем же числом, а меняться обязан только блок
    `bounty`. Заодно это и есть проверка, что уже взятые баунти никуда не
    просачиваются: в контракте их нет, а ответ зависит только от того, что
    висит на экране сейчас.
    """
    cheap = run_analyze(node=bounty_node(analyze_node, {4: 1.50, 7: 1.50}))
    rich = run_analyze(node=bounty_node(analyze_node, {4: 3.00, 7: 3.00}))
    assert rich["icm"] == cheap["icm"]
    assert rich["bounty"]["knockoutCashUsd"] > cheap["bounty"]["knockoutCashUsd"]
```

- [ ] **Шаг 2: убедиться, что тесты падают**

Run: `.venv/Scripts/python -m pytest tests/test_analyze.py -k bounty -v`
Expected: FAIL, `KeyError: 'bounty'`

- [ ] **Шаг 3: поле в `Seat`**

В `src/poker_engine/handstate.py` добавить в `Seat` поле
`bounty_usd: float | None` и в `node_from_dict` — его разбор:
`bounty_usd=_as_optional_float(raw_seat, "bountyUsd")`.

В `_validate_node` добавить:

```python
    priced = [seat for seat in node.seats if seat.bounty_usd is not None]
    for seat in priced:
        check_non_negative(seat.bounty_usd, f"ценник на месте {seat.seat_index}")
    if priced and node.hero.bounty_usd is None:
        raise ValueError(
            "у соперников есть ценники голов, а ценник героя не прочитан: "
            "без него неизвестно, что герой теряет при вылете"
        )
```

- [ ] **Шаг 4: блок в ответе**

В `src/poker_engine/analyze.py`, после блока `requiredEquity` и внутри ветки, где
соперник определён:

```python
    if villain.bounty_usd is not None and hero.bounty_usd is not None:
        result["flags"].append("pko")
        chips_in_play = node.players_left * (
            context.average_stack_bb
            if context.average_stack_bb is not None
            else sum(table) / len(table)
        )
        chip_value = ladder.total() / chips_in_play
        result["bounty"] = {
            "villainPriceUsd": villain.bounty_usd,
            "knockoutCashUsd": knockout_cash(villain.bounty_usd),
            "ownPriceGrowthUsd": own_bounty_growth(villain.bounty_usd),
            "heroPriceAtRiskUsd": hero.bounty_usd,
            "chipValueUsd": chip_value,
        }
        if node.to_call_bb > 0:
            result["bounty"]["requiredEquityWithBounty"] = (
                required_equity_with_bounty(
                    node.pot_bb,
                    node.to_call_bb,
                    villain.stack_bb,
                    villain.bounty_usd,
                    chip_value,
                )
            )
```

- [ ] **Шаг 5: прогнать тесты**

Run: `.venv/Scripts/python -m pytest`
Expected: все зелёные.

- [ ] **Шаг 6: коммит**

```bash
git add src/poker_engine/handstate.py src/poker_engine/analyze.py \
        tests/test_handstate.py tests/test_analyze.py
git commit -m "feat(engine): PKO в разборе — ценники голов со стола"
```

**Приёмка задачи 6:**
1. Турнир без ценников не получает ни `pko`, ни ключа `bounty`, и ни одна функция
   `bounty.py` при его разборе не вызывается.
2. Ценник у соперника без ценника у героя — отказ с внятным текстом.
3. Эквити лесенки и эквити голов лежат в ответе раздельно, не сложены в одно число.
4. Нигде не появилась константа «баунти — половина фонда».
5. Весь сьют зелёный.

---

## Задача 7: защита на баббле

**Files:**
- Modify: `src/poker_engine/handstate.py` (`bubble_refund_usd` в контексте)
- Modify: `src/poker_engine/analyze.py`
- Modify: `tests/test_analyze.py`

**Interfaces:**
- Produces: `TournamentContext.bubble_refund_usd: float | None`; ключ
  `result["bubbleProtection"]`; пометка `bubble_protection`.

**Что это.** Спека §6. GG возвращает бай-ин игроку, вылетевшему на баббле («ранняя
пташка»). Классическая математика бабла исходит из того, что вылет даёт ноль; возврат
уменьшает давление лесенки.

**Как моделируется.** Компенсация — это приз за место сразу за последним оплачиваемым.
То есть лесенка удлиняется на одно значение: места от `places_paid + 1` до
`players_left` платят `bubble_refund_usd`. Отдельного расчёта не нужно — достаточно
удлинить `PayoutLadder`, и вся модель учтёт это сама.

**Почему видно отдельной строкой.** Пользователь обязан видеть, что именно смягчило
давление, иначе число выглядит как ошибка. В ответе показываются обе риск-премии — с
поправкой и без.

**Границы модели.** Где именно кончается бабл, спека оставила открытым вопросом (§11.2).
Здесь принимается простейшее прочтение: компенсация действует на всех местах хуже
последнего оплачиваемого. Это допущение записывается в docstring и в журнал.

- [ ] **Шаг 1: написать падающий тест**

Добавить в `tests/test_analyze.py`:

```python
def test_bubble_protection_is_absent_by_default(analyze_base_result):
    assert "bubble_protection" not in analyze_base_result["flags"]
    assert "bubbleProtection" not in analyze_base_result


def test_a_refund_softens_the_ladder_pressure(run_analyze, analyze_context):
    # Бабл: девять живых на шесть оплачиваемых мест. Без этого, при
    # playersLeft=6 по умолчанию, все уже в деньгах и смягчать нечего.
    tight = dict(analyze_context)
    tight["placesPaid"] = 6
    without = run_analyze(context=tight, playersLeft=9, heroRank=9)

    protected = dict(tight)
    protected["bubbleRefundUsd"] = 6.60
    with_refund = run_analyze(context=protected, playersLeft=9, heroRank=9)

    assert "bubble_protection" in with_refund["flags"]
    assert with_refund["riskPremium"] < without["riskPremium"]


def test_both_risk_premiums_are_reported(run_analyze, analyze_context):
    protected = dict(analyze_context)
    protected["placesPaid"] = 6
    protected["bubbleRefundUsd"] = 6.60
    result = run_analyze(context=protected, playersLeft=9, heroRank=9)
    block = result["bubbleProtection"]
    assert block["refundUsd"] == pytest.approx(6.60)
    assert block["riskPremiumWithoutRefund"] > result["riskPremium"]


def test_a_negative_refund_is_rejected(run_analyze, analyze_context):
    bad = dict(analyze_context)
    bad["bubbleRefundUsd"] = -1.0
    with pytest.raises(
        ValueError, match="возврат бай-ина не может быть отрицательным"
    ):
        run_analyze(context=bad)
```

- [ ] **Шаг 2: убедиться, что тесты падают**

Run: `.venv/Scripts/python -m pytest tests/test_analyze.py -k bubble -v`
Expected: FAIL, `KeyError: 'bubbleProtection'`

- [ ] **Шаг 3: поле в контексте**

В `handstate.py` добавить в `TournamentContext` поле `bubble_refund_usd: float | None`,
в `context_from_dict` — `bubble_refund_usd=_as_optional_float(raw, "bubbleRefundUsd")`,
в `_validate_context` — `check_non_negative(context.bubble_refund_usd, "возврат бай-ина")`
под условием `is not None`.

- [ ] **Шаг 4: удлинить лесенку в `analyze`**

```python
    intervals = [(p.first, p.last, p.amount) for p in context.payouts]
    places_paid = context.places_paid
    if context.bubble_refund_usd:
        # Компенсация — это приз за места хуже последнего оплачиваемого.
        # Модели достаточно удлинённой лесенки: отдельного расчёта нет.
        intervals.append(
            (places_paid + 1, node.players_left, context.bubble_refund_usd)
        )
        places_paid = node.players_left
    ladder = PayoutLadder(intervals, places_paid=places_paid)
```

Риск-премию без поправки считать по лесенке, построенной из исходных интервалов, и
класть в `result["bubbleProtection"]`.

- [ ] **Шаг 5: прогнать весь сьют**

Run: `.venv/Scripts/python -m pytest`
Expected: все зелёные.

- [ ] **Шаг 6: коммит**

```bash
git add src/poker_engine/handstate.py src/poker_engine/analyze.py tests/test_analyze.py
git commit -m "feat(engine): поправка на компенсацию бай-ина при вылете на баббле"
```

**Приёмка задачи 7:**
1. Без `bubbleRefundUsd` в ответе нет ни пометки, ни блока — числа в точности как до
   задачи.
2. Поправка уменьшает риск-премию, и тест это проверяет сравнением, а не константой.
3. Допущение о границах бабла записано в docstring.
4. `ladder_incomplete` не срабатывает ложно от удлинённой лесенки.
5. Весь сьют зелёный.

---

## Задача 8: бюджет двух секунд

**Files:**
- Modify: `src/poker_engine/equity.py`
- Modify: `src/poker_engine/analyze.py` (три вызова ICM вместо семи)
- Modify: `pyproject.toml`, `requirements-dev.lock`
- Test: `tests/test_equity_evaluator.py`, `tests/test_analyze_budget.py`

**Interfaces:**
- Produces: тот же публичный API `equity.py`; внутренняя оценка комбинаций переезжает
  на `eval7`.

**Замеры, на которых стоит задача** (эта машина, Python 3.12):

| Что | Оценок в секунду |
|---|---|
| текущий `_best_hand` на `pokerkit` | 1 934 |
| `StandardHighHand.from_game` на готовых картах | 3 190 |
| `phevaluator.evaluate_cards` | 160 425 |
| **`eval7.evaluate`** | **1 194 297** |

`from_game` даёт всего 1.6× — недостаточно. Берётся `eval7`: 617× к текущему.
`pokerkit` **остаётся в зависимостях** как эталон: тест сверяет порядок рук двух
оценщиков на случайных раздачах.

**Семь вызовов ICM против трёх.** `analyze` считает базовое эквити героя, затем
`risk_premium` и `bubble_factor`, каждая из которых заново считает все три ветви
(сейчас, выигрыш, проигрыш). Ветви считаются один раз и переиспользуются обеими
метриками.

- [ ] **Шаг 1: добавить зависимость**

В `pyproject.toml` в `dependencies` добавить `"eval7>=0.1.11"`.
Установить и дописать точную версию в `requirements-dev.lock`:

```bash
.venv/Scripts/python -m pip install "eval7>=0.1.11"
.venv/Scripts/python -m pip freeze | grep -i eval7 >> requirements-dev.lock
```

- [ ] **Шаг 2: написать тест на согласие оценщиков**

Создать `tests/test_equity_evaluator.py`:

```python
"""Быстрый оценщик обязан ранжировать руки так же, как эталонный pokerkit."""

import random

import eval7
from pokerkit import Card, StandardHighHand

from poker_engine.equity import FULL_DECK


def test_the_fast_evaluator_orders_hands_exactly_like_pokerkit():
    rng = random.Random(20260912)
    disagreements = []
    for _ in range(3000):
        left = rng.sample(FULL_DECK, 7)
        right = rng.sample(FULL_DECK, 7)
        fast = eval7.evaluate([eval7.Card(c) for c in left]) - eval7.evaluate(
            [eval7.Card(c) for c in right]
        )
        slow_left = StandardHighHand.from_game(Card.parse("".join(left[:2])),
                                               Card.parse("".join(left[2:])))
        slow_right = StandardHighHand.from_game(Card.parse("".join(right[:2])),
                                                Card.parse("".join(right[2:])))
        slow = (slow_left > slow_right) - (slow_left < slow_right)
        if (fast > 0) - (fast < 0) != slow:
            disagreements.append((left, right))
    assert disagreements == []
```

- [ ] **Шаг 3: убедиться, что тест проходит до правок**

Run: `.venv/Scripts/python -m pytest tests/test_equity_evaluator.py -v`
Expected: PASS. Если нет — `eval7` использовать нельзя, остановиться и доложить.

- [ ] **Шаг 4: переписать горячий путь**

В `src/poker_engine/equity.py` заменить `_best_hand` и `_score_runout`:

```python
import eval7

_EVAL_CARDS = {code: eval7.Card(code) for code in FULL_DECK}


def _score_runout(
    hands: list[list[str]], board: list[str], wins: list[float]
) -> None:
    board_cards = [_EVAL_CARDS[c] for c in board]
    scores = [
        eval7.evaluate([_EVAL_CARDS[c] for c in hand] + board_cards)
        for hand in hands
    ]
    best = max(scores)
    winners = [i for i, s in enumerate(scores) if s == best]
    share = 1.0 / len(winners)
    for i in winners:
        wins[i] += share
```

Удалить `_best_hand` и импорты `Card`, `StandardHighHand`, `combinations`, если они
больше не используются.

- [ ] **Шаг 5: убедиться, что числа не поехали**

Run: `.venv/Scripts/python -m pytest tests/test_equity.py tests/test_equity_crosscheck.py tests/test_equity_vs_range.py -v`
Expected: все зелёные. Это и есть проверка, что замена оценщика ничего не изменила:
перекрёстная сверка с точным перебором уже существует.

- [ ] **Шаг 6: три вызова ICM вместо семи**

В `analyze.py` посчитать ветви один раз и передать обеим метрикам. Добавить в
`icm_field.py`:

```python
def pressure(
    table: list[float],
    field_count: int,
    field_stack: float,
    ladder: PayoutLadder,
    hero: int,
    villain: int,
) -> tuple[float, float, float]:
    """Эквити героя сейчас плюс риск-премия и bubble factor за один проход.

    Все три ветви ICM считаются один раз: раньше `risk_premium` и
    `bubble_factor` считали их по отдельности, давая семь вызовов на разбор
    вместо трёх.
    """
    now, win, lose = _branches(
        table, field_count, field_stack, ladder, hero, villain, None
    )
    return now, _risk_premium_from(now, win, lose), _bubble_factor_from(now, win, lose)
```

и вынести тела `risk_premium`/`bubble_factor` в `_risk_premium_from` /
`_bubble_factor_from`, оставив публичные функции тонкими обёртками — их тесты из
Задачи 3 обязаны продолжать проходить без изменений.

- [ ] **Шаг 7: тест на бюджет**

Создать `tests/test_analyze_budget.py`:

```python
"""Приёмка плана: разбор укладывается в две секунды."""

import time

import pytest

from poker_engine.analyze import analyze

BUDGET_SECONDS = 2.0


def test_a_full_analysis_fits_the_budget(analyze_context, analyze_node):
    start = time.perf_counter()
    analyze(analyze_context, [analyze_node])
    elapsed = time.perf_counter() - start
    assert elapsed < BUDGET_SECONDS, (
        f"разбор занял {elapsed:.2f} с при бюджете {BUDGET_SECONDS} с"
    )


def test_the_icm_half_of_the_budget_is_spent_three_times_not_seven(
    analyze_context, analyze_node, monkeypatch
):
    from poker_engine import icm_field

    calls = []
    original = icm_field.table_equities

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(icm_field, "table_equities", counted)
    analyze(analyze_context, [analyze_node])
    assert len(calls) <= 3, f"ICM посчитан {len(calls)} раз вместо трёх"
```

- [ ] **Шаг 8: прогнать весь сьют и замерить**

Run: `.venv/Scripts/python -m pytest`
Expected: все зелёные, включая оба теста бюджета.

- [ ] **Шаг 9: коммит**

```bash
git add src/poker_engine/equity.py src/poker_engine/icm_field.py \
        src/poker_engine/analyze.py pyproject.toml requirements-dev.lock \
        tests/test_equity_evaluator.py tests/test_analyze_budget.py
git commit -m "perf(engine): eval7 в горячем пути и три расчёта ICM вместо семи"
```

**Приёмка задачи 8:**
1. Тест согласия `eval7` с `pokerkit` проходит на 3000 пар без единого расхождения.
2. `tests/test_equity_crosscheck.py` проходит без правок — числа не поехали.
3. `table_equities` вызывается не больше трёх раз за разбор, и это проверено тестом,
   а не глазами.
4. Разбор укладывается в 2 секунды на 6-max фикстуре.
5. `eval7` записан и в `pyproject.toml`, и в `requirements-dev.lock` точной версией.
6. `pokerkit` остался в зависимостях как эталон.
7. Весь сьют зелёный.

---

## Финал

- [ ] Финальное ревью всей ветки против спеки целиком, тем же циклом «ревью → починка →
      ревью» до `НАХОДОК НЕТ`.
- [ ] Журнал в `docs/superpowers/state/2026-09-12-icm-field-execution-notes.md`:
      что решено против текста плана, какие тесты удалены и почему, замеры до и после,
      что осталось отложенным.
- [ ] Обновить `CLAUDE.md`: текущее состояние, таблица документов, точка входа.
- [ ] Открытые вопросы спеки §11, не закрытые планом, перенести в журнал списком.
