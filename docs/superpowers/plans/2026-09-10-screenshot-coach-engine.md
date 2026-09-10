# Screenshot Coach — Engine Extensions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Расширить `packages/poker-engine` до состояния, в котором одна команда
`poker-engine analyze` принимает JSON состояния раздачи, полученный из скриншота, и
возвращает JSON со всеми доказуемыми числами и честными пометками о том, что расчётом не является.

**Architecture:** Семь модулей поверх готового ядра. `ranges.py` разбирает нотацию диапазонов
в комбинации. `equity_vs_range` считает эквити героя против диапазона, а не против конкретной
руки. `data/preflop_order.json` — порядок силы 169 стартовых классов, **вычисленный движком**,
а не выписанный по памяти; `profiles.py` строит по нему диапазон соперника из его VPIP.
`field.py` сворачивает поле из сотен игроков к 12–15 узлам, которые Malmuth-Harville считает
мгновенно. `handstate.py` описывает схему раздачи и детерминированно её проверяет. `analyze`
связывает всё в одну команду — единственную, которую будет вызывать Nuxt.

**Tech Stack:** Python 3.12, pokerkit 0.7.5, pytest 9.1.1, только стандартная библиотека сверх
этого. Новые зависимости не добавляются.

**Spec:** `docs/superpowers/specs/2026-09-10-screenshot-coach-design.md`

## Global Constraints

- `requires-python = ">=3.11"`. Новых зависимостей не добавлять — в частности, **pydantic не
  используется**, схема раздачи описывается `dataclass`-ами. Раздел 8 основной спеки упоминает
  pydantic; здесь он сознательно не берётся ради нулевого прироста зависимостей.
- Тексты `ValueError` из движка — пользовательские сообщения об ошибках (конвенция
  `CLAUDE.md`). Сообщения на русском. Существующие тексты менять нельзя без правки тестов.
- Общие **скалярные** гарды живут только в `src/poker_engine/_checks.py`: `check_positive`,
  `check_non_negative`, `check_probability`. Не копировать их в новые модули. Имя гарда —
  всегда имя ограничения, не предметной области; тексты сообщений собираются из параметра
  `name`, поэтому переименования гардов пользователю не видны.
  (`check_pot` → `check_non_negative` в Task 4, `check_amount` → `check_positive` между
  Tasks 4 и 5 — см. раздел «Между Task 4 и Task 5».)
- **Карточные гарды в `_checks.py` не переезжают.** `_parse_cards`, `_parse_board`,
  `_check_duplicates` остаются в `equity.py` рядом с `FULL_DECK`: они не скалярные, а перенос
  тянул бы за собой константы колоды и создавал цикл импорта (`equity.py` импортирует
  `_checks`). Новым модулям — импортировать их из `equity.py`, а не писать свою проверку.
- Тесты — аналитические инварианты, проверяемые на бумаге, а не числа, вспомненные моделью.
  Если тест содержит константу вроде `0.4412`, он написан неправильно.
- Один коммит на задачу, Conventional Commits. Правки ревью — отдельными `fix(engine): …`.
- Все команды из `packages/poker-engine`: интерпретатор `.venv/Scripts/python`.
- Полный прогон перед коммитом каждой задачи: `.venv/Scripts/python -m pytest`. На старте
  плана — 80 зелёных тестов, ни одного skip, ни одного xfail. Это число обязано только расти.
- Единица точности стеков — 0.1 BB: ровно то, что печатает клиент GG (`72.2 BB`).

---

### Task 1: Разбор диапазонов рук

**Files:**
- Create: `src/poker_engine/ranges.py`
- Test: `tests/test_ranges.py`

**Interfaces:**
- Consumes: `RANKS`, `SUITS`, `FULL_DECK` из `src/poker_engine/equity.py`.
- Produces: `parse_range(text: str) -> list[str]` — отсортированный список комбинаций вида
  `"AsKh"` (4 символа, две различные карты), без дублей. Используется в Task 2, 4, 7.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_ranges.py`:

```python
"""Инварианты разбора диапазонов. Числа здесь — комбинаторика, а не память."""

import pytest

from poker_engine.equity import FULL_DECK
from poker_engine.ranges import parse_range


def test_pair_has_six_combos():
    # C(4,2) способов выбрать две масти из четырёх.
    assert len(parse_range("AA")) == 6


def test_suited_has_four_combos():
    # По одной комбинации на каждую из четырёх мастей.
    assert len(parse_range("AKs")) == 4


def test_offsuit_has_twelve_combos():
    # 4 масти старшей × 3 оставшиеся масти младшей.
    assert len(parse_range("AKo")) == 12


def test_unsuffixed_class_is_suited_plus_offsuit():
    assert len(parse_range("AK")) == len(parse_range("AKs")) + len(parse_range("AKo"))


def test_all_pairs_plus_covers_thirteen_ranks():
    # 13 рангов × 6 комбинаций.
    assert len(parse_range("22+")) == 78


def test_suited_plus_walks_the_lower_rank_up():
    # ATs, AJs, AQs, AKs — четыре класса по четыре комбинации.
    assert len(parse_range("ATs+")) == 16


def test_plus_ranges_are_nested():
    assert set(parse_range("ATs+")) < set(parse_range("A9s+"))


def test_explicit_combo_is_a_single_entry():
    assert parse_range("AsKh") == ["AsKh"]


def test_comma_list_is_the_union():
    assert set(parse_range("AA,KK")) == set(parse_range("AA")) | set(parse_range("KK"))


def test_overlapping_tokens_do_not_duplicate():
    assert len(parse_range("AA,AA")) == 6


def test_every_combo_is_two_distinct_real_cards():
    for combo in parse_range("22+,ATs+,KQo"):
        assert len(combo) == 4
        first, second = combo[:2], combo[2:]
        assert first != second
        assert first in FULL_DECK
        assert second in FULL_DECK


def test_result_is_sorted_and_unique():
    combos = parse_range("22+,A2s+")
    assert combos == sorted(combos)
    assert len(combos) == len(set(combos))


@pytest.mark.parametrize(
    "text",
    ["", "AA,", "XX", "AAs", "AsKs+", "AsAs", "A", "AKx", "9Ts"],
)
def test_bad_input_is_rejected(text):
    with pytest.raises(ValueError):
        parse_range(text)
```

Пояснение к `"9Ts"`: старший ранг обязан идти первым, `9T` записан задом наперёд.

- [ ] **Step 2: Запустить и убедиться, что тест падает**

Run: `.venv/Scripts/python -m pytest tests/test_ranges.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'poker_engine.ranges'`

- [ ] **Step 3: Реализовать**

Создать `src/poker_engine/ranges.py`:

```python
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

from .equity import FULL_DECK, RANKS, SUITS


def parse_range(text: str) -> list[str]:
    """Комбинации диапазона: отсортированный список строк вида "AsKh"."""
    combos: set[str] = set()
    for token in (t.strip() for t in text.split(",")):
        if not token:
            raise ValueError(f"пустой элемент в диапазоне: {text!r}")
        combos |= _expand(token)
    if not combos:
        raise ValueError(f"пустой диапазон: {text!r}")
    return sorted(combos)


def _combo(first: str, second: str) -> str:
    """Каноническая запись комбинации — порядок карт фиксирован сортировкой."""
    low, high = sorted((first, second))
    return low + high


def _expand(token: str) -> set[str]:
    plus = token.endswith("+")
    body = token[:-1] if plus else token

    if len(body) == 4 and body[1] in SUITS and body[3] in SUITS:
        if plus:
            raise ValueError(f"'+' неприменим к конкретной комбинации: {token!r}")
        first, second = body[:2], body[2:]
        for card in (first, second):
            if card not in FULL_DECK:
                raise ValueError(f"неизвестная карта: {card!r}")
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
    for l in lows:
        out |= _two_rank_combos(hi, l, suitedness)
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
```

- [ ] **Step 4: Запустить тесты — должны пройти**

Run: `.venv/Scripts/python -m pytest tests/test_ranges.py -v`
Expected: PASS, 21 собранный тест — 12 функций плюс параметризация из 9 входов.

- [ ] **Step 5: Полный прогон**

Run: `.venv/Scripts/python -m pytest`
Expected: PASS, ранее зелёные 80 тестов остаются зелёными.

- [ ] **Step 6: Коммит**

```bash
git add src/poker_engine/ranges.py tests/test_ranges.py
git commit -m "feat(engine): разбор нотации диапазонов рук"
```

---

### Task 2: Эквити против диапазона

**Files:**
- Modify: `src/poker_engine/equity.py` (добавить функцию после `hand_equity`)
- Modify: `src/poker_engine/cli.py` (подкоманда `equity`: новые флаги и ветка диспетчера)
- Test: `tests/test_equity_vs_range.py`
- Test: `tests/test_cli.py` (добавить два теста)

**Interfaces:**
- Consumes: `parse_range` из Task 1; `_parse_cards`, `_parse_board`, `_check_duplicates`,
  `_score_runout`, `FULL_DECK` из `equity.py`; `check_positive` из `_checks.py`
  (на момент исполнения Task 2 гард звался `check_amount`).
- Produces: `equity_vs_range(hero: str, villain_range: list[str], board: list[str],
  trials: int = 10_000, seed: int | None = None) -> list[float]` — два числа, `[герой, соперник]`,
  в сумме ровно 1. Используется в Task 3 и Task 7.
- Produces: CLI `poker-engine equity --hero JhTh --vs-range "22+,ATs+" [--board 8c,2s,9d]`.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_equity_vs_range.py`:

