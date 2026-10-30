# Разбор лобби GG скриптом (D40) — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** команда `poker-engine lobby read` превращает скриншоты лобби GG (два захода на турнир) в
файл турнира — готовый контекст `coach start`; движок сам считает средний стек на каждой раздаче.

**Architecture:** три слоя. `lobby_ocr.py` — картинка → строки OCR (RapidOCR, необязательная
зависимость). `lobby_read.py` — строки OCR одного кадра → поля кадра (чистый, по форме чисел и
расположению). `lobby.py` — кадры захода → проверки → файл турнира (создать / дописать / найти).
Движок: `frames.context_payload` выводит средний стек из `startingStackChips`, новые пометки
`payouts_provisional` и `field_from_table`.

**Tech Stack:** Python 3.12, pytest; RapidOCR (`rapidocr-onnxruntime==1.4.4`,
`onnxruntime==1.20.1`, `pillow==13.0.0`) — группа `[lobby]`.

**Spec:** `docs/superpowers/specs/2026-10-31-lobby-reader-design.md` (утверждена пользователем
2026-10-31).

**Ветка.** `feat/lobby-reader` от `feat/plan6-acceptance` (там L6/L7 после приёмки и починки
Фазы 14) плюс коммиты спеки и плана из `claude/suspicious-elbakyan-ccccde`. Если к старту
`feat/plan6-acceptance` уже влита в `main` — от `main`. Вливание — только с согласия пользователя.

## Отступления от спеки (решения плана)

- **Закрыта ли регистрация** — по уровню, а не по надписи «Идёт» (спека §7.9): `lateRegOpen =
  уровень шапки < уровень закрытия из «Инфо»` («окт 31, 01:30 (Уровень 17)»; на 17-м уровне шапка
  уже «Идёт»). Подписи RapidOCR читает латинскими двойниками, уровень — числом.
- **Ад-дон** (спека §6) не распознаётся: образца нет. Допущение «без ад-донов» пишется в README
  рядом с выводом среднего стека; вернуться, когда пользователь даст лобби турнира с ад-доном.

## Global Constraints

- Конвенции ядра из `CLAUDE.md`: один коммит на задачу, правки ревью — `fix(engine): …`; два
  ревью на задачу (спека, потом качество); валидация — в движке, `cli.py` — чистый парсер; отказ
  в тесте пинится `match=`; тесты — аналитические инварианты и числа со скриншотов, не из памяти.
- Ядро и его тесты в облаке (Linux, без `[lobby]`) работают как раньше: `lobby_read.py` и
  `lobby.py` не импортируют RapidOCR; тесты, которым нужен OCR или скриншоты, — `pytest.skip`.
- Скриншоты в репозиторий не идут. Фикстуры — JSON строк OCR с замаскированными никами (Задача 2).
- Анти-цели спеки §4: не достраивать пропущенную строку, не двигать число под сумму, не писать
  файл при непрошедшей проверке.
