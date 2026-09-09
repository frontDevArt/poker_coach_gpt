# Poker Engine Core — Implementation Plan (План 1: Ф0 + Ф1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Построить вычислительное ядро `poker-engine` (ICM, пот-оддсы, PKO bounty EV, эквити) с доказуемыми тестами и два скилла (L0 онтология, L1 математика), которые обязаны брать числа только из ядра.

**Architecture:** Python-пакет `packages/poker-engine` с единым CLI, отдающим JSON. Каждая функция покрыта аналитическим инвариантом — тестом, чью правильность можно доказать на бумаге, а не взять из памяти модели. Скиллы в `.claude/skills/` содержат контракт «число только из вывода CLI» и таблицу команд.

**Tech Stack:** Python 3.11+, pytest, pokerkit (эвалюация рук), dataclasses. Никаких внешних API.

**Спека:** `docs/superpowers/specs/2026-09-09-poker-skillpack-design.md`

---

## Структура файлов

| Файл | Ответственность |
|---|---|
| `packages/poker-engine/pyproject.toml` | Метаданные пакета, зависимости, конфиг pytest |
| `packages/poker-engine/src/poker_engine/__init__.py` | Публичный экспорт |
| `packages/poker-engine/src/poker_engine/types.py` | Позиции, улицы, `HandState`, инварианты фишек |
| `packages/poker-engine/src/poker_engine/potodds.py` | Пот-оддсы, требуемое эквити, chip-EV колла, fold equity |
| `packages/poker-engine/src/poker_engine/icm.py` | Malmuth-Harville, risk premium, bubble factor |
| `packages/poker-engine/src/poker_engine/bounty.py` | PKO: наличные за нокаут, порог колла с баунти |
| `packages/poker-engine/src/poker_engine/equity.py` | Эквити рук через pokerkit + Monte-Carlo для диапазонов |
| `packages/poker-engine/src/poker_engine/cli.py` | Единая точка входа, вывод JSON |
| `packages/poker-engine/tests/*` | Тесты по одному файлу на модуль |
| `scripts/fetch-vendor-ref.sh` | Воспроизводимое клонирование чужих репо |
| `.claude/skills/poker-ontology/SKILL.md` | L0 — словарь домена |
| `.claude/skills/poker-math/SKILL.md` | L1 — контракт и таблица команд |

Разделение по ответственности: `potodds` не знает про ICM, `icm` не знает про баунти, `bounty` использует `potodds` как базу. `cli` — только парсинг аргументов и сериализация, без логики.

---

### Task 1: Каркас пакета poker-engine

**Files:**
- Create: `packages/poker-engine/pyproject.toml`
- Create: `packages/poker-engine/src/poker_engine/__init__.py`
- Create: `packages/poker-engine/tests/test_smoke.py`
- Modify: `.gitignore`

- [ ] **Step 1: Написать падающий тест**

Create `packages/poker-engine/tests/test_smoke.py`:

```python
from poker_engine import __version__


def test_package_imports():
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: Запустить тест, убедиться что падает**

```bash
cd packages/poker-engine && python -m pytest tests/test_smoke.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'poker_engine'`

- [ ] **Step 3: Создать pyproject.toml**

Create `packages/poker-engine/pyproject.toml`:

```toml
[project]
name = "poker-engine"
version = "0.1.0"
description = "Computation core for MTT poker coaching: ICM, pot odds, PKO bounty EV, equity"
requires-python = ">=3.11"
dependencies = [
    "pokerkit>=0.5",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
poker-engine = "poker_engine.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 4: Создать пакет**

Create `packages/poker-engine/src/poker_engine/__init__.py`:

```python
"""Вычислительное ядро покерного коуча.

Все числа для разбора рук приходят отсюда. Скиллы не считают сами.
"""

__version__ = "0.1.0"
```

- [ ] **Step 5: Создать venv и установить пакет**

```bash
cd packages/poker-engine
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Expected: `Successfully installed poker-engine-0.1.0` и подтянутый `pokerkit`.

- [ ] **Step 6: Запустить тест, убедиться что проходит**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -m pytest tests/test_smoke.py -v
```

Expected: PASS, `1 passed`

- [ ] **Step 7: Добавить venv в .gitignore**

Добавить в конец `.gitignore` файла в корне репо:

```
# poker-engine
packages/poker-engine/.venv/
packages/poker-engine/*.egg-info/
packages/poker-engine/src/*.egg-info/
__pycache__/
*.pyc
.pytest_cache/

# чужие репо, клонируются через scripts/fetch-vendor-ref.sh
vendor-ref/
```

- [ ] **Step 8: Коммит**

```bash
git add .gitignore packages/poker-engine/pyproject.toml packages/poker-engine/src packages/poker-engine/tests
git commit -m "feat(engine): scaffold poker-engine package"
```

---

### Task 2: Скрипт воспроизводимого клонирования vendor-ref

**Files:**
- Create: `scripts/fetch-vendor-ref.sh`

Референсные репозитории нужны для уровней проверки T3 и T4 из спеки. В git они не попадают, но список должен быть зафиксирован.

- [ ] **Step 1: Создать скрипт**

Create `scripts/fetch-vendor-ref.sh`:

```bash
#!/usr/bin/env bash
# Клонирует референсные репозитории в vendor-ref/ (read-only, не в git).
# Используются как источник по формату данных GG и для cross-check (T4).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/vendor-ref"
mkdir -p "$DEST"

clone() {
  local repo="$1" dir="$2"
  if [ -d "$DEST/$dir/.git" ]; then
    echo "skip $dir (уже склонирован)"
    return
  fi
  git clone --depth 50 "https://github.com/$repo.git" "$DEST/$dir"
}

clone "matthiola0/poker-hand-review"      "poker-hand-review"
clone "McDic/pokercraft-local"            "pokercraft-local"
clone "LayorX/GGPoker-Hand-Analyzer"      "ggpoker-hand-analyzer"
clone "AHTOOOXA/poker-charts"             "poker-charts"
clone "uoftcprg/pokerkit"                 "pokerkit"

echo
echo "Готово. Зафиксировать использованные коммиты:"
for d in "$DEST"/*/; do
  [ -d "$d/.git" ] || continue
  printf '%-28s %s\n' "$(basename "$d")" "$(git -C "$d" rev-parse --short HEAD)"
done
```

- [ ] **Step 2: Запустить и проверить**

```bash
bash scripts/fetch-vendor-ref.sh
```

Expected: пять клонов в `vendor-ref/`, затем таблица имя → короткий SHA.

Если какой-то репозиторий недоступен или переименован — записать это в конец плана 5 (cross-check T4) и продолжить. Отсутствие одного референса не блокирует Ф1.

- [ ] **Step 3: Коммит**

```bash
git add scripts/fetch-vendor-ref.sh
git commit -m "chore: add vendor-ref fetch script"
```

---

### Task 3: Типы домена и инвариант фишек

**Files:**
- Create: `packages/poker-engine/src/poker_engine/types.py`
- Test: `packages/poker-engine/tests/test_types.py`

- [ ] **Step 1: Написать падающие тесты**

Create `packages/poker-engine/tests/test_types.py`:

```python
import pytest

from poker_engine.types import (
    ChipConservationError,
    Position,
    Street,
    TableSnapshot,
    positions_for,
)


def test_street_order():
    assert Street.PREFLOP < Street.FLOP < Street.TURN < Street.RIVER


def test_positions_for_six_max():
    assert positions_for(6) == [
        Position.UTG,
        Position.HJ,
        Position.CO,
        Position.BTN,
        Position.SB,
        Position.BB,
    ]


def test_positions_for_eight_max_is_gg_default():
    assert positions_for(8) == [
        Position.UTG1,
        Position.MP,
        Position.LJ,
        Position.HJ,
        Position.CO,
        Position.BTN,
        Position.SB,
        Position.BB,
    ]


def test_positions_for_heads_up():
    assert positions_for(2) == [Position.SB, Position.BB]


def test_snapshot_conserves_chips():
    snap = TableSnapshot(stacks=[1000, 2000, 3000], pot=500, total_chips=6500)
    assert snap.is_consistent()


def test_snapshot_rejects_chip_leak():
    with pytest.raises(ChipConservationError):
        TableSnapshot(stacks=[1000, 2000, 3000], pot=500, total_chips=9000).validate()


def test_effective_stack_is_second_largest_when_heads_up():
    snap = TableSnapshot(stacks=[1200, 800], pot=0, total_chips=2000)
    assert snap.effective_stack(0, 1) == 800
```

- [ ] **Step 2: Запустить, убедиться что падает**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -m pytest tests/test_types.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'poker_engine.types'`

- [ ] **Step 3: Реализовать типы**

Create `packages/poker-engine/src/poker_engine/types.py`:

```python
"""Онтология стола: позиции, улицы, снимок стола с проверкой сохранения фишек."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum


class Street(IntEnum):
    """Улицы в порядке следования. IntEnum — чтобы работало сравнение."""

    PREFLOP = 0
    FLOP = 1
    TURN = 2
    RIVER = 3


class Position(StrEnum):
    UTG = "UTG"
    UTG1 = "UTG+1"
    MP = "MP"
    LJ = "LJ"
    HJ = "HJ"
    CO = "CO"
    BTN = "BTN"
    SB = "SB"
    BB = "BB"


# Порядок посадки от самой ранней позиции к самой поздней.
# Столы меньшего размера отрезают ранние позиции с начала списка.
_FULL_RING_ORDER: list[Position] = [
    Position.UTG,
    Position.UTG1,
    Position.MP,
    Position.LJ,
    Position.HJ,
    Position.CO,
    Position.BTN,
    Position.SB,
    Position.BB,
]


def positions_for(players: int) -> list[Position]:
    """Позиции за столом на `players` игроков.

    GG по умолчанию раздаёт 8-max в MTT. Хедз-ап вырождается в SB/BB.
    """
    if players < 2:
        raise ValueError(f"нужно минимум 2 игрока, получено {players}")
    if players > len(_FULL_RING_ORDER):
        raise ValueError(f"максимум {len(_FULL_RING_ORDER)} игроков, получено {players}")
    if players == 2:
        return [Position.SB, Position.BB]
    return _FULL_RING_ORDER[len(_FULL_RING_ORDER) - players:]


class ChipConservationError(ValueError):
    """Сумма стеков и банка не сходится с общим числом фишек в раздаче."""


@dataclass(frozen=True)
class TableSnapshot:
    """Снимок стола в один момент времени.

    `total_chips` — сколько фишек было в раздаче на её старте. Инвариант:
    сумма текущих стеков плюс банк обязана равняться этому числу. Нарушение
    означает ошибку распознавания скриншота или бага в логике.
    """

    stacks: list[int]
    pot: int
    total_chips: int
    tolerance: int = field(default=0)

    def chip_sum(self) -> int:
        return sum(self.stacks) + self.pot

    def is_consistent(self) -> bool:
        return abs(self.chip_sum() - self.total_chips) <= self.tolerance

    def validate(self) -> None:
        if not self.is_consistent():
            raise ChipConservationError(
                f"стеки+банк = {self.chip_sum()}, ожидалось {self.total_chips}"
            )

    def effective_stack(self, hero: int, villain: int) -> int:
        return min(self.stacks[hero], self.stacks[villain])
```

- [ ] **Step 4: Запустить тесты**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -m pytest tests/test_types.py -v
```

Expected: PASS, `7 passed`

- [ ] **Step 5: Коммит**

```bash
git add packages/poker-engine/src/poker_engine/types.py packages/poker-engine/tests/test_types.py
git commit -m "feat(engine): add domain types with chip conservation invariant"
```

---

### Task 4: Пот-оддсы и chip-EV

**Files:**
- Create: `packages/poker-engine/src/poker_engine/potodds.py`
- Test: `packages/poker-engine/tests/test_potodds.py`

Соглашение по терминам, единое для всего ядра: `pot_before_call` — банк **до** того, как герой доложил, то есть ровно та сумма, которую герой выигрывает при победе. `call_amount` — сколько герой доплачивает.

- [ ] **Step 1: Написать падающие тесты**

Create `packages/poker-engine/tests/test_potodds.py`:

```python
import pytest

from poker_engine.potodds import (
    ev_call,
    ev_shove,
    required_equity,
)


def test_required_equity_third_of_pot():
    # Банк 100, колл 50. Герой вкладывает 50 в итоговый банк 150 -> 1/3.
    assert required_equity(pot_before_call=100, call_amount=50) == pytest.approx(1 / 3)


def test_required_equity_half_when_pot_equals_call():
    assert required_equity(pot_before_call=50, call_amount=50) == pytest.approx(0.5)


def test_required_equity_rejects_zero_call():
    with pytest.raises(ValueError):
        required_equity(pot_before_call=100, call_amount=0)


def test_ev_call_is_zero_at_required_equity():
    # Ключевая связка: при эквити ровно на пороге chip-EV равен нулю.
    q = required_equity(pot_before_call=100, call_amount=50)
    assert ev_call(pot_before_call=100, call_amount=50, equity=q) == pytest.approx(0.0)


def test_ev_call_positive_above_threshold():
    assert ev_call(pot_before_call=100, call_amount=50, equity=0.5) == pytest.approx(25.0)


def test_ev_call_negative_below_threshold():
    assert ev_call(pot_before_call=100, call_amount=50, equity=0.2) == pytest.approx(-20.0)


def test_ev_shove_with_certain_fold_equals_pot():
    # Оппонент всегда фолдит -> герой забирает банк, риска нет.
    assert ev_shove(
        pot_before_shove=100, shove_amount=200, fold_equity=1.0, equity_when_called=0.0
    ) == pytest.approx(100.0)


def test_ev_shove_without_fold_equity_reduces_to_ev_call():
    # Оппонент никогда не фолдит -> шов эквивалентен всаживанию тех же фишек.
    shove = ev_shove(
        pot_before_shove=100, shove_amount=200, fold_equity=0.0, equity_when_called=0.4
    )
    manual = 0.4 * (100 + 200) - 0.6 * 200
    assert shove == pytest.approx(manual)
```

- [ ] **Step 2: Запустить, убедиться что падает**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -m pytest tests/test_potodds.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'poker_engine.potodds'`

- [ ] **Step 3: Реализовать**

Create `packages/poker-engine/src/poker_engine/potodds.py`:

```python
"""Пот-оддсы и chip-EV. Никакого ICM — только фишки.

Соглашение: `pot_before_call` — банк до доплаты героя, то есть ровно то,
что герой забирает при победе. `call_amount` — сколько герой доплачивает.
"""

from __future__ import annotations


def required_equity(pot_before_call: float, call_amount: float) -> float:
    """Минимальное эквити, при котором колл безубыточен по фишкам."""
    if call_amount <= 0:
        raise ValueError(f"call_amount должен быть > 0, получено {call_amount}")
    if pot_before_call < 0:
        raise ValueError(f"pot_before_call не может быть отрицательным: {pot_before_call}")
    return call_amount / (pot_before_call + call_amount)


def ev_call(pot_before_call: float, call_amount: float, equity: float) -> float:
    """Chip-EV колла: выигрываем банк с вероятностью equity, иначе теряем колл."""
    _check_probability(equity, "equity")
    return equity * pot_before_call - (1.0 - equity) * call_amount


def ev_shove(
    pot_before_shove: float,
    shove_amount: float,
    fold_equity: float,
    equity_when_called: float,
) -> float:
    """Chip-EV шова.

    С вероятностью fold_equity оппонент фолдит и герой забирает банк.
    Иначе идёт вскрытие: герой выигрывает банк плюс колл оппонента,
    либо теряет свой шов.
    """
    _check_probability(fold_equity, "fold_equity")
    _check_probability(equity_when_called, "equity_when_called")
    ev_fold = pot_before_shove
    ev_called = (
        equity_when_called * (pot_before_shove + shove_amount)
        - (1.0 - equity_when_called) * shove_amount
    )
    return fold_equity * ev_fold + (1.0 - fold_equity) * ev_called


def _check_probability(value: float, name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} должен быть в [0, 1], получено {value}")
```

- [ ] **Step 4: Запустить тесты**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -m pytest tests/test_potodds.py -v
```

Expected: PASS, `8 passed`

- [ ] **Step 5: Коммит**

```bash
git add packages/poker-engine/src/poker_engine/potodds.py packages/poker-engine/tests/test_potodds.py
git commit -m "feat(engine): add pot odds and chip EV"
```

---

### Task 5: ICM по Malmuth-Harville

**Files:**
- Create: `packages/poker-engine/src/poker_engine/icm.py`
- Test: `packages/poker-engine/tests/test_icm.py`

Ожидаемые значения в тестах выведены вручную по формуле M-H, а не взяты из памяти. Вывод для случая `stacks=[50,30,20]`, `payouts=[50,30,20]`:

```
P(i первый) = s_i / S
P(i второй) = Σ_{j≠i} P(j первый) · s_i / (S − s_j)

P1: первый 1/2, второй 3/14 + 1/8 = 19/56, третий 9/56
    EV1 = 50·(1/2) + 30·(19/56) + 20·(9/56) = 38.392857142857146
P2: первый 3/10, второй 3/8, третий 0.325
    EV2 = 50·0.3 + 30·0.375 + 20·0.325 = 32.75
P3: первый 1/5, второй 2/7, третий 0.5142857142857142
    EV3 = 50·0.2 + 30·(2/7) + 20·0.5142857142857142 = 28.857142857142854
Сумма = 100.0
```

- [ ] **Step 1: Написать падающие тесты**

Create `packages/poker-engine/tests/test_icm.py`:

```python
import pytest

from poker_engine.icm import bubble_factor, icm_equities, risk_premium


def test_two_players_analytic():
    # P(1-й) = 75/100. EV1 = 0.75*70 + 0.25*30 = 60. EV2 = 40.
    result = icm_equities(stacks=[75, 25], payouts=[70, 30])
    assert result == pytest.approx([60.0, 40.0])


def test_three_players_analytic():
    result = icm_equities(stacks=[50, 30, 20], payouts=[50, 30, 20])
    assert result == pytest.approx(
        [38.392857142857146, 32.75, 28.857142857142854]
    )


def test_sum_of_equities_equals_prize_pool():
    payouts = [500, 300, 200, 100]
    result = icm_equities(stacks=[120, 45, 80, 15], payouts=payouts)
    assert sum(result) == pytest.approx(sum(payouts))


def test_equal_stacks_split_prize_pool_evenly():
    result = icm_equities(stacks=[100, 100, 100], payouts=[50, 30, 20])
    assert result == pytest.approx([100 / 3, 100 / 3, 100 / 3])


def test_winner_take_all_is_linear_in_chips():
    # Единственная выплата -> ICM вырождается в долю фишек.
    result = icm_equities(stacks=[50, 30, 20], payouts=[100, 0, 0])
    assert result == pytest.approx([50.0, 30.0, 20.0])


def test_payouts_shorter_than_field_are_padded_with_zeros():
    result = icm_equities(stacks=[50, 30, 20], payouts=[100])
    assert result == pytest.approx([50.0, 30.0, 20.0])


def test_rejects_more_payouts_than_players():
    with pytest.raises(ValueError):
        icm_equities(stacks=[50, 50], payouts=[50, 30, 20])


def test_rejects_nonpositive_stack():
    with pytest.raises(ValueError):
        icm_equities(stacks=[50, 0], payouts=[100])


def test_bubble_factor_is_one_under_winner_take_all():
    # Без лесенки выплат риска сверх фишкового нет.
    bf = bubble_factor(
        stacks=[50, 30, 20], payouts=[100, 0, 0], hero=0, villain=1
    )
    assert bf == pytest.approx(1.0)


def test_bubble_factor_exceeds_one_with_ladder():
    bf = bubble_factor(
        stacks=[50, 30, 20], payouts=[50, 30, 20], hero=0, villain=1
    )
    assert bf > 1.0


def test_risk_premium_is_zero_under_winner_take_all():
    rp = risk_premium(
        stacks=[50, 30, 20], payouts=[100, 0, 0], hero=0, villain=1
    )
    assert rp == pytest.approx(0.0, abs=1e-9)


def test_risk_premium_positive_with_ladder():
    rp = risk_premium(
        stacks=[50, 30, 20], payouts=[50, 30, 20], hero=0, villain=1
    )
    assert rp > 0.0


def test_bubble_factor_heads_up_survives_single_player_branch():
    # Выигрыш олл-ина в хедз-апе оставляет одного игрока — вырожденная
    # ветка, на которой наивная реализация падает.
    bf = bubble_factor(stacks=[60, 40], payouts=[70, 30], hero=0, villain=1)
    assert bf > 0.0
```

- [ ] **Step 2: Запустить, убедиться что падает**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -m pytest tests/test_icm.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'poker_engine.icm'`

- [ ] **Step 3: Реализовать ICM**

Create `packages/poker-engine/src/poker_engine/icm.py`:

```python
"""ICM по Malmuth-Harville плюс производные метрики риска.

Известное ограничение модели: M-H систематически завышает вероятность
второго места для крупного стека. На баббле результат стоит сверять с
Monte-Carlo ICM (план 5). Здесь это не исправляется, а документируется.

Сложность рекурсии — O(n · 2^n) по числу игроков за счёт мемоизации по
множеству уже занявших места. Для 9-max это приемлемо; выплат обычно
меньше, чем игроков, поэтому рекурсия обрывается на глубине len(payouts).
"""

from __future__ import annotations

from functools import lru_cache


def icm_equities(stacks: list[int], payouts: list[float]) -> list[float]:
    """Денежное эквити каждого игрока по модели Malmuth-Harville.

    stacks — фишки игроков в текущем порядке.
    payouts — призовые по местам, от первого. Короче списка игроков — добьётся нулями.
    """
    _validate(stacks, payouts)
    n = len(stacks)
    padded = list(payouts) + [0.0] * (n - len(payouts))
    depth = _significant_depth(padded)

    total = float(sum(stacks))
    frozen = tuple(float(s) for s in stacks)

    @lru_cache(maxsize=None)
    def place_probs(taken: frozenset[int], player: int) -> float:
        """Вероятность, что `player` займёт следующее место среди оставшихся."""
        remaining = total - sum(frozen[i] for i in taken)
        if remaining <= 0:
            return 0.0
        return frozen[player] / remaining

    equities = [0.0] * n

    def walk(taken: frozenset[int], prob: float, place: int) -> None:
        if place >= depth or prob == 0.0:
            return
        for player in range(n):
            if player in taken:
                continue
            p = prob * place_probs(taken, player)
            if p == 0.0:
                continue
            equities[player] += p * padded[place]
            walk(taken | {player}, p, place + 1)

    walk(frozenset(), 1.0, 0)

    # Места глубже depth оплачиваются нулём, но остаточная вероятность
    # обязана быть учтена в сумме — при нулевой выплате вклад нулевой.
    return equities


def bubble_factor(
    stacks: list[int], payouts: list[float], hero: int, villain: int
) -> float:
    """Во сколько раз проигрыш дороже выигрыша в деньгах против фишек.

    1.0 — денежная лесенка не давит (winner-take-all).
    Больше 1.0 — герой рискует деньгами сильнее, чем фишками.
    """
    now, win, lose = _icm_branches(stacks, payouts, hero, villain)
    money_down = now - lose
    money_up = win - now
    if money_up <= 0:
        raise ValueError("выигрыш не увеличивает ICM-эквити, bubble factor не определён")

    chips_now = float(stacks[hero])
    chips_win = float(stacks[hero] + min(stacks[hero], stacks[villain]))
    chips_lose = float(stacks[hero] - min(stacks[hero], stacks[villain]))
    chip_down = chips_now - chips_lose
    chip_up = chips_win - chips_now

    return (money_down / money_up) / (chip_down / chip_up)


def risk_premium(
    stacks: list[int], payouts: list[float], hero: int, villain: int
) -> float:
    """Насколько выше должно быть эквити героя из-за ICM.

    Разница между порогом безубыточности в деньгах и в фишках.
    Ноль при winner-take-all, положительно при лесенке выплат.
    """
    now, win, lose = _icm_branches(stacks, payouts, hero, villain)
    money_threshold = (now - lose) / (win - lose)

    chips_win = float(stacks[hero] + min(stacks[hero], stacks[villain]))
    chips_lose = float(stacks[hero] - min(stacks[hero], stacks[villain]))
    chip_threshold = (float(stacks[hero]) - chips_lose) / (chips_win - chips_lose)

    return money_threshold - chip_threshold


def _icm_branches(
    stacks: list[int], payouts: list[float], hero: int, villain: int
) -> tuple[float, float, float]:
    """ICM-эквити героя сейчас, после выигрыша и после проигрыша олл-ина."""
    if hero == villain:
        raise ValueError("hero и villain должны различаться")
    at_risk = min(stacks[hero], stacks[villain])
    if at_risk <= 0:
        raise ValueError("эффективный стек равен нулю")

    now = icm_equities(stacks, payouts)[hero]

    won = list(stacks)
    won[hero] += at_risk
    won[villain] -= at_risk
    win = _equity_with_busts(won, payouts, hero)

    lost = list(stacks)
    lost[hero] -= at_risk
    lost[villain] += at_risk
    lose = _equity_with_busts(lost, payouts, hero)

    return now, win, lose


def _equity_with_busts(stacks: list[int], payouts: list[float], hero: int) -> float:
    """ICM-эквити героя после раздачи, где кто-то мог вылететь.

    Вылетевшие получают выплату за своё место и убираются из расчёта.
    Для двухстороннего олл-ина вылететь может только один из двоих,
    поэтому достаточно отбросить нулевые стеки и сдвинуть выплаты.
    """
    survivors = [(i, s) for i, s in enumerate(stacks) if s > 0]
    busted = len(stacks) - len(survivors)
    if busted == 0:
        return icm_equities(stacks, payouts)

    if stacks[hero] <= 0:
        # Герой вылетел: получает выплату за первое место среди выбывших.
        place_index = len(survivors)
        padded = list(payouts) + [0.0] * (len(stacks) - len(payouts))
        return padded[place_index]

    if len(survivors) == 1:
        # Остался один игрок — он и есть герой, забирает первое место.
        padded = list(payouts) + [0.0] * (len(stacks) - len(payouts))
        return padded[0]

    shifted_stacks = [s for _, s in survivors]
    shifted_payouts = list(payouts)[: len(survivors)]
    hero_index = [i for i, _ in survivors].index(hero)
    return icm_equities(shifted_stacks, shifted_payouts)[hero_index]


def _significant_depth(payouts: list[float]) -> int:
    """Глубина рекурсии: дальше последней ненулевой выплаты считать нечего."""
    for i in range(len(payouts) - 1, -1, -1):
        if payouts[i] != 0.0:
            return i + 1
    return 0


def _validate(stacks: list[int], payouts: list[float]) -> None:
    if len(stacks) < 2:
        raise ValueError(f"нужно минимум 2 игрока, получено {len(stacks)}")
    if any(s <= 0 for s in stacks):
        raise ValueError(f"все стеки должны быть положительными: {stacks}")
    if len(payouts) > len(stacks):
        raise ValueError(
            f"выплат ({len(payouts)}) больше, чем игроков ({len(stacks)})"
        )
    if any(p < 0 for p in payouts):
        raise ValueError(f"выплаты не могут быть отрицательными: {payouts}")
```

- [ ] **Step 4: Запустить тесты**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -m pytest tests/test_icm.py -v
```

Expected: PASS, `13 passed`

Если `test_three_players_analytic` падает — сверить реализацию с ручным выводом в шапке этой задачи, а не подгонять ожидаемые числа под код.

- [ ] **Step 5: Коммит**

```bash
git add packages/poker-engine/src/poker_engine/icm.py packages/poker-engine/tests/test_icm.py
git commit -m "feat(engine): add Malmuth-Harville ICM, bubble factor, risk premium"
```

---

### Task 6: PKO bounty EV

**Files:**
- Create: `packages/poker-engine/src/poker_engine/bounty.py`
- Test: `packages/poker-engine/tests/test_bounty.py`

Модель PKO: при нокауте половина головы соперника выплачивается наличными сразу, вторая половина уходит в собственную голову героя. Доля вынесена параметром `split`, потому что не все баунти-форматы делят пополам.

- [ ] **Step 1: Написать падающие тесты**

Create `packages/poker-engine/tests/test_bounty.py`:

```python
import pytest

from poker_engine.bounty import (
    bounty_in_chips,
    knockout_cash,
    required_equity_with_bounty,
)
from poker_engine.potodds import required_equity


def test_knockout_pays_half_by_default():
    assert knockout_cash(bounty=2.50) == pytest.approx(1.25)


def test_knockout_split_is_configurable():
    assert knockout_cash(bounty=2.50, split=1.0) == pytest.approx(2.50)


def test_bounty_in_chips_converts_by_chip_value():
    # 1.25 наличными при цене фишки 0.025 = 50 фишек.
    assert bounty_in_chips(bounty=2.50, chip_value=0.025) == pytest.approx(50.0)


def test_required_equity_with_zero_bounty_matches_plain_pot_odds():
    with_b = required_equity_with_bounty(
        pot_before_call=100,
        call_amount=50,
        villain_stack=50,
        bounty=0.0,
        chip_value=0.025,
    )
    plain = required_equity(pot_before_call=100, call_amount=50)
    assert with_b == pytest.approx(plain)


def test_required_equity_with_bounty_is_analytic():
    # Голова 2.50, сплит 0.5, цена фишки 0.025 -> 50 фишек добавки.
    # Порог = 50 / (100 + 50 + 50) = 0.25
    q = required_equity_with_bounty(
        pot_before_call=100,
        call_amount=50,
        villain_stack=50,
        bounty=2.50,
        chip_value=0.025,
    )
    assert q == pytest.approx(0.25)


def test_bounty_lowers_the_bar():
    plain = required_equity(pot_before_call=100, call_amount=50)
    with_b = required_equity_with_bounty(
        pot_before_call=100,
        call_amount=50,
        villain_stack=50,
        bounty=2.50,
        chip_value=0.025,
    )
    assert with_b < plain


def test_no_bounty_credit_when_villain_is_not_covered():
    # Стек соперника больше колла героя -> нокаута не будет, голова не считается.
    q = required_equity_with_bounty(
        pot_before_call=100,
        call_amount=50,
        villain_stack=500,
        bounty=2.50,
        chip_value=0.025,
    )
    assert q == pytest.approx(required_equity(pot_before_call=100, call_amount=50))


def test_rejects_nonpositive_chip_value():
    with pytest.raises(ValueError):
        bounty_in_chips(bounty=2.50, chip_value=0.0)
```

- [ ] **Step 2: Запустить, убедиться что падает**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -m pytest tests/test_bounty.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'poker_engine.bounty'`

- [ ] **Step 3: Реализовать**

Create `packages/poker-engine/src/poker_engine/bounty.py`:

```python
"""Progressive Knockout: перевод головы в фишки и порог колла с учётом баунти.

В стандартном PKO половина головы выбитого выплачивается наличными,
половина увеличивает собственную голову героя. В EV конкретной руки
считается только наличная половина: прирост своей головы обналичится
лишь при последующих нокаутах и здесь не моделируется.
"""

from __future__ import annotations

from .potodds import required_equity

DEFAULT_SPLIT = 0.5


def knockout_cash(bounty: float, split: float = DEFAULT_SPLIT) -> float:
    """Наличные, которые герой получает сразу за нокаут."""
    if bounty < 0:
        raise ValueError(f"bounty не может быть отрицательным: {bounty}")
    if not 0.0 < split <= 1.0:
        raise ValueError(f"split должен быть в (0, 1], получено {split}")
    return bounty * split


def bounty_in_chips(
    bounty: float, chip_value: float, split: float = DEFAULT_SPLIT
) -> float:
    """Наличная половина головы, выраженная в фишках.

    chip_value — сколько долларов стоит одна фишка на текущей стадии.
    Берётся как призовой фонд, делённый на общее число фишек в турнире.
    """
    if chip_value <= 0:
        raise ValueError(f"chip_value должен быть > 0, получено {chip_value}")
    return knockout_cash(bounty, split) / chip_value


def required_equity_with_bounty(
    pot_before_call: float,
    call_amount: float,
    villain_stack: float,
    bounty: float,
    chip_value: float,
    split: float = DEFAULT_SPLIT,
) -> float:
    """Порог эквити для колла в PKO.

    Голова засчитывается только если колл героя покрывает стек соперника,
    то есть нокаут действительно возможен в этой раздаче.
    """
    covers_villain = call_amount >= villain_stack
    extra = (
        bounty_in_chips(bounty, chip_value, split)
        if covers_villain and bounty > 0
        else 0.0
    )
    if extra == 0.0:
        return required_equity(pot_before_call, call_amount)
    return call_amount / (pot_before_call + extra + call_amount)
```

- [ ] **Step 4: Запустить тесты**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -m pytest tests/test_bounty.py -v
```

Expected: PASS, `8 passed`

- [ ] **Step 5: Коммит**

```bash
git add packages/poker-engine/src/poker_engine/bounty.py packages/poker-engine/tests/test_bounty.py
git commit -m "feat(engine): add PKO bounty EV"
```

---

### Task 7: Эквити рук через pokerkit

**Files:**
- Create: `packages/poker-engine/src/poker_engine/equity.py`
- Test: `packages/poker-engine/tests/test_equity.py`

Тесты опираются только на симметрию и монотонность — утверждения, чью истинность можно доказать, не сверяясь с внешними таблицами. Точные эталонные значения заносятся из внешнего источника в плане 5 (уровень T2).

- [ ] **Step 1: Проверить API pokerkit**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -c "from pokerkit import Card, StandardHighHand; print(StandardHighHand.from_game('AcAdAhAsKc'))"
```

Expected: печатается объект руки без исключения.

Если сигнатура отличается — свериться с актуальной документацией через Context7 (`resolve-library-id` для `pokerkit`, затем `query-docs`) и поправить обёртку `_best_hand` в шаге 3. Остальной код задачи от этого не зависит.

- [ ] **Step 2: Написать падающие тесты**

Create `packages/poker-engine/tests/test_equity.py`:

```python
import pytest

from poker_engine.equity import hand_equity


def test_mirror_hands_split_equity_exactly():
    # AhKh против AdKd симметричны относительно перестановки мастей,
    # поэтому эквити обязано делиться пополам при любом числе прогонов.
    result = hand_equity(["AhKh", "AdKd"], board=[], trials=4000, seed=1)
    assert result[0] == pytest.approx(result[1], abs=1e-9)


def test_equities_sum_to_one():
    result = hand_equity(["AsAd", "KsKd"], board=[], trials=4000, seed=1)
    assert sum(result) == pytest.approx(1.0)


def test_dominant_pair_beats_lower_pair():
    result = hand_equity(["AsAd", "KsKd"], board=[], trials=4000, seed=1)
    assert result[0] > result[1]


def test_made_nuts_on_river_wins_outright():
    # Готовый стрит-флеш на ривере: доска дорисована, случайности нет.
    result = hand_equity(
        ["9h8h", "AcAd"], board=["7h", "6h", "5h", "2c", "2d"], trials=1, seed=1
    )
    assert result == pytest.approx([1.0, 0.0])


def test_identical_hole_cards_on_board_split():
    # Обе руки играют доску -> ровный сплит.
    result = hand_equity(
        ["2c3d", "2h3s"], board=["As", "Ks", "Qs", "Js", "Ts"], trials=1, seed=1
    )
    assert result == pytest.approx([0.5, 0.5])


def test_same_seed_gives_same_result():
    a = hand_equity(["AsAd", "KsKd"], board=[], trials=2000, seed=42)
    b = hand_equity(["AsAd", "KsKd"], board=[], trials=2000, seed=42)
    assert a == pytest.approx(b)


def test_rejects_duplicate_cards():
    with pytest.raises(ValueError):
        hand_equity(["AsAd", "AsKd"], board=[], trials=100, seed=1)


def test_rejects_oversized_board():
    with pytest.raises(ValueError):
        hand_equity(
            ["AsAd", "KsKd"],
            board=["2c", "3c", "4c", "5c", "6c", "7c"],
            trials=100,
            seed=1,
        )
```

- [ ] **Step 3: Запустить, убедиться что падает**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -m pytest tests/test_equity.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'poker_engine.equity'`

- [ ] **Step 4: Реализовать**

Create `packages/poker-engine/src/poker_engine/equity.py`:

```python
"""Эквити рук: полный перебор при дорисованной доске, иначе Monte-Carlo.

Сплиты делятся поровну между выигравшими, поэтому сумма эквити всегда 1.
Генератор случайных чисел засеивается явно — результат воспроизводим,
иначе тесты и разборы плавали бы от прогона к прогону.
"""

from __future__ import annotations

import random
from itertools import combinations

from pokerkit import Card, StandardHighHand

RANKS = "23456789TJQKA"
SUITS = "cdhs"
FULL_DECK: list[str] = [r + s for r in RANKS for s in SUITS]


def hand_equity(
    hands: list[str],
    board: list[str],
    trials: int = 10_000,
    seed: int | None = None,
) -> list[float]:
    """Доля банка, которую в среднем забирает каждая рука.

    hands — строки вида "AsKd" по две карты.
    board — уже открытые карты, от нуля до пяти.
    trials — число прогонов Monte-Carlo. Игнорируется, если доска полная.
    """
    parsed = [_parse_cards(h, expected=2, label="рука") for h in hands]
    parsed_board = _parse_board(board)
    _check_duplicates([c for hand in parsed for c in hand] + parsed_board)

    if len(parsed) < 2:
        raise ValueError("нужно минимум две руки")

    known = {c for hand in parsed for c in hand} | set(parsed_board)
    deck = [c for c in FULL_DECK if c not in known]
    need = 5 - len(parsed_board)

    wins = [0.0] * len(parsed)

    if need == 0:
        _score_runout(parsed, parsed_board, wins)
        total = 1
    elif len(deck) <= 20 and need <= 1:
        # Полный перебор дешевле выборки, когда осталась одна карта.
        runouts = list(combinations(deck, need))
        for extra in runouts:
            _score_runout(parsed, parsed_board + list(extra), wins)
        total = len(runouts)
    else:
        rng = random.Random(seed)
        for _ in range(trials):
            extra = rng.sample(deck, need)
            _score_runout(parsed, parsed_board + extra, wins)
        total = trials

    return [w / total for w in wins]


def _score_runout(
    hands: list[list[str]], board: list[str], wins: list[float]
) -> None:
    scores = [_best_hand(hand + board) for hand in hands]
    best = max(scores)
    winners = [i for i, s in enumerate(scores) if s == best]
    share = 1.0 / len(winners)
    for i in winners:
        wins[i] += share


def _best_hand(cards: list[str]) -> StandardHighHand:
    """Лучшая пятикарточная комбинация из семи карт."""
    return max(
        StandardHighHand(Card.parse("".join(combo)))
        for combo in combinations(cards, 5)
    )


def _parse_cards(text: str, expected: int, label: str) -> list[str]:
    cards = [text[i : i + 2] for i in range(0, len(text), 2)]
    if len(cards) != expected:
        raise ValueError(f"{label} '{text}': ожидалось {expected} карт, вышло {len(cards)}")
    for c in cards:
        if c not in FULL_DECK:
            raise ValueError(f"неизвестная карта '{c}' в '{text}'")
    return cards


def _parse_board(board: list[str]) -> list[str]:
    if len(board) > 5:
        raise ValueError(f"на доске не может быть больше 5 карт, получено {len(board)}")
    for c in board:
        if c not in FULL_DECK:
            raise ValueError(f"неизвестная карта на доске: '{c}'")
    return list(board)


def _check_duplicates(cards: list[str]) -> None:
    seen: set[str] = set()
    for c in cards:
        if c in seen:
            raise ValueError(f"карта '{c}' встречается дважды")
        seen.add(c)
```

- [ ] **Step 5: Запустить тесты**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -m pytest tests/test_equity.py -v
```

Expected: PASS, `8 passed`

Если `_best_hand` не собирается из-за отличий в API pokerkit — вернуться к шагу 1, уточнить сигнатуру через Context7 и поправить только эту функцию.

- [ ] **Step 6: Коммит**

```bash
git add packages/poker-engine/src/poker_engine/equity.py packages/poker-engine/tests/test_equity.py
git commit -m "feat(engine): add hand equity via pokerkit"
```

---

### Task 8: Перекрёстная проверка Monte-Carlo против полного перебора

**Files:**
- Test: `packages/poker-engine/tests/test_equity_crosscheck.py`

Независимая проверка корректности выборки: на тёрне остаётся одна карта, полный перебор даёт точный ответ, к нему обязана сходиться Monte-Carlo-ветка.

- [ ] **Step 1: Написать тест**

Create `packages/poker-engine/tests/test_equity_crosscheck.py`:

```python
import pytest

from poker_engine.equity import hand_equity


def _exhaustive_turn_equity(hands, board):
    """Точное эквити перебором последней карты, без Monte-Carlo."""
    return hand_equity(hands, board=board, trials=1, seed=0)


def test_monte_carlo_converges_to_exhaustive_on_turn():
    hands = ["AsKs", "7h7d"]
    board = ["Ks", "8c", "3d", "2h"]

    exact = _exhaustive_turn_equity(hands, board)
    sampled = hand_equity(hands, board=board, trials=20_000, seed=7)

    assert sampled[0] == pytest.approx(exact[0], abs=0.01)
    assert sampled[1] == pytest.approx(exact[1], abs=0.01)


def test_equity_is_symmetric_under_hand_order():
    forward = hand_equity(["AsAd", "KsKd"], board=[], trials=8000, seed=3)
    backward = hand_equity(["KsKd", "AsAd"], board=[], trials=8000, seed=3)
    assert forward[0] == pytest.approx(backward[1], abs=0.02)
```

- [ ] **Step 2: Запустить**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -m pytest tests/test_equity_crosscheck.py -v
```

Expected: PASS, `2 passed`

Если сходимости нет — баг в выборке `_score_runout` или в раздаче колоды, а не в допуске. Допуск не расширять.

- [ ] **Step 3: Коммит**

```bash
git add packages/poker-engine/tests/test_equity_crosscheck.py
git commit -m "test(engine): cross-check Monte-Carlo equity against exhaustive enumeration"
```

---

### Task 9: CLI с выводом JSON

**Files:**
- Create: `packages/poker-engine/src/poker_engine/cli.py`
- Test: `packages/poker-engine/tests/test_cli.py`

CLI — единственный интерфейс, через который скиллы и Nuxt получают числа. Только парсинг и сериализация, без вычислительной логики.

- [ ] **Step 1: Написать падающие тесты**

Create `packages/poker-engine/tests/test_cli.py`:

```python
import json

import pytest

from poker_engine.cli import main


def run(argv, capsys):
    code = main(argv)
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_icm_command(capsys):
    code, data = run(
        ["icm", "--stacks", "75,25", "--payouts", "70,30"], capsys
    )
    assert code == 0
    assert data["equities"] == pytest.approx([60.0, 40.0])


def test_potodds_command(capsys):
    code, data = run(["potodds", "--pot", "100", "--call", "50"], capsys)
    assert code == 0
    assert data["required_equity"] == pytest.approx(1 / 3)


def test_bounty_command(capsys):
    code, data = run(
        [
            "bounty-ev",
            "--pot", "100",
            "--call", "50",
            "--villain-stack", "50",
            "--bounty", "2.50",
            "--chip-value", "0.025",
        ],
        capsys,
    )
    assert code == 0
    assert data["required_equity"] == pytest.approx(0.25)


def test_riskpremium_command(capsys):
    code, data = run(
        [
            "risk-premium",
            "--stacks", "50,30,20",
            "--payouts", "100,0,0",
            "--hero", "0",
            "--villain", "1",
        ],
        capsys,
    )
    assert code == 0
    assert data["risk_premium"] == pytest.approx(0.0, abs=1e-9)
    assert data["bubble_factor"] == pytest.approx(1.0)


def test_equity_command(capsys):
    code, data = run(
        ["equity", "--hands", "AhKh,AdKd", "--trials", "2000", "--seed", "1"], capsys
    )
    assert code == 0
    assert data["equities"][0] == pytest.approx(data["equities"][1], abs=1e-9)


def test_invalid_input_returns_error_json(capsys):
    code = main(["icm", "--stacks", "50", "--payouts", "100"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert code == 1
    assert "error" in data
```

- [ ] **Step 2: Запустить, убедиться что падает**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -m pytest tests/test_cli.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'poker_engine.cli'`

- [ ] **Step 3: Реализовать**

Create `packages/poker-engine/src/poker_engine/cli.py`:

```python
"""CLI ядра. Единственный канал, через который скиллы получают числа.

Любая ошибка сериализуется в JSON с ключом `error` и кодом возврата 1 —
вызывающая сторона всегда получает разбираемый ответ, а не трейсбек.
"""

from __future__ import annotations

import argparse
import json
import sys

from .bounty import required_equity_with_bounty
from .equity import hand_equity
from .icm import bubble_factor, icm_equities, risk_premium
from .potodds import required_equity


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        payload = _dispatch(args)
    except (ValueError, IndexError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def _dispatch(args: argparse.Namespace) -> dict:
    if args.command == "icm":
        return {"equities": icm_equities(args.stacks, args.payouts)}

    if args.command == "potodds":
        return {"required_equity": required_equity(args.pot, args.call)}

    if args.command == "bounty-ev":
        return {
            "required_equity": required_equity_with_bounty(
                pot_before_call=args.pot,
                call_amount=args.call,
                villain_stack=args.villain_stack,
                bounty=args.bounty,
                chip_value=args.chip_value,
                split=args.split,
            )
        }

    if args.command == "risk-premium":
        return {
            "risk_premium": risk_premium(
                args.stacks, args.payouts, args.hero, args.villain
            ),
            "bubble_factor": bubble_factor(
                args.stacks, args.payouts, args.hero, args.villain
            ),
        }

    if args.command == "equity":
        return {
            "equities": hand_equity(
                args.hands, board=args.board, trials=args.trials, seed=args.seed
            )
        }

    raise ValueError(f"неизвестная команда: {args.command}")


def _int_list(text: str) -> list[int]:
    return [int(x) for x in text.split(",") if x.strip()]


def _float_list(text: str) -> list[float]:
    return [float(x) for x in text.split(",") if x.strip()]


def _str_list(text: str) -> list[str]:
    return [x.strip() for x in text.split(",") if x.strip()]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poker-engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p_icm = sub.add_parser("icm", help="ICM-эквити по Malmuth-Harville")
    p_icm.add_argument("--stacks", type=_int_list, required=True)
    p_icm.add_argument("--payouts", type=_float_list, required=True)

    p_po = sub.add_parser("potodds", help="порог эквити по пот-оддсам")
    p_po.add_argument("--pot", type=float, required=True)
    p_po.add_argument("--call", type=float, required=True)

    p_b = sub.add_parser("bounty-ev", help="порог эквити с учётом головы PKO")
    p_b.add_argument("--pot", type=float, required=True)
    p_b.add_argument("--call", type=float, required=True)
    p_b.add_argument("--villain-stack", type=float, required=True)
    p_b.add_argument("--bounty", type=float, required=True)
    p_b.add_argument("--chip-value", type=float, required=True)
    p_b.add_argument("--split", type=float, default=0.5)

    p_rp = sub.add_parser("risk-premium", help="risk premium и bubble factor")
    p_rp.add_argument("--stacks", type=_int_list, required=True)
    p_rp.add_argument("--payouts", type=_float_list, required=True)
    p_rp.add_argument("--hero", type=int, required=True)
    p_rp.add_argument("--villain", type=int, required=True)

    p_eq = sub.add_parser("equity", help="эквити рук")
    p_eq.add_argument("--hands", type=_str_list, required=True)
    p_eq.add_argument("--board", type=_str_list, default=[])
    p_eq.add_argument("--trials", type=int, default=10_000)
    p_eq.add_argument("--seed", type=int, default=None)

    return parser


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Запустить тесты**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -m pytest tests/test_cli.py -v
```

Expected: PASS, `6 passed`

- [ ] **Step 5: Проверить установленную команду вручную**

```bash
cd packages/poker-engine && .venv/Scripts/poker-engine.exe icm --stacks 75,25 --payouts 70,30
```

Expected: `{"equities": [60.0, 40.0]}`

- [ ] **Step 6: Прогнать весь набор тестов**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -m pytest -v
```

Expected: PASS, `53 passed` — это 1 smoke + 7 types + 8 potodds + 13 icm + 8 bounty + 8 equity + 2 crosscheck + 6 cli. Если счёт разошёлся, найти пропущенный или лишний тест, а не править ожидание.

- [ ] **Step 7: Коммит**

```bash
git add packages/poker-engine/src/poker_engine/cli.py packages/poker-engine/tests/test_cli.py
git commit -m "feat(engine): add JSON CLI"
```

---

### Task 10: Скилл L1 — poker-math

**Files:**
- Create: `.claude/skills/poker-math/SKILL.md`

- [ ] **Step 1: Написать скилл**

Create `.claude/skills/poker-math/SKILL.md`:

```markdown
---
name: poker-math
description: Use when a poker decision needs a number — ICM equity, risk premium, bubble factor, PKO bounty EV, pot odds, required equity, hand equity, fold equity. Covers MTT tournament math on any platform. Never compute these from memory.
---

# Покерная математика

## Контракт

Число в ответе допустимо **только** из вывода `poker-engine`. Нет вызова — нет числа.

Запрещено:
- писать проценты и эквити по памяти
- округлять «примерно 35%» без вызова
- пересчитывать ICM в уме
- ссылаться на таблицы, которых нет в репозитории

Если вызвать движок невозможно, честно сказать «не посчитано» и продолжить качественным разбором без цифр.

## Как вызывать

Из корня репозитория:

```bash
packages/poker-engine/.venv/Scripts/poker-engine.exe <команда> [опции]
```

Вывод — одна строка JSON. При ошибке: `{"error": "..."}` и код возврата 1.

## Команды

| Что нужно | Команда |
|---|---|
| ICM-эквити всех игроков | `poker-engine icm --stacks 12000,30000,8000,50000 --payouts 40,25,18,17` |
| Risk premium и bubble factor | `poker-engine risk-premium --stacks 12000,30000,8000 --payouts 50,30,20 --hero 0 --villain 1` |
| Порог эквити по пот-оддсам | `poker-engine potodds --pot 100 --call 50` |
| Порог эквити в PKO | `poker-engine bounty-ev --pot 100 --call 50 --villain-stack 50 --bounty 2.50 --chip-value 0.025` |
| Эквити рук | `poker-engine equity --hands AsKs,7h7d --board Ks,8c,3d --trials 20000 --seed 1` |

## Соглашения по аргументам

- `--pot` — банк **до** доплаты героя, то есть ровно то, что герой забирает при победе.
- `--call` — сколько герой доплачивает.
- `--stacks` — фишки, а не большие блайнды.
- `--payouts` — призовые по местам от первого; список короче поля добивается нулями.
- `--chip-value` — доллары за одну фишку: призовой фонд, делённый на все фишки турнира.
- `--seed` — обязателен, когда результат идёт в разбор: без него прогоны не воспроизводятся.

## Как читать результат

**Risk premium** — насколько выше должно быть эквити героя из-за денежной лесенки. Ноль означает, что ICM не давит. Прибавляется к порогу из `potodds`.

**Bubble factor** — во сколько раз проигрыш дороже выигрыша в деньгах против фишек. 1.0 — давления нет.

**PKO** — голова засчитывается, только если колл героя покрывает стек соперника. Иначе `bounty-ev` возвращает обычный пот-оддс, и это не ошибка.

## Известные ограничения — упоминать в разборе

- Модель ICM — Malmuth-Harville. Она систематически завышает шанс большого стека занять второе место. На баббле результат трактовать как оценку, а не как точное значение.
- Прирост собственной головы после нокаута в EV раздачи не моделируется — считается только наличная половина.
- `equity` с непустой доской и Monte-Carlo даёт погрешность порядка процента при 20000 прогонов. Для решений на грани увеличить `--trials`.

## Связанные скиллы

- `poker-ontology` — что означают позиции, улицы, SPR, эффективный стек.
- `poker-review-method` — как из этих чисел собрать разбор руки.
```

- [ ] **Step 2: Проверить, что все команды из скилла реально работают**

```bash
cd packages/poker-engine
.venv/Scripts/poker-engine.exe icm --stacks 12000,30000,8000,50000 --payouts 40,25,18,17
.venv/Scripts/poker-engine.exe risk-premium --stacks 12000,30000,8000 --payouts 50,30,20 --hero 0 --villain 1
.venv/Scripts/poker-engine.exe potodds --pot 100 --call 50
.venv/Scripts/poker-engine.exe bounty-ev --pot 100 --call 50 --villain-stack 50 --bounty 2.50 --chip-value 0.025
.venv/Scripts/poker-engine.exe equity --hands AsKs,7h7d --board Ks,8c,3d --trials 20000 --seed 1
```

Expected: пять строк JSON, ни одной с ключом `error`.

Если какая-то команда падает — это ошибка в скилле или в CLI. Исправить, а не убрать команду из документации.

- [ ] **Step 3: Коммит**

```bash
git add .claude/skills/poker-math/SKILL.md
git commit -m "feat(skills): add poker-math skill with engine-only number contract"
```

---

### Task 11: Скилл L0 — poker-ontology

**Files:**
- Create: `.claude/skills/poker-ontology/SKILL.md`

- [ ] **Step 1: Написать скилл**

Create `.claude/skills/poker-ontology/SKILL.md`:

```markdown
---
name: poker-ontology
description: Use when reading, describing, or reasoning about any Texas Hold'em hand — position names, street order, board texture classes, SPR, effective stack, betting line vocabulary, MTT stage terminology on GG Network. Load before any hand discussion.
---

# Онтология покерного стола

Словарь домена. Ничего не считает — задаёт язык, на котором говорят остальные скиллы.

## Позиции

GG раздаёт MTT преимущественно 8-max. Порядок от ранней к поздней:

| Стол | Позиции |
|---|---|
| 9-max | UTG, UTG+1, MP, LJ, HJ, CO, BTN, SB, BB |
| 8-max | UTG+1, MP, LJ, HJ, CO, BTN, SB, BB |
| 6-max | UTG, HJ, CO, BTN, SB, BB |
| Хедз-ап | SB (он же баттон, действует первым до флопа), BB |

Столы меньшего размера отрезают ранние позиции с начала списка. Источник истины — `poker_engine.types.positions_for(n)`.

## Улицы

PREFLOP → FLOP → TURN → RIVER. Сравнимы по порядку.

## Стек и SPR

**Эффективный стек** — меньший из двух стеков. Только он реально может быть разыгран.

**SPR** = эффективный стек ÷ банк на начало улицы. Определяет, есть ли вообще постфлоп-игра:

| SPR | Что это значит |
|---|---|
| < 2 | Постфлопа почти нет. Решение принимается на флопе, часто на весь стек |
| 2–6 | Одна улица манёвра. Топ-пара часто уже готова идти до конца |
| 7–13 | Полноценная многоуличная игра |
| > 13 | Глубоко. Растут импликативные шансы, дорожают доминируемые руки |

**Стек в больших блайндах** — основная единица в MTT. Переводить в bb до любых рассуждений о префлопе: 22000 фишек при блайндах 500/1000 = 22 bb.

## Стадии турнира

Определяются по эффективному стеку в bb и по близости к деньгам, не по времени.

| Стадия | Признак | Что доминирует |
|---|---|---|
| Ранняя | 40+ bb, до анте, деньги далеко | Игра почти как в кэше, ICM не давит |
| Средняя | 20–40 bb, введены анте | Борьба за банк с анте, растёт ценность стила |
| Баббл | До призовых 1–2 выбывания | Максимальное давление ICM, risk premium наибольший |
| Пост-баббл | Деньги достигнуты | Давление резко падает, поле снова расширяет диапазоны |
| Финальный стол | Крутая лесенка выплат | ICM возвращается, каждое место дорого |
| Хедз-ап | Двое | ICM почти линеен, чистая фишковая игра |

Числовые пороги давления не выдумывать — считать через `poker-math`, команда `risk-premium`.

## Скорость структуры

| Уровень | Тип | Следствие |
|---|---|---|
| 3 мин | гипер/турбо | Стеки мелко́, префлоп-решения доминируют, постфлоп редок |
| 5–8 мин | турбо/regular | Смешанный режим |
| 12 мин | regular | Есть глубокая игра, постфлоп значим |

Конкретные блайнд-структуры GG в репозитории пока отсутствуют. До их получения стадию определять по эффективному стеку в bb и не ссылаться на номера уровней.

## Текстура доски

| Класс | Признак |
|---|---|
| Сухая | Разномастная, без связок, без стрит-дро |
| Полусвязная | Одна масть или одна связка |
| Мокрая | Две карты одной масти плюс связки, много дро |
| Спаренная | Пара на доске |
| Монотонная | Три одной масти |
| Высокая / низкая | По старшинству старшей карты относительно диапазонов |

## Словарь линий

| Термин | Значение |
|---|---|
| RFI | Первым вошёл повышением |
| Лимп | Вход коллом большого блайнда |
| Изоляция | Рейз против лимпера, чтобы остаться с ним один на один |
| 3-bet / 4-bet / 5-bet | Второй, третий, четвёртый рейз в серии |
| C-bet | Ставка агрессора предыдущей улицы |
| Delayed c-bet | Чек на флопе, ставка на тёрне тем же агрессором |
| Probe | Ставка вне позиции после чека агрессора |
| Donk | Ставка вне позиции против агрессора предыдущей улицы |
| Float | Колл со слабой рукой ради отъёма банка на следующей улице |
| Блокер | Своя карта, снижающая число комбинаций сильных рук соперника |
| Полярный диапазон | Только очень сильное и блефы, без середины |
| Мердж | Ставка руками средней силы ради вэлью от худших |

## Специфика GG, влияющая на разбор

- **Нет HUD и нет экспорта hand history.** Статистики соперника не существует. Профилировать только по действиям внутри разбираемой руки.
- **Ввод руки — скриншот.** Данные могут быть распознаны неверно; проверять сохранение фишек до любых расчётов.
- **Bubble Protection и All-in Insurance** искажают стандартную ICM-математику. Если механика активна, отмечать это явно и трактовать ICM как оценку.

## Связанные скиллы

- `poker-math` — все числа.
- `poker-review-method` — процедура разбора руки.
```

- [ ] **Step 2: Проверить консистентность с кодом**

Позиции в скилле обязаны совпадать с `positions_for`:

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -c "from poker_engine.types import positions_for; [print(n, [p.value for p in positions_for(n)]) for n in (2, 6, 8, 9)]"
```

Expected: вывод совпадает с таблицей позиций в скилле. Расхождение — править обе стороны до совпадения.

- [ ] **Step 3: Коммит**

```bash
git add .claude/skills/poker-ontology/SKILL.md
git commit -m "feat(skills): add poker-ontology skill"
```

---

### Task 12: Финальная проверка плана 1

**Files:**
- Create: `packages/poker-engine/README.md`

- [ ] **Step 1: Прогнать весь набор тестов начисто**

```bash
cd packages/poker-engine && .venv/Scripts/python.exe -m pytest -v
```

Expected: все тесты зелёные, ни одного skip, ни одного xfail.

- [ ] **Step 2: Написать README пакета**

Create `packages/poker-engine/README.md`:

```markdown
# poker-engine

Вычислительное ядро покерного коуча. Единственный источник чисел для скиллов
из `.claude/skills/` и для Nuxt-приложения.

## Установка

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

## Тесты

```bash
.venv/Scripts/python.exe -m pytest -v
```

## Использование

```bash
.venv/Scripts/poker-engine.exe icm --stacks 75,25 --payouts 70,30
```

Все команды печатают одну строку JSON. При ошибке — `{"error": "..."}` и код возврата 1.
Полный список команд — в `.claude/skills/poker-math/SKILL.md`.

## Что реализовано

| Модуль | Содержание | Уровень проверки |
|---|---|---|
| `potodds` | Пот-оддсы, chip-EV колла и шова | T1 аналитические инварианты |
| `icm` | Malmuth-Harville, risk premium, bubble factor | T1 аналитические инварианты |
| `bounty` | PKO: наличные за нокаут, порог колла | T1 аналитические инварианты |
| `equity` | Эквити рук, Monte-Carlo и полный перебор | T1 симметрия, T4 перекрёстная сверка |
| `types` | Позиции, улицы, сохранение фишек | T1 инварианты |

## Что ещё не сделано

Уровень T2 из спеки — сверка с публичными эталонами (Nash-чарты, таблицы эквити,
опубликованные примеры ICM) — относится к плану 2 и плану 5. Модули `fgs`,
`pushfold`, `structure`, `handstate` в этом плане не реализуются.
```

- [ ] **Step 3: Проверить, что скиллы видны Claude Code**

Открыть новую сессию в корне репозитория и убедиться, что `poker-math` и `poker-ontology` присутствуют в списке доступных скиллов.

Если не видны — проверить, что файлы лежат по путям `.claude/skills/<name>/SKILL.md` и что поле `name` во фронтматтере совпадает с именем каталога.

- [ ] **Step 4: Коммит**

```bash
git add packages/poker-engine/README.md
git commit -m "docs(engine): add package README"
```

---

## Что даёт этот план

По завершении есть работающее и проверенное ядро для ICM, пот-оддсов, PKO и эквити,
плюс два скилла, которые физически не могут выдумать число — они обязаны вызвать CLI.

## Что этот план сознательно не делает

| Не сделано | Куда отнесено |
|---|---|
| Nash push/fold, префлоп-чарты | План 2 (Ф2) |
| Постфлоп, стадии турнира | План 3 (Ф3) |
| Vision, распознавание скриншота, `handstate` | План 4 (Ф5) |
| FGS, Monte-Carlo ICM как второе мнение | План 5 |
| Эксплойт-слой, методология разбора, golden-set, линтер чисел | План 5 (Ф4 + Ф6) |
| Блайнд-структуры GG, модуль `structure` | Блокировано данными от пользователя |
| Nuxt-продукт | План 6 (Ф7) |