```python
"""Инварианты эквити против диапазона.

Ни одно ожидание здесь не является запомненным числом: это либо тождества
(сумма долей банка равна единице), либо факты, доказуемые без счёта
(против одной пары тузов у тузов ровно половина — банк всегда делится).
"""

import pytest

from poker_engine.equity import equity_vs_range, hand_equity
from poker_engine.ranges import parse_range

TRIALS = 20_000
SEED = 7


def test_shares_sum_to_one():
    shares = equity_vs_range("JhTh", parse_range("22+"), [], TRIALS, SEED)
    assert len(shares) == 2
    assert sum(shares) == pytest.approx(1.0)


def test_seed_makes_result_reproducible():
    first = equity_vs_range("JhTh", parse_range("AK"), [], TRIALS, SEED)
    second = equity_vs_range("JhTh", parse_range("AK"), [], TRIALS, SEED)
    assert first == second


def test_range_of_one_combo_agrees_with_direct_equity():
    # Диапазон из одной комбинации — это и есть конкретная рука.
    # Обе стороны выборочные, поэтому допуск масштаба выборки, а не 1e-9.
    ranged = equity_vs_range("JhTh", ["AsKd"], [], TRIALS, SEED)
    direct = hand_equity(["JhTh", "AsKd"], [], TRIALS, SEED)
    assert ranged[0] == pytest.approx(direct[0], abs=0.02)


def test_aces_against_only_aces_split_the_pot():
    # Единственная оставшаяся комбинация тузов после блокеров — всегда ничья.
    # Результат точный при любом числе прогонов, поэтому допуск нулевой.
    shares = equity_vs_range("AsAh", parse_range("AA"), [], 200, SEED)
    assert shares[0] == pytest.approx(0.5)


def test_best_starting_hand_is_never_behind_a_range():
    shares = equity_vs_range("AsAh", parse_range("22+,A2s+,K2s+"), [], TRIALS, SEED)
    assert shares[0] >= 0.5


def test_complete_board_needs_no_sampling():
    # Доска дорисована: исход каждой комбинации диапазона определён,
    # и число прогонов на результат не влияет.
    board = ["8c", "2s", "9d", "4c", "Tc"]
    few = equity_vs_range("JhTh", parse_range("AA"), board, 50, SEED)
    many = equity_vs_range("JhTh", parse_range("AA"), board, 5_000, SEED)
    assert few[0] == pytest.approx(many[0])


def test_range_fully_blocked_by_known_cards_is_rejected():
    with pytest.raises(ValueError):
        equity_vs_range("AsAh", parse_range("AA"), ["Ad", "Ac", "2s"], TRIALS, SEED)


def test_hero_card_duplicated_on_board_is_rejected():
    with pytest.raises(ValueError):
        equity_vs_range("AsAh", parse_range("KK"), ["As", "2s", "3d"], TRIALS, SEED)


def test_non_positive_trials_rejected():
    with pytest.raises(ValueError):
        equity_vs_range("JhTh", parse_range("AA"), [], 0, SEED)
```

Пояснение к `test_aces_against_only_aces_split_the_pot`: у героя `AsAh`, диапазон `AA` даёт
шесть комбинаций, пять из них блокированы, остаётся `AdAc` — одинаковая рука, всегда сплит.

Пояснение к `test_complete_board_needs_no_sampling`: доска из пяти карт, рука соперника
выбирается из диапазона `AA` (четыре живые комбинации), исход каждой определён. Средневзвешенное
по выборке из четырёх равновероятных исходов при большом числе прогонов совпадает — но чтобы
тест был точным, а не почти точным, реализация обязана при полной доске перебирать диапазон
целиком, а не сэмплировать.

- [ ] **Step 2: Запустить и убедиться, что тест падает**

Run: `.venv/Scripts/python -m pytest tests/test_equity_vs_range.py -v`
Expected: FAIL — `ImportError: cannot import name 'equity_vs_range'`

- [ ] **Step 3: Реализовать функцию**

Добавить в `src/poker_engine/equity.py` сразу после `hand_equity`:

```python
def equity_vs_range(
    hero: str,
    villain_range: list[str],
    board: list[str],
    trials: int = 10_000,
    seed: int | None = None,
) -> list[float]:
    """Доли банка героя и соперника, чья рука случайна внутри диапазона.

    hero — строка вида "JhTh".
    villain_range — комбинации из `ranges.parse_range`.
    Комбинации, конфликтующие с картами героя или доской, исключаются:
    соперник не может держать карту, которую мы уже видим.

    При дорисованной доске диапазон перебирается целиком и результат
    точен; иначе идёт Monte-Carlo по паре (комбинация, ранаут).
    """
    hero_cards = _parse_cards(hero, expected=2, label="рука")
    parsed_board = _parse_board(board)
    _check_duplicates(hero_cards + parsed_board)
    check_positive(trials, "trials")

    blocked = set(hero_cards) | set(parsed_board)
    live: list[list[str]] = []
    for combo in villain_range:
        cards = _parse_cards(combo, expected=2, label="комбинация")
        if not blocked.intersection(cards):
            live.append(cards)
    if not live:
        raise ValueError("диапазон соперника пуст после исключения известных карт")

    need = 5 - len(parsed_board)
    wins = [0.0, 0.0]

    if need == 0:
        for villain in live:
            _score_runout([hero_cards, villain], parsed_board, wins)
        total = len(live)
    else:
        rng = random.Random(seed)
        for _ in range(trials):
            villain = rng.choice(live)
            deck = [c for c in FULL_DECK if c not in blocked and c not in villain]
            extra = rng.sample(deck, need)
            _score_runout([hero_cards, villain], parsed_board + extra, wins)
        total = trials

    return [w / total for w in wins]
```

- [ ] **Step 4: Запустить тесты функции**

Run: `.venv/Scripts/python -m pytest tests/test_equity_vs_range.py -v`
Expected: PASS, 9 тестов.

- [ ] **Step 5: Написать падающие тесты CLI**

Добавить в конец `tests/test_cli.py`. В файле уже есть хелпер
`run(argv, capsys) -> tuple[int, dict]` (`tests/test_cli.py:10`) — использовать его, второй
способ вызова рядом не заводить:

```python
def test_equity_accepts_a_range(capsys):
    code, data = run(
        [
            "equity",
            "--hero", "JhTh",
            "--vs-range", "AA",
            "--board", "8c,2s,9d,4c,Tc",
        ],
        capsys,
    )
    assert code == 0
    assert len(data["equity"]) == 2
    assert sum(data["equity"]) == pytest.approx(1.0)


def test_equity_without_hands_or_range_is_a_json_error(capsys):
    code, data = run(["equity", "--board", "8c,2s,9d"], capsys)
    assert code == 1
    assert "error" in data


def test_equity_rejects_hands_and_range_together(capsys):
    code, data = run(
        ["equity", "--hands", "JhTh,AsKd", "--hero", "JhTh", "--vs-range", "AA"],
        capsys,
    )
    assert code == 1
    assert "error" in data
```

- [ ] **Step 6: Запустить и убедиться, что падает**

Run: `.venv/Scripts/python -m pytest tests/test_cli.py -v`
Expected: FAIL — `unrecognized arguments: --hero`

- [ ] **Step 7: Расширить CLI**

В `src/poker_engine/cli.py`:

1. К импортам добавить:

```python
from .equity import equity_vs_range, hand_equity
from .ranges import parse_range
```

2. В `_build_parser`, подкоманда `equity` — снять `required` с `--hands` и добавить два флага:

```python
    p_eq = sub.add_parser("equity", help="эквити рук")
    p_eq.add_argument("--hands", type=_str_list, default=None)
    p_eq.add_argument("--hero", type=str, default=None)
    p_eq.add_argument("--vs-range", dest="vs_range", type=str, default=None)
    p_eq.add_argument("--board", type=_str_list, default=[])
    p_eq.add_argument("--trials", type=int, default=10_000)
    p_eq.add_argument("--seed", type=int, default=None)
```

3. В `_dispatch` заменить ветку `equity` на:

```python
    if args.command == "equity":
        if args.vs_range is not None:
            if args.hero is None:
                raise ValueError("для --vs-range нужен --hero")
            if args.hands is not None:
                raise ValueError("--hands и --vs-range взаимоисключающи")
            return {
                "equity": equity_vs_range(
                    args.hero,
                    parse_range(args.vs_range),
                    board=args.board,
                    trials=args.trials,
                    seed=args.seed,
                )
            }
        if args.hands is None:
            raise ValueError("нужен либо --hands, либо --hero вместе с --vs-range")
        return {
            "equity": hand_equity(
                args.hands, board=args.board, trials=args.trials, seed=args.seed
            )
        }
```

Ветка `equity` в `_dispatch` находится примерно на строках 95–105 — сверить по месту, а не по
номеру строки.

- [ ] **Step 8: Полный прогон**

Run: `.venv/Scripts/python -m pytest`
Expected: PASS. Если упал существующий тест, ожидавший `required=True` у `--hands` — это
ожидаемое последствие: снятие `required` меняет текст ошибки argparse на текст движка. Тест
следует обновить под новый текст, а не возвращать `required`, потому что новое сообщение
объясняет обе допустимые формы вызова, а argparse-овское — нет.

- [ ] **Step 9: Коммит**

```bash
git add src/poker_engine/equity.py src/poker_engine/cli.py tests/test_equity_vs_range.py tests/test_cli.py
git commit -m "feat(engine): эквити против диапазона и флаги --hero/--vs-range"
```

---

### Task 3: Порядок силы стартовых рук, вычисленный движком

**Files:**
- Create: `scripts/gen_preflop_order.py`
- Create: `src/poker_engine/data/preflop_order.json` (порождается скриптом, коммитится)
- Create: `src/poker_engine/preflop.py`
- Modify: `pyproject.toml` (включить `data/*.json` в пакет)
- Test: `tests/test_preflop_order.py`