- `onnxruntime==1.31.1` падает на машине пользователя (segfault при импорте) — пин 1.20.1.
- Скриншоты для тестов: `C:\Users\Admin\Documents\Screenshots\lobby\fifty-stack-2026-10-30\`
  (`pass1-info-level13.png`, `pass1-prizes-level14.png`, `pass1-structure-level16.png`,
  `pass2-info-level17.png`, `pass2-prizes-level17.png`, все 1195×1035) и
  `C:\Users\Admin\Documents\Screenshots\win_2026-09-10_00-29-09.png` (Инфо),
  `…_00-29-48.png` (Структура), `…_00-31-04.png` (Призовой фонд, 13 строк из 165 мест), 1200×740.

## Review Focus

1. **Шум OCR в числах:** полноширинные скобки и пробелы (`（146,571(29.3 BB)`), диапазон мест как
   `11~12`, `16 ~19`, `70 ~ 107`, `11-12`; заголовок турнира разбит на два бокса (`Fifty` +
   `Stack $5.50`). Ожидание — то же значение, что на экране. Тест — Задача 3,
   `test_noisy_numbers_normalize`.
2. **Лишний кадр в заходе** (вкладка «Структура», «Игроки» или чужое окно). Ожидание —
   предупреждение «кадр пропущен», не отказ и не мусор в выплатах. Тест — Задача 4,
   `test_structure_shot_is_skipped_with_warning`.
3. **Заход 2 без кадра «Инфо», а файлов с этим названием два** (тот же турнир в другой день).
   Ожидание — отказ со списком файлов и просьбой добавить «Инфо». Тест — Задача 4,
   `test_second_pass_ambiguous_without_info`.
4. **Повторный заход 1 после захода 2** (предварительные выплаты поверх окончательных).
   Ожидание — отказ, файл прежний. Тест — Задача 4, `test_provisional_never_overwrites_final`.
5. **Раздача во время поздней регистрации при окончательном лобби.** Ожидание — средний стек по
   столу, пометка `field_from_table`, но не `payouts_provisional`. Тест — Задача 1,
   `test_late_reg_hand_with_final_lobby_uses_table`.

---

### Task 1: Движок — средний стек из стартового стека, пометки, `--late-reg`

**Files:**
- Modify: `packages/poker-engine/src/poker_engine/frames.py` (`context_payload`)
- Modify: `packages/poker-engine/src/poker_engine/handstate.py` (`TournamentContext`, `context_from_dict`, `_validate_context`)
- Modify: `packages/poker-engine/src/poker_engine/pushfold.py` (`_context_flags`), `analyze.py` (пометки)
- Modify: `packages/poker-engine/src/poker_engine/coach.py` (`start`, `step`), `cli.py` (`coach start --late-reg`)
- Modify: `.claude/skills/poker-preflop-mtt/SKILL.md` и `packages/poker-engine/README.md` — таблицы пометок
- Test: `tests/test_frames.py`, `tests/test_handstate.py`, `tests/test_coach.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: поля контекста `startingStackChips` (число > 0), `payoutsFinal` (bool, необязательно),
  `averageStackSource` (`"lobby"` | `"table"`, ставит `context_payload`);
  `TournamentContext.payouts_final: bool | None`, `TournamentContext.average_stack_source: str | None`;
  `context_payload(raw: dict, last_frame: dict | None, first_frame: dict | None = None) -> dict`;
  `coach.start(path: str, context: dict, late_reg_open: bool | None = None) -> dict`;
  пометки `payouts_provisional`, `field_from_table`.

Правило `context_payload` (по порядку):
1. Есть `averageStackBb` или `averageStackChips` — как сейчас, вывода нет, источник не ставится.
2. Иначе есть `startingStackChips` и кадр:
   - `lateRegOpen` ложно — `averageStackBb = startingStackChips × entrants / playersLeft(last_frame) / bb(last_frame)`,
     `averageStackSource = "lobby"`;
   - `lateRegOpen` истинно — `averageStackBb` = среднее `stackBb + investedBb` по местам
     `node_payload(first_frame)` (в BB, единицы кадра уже сняты), `averageStackSource = "table"`.
3. `startingStackChips`, если есть, всегда проверяется `check_positive` (имя «стартовый стек») —
   и без кадра (`coach start`), и когда вывод не нужен.

- [ ] **Step 1: Тесты вывода среднего стека** — в `tests/test_frames.py`:

```python
def test_average_stack_from_starting_stack_after_late_reg():
    raw = {**_context(), "startingStackChips": 50000, "entrants": 2351, "lateRegOpen": False}
    frame = {**preflop_vs_open()[0], "playersLeft": 802, "unit": "bb"}
    frame["blinds"] = {"sb": 2500, "bb": 5000, "ante": 600}
    payload = context_payload(raw, frame, first_frame=frame)
    assert payload["averageStackBb"] == pytest.approx(50000 * 2351 / 802 / 5000)
    assert payload["averageStackSource"] == "lobby"

def test_late_reg_hand_with_final_lobby_uses_table():
    first = preflop_vs_open()[0]
    raw = {**_context(), "startingStackChips": 50000, "lateRegOpen": True, "payoutsFinal": True}
    payload = context_payload(raw, preflop_vs_open()[-1], first_frame=first)
    seats = node_payload(first)["seats"]
    expected = sum(s["stackBb"] + s.get("investedBb", 0.0) for s in seats) / len(seats)
    assert payload["averageStackBb"] == pytest.approx(expected)
    assert payload["averageStackSource"] == "table"

def test_explicit_average_stack_wins_over_starting_stack():
    raw = {**_context(), "averageStackBb": 50.5, "startingStackChips": 50000}
    payload = context_payload(raw, preflop_vs_open()[0], first_frame=preflop_vs_open()[0])
    assert payload["averageStackBb"] == 50.5 and "averageStackSource" not in payload

def test_starting_stack_must_be_positive():
    with pytest.raises(ValueError, match="стартовый стек должен быть > 0"):
        context_payload({**_context(), "startingStackChips": 0}, None)
```

(`_context()` фикстуры несёт `averageStackBb` — в тестах вывода его убрать: `raw.pop("averageStackBb")`
перед вызовом; строитель правит фикстуру вызова, не `conftest.py`.)

- [ ] **Step 2: Тесты пометок и `--late-reg`** — пометки идут через `advise`/`analyze` на контексте
  с `payoutsFinal: False` → `payouts_provisional` есть; `payoutsFinal` нет или `True` — пометки
  нет (старые контексты не меняются); `averageStackSource: "table"` → `field_from_table`.
  `test_coach.py::test_start_late_reg_overrides_context`: `coach.start(path, ctx_with_lateRegOpen_False, late_reg_open=True)`
  — в файле раздачи `context["lateRegOpen"] is True`; без аргумента — как в контексте.
  `test_cli.py`: `coach start --late-reg open|closed` передаёт `True|False`, без флага — `None`.
  `context_from_dict` отвергает `averageStackSource` вне `{"lobby","table"}`:
  `match="averageStackSource"`.

- [ ] **Step 3: Прогнать — падают.** `.venv/Scripts/python -m pytest tests/test_frames.py tests/test_coach.py tests/test_cli.py -q`

- [ ] **Step 4: Реализация.** `context_payload` по правилу выше; `coach.step` передаёт
  `first_frame=seen[0]`; `TournamentContext` — два поля (`None` по умолчанию в
  `context_from_dict`); `_context_flags` и `analyze` добавляют `payouts_provisional`
  (`payouts_final is False`) и `field_from_table` (`average_stack_source == "table"`) после
  `late_reg_open`. Тексты пометок в `poker-preflop-mtt/SKILL.md` и README:
  - `payouts_provisional` — «выплаты сняты до закрытия поздней регистрации: лесенка предварительна»;
  - `field_from_table` — «средний стек поля — средний по столу: раздача во время поздней регистрации»;
  - `late_reg_open` — «поздняя регистрация была открыта: поле ещё росло» (лесенка теперь может быть
    окончательной — о ней говорит `payouts_provisional`).

- [ ] **Step 5: Полный прогон** — `.venv/Scripts/python -m pytest -q`: прежнее число passed плюс новые.

- [ ] **Step 6: Commit** — `feat(engine): средний стек из стартового стека, пометки лобби, coach start --late-reg`

---

### Task 2: Распознавание и фикстуры