**Interfaces:**
- Consumes: `equity_vs_range` (Task 2), `parse_range` (Task 1).
- Produces: `hand_classes() -> list[str]` — 169 классов вида `"AA"`, `"AKs"`, `"AKo"`.
- Produces: `preflop_order() -> list[dict]` — записи `{"hand": str, "combos": int,
  "equity": float}`, отсортированные по убыванию эквити. Используется в Task 4.

**Почему так.** Таблица «VPIP → диапазон» требует порядка силы стартовых рук. Выписать его по
памяти — ровно то, что запрещает конвенция репозитория. Поэтому порядок вычисляется: эквити
каждого класса против случайной руки считается тем же движком, результат кладётся в `data/`
и коммитится, чтобы прогон тестов не стоил минут.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_preflop_order.py`:

```python
"""Инварианты вычисленного порядка силы стартовых рук.

Проверяется не «какое эквити у AKs», а структура: полнота перебора,
монотонность сортировки и два факта, доказуемых без счёта — лучшая
и худшая стартовая рука.
"""

from poker_engine.preflop import hand_classes, preflop_order
from poker_engine.ranges import parse_range

TOTAL_COMBOS = 1326  # C(52,2)


def test_there_are_exactly_169_classes():
    # 13 пар + 78 одномастных + 78 разномастных.
    assert len(hand_classes()) == 169
    assert len(set(hand_classes())) == 169


def test_classes_partition_the_whole_deck():
    combos = set()
    for name in hand_classes():
        combos |= set(parse_range(name))
    assert len(combos) == TOTAL_COMBOS


def test_order_covers_every_class_once():
    order = preflop_order()
    assert len(order) == 169
    assert {entry["hand"] for entry in order} == set(hand_classes())


def test_combos_column_matches_the_parser():
    for entry in preflop_order():
        assert entry["combos"] == len(parse_range(entry["hand"]))


def test_combos_sum_to_the_whole_deck():
    assert sum(entry["combos"] for entry in preflop_order()) == TOTAL_COMBOS


def test_order_is_monotone_by_equity():
    values = [entry["equity"] for entry in preflop_order()]
    assert values == sorted(values, reverse=True)


def test_every_equity_is_a_probability():
    for entry in preflop_order():
        assert 0.0 < entry["equity"] < 1.0


def test_aces_are_first_and_the_worst_offsuit_hand_is_last():
    # Против случайной руки AA — сильнейшая стартовая рука, 32o — слабейшая.
    # Это свойство игры, а не результат конкретного прогона.
    order = preflop_order()
    assert order[0]["hand"] == "AA"
    assert order[-1]["hand"] == "32o"


def test_pairs_beat_their_own_offsuit_kickers():
    # Пара против случайной руки сильнее любой неспаренной руки тех же рангов.
    rank = {entry["hand"]: index for index, entry in enumerate(preflop_order())}
    for pair, weaker in [("KK", "KQo"), ("77", "76o"), ("33", "32o")]:
        assert rank[pair] < rank[weaker]
```

- [ ] **Step 2: Запустить и убедиться, что тест падает**

Run: `.venv/Scripts/python -m pytest tests/test_preflop_order.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'poker_engine.preflop'`

- [ ] **Step 3: Написать модуль чтения**

Создать `src/poker_engine/preflop.py`:

```python
"""Порядок силы 169 стартовых классов, вычисленный против случайной руки.

Данные лежат в `data/preflop_order.json` и порождаются
`scripts/gen_preflop_order.py`. Они вычислены этим же движком, а не
взяты из чарта: конвенция репозитория запрещает числа из памяти.

Соседние по силе классы могут стоять в порядке, продиктованном шумом
выборки — эквити у них различается в третьем знаке. Для построения
диапазонов по VPIP это несущественно: там важна верхняя граница отсечения,
а не точное соседство двух почти равных рук.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .equity import RANKS

_DATA = Path(__file__).parent / "data" / "preflop_order.json"


def hand_classes() -> list[str]:
    """169 стартовых классов: пары, одномастные, разномастные."""
    out: list[str] = []
    for i, high in enumerate(RANKS):
        for j, low in enumerate(RANKS):
            if i == j:
                out.append(high + low)
            elif i > j:
                out.append(high + low + "s")
                out.append(high + low + "o")
    return out


@lru_cache(maxsize=1)
def _load() -> tuple[dict, ...]:
    with _DATA.open(encoding="utf-8") as handle:
        return tuple(json.load(handle))


def preflop_order() -> list[dict]:
    """Классы по убыванию эквити против случайной руки."""
    return [dict(entry) for entry in _load()]
```

- [ ] **Step 4: Написать генератор**

Создать `scripts/gen_preflop_order.py`:

```python
"""Считает эквити каждого стартового класса против случайной руки.

Запуск (из packages/poker-engine, идёт несколько минут):

    .venv/Scripts/python ../../scripts/gen_preflop_order.py

Результат перезаписывает src/poker_engine/data/preflop_order.json.
Внутри класса все комбинации эквивалентны с точностью до перестановки
мастей, поэтому считается по одному представителю на класс.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

from poker_engine.equity import FULL_DECK, equity_vs_range
from poker_engine.preflop import hand_classes
from poker_engine.ranges import parse_range

TRIALS = 20_000
SEED = 20260910
OUT = Path(__file__).resolve().parents[1] / "packages" / "poker-engine" / "src" / "poker_engine" / "data" / "preflop_order.json"

RANDOM_HAND = ["".join(sorted(pair)) for pair in combinations(FULL_DECK, 2)]