**Files:**
- Modify: `packages/poker-engine/pyproject.toml` — `[project.optional-dependencies] lobby = ["rapidocr-onnxruntime==1.4.4", "onnxruntime==1.20.1", "pillow==13.0.0"]`
- Create: `packages/poker-engine/requirements-lobby.lock` — `pip freeze` рабочего окружения (пины из спайка: `numpy==2.5.4`, `opencv-python==5.0.0.93`, `shapely==2.2.0`, `pyclipper==1.4.0`, …), комментарий как у `requirements-dev.lock`
- Create: `packages/poker-engine/src/poker_engine/lobby_ocr.py`
- Create: `packages/poker-engine/scripts/record_lobby_fixtures.py`
- Create: `packages/poker-engine/tests/data/lobby/*.json` — восемь фикстур (по скриншоту из Global Constraints, имя = имя файла без `.png`)
- Test: `tests/test_lobby_ocr.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Line: text: str; x: float; y: float; w: float; h: float; score: float`
  (рамка в пикселях исходного кадра) — в `lobby_read.py` (Задача 3 его импортирует; здесь
  создаётся модуль с одним `Line`, чтобы `lobby_ocr` не тянул разбор);
  `ocr_image(path: str) -> tuple[list[Line], int, int]` (строки, ширина, высота);
  формат фикстуры: `{"width", "height", "captured": "YYYY-MM-DD", "lines": [{"text","x","y","w","h","score"}]}`.

- [ ] **Step 1: Тест OCR (локальный)** — `test_lobby_ocr.py::test_final_prizes_are_read`:
  `pytest.importorskip("rapidocr_onnxruntime")`, скип без файла `pass2-prizes-level17.png`;
  тексты строк содержат `"$11,896.06"`, `"$1,450.17"`, `"208~330"` (после нормализации пробелов
  вокруг `~`), `"802/2,351"`.
- [ ] **Step 2: `ocr_image`** — RapidOCR на всём кадре, увеличенном в 2 раза (LANCZOS), координаты
  делятся обратно на 2. Нет зависимостей — `ValueError("для разбора лобби нужны зависимости:
  pip install -e \".[lobby]\"")`. Замер спайка: ~31 с на кадр 1195×1035 на i5-4460 — допустимо;
  быстрее можно, если тест Step 1 и тесты Задачи 3 на настоящих кадрах остаются зелёными.
- [ ] **Step 3: Рекордер** — `python scripts/record_lobby_fixtures.py <png…> --out tests/data/lobby`:
  пишет фикстуру; `captured` — дата изменения файла. **Маска ников:** текст строки заменяется на
  `"•"`, если центр рамки ниже 190 px и левее `0.34·width` или правее `0.65·width` (панели
  «Бэкинг» и «Игроки»), либо ниже 100 px и левее 400 px (строка лидеров шапки). Заголовок турнира
  (выше 100 px) и средняя колонка не маскируются. Строитель глазами сверяет каждую фикстуру: ни
  одного ника.
- [ ] **Step 4: Записать восемь фикстур**, прогнать тест Step 1.
- [ ] **Step 5: Commit** — `feat(engine): распознавание лобби (RapidOCR) и фикстуры`

---

### Task 3: Кадр лобби → поля (`lobby_read.py`)

**Files:**
- Modify: `packages/poker-engine/src/poker_engine/lobby_read.py`
- Test: `tests/test_lobby_read.py` (на фикстурах Задачи 2, без OCR)

**Interfaces:**
- Consumes: `Line`, фикстуры Задачи 2.
- Produces:

```python
@dataclass(frozen=True)
class Header:
    level: int
    players_left: int
    entrants: int
    unique: int
    reentries: int
    prize_pool_usd: float
    buy_in_usd: float
    average_stack_chips: int

@dataclass(frozen=True)
class Info:
    prize_share_usd: float          # «$5.06+$0.44» → 5.06
    fee_usd: float                  # → 0.44
    starting_stack_chips: int
    start: tuple[int, int, int, int]            # месяц, день, час, минута
    late_reg_close_level: int                   # «(Уровень 17)»
    blind_interval_min: int
    seats_per_table: int                        # «8 игроков на стол»
    early_bird: bool

@dataclass(frozen=True)
class Shot:
    kind: str                        # "prizes" | "info" | "other"
    title: str                       # «Fifty Stack $5.50»
    header: Header
    payouts: list[tuple[int, int, float]]   # только у "prizes"
    places_paid: int | None                 # «N призовых мест», только у "prizes"
    info: Info | None                       # только у "info"
    low_confidence: list[str]               # имена полей с уверенностью < 0.8

def read_shot(lines: list[Line], width: int, height: int) -> Shot: ...
```