def main() -> None:
    rows = []
    for index, name in enumerate(hand_classes(), start=1):
        combos = parse_range(name)
        shares = equity_vs_range(combos[0], RANDOM_HAND, [], TRIALS, SEED)
        rows.append({"hand": name, "combos": len(combos), "equity": round(shares[0], 6)})
        print(f"{index:3}/169  {name:4}  {shares[0]:.4f}", flush=True)

    rows.sort(key=lambda row: row["equity"], reverse=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    print(f"записано {len(rows)} классов в {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Породить данные**

Run: `.venv/Scripts/python ../../scripts/gen_preflop_order.py`
Expected: печатает 169 строк прогресса, затем `записано 169 классов в …preflop_order.json`.
Занимает несколько минут — это разовая цена, в тесты она не входит.

Если `test_aces_are_first_and_the_worst_offsuit_hand_is_last` после генерации падает,
причина — недостаточная выборка на краях: увеличить `TRIALS` и перегенерировать. Не
править данные руками.

- [ ] **Step 6: Включить данные в пакет**

В `pyproject.toml` после блока `[tool.setuptools.packages.find]` добавить:

```toml
[tool.setuptools.package-data]
poker_engine = ["data/*.json"]
```

Без этого `data/preflop_order.json` не попадёт в установленный пакет и `preflop_order()`
упадёт на машине, где ядро поставлено, а не запущено из исходников.

- [ ] **Step 7: Запустить тесты**

Run: `.venv/Scripts/python -m pytest tests/test_preflop_order.py -v`
Expected: PASS, 9 тестов.

- [ ] **Step 8: Полный прогон**

Run: `.venv/Scripts/python -m pytest`
Expected: PASS.

- [ ] **Step 9: Коммит**

```bash
git add scripts/gen_preflop_order.py src/poker_engine/preflop.py src/poker_engine/data/preflop_order.json pyproject.toml tests/test_preflop_order.py
git commit -m "feat(engine): вычисленный порядок силы стартовых рук"
```

---

### Task 4: Диапазон соперника из его VPIP

**Files:**
- Create: `src/poker_engine/profiles.py`
- Test: `tests/test_profiles.py`

**Interfaces:**
- Consumes: `preflop_order` (Task 3), `parse_range` (Task 1).
- Produces: `range_for_vpip(vpip: float | None, hands: int | None) -> tuple[list[str], bool]` —
  комбинации диапазона и флаг «взят дефолт, наблюдению верить нельзя». Используется в Task 7.
- Produces: константы `DEFAULT_VPIP`, `MIN_VPIP_HANDS`, `TOTAL_COMBOS`.

**Модель.** Диапазон на VPIP `v` — верхние `v%` комбинаций по порядку из Task 3. Вложенность
диапазонов гарантирована конструкцией: больший процент берёт префикс того же списка.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_profiles.py`:

```python
"""Инварианты отображения VPIP в диапазон.

Ничего не проверяется про «правильность» конкретного диапазона — это
калибровочный вопрос, открытый в спеке. Проверяется структура: вложенность,
доля от колоды и поведение при недостаточной выборке.
"""

import pytest

from poker_engine.profiles import (
    DEFAULT_VPIP,
    MIN_VPIP_HANDS,
    TOTAL_COMBOS,
    range_for_vpip,
)

MANY = MIN_VPIP_HANDS * 10
MAX_CLASS_SIZE = 12  # самый крупный класс — разномастный, 12 комбинаций


def test_wider_vpip_is_a_superset():
    tight, _ = range_for_vpip(15, MANY)
    loose, _ = range_for_vpip(30, MANY)
    assert set(tight) < set(loose)


def test_share_of_deck_tracks_vpip():
    for vpip in (5, 15, 25, 40, 60):
        combos, _ = range_for_vpip(vpip, MANY)
        target = TOTAL_COMBOS * vpip / 100
        # Диапазон минимально покрывающий: не меньше цели и не больше,
        # чем цель плюс один класс.
        assert target <= len(combos) <= target + MAX_CLASS_SIZE


def test_hundred_percent_is_the_whole_deck():
    combos, _ = range_for_vpip(100, MANY)
    assert len(combos) == TOTAL_COMBOS


def test_zero_vpip_still_yields_a_playable_range():
    # Ноль наблюдённых входов не означает, что соперник не держит карт.
    combos, _ = range_for_vpip(0, MANY)
    assert len(combos) > 0


def test_small_sample_falls_back_to_default_and_says_so():
    combos, used_default = range_for_vpip(3, MIN_VPIP_HANDS - 1)
    reference, _ = range_for_vpip(DEFAULT_VPIP, MANY)
    assert used_default is True
    assert combos == reference


def test_missing_vpip_falls_back_to_default():
    combos, used_default = range_for_vpip(None, None)
    reference, _ = range_for_vpip(DEFAULT_VPIP, MANY)
    assert used_default is True
    assert combos == reference


def test_sufficient_sample_is_not_flagged_as_default():
    _, used_default = range_for_vpip(22, MIN_VPIP_HANDS)
    assert used_default is False


def test_result_is_sorted_and_unique():
    combos, _ = range_for_vpip(35, MANY)
    assert combos == sorted(combos)
    assert len(combos) == len(set(combos))


@pytest.mark.parametrize("vpip", [-1, 101])
def test_impossible_vpip_is_rejected(vpip):
    with pytest.raises(ValueError):
        range_for_vpip(vpip, MANY)


def test_negative_hand_count_is_rejected():
    with pytest.raises(ValueError):
        range_for_vpip(20, -1)
```

- [ ] **Step 2: Запустить и убедиться, что тест падает**

Run: `.venv/Scripts/python -m pytest tests/test_profiles.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'poker_engine.profiles'`

- [ ] **Step 3: Реализовать**

Создать `src/poker_engine/profiles.py`:

```python
"""Диапазон соперника по наблюдённому VPIP.

Клиент GG печатает VPIP бейджем у аватара: доля раздач, в которых игрок
добровольно вложил деньги на префлопе коллом или рейзом. Диапазон на
VPIP `v` — верхние `v%` комбинаций по порядку силы из `preflop.py`.
Вложенность диапазонов следует из конструкции: больший процент берёт
префикс того же списка.

Модель приблизительна и это признано: реальные диапазоны не упорядочены
по эквити против случайной руки — коннекторы в них весят больше, чем даёт
такая сортировка. Калибровка вынесена в открытые вопросы спеки.
"""

from __future__ import annotations

from .preflop import preflop_order
from .ranges import parse_range

TOTAL_COMBOS = 1326

# Калибровочные параметры. Меняются по мере накопления наблюдений;
# ни один из них не является результатом расчёта.
DEFAULT_VPIP = 25.0
MIN_VPIP_HANDS = 30


def range_for_vpip(vpip: float | None, hands: int | None) -> tuple[list[str], bool]:
    """Комбинации диапазона и признак того, что взят дефолт.

    Второй элемент истинен, когда VPIP отсутствует или посчитан по
    выборке меньше `MIN_VPIP_HANDS`. Бейдж `0` у только что подсевшего
    игрока не означает нита, и вывод обязан это помечать.
    """
    if vpip is not None and not 0 <= vpip <= 100:
        raise ValueError(f"VPIP вне диапазона 0..100: {vpip}")
    if hands is not None and hands < 0:
        raise ValueError(f"число раздач не может быть отрицательным: {hands}")

    used_default = vpip is None or hands is None or hands < MIN_VPIP_HANDS
    value = DEFAULT_VPIP if used_default else float(vpip)

    target = TOTAL_COMBOS * value / 100
    combos: set[str] = set()
    for entry in preflop_order():
        if len(combos) >= target:
            break
        combos |= set(parse_range(entry["hand"]))

    return sorted(combos), used_default
```

- [ ] **Step 4: Запустить тесты**

Run: `.venv/Scripts/python -m pytest tests/test_profiles.py -v`
Expected: PASS, 11 тестов.

- [ ] **Step 5: Полный прогон**

Run: `.venv/Scripts/python -m pytest`
Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add src/poker_engine/profiles.py tests/test_profiles.py
git commit -m "feat(engine): диапазон соперника по наблюдённому VPIP"
```

---

### Между Task 4 и Task 5: два закрытых долга

Оба вопроса, оставленных открытыми после Task 4, решены. Первый — чистая правка кода,
отдельным коммитом **до** начала Task 5. Второй решён «оставить как есть» и требует только
одной добавки в Task 6 (уже внесена ниже).

**Files:**
- Modify: `src/poker_engine/_checks.py`, `src/poker_engine/equity.py`,
  `src/poker_engine/bounty.py`, `src/poker_engine/potodds.py`

- [ ] **Step 1: `check_amount` → `check_positive`**

Механическое переименование: определение плюс 6 вызовов (`equity.py` ×2, `potodds.py` ×3,
`bounty.py` ×1). Мотив: `check_amount(trials, "trials")` — «amount» неправда, `trials` не
сумма. После правки все три гарда названы по ограничению, а не по домену: `check_positive`
(`> 0`), `check_non_negative` (`>= 0`), `check_probability` (`[0, 1]` — «быть вероятностью»
и есть это ограничение). Это закрывает вторую половину Minor № 2 ревью плана 1
(`2026-09-09-poker-engine-execution-notes.md:84-86`).

Тексты `ValueError` **не меняются**: они целиком собираются из параметра `name`. Ни один
тест на сообщения править не нужно, `cli.py` `_checks` не импортирует.

Заодно удалить из докстринга `_checks.py` абзац про «две другие функции названы доменно» —
после правки исключения нет, конвенция ровная: имя гарда = имя ограничения.

Проверка: `grep -rn "check_amount" .` по всему репозиторию (включая `tests/`, `.claude/skills/`,
`README`, `docs/`) должен вернуть только исторические упоминания в журналах исполнения.

Run: `.venv/Scripts/python -m pytest`
Expected: PASS, 144 теста, ни одного изменённого текста ошибки.

- [ ] **Step 2: Коммит**

```bash
git add src/poker_engine/_checks.py src/poker_engine/equity.py \
        src/poker_engine/bounty.py src/poker_engine/potodds.py
git commit -m "refactor(engine): check_amount -> check_positive"
```

**Решение по карточным гардам (кода не требует).** `_parse_cards`/`_parse_board`/
`_check_duplicates` **остаются в `equity.py`**. В `_checks.py` им не место: модуль по
контракту скалярный, а перенос потянул бы туда `RANKS`/`SUITS`/`FULL_DECK` либо создал цикл
импорта. Подчёркивание в именах сохраняется — это package-private, легитимно разделяемое
внутри пакета, ровно как сам `_checks.py`. Следствие для Task 6: `handstate.py`
**импортирует** проверку из `equity.py`, а не пишет третью копию (см. Task 6, Step 3).

---

### Task 5: Свёртка турнирного поля для ICM

**Files:**
- Create: `src/poker_engine/field.py`
- Test: `tests/test_field.py`
- Test: `tests/test_icm.py` (добавить один тест масштабной инвариантности)

**Interfaces:**
- Consumes: ничего из предыдущих задач.
- Produces: `reduce_field(table_stacks_bb: list[float], hero_index: int, players_left: int,
  average_stack_bb: float, max_nodes: int = 15) -> list[int]` — стеки в десятых долях BB,
  готовые для `icm_equities`. Индекс героя сохраняется. Используется в Task 7.
- Produces: константа `SCALE = 10`.

**Почему.** Malmuth-Harville перебирает упорядоченные префиксы игроков и на поле из 782 человек
не считается. Реальные стеки со стола сохраняются как есть, остальное поле схлопывается в
несколько узлов «средний игрок» — так, чтобы сумма фишек и доля героя в ней не поехали.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_field.py`:

```python
"""Инварианты свёртки поля.

Проверяется сохранение того, от чего зависит ICM: суммы фишек, доли
героя в ней и его индекса. Точных значений ICM здесь нет — они предмет
`test_icm.py`.
"""

import pytest

from poker_engine.field import SCALE, reduce_field

TABLE = [72.2, 66.1, 94.4, 35.3, 23.2, 39.2, 35.7, 63.3]
HERO = 7


def test_hero_stack_survives_scaling():
    reduced = reduce_field(TABLE, HERO, players_left=782, average_stack_bb=50.5)
    assert reduced[HERO] == round(TABLE[HERO] * SCALE)


def test_table_stacks_come_first_and_in_order():
    reduced = reduce_field(TABLE, HERO, players_left=782, average_stack_bb=50.5)
    assert reduced[: len(TABLE)] == [round(stack * SCALE) for stack in TABLE]


def test_node_count_is_capped():
    reduced = reduce_field(TABLE, HERO, players_left=782, average_stack_bb=50.5, max_nodes=15)
    assert len(reduced) <= 15


def test_total_chips_are_preserved():
    players_left, average = 782, 50.5
    reduced = reduce_field(TABLE, HERO, players_left, average)
    expected = players_left * average * SCALE
    # Допуск — округление каждого узла до 0.1 BB.
    assert sum(reduced) == pytest.approx(expected, abs=len(reduced))


def test_hero_share_of_chips_is_preserved():
    players_left, average = 782, 50.5
    reduced = reduce_field(TABLE, HERO, players_left, average)
    share = reduced[HERO] / sum(reduced)
    expected = TABLE[HERO] / (players_left * average)
    assert share == pytest.approx(expected, rel=1e-3)


def test_field_equal_to_the_table_is_left_alone():
    reduced = reduce_field(TABLE, HERO, players_left=len(TABLE), average_stack_bb=53.675)
    assert reduced == [round(stack * SCALE) for stack in TABLE]


def test_every_stack_is_a_positive_integer():
    reduced = reduce_field(TABLE, HERO, players_left=782, average_stack_bb=50.5)
    assert all(isinstance(stack, int) and stack > 0 for stack in reduced)


def test_field_smaller_than_the_table_is_rejected():
    with pytest.raises(ValueError):
        reduce_field(TABLE, HERO, players_left=3, average_stack_bb=50.5)


def test_average_inconsistent_with_the_table_is_rejected():
    # Стол держит больше фишек, чем всё поле по среднему стеку.
    with pytest.raises(ValueError):
        reduce_field(TABLE, HERO, players_left=10, average_stack_bb=1.0)


def test_hero_index_outside_the_table_is_rejected():
    with pytest.raises(ValueError):
        reduce_field(TABLE, len(TABLE), players_left=782, average_stack_bb=50.5)


def test_cap_below_table_size_is_rejected():
    with pytest.raises(ValueError):
        reduce_field(TABLE, HERO, players_left=782, average_stack_bb=50.5, max_nodes=4)


def test_stack_below_the_printed_precision_is_rejected():
    with pytest.raises(ValueError):
        reduce_field([0.04, 50.0], 0, players_left=2, average_stack_bb=25.02)
```

- [ ] **Step 2: Запустить и убедиться, что тест падает**

Run: `.venv/Scripts/python -m pytest tests/test_field.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'poker_engine.field'`

- [ ] **Step 3: Реализовать**

Создать `src/poker_engine/field.py`:

```python
"""Свёртка турнирного поля до размера, посильного Malmuth-Harville.

`icm_equities` перебирает упорядоченные префиксы игроков; на поле из
сотен человек это не считается. Стеки за столом сохраняются поимённо,
остальное поле схлопывается в несколько узлов «средний игрок» так, что
общая сумма фишек и доля героя в ней сохраняются.

Стеки приходят в BB, потому что клиент печатает их так, а `icm_equities`
принимает целые. ICM инвариантен к общему масштабу стеков, поэтому BB
умножаются на 10 — это ровно та точность, которая напечатана на экране.
"""

from __future__ import annotations

SCALE = 10


def reduce_field(
    table_stacks_bb: list[float],
    hero_index: int,
    players_left: int,
    average_stack_bb: float,
    max_nodes: int = 15,
) -> list[int]:
    """Стеки поля в десятых долях BB: стол как есть, остальные схлопнуты.

    Индекс героя не меняется — стол всегда идёт первым.
    """
    if not table_stacks_bb:
        raise ValueError("за столом нет игроков")
    if not 0 <= hero_index < len(table_stacks_bb):
        raise ValueError(f"индекс героя вне стола: {hero_index}")
    if any(stack <= 0 for stack in table_stacks_bb):
        raise ValueError("стек должен быть больше нуля")
    if players_left < len(table_stacks_bb):
        raise ValueError(
            f"осталось игроков ({players_left}) меньше, чем за столом "
            f"({len(table_stacks_bb)})"
        )
    if average_stack_bb <= 0:
        raise ValueError("средний стек должен быть больше нуля")
    if max_nodes < len(table_stacks_bb):
        raise ValueError(
            f"предел узлов ({max_nodes}) меньше числа мест за столом "
            f"({len(table_stacks_bb)})"
        )

    stacks = list(table_stacks_bb)
    rest_players = players_left - len(table_stacks_bb)

    if rest_players:
        if max_nodes == len(table_stacks_bb):
            raise ValueError("нет места под остальное поле: увеличьте предел узлов")
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
```

- [ ] **Step 4: Запустить тесты свёртки**

Run: `.venv/Scripts/python -m pytest tests/test_field.py -v`
Expected: PASS, 12 тестов.

- [ ] **Step 5: Добавить тест масштабной инвариантности ICM**

Свёртка опирается на то, что ICM не зависит от общего масштаба стеков. Это свойство модели
нигде не закреплено тестом — закрепить. Добавить в `tests/test_icm.py`:

```python
def test_icm_is_invariant_to_stack_scale():
    # Свёртка поля переводит BB в десятые доли BB. Это допустимо только
    # потому, что ICM зависит от долей стеков, а не от их абсолюта.
    payouts = [50.0, 30.0, 20.0]
    base = icm_equities([12, 30, 8, 50], payouts)
    scaled = icm_equities([120, 300, 80, 500], payouts)
    for first, second in zip(base, scaled):
        assert first == pytest.approx(second)
```

Сверить, что `icm_equities` и `pytest` уже импортированы в `tests/test_icm.py`; если нет —
добавить импорт по образцу файла.

- [ ] **Step 6: Полный прогон**

Run: `.venv/Scripts/python -m pytest`
Expected: PASS.

- [ ] **Step 7: Коммит**

```bash
git add src/poker_engine/field.py tests/test_field.py tests/test_icm.py
git commit -m "feat(engine): свёртка турнирного поля для ICM"
```

---

### Task 6: Схема раздачи и её валидатор

**Files:**
- Create: `src/poker_engine/handstate.py`
- Test: `tests/test_handstate.py`

**Interfaces:**
- Consumes: `positions_for`, `Position` из `src/poker_engine/types.py`.
- Consumes: `FULL_DECK` из `equity.py` — проверку личности карт **не писать заново**
  (решение раздела «Между Task 4 и Task 5»). `_parse_cards` здесь не подходит по форме: он
  разбирает склейку `"JhTh"`, а схема Nuxt даёт список `["Jh", "Th"]`. Нужна проверка
  членства в `FULL_DECK`, как в `_parse_board`.
- Produces: `Seat`, `DecisionNode`, `TournamentContext` — фризнутые `dataclass`-ы.
- Produces: `context_from_dict(raw: dict) -> TournamentContext`,
  `node_from_dict(raw: dict) -> DecisionNode` — разбор JSON с camelCase-ключами от Nuxt.
- Produces: `validate_hand(context: TournamentContext, nodes: list[DecisionNode]) -> None` —
  бросает `ValueError` с русским текстом при нарушении.
- Produces: `assign_positions(node: DecisionNode) -> dict[int, Position]` — место → позиция,
  считается от кнопки.
- Produces: `payout_ladder(context: TournamentContext, places: int) -> list[float]` — призовые
  по местам от первого, добитые нулями до `places`.
- Всё используется в Task 7.

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_handstate.py`:

```python
"""Инварианты схемы раздачи и её валидатора.

Каждое правило из раздела 7 спеки имеет здесь свой тест. Базовый узел
корректен; каждый тест ломает ровно одно и проверяет, что валидатор это
ловит.
"""

import pytest

from poker_engine.handstate import (
    assign_positions,
    context_from_dict,
    node_from_dict,
    payout_ladder,
    validate_hand,
)
from poker_engine.types import Position

CONTEXT = {
    "payouts": [
        {"from": 1, "to": 1, "amount": 1090.51},
        {"from": 2, "to": 2, "amount": 840.37},
        {"from": 3, "to": 3, "amount": 648.01},
        {"from": 4, "to": 6, "amount": 400.0},
    ],
    "placesPaid": 165,
    "entrants": 1107,
    "playersLeft": 782,
    "lateRegOpen": True,
    "seatsPerTable": 8,
    "averageStackBb": 50.5,
}


def _seat(index, stack, *, hero=False, in_hand=True, invested=0.0, vpip=25.0, hands=60):
    return {
        "seatIndex": index,
        "name": f"p{index}",
        "stackBb": stack,
        "investedBb": invested,
        "inHand": in_hand,
        "isHero": hero,
        "vpip": vpip,
        "vpipHands": hands,
    }


def _node(**overrides):
    base = {
        "street": "preflop",
        "level": 13,
        "blinds": {"sb": 700, "bb": 1400, "ante": 175},
        "heroRank": 90,
        "playersLeft": 496,
        "seats": [
            _seat(0, 72.2),
            _seat(1, 66.1),
            _seat(2, 94.4),
            _seat(3, 35.3),
            _seat(4, 23.2, invested=7.3),
            _seat(5, 39.2),
            _seat(6, 35.7),
            _seat(7, 63.3, hero=True),
        ],
        "buttonSeat": 4,
        "heroCards": ["Jh", "Th"],
        "board": [],
        "potBb": 9.4,
        "toCallBb": 7.3,
        "raiseToBb": 14.5,
    }
    base.update(overrides)
    return base


def _validate(nodes):
    validate_hand(
        context_from_dict(CONTEXT), [node_from_dict(raw) for raw in nodes]
    )


def test_valid_hand_passes():
    _validate([_node()])


def test_button_seat_gets_the_button_position():
    positions = assign_positions(node_from_dict(_node()))
    assert positions[4] == Position.BTN


def test_positions_run_clockwise_from_the_button():
    positions = assign_positions(node_from_dict(_node()))
    assert positions[5] == Position.SB
    assert positions[6] == Position.BB


def test_positions_are_unique_and_complete():
    positions = assign_positions(node_from_dict(_node()))
    assert len(set(positions.values())) == 8


def test_board_size_must_match_the_street():
    with pytest.raises(ValueError):
        _validate([_node(street="flop", board=["8c", "2s"])])


def test_unknown_street_is_rejected():
    with pytest.raises(ValueError):
        _validate([_node(street="showdown")])


def test_exactly_one_hero_is_required():
    seats = _node()["seats"]
    seats[0]["isHero"] = True
    with pytest.raises(ValueError):
        _validate([_node(seats=seats)])


def test_hero_must_be_in_the_hand():
    seats = _node()["seats"]
    seats[7]["inHand"] = False
    with pytest.raises(ValueError):
        _validate([_node(seats=seats)])


def test_button_seat_must_exist():
    with pytest.raises(ValueError):
        _validate([_node(buttonSeat=99)])


def test_seat_indices_must_be_unique():
    seats = _node()["seats"]
    seats[1]["seatIndex"] = 0
    with pytest.raises(ValueError):
        _validate([_node(seats=seats)])


def test_too_many_seats_are_rejected():
    seats = [_seat(i, 30.0) for i in range(10)]
    seats[0]["isHero"] = True
    with pytest.raises(ValueError):
        _validate([_node(seats=seats, buttonSeat=0)])


def test_negative_stack_is_rejected():
    seats = _node()["seats"]
    seats[2]["stackBb"] = -1.0
    with pytest.raises(ValueError):
        _validate([_node(seats=seats)])


def test_empty_pot_is_rejected():
    with pytest.raises(ValueError):
        _validate([_node(potBb=0.0)])


def test_negative_call_is_rejected():
    with pytest.raises(ValueError):
        _validate([_node(toCallBb=-1.0)])


def test_raise_must_exceed_the_call():
    with pytest.raises(ValueError):
        _validate([_node(toCallBb=7.3, raiseToBb=5.0)])


def test_hero_rank_cannot_exceed_the_field():
    with pytest.raises(ValueError):
        _validate([_node(heroRank=500, playersLeft=496)])


def test_card_outside_the_deck_is_rejected():
    # Источник схемы — vision-модель; "Xz" это не гипотеза.
    with pytest.raises(ValueError, match="неизвестная карта"):
        _validate([_node(heroCards=["Jh", "Xz"])])


def test_board_card_outside_the_deck_is_rejected():
    with pytest.raises(ValueError, match="неизвестная карта"):
        _validate([_node(street="flop", board=["8c", "2s", "9x"])])


def test_hero_must_hold_exactly_two_cards():
    with pytest.raises(ValueError):
        _validate([_node(heroCards=["Jh"])])


def test_duplicate_card_between_hand_and_board_is_rejected():
    with pytest.raises(ValueError):
        _validate([_node(street="flop", board=["Jh", "2s", "9d"], potBb=9.4)])


def test_duplicate_card_inside_the_board_is_rejected():
    with pytest.raises(ValueError):
        _validate([_node(street="flop", board=["8c", "8c", "9d"])])


def test_streets_must_advance():
    first = _node()
    second = _node(street="preflop", potBb=10.0)
    with pytest.raises(ValueError):
        _validate([first, second])


def test_board_must_extend_the_previous_board():
    first = _node(street="flop", board=["8c", "2s", "9d"], potBb=5.9)
    second = _node(street="turn", board=["8c", "2s", "Qd", "4c"], potBb=12.0)
    with pytest.raises(ValueError):
        _validate([first, second])


def test_hero_cards_cannot_change_mid_hand():
    first = _node()
    second = _node(street="flop", board=["8c", "2s", "9d"], heroCards=["Ah", "Kh"])
    with pytest.raises(ValueError):
        _validate([first, second])


def test_a_folded_player_cannot_return():
    seats = _node()["seats"]
    seats[0]["inHand"] = False
    first = _node(seats=seats)
    second = _node(street="flop", board=["8c", "2s", "9d"])
    with pytest.raises(ValueError):
        _validate([first, second])


def test_chips_must_be_conserved_between_nodes():
    first = _node()
    second = _node(street="flop", board=["8c", "2s", "9d"], potBb=900.0)
    with pytest.raises(ValueError):
        _validate([first, second])


def test_rounding_between_nodes_is_tolerated():
    # Клиент печатает стеки с точностью 0.1 BB; сумма по восьми местам
    # может разойтись на эту величину без всякой ошибки распознавания.
    first = _node()
    seats = _node()["seats"]
    seats[0]["stackBb"] = 72.1
    second = _node(street="flop", board=["8c", "2s", "9d"], seats=seats, potBb=9.5)
    _validate([first, second])


def test_payout_ladder_expands_ranges():
    # Интервал 4–6 разворачивается в три одинаковых места.
    ladder = payout_ladder(context_from_dict(CONTEXT), places=12)
    assert ladder[0] == pytest.approx(1090.51)
    assert ladder[3] == pytest.approx(400.0)
    assert ladder[5] == pytest.approx(400.0)


def test_payout_ladder_pads_unpaid_places_with_zero():
    ladder = payout_ladder(context_from_dict(CONTEXT), places=15)
    assert len(ladder) == 15
    assert ladder[6] == 0.0
    assert ladder[14] == 0.0


def test_payout_ladder_must_not_increase_with_place():
    ladder = payout_ladder(context_from_dict(CONTEXT), places=12)
    assert ladder == sorted(ladder, reverse=True)


def test_overlapping_payout_ranges_are_rejected():
    broken = dict(CONTEXT)
    broken["payouts"] = [
        {"from": 1, "to": 3, "amount": 100.0},
        {"from": 3, "to": 5, "amount": 50.0},
    ]
    with pytest.raises(ValueError):
        validate_hand(context_from_dict(broken), [node_from_dict(_node())])


def test_field_smaller_than_the_table_is_rejected():
    with pytest.raises(ValueError):
        _validate([_node(playersLeft=3)])
```

- [ ] **Step 2: Запустить и убедиться, что тест падает**

Run: `.venv/Scripts/python -m pytest tests/test_handstate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'poker_engine.handstate'`

- [ ] **Step 3: Реализовать**

Создать `src/poker_engine/handstate.py`:

```python
"""Схема раздачи, снятой со скриншотов, и её детерминированная проверка.

Раздача — это турнирный контекст плюс упорядоченный список узлов решения,
по одному на скриншот. Отдельного механизма истории нет: весь список и
есть история.

Валидатор запускается до любого расчёта. Он ловит то, что физически
невозможно (дубль карты, вернувшийся в раздачу игрок, несходящиеся фишки),
а не то, что маловероятно. Каждое сообщение об ошибке видит пользователь.
"""

from __future__ import annotations

from dataclasses import dataclass

from .equity import FULL_DECK
from .types import Position, positions_for

STREETS = ("preflop", "flop", "turn", "river")
BOARD_SIZE = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}

# Клиент печатает стеки с точностью 0.1 BB. Сумма по местам расходится
# на величину порядка этого шага, и это не ошибка распознавания.
ROUNDING_STEP_BB = 0.1


@dataclass(frozen=True)
class Seat:
    seat_index: int
    name: str
    stack_bb: float
    invested_bb: float
    in_hand: bool
    is_hero: bool
    vpip: float | None
    vpip_hands: int | None


@dataclass(frozen=True)
class DecisionNode:
    street: str
    level: int
    blinds: dict
    hero_rank: int
    players_left: int
    seats: list[Seat]
    button_seat: int
    hero_cards: list[str]
    board: list[str]
    pot_bb: float
    to_call_bb: float
    raise_to_bb: float | None

    @property
    def hero(self) -> Seat:
        for seat in self.seats:
            if seat.is_hero:
                return seat
        raise ValueError("в узле нет героя")


@dataclass(frozen=True)
class Payout:
    first: int
    last: int
    amount: float


@dataclass(frozen=True)
class TournamentContext:
    payouts: list[Payout]
    places_paid: int
    entrants: int
    players_left: int
    late_reg_open: bool
    seats_per_table: int
    average_stack_bb: float


def _require(raw: dict, key: str):
    if key not in raw:
        raise ValueError(f"в данных нет обязательного поля {key!r}")
    return raw[key]


def context_from_dict(raw: dict) -> TournamentContext:
    payouts = [
        Payout(
            first=int(_require(entry, "from")),
            last=int(_require(entry, "to")),
            amount=float(_require(entry, "amount")),
        )
        for entry in _require(raw, "payouts")
    ]
    return TournamentContext(
        payouts=payouts,
        places_paid=int(_require(raw, "placesPaid")),
        entrants=int(_require(raw, "entrants")),
        players_left=int(_require(raw, "playersLeft")),
        late_reg_open=bool(_require(raw, "lateRegOpen")),
        seats_per_table=int(_require(raw, "seatsPerTable")),
        average_stack_bb=float(_require(raw, "averageStackBb")),
    )


def node_from_dict(raw: dict) -> DecisionNode:
    seats = [
        Seat(
            seat_index=int(_require(entry, "seatIndex")),
            name=str(entry.get("name", "")),
            stack_bb=float(_require(entry, "stackBb")),
            invested_bb=float(entry.get("investedBb", 0.0)),
            in_hand=bool(_require(entry, "inHand")),
            is_hero=bool(entry.get("isHero", False)),
            vpip=None if entry.get("vpip") is None else float(entry["vpip"]),
            vpip_hands=(
                None if entry.get("vpipHands") is None else int(entry["vpipHands"])
            ),
        )
        for entry in _require(raw, "seats")
    ]
    raise_to = raw.get("raiseToBb")
    return DecisionNode(
        street=str(_require(raw, "street")),
        level=int(raw.get("level", 0)),
        blinds=dict(raw.get("blinds", {})),
        hero_rank=int(_require(raw, "heroRank")),
        players_left=int(_require(raw, "playersLeft")),
        seats=seats,
        button_seat=int(_require(raw, "buttonSeat")),
        hero_cards=list(_require(raw, "heroCards")),
        board=list(raw.get("board", [])),
        pot_bb=float(_require(raw, "potBb")),
        to_call_bb=float(_require(raw, "toCallBb")),
        raise_to_bb=None if raise_to is None else float(raise_to),
    )


def assign_positions(node: DecisionNode) -> dict[int, Position]:
    """Место за столом → позиция, отсчитанная от кнопки.

    Позиции не подписаны на скриншоте и не называются моделью: порядок
    берётся из `positions_for`, который уже знает неочевидные соглашения
    для 2 и 6 игроков, и разворачивается по кругу от кнопки.
    """
    seats = sorted(node.seats, key=lambda seat: seat.seat_index)
    order = positions_for(len(seats))
    button_at = next(
        i for i, seat in enumerate(seats) if seat.seat_index == node.button_seat
    )
    button_in_order = order.index(Position.BTN)
    shift = button_at - button_in_order
    return {
        seats[(button_in_order + offset + shift) % len(seats)].seat_index: order[
            (button_in_order + offset) % len(order)
        ]
        for offset in range(len(seats))
    }


def payout_ladder(context: TournamentContext, places: int) -> list[float]:
    """Призовые по местам от первого, добитые нулями до `places`."""
    ladder = [0.0] * places
    for payout in context.payouts:
        for place in range(payout.first, payout.last + 1):
            if 1 <= place <= places:
                ladder[place - 1] = payout.amount
    return ladder


def validate_hand(
    context: TournamentContext, nodes: list[DecisionNode]
) -> None:
    """Проверяет раздачу целиком. Бросает `ValueError` при нарушении."""
    if not nodes:
        raise ValueError("в раздаче нет ни одного узла решения")

    _validate_context(context)
    for node in nodes:
        _validate_node(node)
    for earlier, later in zip(nodes, nodes[1:]):
        _validate_transition(earlier, later)


def _validate_context(context: TournamentContext) -> None:
    if not context.payouts:
        raise ValueError("лесенка выплат пуста")
    seen: set[int] = set()
    previous_amount: float | None = None
    for payout in sorted(context.payouts, key=lambda p: p.first):
        if payout.first < 1 or payout.last < payout.first:
            raise ValueError(
                f"неверный интервал мест в выплатах: {payout.first}–{payout.last}"
            )
        if payout.amount <= 0:
            raise ValueError(f"выплата должна быть больше нуля: {payout.amount}")
        places = set(range(payout.first, payout.last + 1))
        if places & seen:
            raise ValueError(
                f"интервалы выплат пересекаются на месте "
                f"{min(places & seen)}"
            )
        seen |= places
        if previous_amount is not None and payout.amount > previous_amount:
            raise ValueError("выплата за более низкое место больше, чем за высокое")
        previous_amount = payout.amount
    if context.entrants < context.players_left:
        raise ValueError(
            f"осталось игроков ({context.players_left}) больше, чем входов "
            f"({context.entrants})"
        )
    if context.average_stack_bb <= 0:
        raise ValueError("средний стек должен быть больше нуля")


def _validate_node(node: DecisionNode) -> None:
    if node.street not in BOARD_SIZE:
        raise ValueError(f"неизвестная улица: {node.street!r}")
    if len(node.board) != BOARD_SIZE[node.street]:
        raise ValueError(
            f"на улице {node.street} должно быть {BOARD_SIZE[node.street]} карт "
            f"на доске, получено {len(node.board)}"
        )

    indices = [seat.seat_index for seat in node.seats]
    if len(set(indices)) != len(indices):
        raise ValueError("места за столом повторяются")
    # Границы 2..9 и соглашения для 2 и 6 игроков — забота positions_for.
    positions_for(len(node.seats))
    if node.button_seat not in indices:
        raise ValueError(f"кнопки нет среди мест за столом: {node.button_seat}")

    heroes = [seat for seat in node.seats if seat.is_hero]
    if len(heroes) != 1:
        raise ValueError(f"героев в узле должно быть ровно один, найдено {len(heroes)}")
    if not heroes[0].in_hand:
        raise ValueError("герой помечен как выбывший из раздачи")

    for seat in node.seats:
        if seat.stack_bb < 0:
            raise ValueError(f"отрицательный стек у места {seat.seat_index}")
        if seat.invested_bb < 0:
            raise ValueError(f"отрицательное вложение у места {seat.seat_index}")

    if node.pot_bb <= 0:
        raise ValueError("банк должен быть больше нуля")
    if node.to_call_bb < 0:
        raise ValueError("сумма колла не может быть отрицательной")
    if node.raise_to_bb is not None and node.raise_to_bb <= node.to_call_bb:
        raise ValueError("рейз не превышает сумму колла")

    if node.players_left < len(node.seats):
        raise ValueError(
            f"осталось игроков ({node.players_left}) меньше, чем за столом "
            f"({len(node.seats)})"
        )
    if not 1 <= node.hero_rank <= node.players_left:
        raise ValueError(
            f"ранг героя ({node.hero_rank}) вне поля из {node.players_left} игроков"
        )

    # Личность карт проверяется здесь, а не откладывается до equity_vs_range
    # в Task 7: там она всплывёт как ошибка про склейку "JhXz", которой
    # пользователь не писал. Источник — vision-модель, `"Xz"` от неё реален.
    if len(node.hero_cards) != 2:
        raise ValueError(
            f"у героя должно быть 2 карты, получено {len(node.hero_cards)}"
        )
    cards = list(node.hero_cards) + list(node.board)
    for card in cards:
        if card not in FULL_DECK:
            raise ValueError(f"неизвестная карта: {card!r}")
    if len(set(cards)) != len(cards):
        raise ValueError(f"карта встречается дважды: {sorted(cards)}")


def _validate_transition(earlier: DecisionNode, later: DecisionNode) -> None:
    if STREETS.index(later.street) <= STREETS.index(earlier.street):
        raise ValueError(
            f"улицы не идут по порядку: {earlier.street} → {later.street}"
        )
    if list(later.hero_cards) != list(earlier.hero_cards):
        raise ValueError("карты героя изменились внутри раздачи")
    if list(later.board[: len(earlier.board)]) != list(earlier.board):
        raise ValueError("доска не продолжает предыдущую улицу")

    was_in = {seat.seat_index for seat in earlier.seats if seat.in_hand}
    now_in = {seat.seat_index for seat in later.seats if seat.in_hand}
    returned = now_in - was_in
    if returned:
        raise ValueError(f"игрок вернулся в раздачу после фолда: место {min(returned)}")

    before = sum(seat.stack_bb for seat in earlier.seats) + earlier.pot_bb
    after = sum(seat.stack_bb for seat in later.seats) + later.pot_bb
    tolerance = ROUNDING_STEP_BB * max(len(earlier.seats), len(later.seats))
    if abs(before - after) > tolerance:
        raise ValueError(
            f"фишки не сходятся между улицами: было {before:.1f} BB, "
            f"стало {after:.1f} BB"
        )
```

- [ ] **Step 4: Запустить тесты**

Run: `.venv/Scripts/python -m pytest tests/test_handstate.py -v`
Expected: PASS, 29 тестов.

- [ ] **Step 5: Полный прогон**

Run: `.venv/Scripts/python -m pytest`
Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add src/poker_engine/handstate.py tests/test_handstate.py
git commit -m "feat(engine): схема раздачи со скриншота и её валидатор"
```

---

### Task 7: Команда `analyze`

**Files:**
- Create: `src/poker_engine/analyze.py`
- Modify: `src/poker_engine/cli.py` (подкоманда `analyze`)
- Create: `tests/conftest.py`
- Test: `tests/test_analyze.py`
- Test: `tests/test_cli.py` (добавить три теста)
- Modify: `README.md` (раздел с командами)

**Interfaces:**
- Consumes: всё из Task 1–6, плюс `icm_equities`, `risk_premium` из `icm.py` и
  `required_equity` из `potodds.py`.
- Produces: `analyze(context: dict, nodes: list[dict]) -> dict` — единственная функция,
  которую будет вызывать Nuxt.
- Produces: CLI `poker-engine analyze --input hand.json` (`-` = stdin).

**Формат ответа.** Ключи, которых нельзя посчитать, отсутствуют, а не заполняются нулями.
`flags` — список пометок о том, что расчётом не является; он часть ответа, а не сноска.

```json
{
  "street": "preflop",
  "heroPosition": "BB",
  "villainPosition": "BTN",
  "effectiveStackBb": 23.2,
  "icm": { "heroEquity": 12.34, "fieldNodes": 15 },
  "riskPremium": { "riskPremium": 0.041, "bubbleFactor": 1.18 },
  "requiredEquity": 0.168,
  "equity": { "hero": 0.44, "villain": 0.56, "rangeSource": "vpip" },
  "flags": ["late_reg_open", "reduced_field", "mh_bias", "no_pushfold"]
}
```

**Выбор соперника.** Соперник — активный игрок с наибольшим вложением на текущей улице (тот,
на чьё действие герой отвечает); при равенстве вложений — с наибольшим стеком. Это соглашение,
а не расчёт, и оно записано в докстринге.

- [ ] **Step 1: Написать падающий тест**

Сначала создать `tests/conftest.py` — общие данные, которыми пользуются и этот файл, и
тесты CLI из шага 6. Файла в `tests/` пока нет:

```python
"""Общие данные тестов: корректная раздача, снятая со скриншота."""

import pytest


@pytest.fixture
def analyze_context():
    return {
        "payouts": [
            {"from": 1, "to": 1, "amount": 1090.51},
            {"from": 2, "to": 2, "amount": 840.37},
            {"from": 3, "to": 3, "amount": 648.01},
            {"from": 4, "to": 6, "amount": 400.0},
        ],
        "placesPaid": 165,
        "entrants": 1107,
        "playersLeft": 782,
        "lateRegOpen": True,
        "seatsPerTable": 8,
        "averageStackBb": 50.5,
    }


@pytest.fixture
def analyze_node():
    def seat(index, stack, *, hero=False, in_hand=True, invested=0.0):
        return {
            "seatIndex": index,
            "name": f"p{index}",
            "stackBb": stack,
            "investedBb": invested,
            "inHand": in_hand,
            "isHero": hero,
            "vpip": 25.0,
            "vpipHands": 60,
        }

    return {
        "street": "preflop",
        "level": 13,
        "blinds": {"sb": 700, "bb": 1400, "ante": 175},
        "heroRank": 90,
        "playersLeft": 496,
        "seats": [
            seat(0, 72.2, in_hand=False),
            seat(1, 66.1, in_hand=False),
            seat(2, 94.4, in_hand=False),
            seat(3, 35.3, in_hand=False),
            seat(4, 23.2, invested=7.3),
            seat(5, 39.2, in_hand=False),
            seat(6, 35.7, in_hand=False),
            seat(7, 63.3, hero=True, invested=1.0),
        ],
        "buttonSeat": 4,
        "heroCards": ["Jh", "Th"],
        "board": [],
        "potBb": 9.4,
        "toCallBb": 7.3,
        "raiseToBb": 14.5,
    }
```

Затем создать `tests/test_analyze.py`:

```python
"""Инварианты сквозного разбора.

Проверяется состав ответа и его согласованность с частями движка, а не
конкретные значения ICM или эквити — они предмет тестов своих модулей.
"""

import copy
import json

import pytest

from poker_engine.analyze import analyze
from poker_engine.potodds import required_equity
from poker_engine.types import Position


@pytest.fixture
def run_analyze(analyze_context, analyze_node):
    def call(**overrides):
        node = copy.deepcopy(analyze_node)
        node.update(overrides)
        return analyze(analyze_context, [node], trials=2_000, seed=11)

    return call


def test_hero_position_comes_from_the_button(run_analyze):
    assert run_analyze()["heroPosition"] == Position.UTG1.value


def test_villain_is_the_player_who_invested_most(run_analyze):
    assert run_analyze()["villainPosition"] == Position.BTN.value


def test_effective_stack_is_the_smaller_of_the_two(run_analyze):
    # Соперник на кнопке держит 23.2 BB, герой 63.3 BB.
    assert run_analyze()["effectiveStackBb"] == pytest.approx(23.2)


def test_required_equity_matches_the_pot_odds_module(run_analyze):
    result = run_analyze()
    assert result["requiredEquity"] == pytest.approx(required_equity(9.4, 7.3))


def test_no_call_means_no_required_equity(run_analyze):
    assert "requiredEquity" not in run_analyze(toCallBb=0.0, raiseToBb=None)


def test_icm_equity_is_within_the_prize_pool(run_analyze):
    assert 0 < run_analyze()["icm"]["heroEquity"] < 1090.51


def test_field_is_reduced_not_taken_whole(run_analyze):
    assert run_analyze()["icm"]["fieldNodes"] <= 15


def test_equity_shares_sum_to_one(run_analyze):
    equity = run_analyze()["equity"]
    assert equity["hero"] + equity["villain"] == pytest.approx(1.0)


def test_range_source_is_vpip_when_the_sample_suffices(run_analyze):
    assert run_analyze()["equity"]["rangeSource"] == "vpip"


def test_small_vpip_sample_is_reported_as_default(run_analyze, analyze_node):
    seats = copy.deepcopy(analyze_node["seats"])
    seats[4]["vpipHands"] = 4
    result = run_analyze(seats=seats)
    assert result["equity"]["rangeSource"] == "default"
    assert "vpip_default" in result["flags"]


def test_open_late_registration_is_flagged(run_analyze):
    assert "late_reg_open" in run_analyze()["flags"]


def test_reduced_field_and_mh_bias_are_always_flagged(run_analyze):
    flags = run_analyze()["flags"]
    assert "reduced_field" in flags
    assert "mh_bias" in flags


def test_preflop_advice_is_flagged_as_not_computed(run_analyze):
    # Ф2 (Nash push/fold) ещё нет: рекомендация действия на префлопе
    # расчётом не является и обязана это сообщать.
    assert "no_pushfold" in run_analyze()["flags"]


def test_postflop_is_not_flagged_as_missing_pushfold(analyze_context, analyze_node):
    flop = copy.deepcopy(analyze_node)
    flop.update(
        street="flop",
        board=["8c", "2s", "9d"],
        toCallBb=0.0,
        raiseToBb=None,
    )
    result = analyze(analyze_context, [analyze_node, flop], trials=2_000, seed=11)
    assert "no_pushfold" not in result["flags"]


def test_hand_with_no_active_opponent_skips_head_to_head_numbers(
    run_analyze, analyze_node
):
    seats = copy.deepcopy(analyze_node["seats"])
    seats[4]["inHand"] = False
    result = run_analyze(seats=seats, toCallBb=0.0, raiseToBb=None)
    assert "equity" not in result
    assert "riskPremium" not in result
    assert "icm" in result


def test_invalid_hand_is_rejected_before_any_computation(analyze_context, analyze_node):
    broken = copy.deepcopy(analyze_node)
    broken["potBb"] = 0.0
    with pytest.raises(ValueError):
        analyze(analyze_context, [broken], trials=2_000, seed=11)


def test_result_is_json_serialisable(run_analyze):
    json.dumps(run_analyze())
```

Пояснение к `test_hero_position_comes_from_the_button`: кнопка на месте 4, за столом восемь
игроков. `positions_for(8)` даёт `[UTG+1, MP, LJ, HJ, CO, BTN, SB, BB]`; отсчёт от кнопки по
кругу ставит место 7 на `UTG+1`.

- [ ] **Step 2: Запустить и убедиться, что тест падает**

Run: `.venv/Scripts/python -m pytest tests/test_analyze.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'poker_engine.analyze'`

- [ ] **Step 3: Реализовать**

Создать `src/poker_engine/analyze.py`:

```python
"""Сквозной разбор состояния, снятого со скриншота.

Одна функция на всё: принимает турнирный контекст и список узлов решения,
возвращает всё, что движок способен посчитать, плюс список пометок о том,
что расчётом не является. Это единственная точка, которую вызывает
приложение.

Ключи, которых посчитать нельзя, в ответе отсутствуют. Заполнять их
нулями значило бы выдавать незнание за число.
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
    result["flags"].extend(["reduced_field", "mh_bias"])
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
```

`risk_premium` (`icm.py:96`) и `bubble_factor` (`icm.py:66`) — две отдельные функции, каждая
возвращает один `float`. Не объединять их и не менять их сигнатуры.

- [ ] **Step 4: Запустить тесты разбора**

Run: `.venv/Scripts/python -m pytest tests/test_analyze.py -v`
Expected: PASS, 17 тестов.

- [ ] **Step 5: Добавить подкоманду в CLI**

В `src/poker_engine/cli.py`:

1. К импортам добавить `import json` уже есть; добавить:

```python
from .analyze import analyze
```

2. В `_build_parser` добавить перед `return parser`:

```python
    p_an = sub.add_parser("analyze", help="разбор состояния, снятого со скриншота")
    p_an.add_argument("--input", required=True, help="файл с JSON или '-' для stdin")
    p_an.add_argument("--trials", type=int, default=10_000)
    p_an.add_argument("--seed", type=int, default=None)
```

3. В `_dispatch` добавить ветку:

```python
    if args.command == "analyze":
        payload = _read_json(args.input)
        if "context" not in payload or "nodes" not in payload:
            raise ValueError("во входном JSON нужны ключи 'context' и 'nodes'")
        return analyze(
            payload["context"], payload["nodes"], trials=args.trials, seed=args.seed
        )
```

4. Рядом с `_int_list` добавить:

```python
def _read_json(source: str) -> dict:
    text = sys.stdin.read() if source == "-" else _read_file(source)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"вход не является корректным JSON: {exc}") from exc


def _read_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise ValueError(f"не удалось прочитать {path!r}: {exc}") from exc
```

- [ ] **Step 6: Добавить тесты CLI**

Фикстуры `analyze_context` и `analyze_node` уже созданы в `tests/conftest.py` на шаге 1 —
pytest подхватывает их и в `tests/test_cli.py` без импорта. Добавить туда:

```python
def test_analyze_reads_a_file(tmp_path, capsys, analyze_context, analyze_node):
    path = tmp_path / "hand.json"
    path.write_text(
        json.dumps({"context": analyze_context, "nodes": [analyze_node]}),
        encoding="utf-8",
    )
    code, data = run(
        ["analyze", "--input", str(path), "--trials", "500", "--seed", "3"], capsys
    )
    assert code == 0
    assert data["street"] == "preflop"
    assert "flags" in data


def test_analyze_on_broken_json_is_a_json_error(tmp_path, capsys):
    path = tmp_path / "hand.json"
    path.write_text("{не json", encoding="utf-8")
    code, data = run(["analyze", "--input", str(path)], capsys)
    assert code == 1
    assert "error" in data


def test_analyze_on_missing_file_is_a_json_error(capsys):
    code, data = run(["analyze", "--input", "нет-такого.json"], capsys)
    assert code == 1
    assert "error" in data
```

- [ ] **Step 7: Полный прогон**

Run: `.venv/Scripts/python -m pytest`
Expected: PASS.

- [ ] **Step 8: Обновить README**

В `README.md` в таблицу команд добавить строку про `analyze` с примером вызова и указанием,
что это единственная команда, предназначенная для приложения; остальные — для скиллов и
отладки. Там же исправить давно отмеченное: упомянуть `requirements-dev.lock` и сказать, что
`equity` работает либо по двум конкретным рукам (`--hands`), либо против диапазона
(`--hero` + `--vs-range`).

- [ ] **Step 9: Коммит**

```bash
git add src/poker_engine/analyze.py src/poker_engine/cli.py tests/test_analyze.py tests/test_cli.py tests/conftest.py README.md
git commit -m "feat(engine): команда analyze — сквозной разбор состояния со скриншота"
```

---

## Что остаётся приложению

После Task 7 ядро закрыто для прототипа: Nuxt вызывает одну команду и получает готовый JSON.
План на приложение (vision-роуты, `engine.ts`, интерфейс) пишется отдельно, после того как
формат ответа `analyze` перестанет быть предсказанием и станет фактом.

## Открытые вопросы, не закрываемые этим планом

- `DEFAULT_VPIP` и `MIN_VPIP_HANDS` — калибровочные константы, а не результат расчёта.
- Порядок соседних по силе классов в `preflop_order.json` определён выборкой и в третьем
  знаке шумит. На отсечение по проценту это не влияет.
- Выбор соперника по наибольшему вложению — соглашение. Скриншот не хранит порядок ходов.
- Проверка спеки «`toCallBb = 0` при отсутствии кнопки колла» здесь не реализуется: она
  сопоставляет JSON с пикселями и потому принадлежит слою распознавания, а не движку.
  Движок проверяет то, что видит: `toCallBb >= 0` и `raiseToBb > toCallBb`.
- Восстановление действий соперников между двумя скриншотами героя этим планом не делается.