Поля ищутся по форме чисел и взаимному расположению, не по подписям (подписи — латинские
двойники, спека §3, §8). Опоры: `A/B` без скобок справа от середины шапки — осталось/входы;
`A/B (C)` — блайнды; `A|B` — уникальные/ре-энтри; самый левый `$x.xx` шапки — призовой фонд;
последняя по высоте строка `N (x BB)` правой колонки шапки — средний стек; таблица «место —
$приз» средней колонки — выплаты; `N` перед двойником «призовых мест» над таблицой — `places_paid`;
в «Инфо» `$a+$b`, `N (x BB)`, `мес D, ЧЧ:ММ (… N)`, `N` перед двойником «мин» в строке интервала.
Месяцы — по трём буквам с двойниками (`OKT` = окт). Текст нормализуется NFKC, пробелы вокруг `~`,
`/`, `|` убираются, `-` между числами диапазона = `~`. Кадр без таблицы выплат и без строк «Инфо» —
`kind = "other"`. Нет обязательного поля шапки — `ValueError(f"на кадре не найдено: {поле}")`
(поле по-русски: «счётчик игроков», «призовой фонд», «средний стек», …).

- [ ] **Step 1: Тесты на фикстурах — точные значения со скриншотов:**

```python
def test_final_prizes_shot():                       # pass2-prizes-level17
    shot = read_shot(*_fixture("pass2-prizes-level17"))
    assert shot.kind == "prizes" and shot.title == "Fifty Stack $5.50"
    assert shot.places_paid == 330
    assert shot.payouts == [(1, 1, 1450.17), (2, 2, 1116.80), (3, 3, 861.17), (4, 4, 664.05),
        (5, 5, 512.05), (6, 6, 394.84), (7, 7, 304.47), (8, 8, 234.77), (9, 9, 181.03),
        (10, 10, 119.02), (11, 12, 94.42), (13, 15, 74.91), (16, 19, 59.43), (20, 26, 47.14),
        (27, 37, 37.40), (38, 55, 29.67), (56, 84, 23.54), (85, 131, 18.67), (132, 207, 14.81),
        (208, 330, 11.75)]
    assert shot.header == Header(level=17, players_left=802, entrants=2351, unique=1808,
        reentries=543, prize_pool_usd=11896.06, buy_in_usd=5.50, average_stack_chips=146571)

def test_provisional_prizes_shot():                 # pass1-prizes-level14
    shot = read_shot(*_fixture("pass1-prizes-level14"))
    assert shot.places_paid == 270 and len(shot.payouts) == 19
    assert shot.payouts[0] == (1, 1, 1154.30) and shot.payouts[-1] == (170, 270, 11.15)
    assert (shot.header.players_left, shot.header.entrants) == (951, 1823)
    assert (shot.header.unique, shot.header.reentries) == (1474, 349)
    assert shot.header.prize_pool_usd == 9224.38 and shot.header.average_stack_chips == 95951

def test_info_shot():                                # pass1-info-level13
    shot = read_shot(*_fixture("pass1-info-level13"))
    assert shot.kind == "info" and shot.header.level == 13
    assert shot.info == Info(prize_share_usd=5.06, fee_usd=0.44, starting_stack_chips=50000,
        start=(10, 30, 23, 5), late_reg_close_level=17, blind_interval_min=8,
        seats_per_table=8, early_bird=True)

def test_old_small_window_shots():                   # 1200×740, 2026-09-10
    prizes = read_shot(*_fixture("win_2026-09-10_00-31-04"))
    assert prizes.places_paid == 165 and prizes.payouts[-1] == (13, 15, 58.94)
    assert (prizes.header.players_left, prizes.header.entrants) == (783, 1134)
    info = read_shot(*_fixture("win_2026-09-10_00-29-09"))
    assert info.info.start == (9, 9, 23, 5) and info.info.seats_per_table == 8
    assert info.header.prize_pool_usd == 8000.0       # оверлей: строка «Оверлей» в шапке есть

def test_structure_shot_is_other():
    assert read_shot(*_fixture("pass1-structure-level16")).kind == "other"

def test_noisy_numbers_normalize():                  # Review Focus 1, синтетические Line
    ...  # «（146,571(29.3 BB)» → 146571; «16 ~19» → (16, 19); «11-12» → (11, 12);
         # заголовок «Fifty» + «Stack $5.50» в одной строке → «Fifty Stack $5.50»
```

Плюс отказ: фикстура `pass2-prizes-level17` без строки счётчика →
`pytest.raises(ValueError, match="на кадре не найдено: счётчик игроков")`; строка цены с
`score=0.5` → `"призовой фонд" in shot.low_confidence`.

- [ ] **Step 2: Прогнать — падают.**
- [ ] **Step 3: Реализация `read_shot`** по опорам выше.
- [ ] **Step 4: Прогнать — проходят;** плюс локальный тест «скриншот → `ocr_image` → `read_shot`»
  на пяти кадрах 10-30, скип без `[lobby]`/файлов.
- [ ] **Step 5: Commit** — `feat(engine): разбор кадра лобби по форме чисел`

---

### Task 4: Заход → проверки → файл турнира (`lobby.py`)

**Files:**
- Create: `packages/poker-engine/src/poker_engine/lobby.py`
- Test: `tests/test_lobby.py` (`Shot` руками и фикстуры через `read_shot`; без OCR)

**Interfaces:**
- Consumes: `Shot`, `Header`, `Info`, `read_shot` (Задача 3); `_validate_context`,
  `context_from_dict` (`handstate`).
- Produces:
  - `merge(shots: list[tuple[str, Shot]], existing: dict | None, captured: date) -> tuple[dict, list[str]]`
    — запись турнира и предупреждения; отказ — `ValueError`. Строка кортежа — имя файла кадра для
    текстов.
  - `tournament_path(directory: str, title: str, start: date) -> str` — `<dir>/<title> <YYYY-MM-DD>.json`,
    символы, запрещённые в именах Windows, заменяются на `_`.
  - `find(directory: str, title: str) -> list[dict]` — `[{"path", "start", "payoutsFinal"}]`.
  - `save(shots, directory, captured) -> dict` — ищет существующий файл, `merge`, пишет;
    ответ `{"tournament": path, "payoutsFinal": bool, "warnings": [...]}`.

Запись турнира — контекст `coach start` плюс справка:
`{"format": "poker-coach-tournament", "version": 1, "title", "start": "YYYY-MM-DDTHH:MM",
"prizeShareUsd", "feeUsd", "buyInUsd", "pko", "blindIntervalMin", "lateRegCloseLevel",
"earlyBird", "seatsPerTable", "startingStackChips", "payouts": [{"from","to","amount"}],
"placesPaid", "payoutsFinal", "entrants", "playersLeft", "lateRegOpen", "prizePoolUsd"}`.
`bubbleRefundUsd` и средний стек не пишутся (спека §6). `pko` — `"Bounty" in title`. Год `start` —
год `captured`; месяц `start` больше месяца `captured` — год минус один. `lateRegOpen` =
`header.level < lateRegCloseLevel`; `payoutsFinal = not lateRegOpen` у кадра выплат.

Проверки и их тексты (по порядку, отказ — файл не тронут):

| # | Условие | Текст `ValueError` / предупреждения |
|---|---|---|
| 1 | нет кадра `prizes` | `нет кадра «Призового фонда»` |
| 2 | нет кадра `info` и нет файла турнира | `нет кадра «Инфо»: без него не узнать стартовый стек и размер стола` |
| 3 | `low_confidence` не пуст | `поле «{поле}» прочитано неуверенно на кадре {файл}: снимите его заново` |
| 4 | одна строка мест на двух кадрах с разной суммой | `строка мест {a}–{b} читается по-разному: ${p1} и ${p2}` |
| 5 | первое место ≠ 1 или дыра | `нет мест {a}–{b}: снимите кадр «Призового фонда», где они видны` |
| 6 | конец списка < `places_paid` | то же сообщение с `a = конец + 1`, `b = places_paid` |
| 7 | `unique + reentries ≠ entrants` | `в шапке {файл} уникальных и ре-энтри {u} + {r}, а входов {e}` |
| 8 | `|start × entrants / players_left − average| > 0.5%` | `средний стек шапки {avg} не сходится с расчётом {calc} на кадре {файл}` |
| 9 | `payoutsFinal` и `|Σ − фонд| > 0.005 × places_paid + 0.005` | `сумма выплат ${s} не равна призовому фонду ${pool}: перечитайте строки или снимите кадр заново` |
| 10 | не `payoutsFinal` и та же разница | предупреждение `выплаты предварительные: сумма ${s} против фонда ${pool}` |
| 11 | файл есть, другое название / стартовый стек, входов меньше | `кадры от другого турнира: {поле} {было} против {стало}` |
| 12 | в файле `payoutsFinal`, а кадры предварительные | `в файле турнира уже окончательные выплаты, а кадры сняты во время поздней регистрации` |
| 13 | нет `info`, файлов с названием несколько | `турниров «{title}» несколько: {пути} — добавьте кадр «Инфо»` |
| 14 | кадр `other` | предупреждение `кадр {файл} пропущен: это не «Инфо» и не «Призовой фонд»` |
| 15 | итог | `_validate_context(context_from_dict(record))` |

Суммы в текстах — с двумя знаками и разделителем тысяч, как в лобби (`$11,896.06`). Шапка
сверяется (7, 8) на каждом кадре; из кадров захода в запись идёт шапка кадра выплат.

- [ ] **Step 1: Тесты — по одному на каждую строку таблицы**, каждый с `match=` своего текста, плюс:

```python
def test_two_passes_end_to_end():
    first = save([_shot("pass1-info-level13"), _shot("pass1-prizes-level14")], tmp, date(2026, 10, 30))
    record = json.load(open(first["tournament"], encoding="utf-8"))
    assert first["tournament"].endswith("Fifty Stack $5.50 2026-10-30.json")
    assert record["payoutsFinal"] is False and record["placesPaid"] == 270
    assert any(w.startswith("выплаты предварительные: сумма $9,234.50 против фонда $9,224.38")
               for w in first["warnings"])
    second = save([_shot("pass2-prizes-level17")], tmp, date(2026, 10, 31))
    record = json.load(open(second["tournament"], encoding="utf-8"))
    assert second["tournament"] == first["tournament"] and second["warnings"] == []
    assert record["payoutsFinal"] is True and record["lateRegOpen"] is False
    assert record["placesPaid"] == 330 and record["entrants"] == 2351
    assert record["startingStackChips"] == 50000 and record["seatsPerTable"] == 8
    assert sum((p["to"] - p["from"] + 1) * p["amount"] for p in record["payouts"]) == pytest.approx(11896.06)

def test_old_partial_list_names_missing_places():
    with pytest.raises(ValueError, match="нет мест 16–165: снимите кадр"):
        save([_shot("win_2026-09-10_00-29-09"), _shot("win_2026-09-10_00-31-04")], tmp, date(2026, 9, 10))
    assert os.listdir(tmp) == []
```

  Плюс Review Focus 2–4: `test_structure_shot_is_skipped_with_warning`,
  `test_second_pass_ambiguous_without_info`, `test_provisional_never_overwrites_final`.
- [ ] **Step 2: Прогнать — падают.**
- [ ] **Step 3: Реализация** `merge`, `tournament_path`, `find`, `save`; запись — через временный
  файл и замену, как `coach._write`.
- [ ] **Step 4: Прогнать — проходят;** мутационная проверка: снести каждую проверку таблицы
  целиком — падает её тест.
- [ ] **Step 5: Commit** — `feat(engine): файл турнира из кадров лобби, проверки без угадывания`

---

### Task 5: CLI, скиллы, сквозная раздача

**Files:**
- Modify: `packages/poker-engine/src/poker_engine/cli.py` — `lobby read`, `lobby find`
- Modify: `.claude/skills/poker-hand-vision/SKILL.md` (раздел «Контекст из лобби»),
  `.claude/skills/poker-review-method/SKILL.md` (шаг «Старт»), `packages/poker-engine/README.md`
- Modify: `CLAUDE.md` (строка состояния и команды), журнал/реестр долгов: D40 закрыт, D41 новый
  (защита на баббле не по правилам ПОКЕРОК — спека §6), D11 — отложен с доводом (спека §4)
- Test: `tests/test_cli.py`, `tests/test_lobby.py` (сквозной)

**Interfaces:**
- Consumes: `lobby.save`, `lobby.find`, `lobby_ocr.ocr_image`, `lobby_read.read_shot`,
  `coach.start(..., late_reg_open=...)`.
- Produces: `poker-engine lobby read <png…> [--dir DIR]` →
  `{"tournament", "payoutsFinal", "warnings"}`; `poker-engine lobby find --title T [--dir DIR]` →
  `{"tournaments": [...]}`. `DIR` по умолчанию — `%USERPROFILE%\Documents\poker-coach\tournaments`
  (`Path.home() / "Documents" / "poker-coach" / "tournaments"`). Дата съёмки — дата изменения
  самого нового кадра.

- [ ] **Step 1: Тесты CLI** — `lobby read` без `[lobby]` → `{"error": "для разбора лобби нужны
  зависимости…"}` с кодом 1 (подменой импорта); `lobby find` по каталогу с двумя файлами
  одного названия — два элемента, отсортированы по `start`.
- [ ] **Step 2: Сквозной тест** `test_lobby_file_drives_a_hand`: файл захода 2 из фикстур →
  `coach.start(hand, record, late_reg_open=False)` → `coach.step` с кадром префлопа фикстур
  (`blinds.bb` = 5000, `playersLeft` = 802) → в `answer["flags"]` нет `ladder_incomplete`,
  `payouts_provisional`, `field_from_table`; в файле раздачи — контекст с
  `startingStackChips`. Тот же старт с `late_reg_open=True` → есть `field_from_table`.
- [ ] **Step 3: Реализация CLI** — чистый парсер: OCR → `read_shot` → `lobby.save`; ошибки — как
  у прочих команд.
- [ ] **Step 4: Скиллы.** L6 «Контекст из лобби»: таблица полей заменяется на «два захода (спека
  §5) → `poker-engine lobby read <кадры>`; ответ `error` — снять кадр, названный в тексте; руками
  поля не переписывать». L7 «Старт»: `poker-engine lobby find --title "<название из заголовка
  стола>"` → один файл — `coach start --context <файл> --late-reg open|closed` (по панели стола
  первого кадра: «Поздняя регистрация» — `open`, «Ср. стек» — `closed`); несколько — спросить
  пользователя дату; нет — попросить кадры лобби.
- [ ] **Step 5: Полный прогон** `.venv/Scripts/python -m pytest -q` и ручной прогон
  `poker-engine lobby read` на пяти кадрах 10-30 (два захода) на машине пользователя; время
  записать в журнал.
- [ ] **Step 6: Commit** — `feat(engine): команда lobby, L6/L7 на файле турнира; docs: D40 закрыт, D41`
