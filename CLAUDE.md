# poker_coach_gpt

Nuxt-оболочка плюс Python-ядро `packages/poker-engine` (ICM, пот-оддсы, PKO bounty EV, эквити).
Вся текущая работа идёт в ядре; Nuxt-часть план не трогает.

## Текущее состояние

**Идёт план 3** — модель поля, настоящая лесенка, PKO и бюджет 2 секунды
(`docs/superpowers/plans/2026-09-12-icm-field-model.md`, спека
`docs/superpowers/specs/2026-09-12-icm-field-model-design.md`).

**Остаток плана идёт по фазам** (решение пользователя 2026-09-24):
`docs/superpowers/state/2026-09-24-plan3-phases.md`. Одна фаза — одна сессия до ~150k
контекста. Ревью задачи делает следующая фаза. Там же реестр долгов с хозяевами.
Каждая фаза пишет отчёт в журнал `docs/superpowers/state/2026-09-12-icm-field-execution-notes.md`
и промпт следующей фазы в `docs/superpowers/state/plan3-next-prompt.md`.

- Задача 1 (лесенка выплат, `ladder.py`) — в `main`, прогоны ревью A–D (`472021d` … `d686089`).
- Фаза 1 сделана (ветка `claude/serene-bell-yni6li`): прогон E Задачи 1, Задача 2 (`icm_field.py`), 376 passed.
- Фаза 2 сделана: ревью Задачи 2 (F2.1, `0f5336e`), Задача 3 (риск-премия и bubble factor в `icm_field.py`), 394 passed.
- Фаза 3 сделана: ревью Задачи 3 — `НАХОДОК НЕТ`, Задача 4 (`analyze` на модели поля, `178ea65`, D2–D6, D17), 404 passed.
- Фаза 4 сделана: ревью Задачи 4 — F4.1 (`573e12c`), Задача 5 (модель половины, `--split` убран, `37710bd`, D8), 413 passed.
- Фаза 5 сделана: ревью Задачи 5 — F5.1 (`8616497`), Задача 6 (PKO в `analyze`, `61e57fd`), 439 passed.
- Фаза 6 сделана: ревью Задачи 6 — F6.1 (`b15f8e8`), Задача 7 (защита на баббле, `03aa820`, D9 закрыт ответом пользователя), 459 passed.
- **Следующая — Фаза 7:** ревью Задачи 7 и F6.1, затем Задача 8 (бюджет 2 с, D7, D20; нужна сеть для `eval7`). Промпт — `docs/superpowers/state/plan3-next-prompt.md`.

Планы 1 (`feat/poker-engine-core`) и 2 (`feat/screenshot-coach-engine`) закрыты и влиты
в `main` (обе ветки удалены 2026-09-24, история целиком в `main`): оба ревью на задачу, мутационная приёмка, финальное ревью ветки, 304 теста зелёные.
Пункт журнала «копии `check_positive` в `bounty.py`» закрыт в плане 3 (прогон D Задачи 1);
«семь вызовов ICM в три» — Задача 8 плана 3.

**Для контекста планов 1–2 прочитать `docs/superpowers/state/2026-09-10-screenshot-coach-execution-notes.md`**,
разделы «Task 7» и «Дальше» — что решено против текста плана, мутационная таблица, ledger
отложенного и два открытых вопроса про модель ICM (оба — предмет отдельного плана).

**Затем `docs/superpowers/state/HANDOFF.md`** — там сетап машины, что появилось
в Tasks 7–12, восемь решений, принятых против текста плана (план требовал недоказуемых инвариантов),
один пункт, ждущий решения пользователя, и список сознательно отложенных мелочей.

| Документ | Что |
|---|---|
| `docs/superpowers/plans/2026-09-09-poker-engine-core.md` | план, 12 задач |
| `docs/superpowers/specs/2026-09-09-poker-skillpack-design.md` | спека |
| `docs/superpowers/state/HANDOFF.md` | точка входа для новой сессии |
| `docs/superpowers/state/2026-09-09-poker-engine-execution-notes.md` | полный журнал ревью Tasks 1–6 плана 1 |
| `docs/superpowers/plans/2026-09-10-screenshot-coach-engine.md` | план 2, 7 задач |
| `docs/superpowers/specs/2026-09-10-screenshot-coach-design.md` | спека плана 2 |
| `docs/superpowers/state/2026-09-10-screenshot-coach-execution-notes.md` | **точка входа**: журнал плана 2, Tasks 1–7 |
| `docs/superpowers/state/2026-09-11-task7-handoff-2.md` | handoff второй сессии Task 7 (историческое) |
| `docs/superpowers/state/2026-09-11-task7-handoff.md` | handoff первой сессии Task 7 (историческое) |
| `docs/superpowers/state/2026-09-11-next-session-prompt.md` | промпт третьей сессии (историческое) |
| `docs/superpowers/plans/2026-09-12-icm-field-model.md` | **план 3, 8 задач — текущая работа**; решения прогонов A–D Задачи 1 внутри |
| `docs/superpowers/specs/2026-09-12-icm-field-model-design.md` | спека плана 3 |
| `docs/superpowers/state/2026-09-24-plan3-phases.md` | **фазы плана 3**: правила сессий, бюджет, реестр долгов, шаблоны промптов |
| `docs/superpowers/state/2026-09-12-icm-field-execution-notes.md` | журнал плана 3, раздел на каждую фазу |
| `docs/superpowers/state/plan3-next-prompt.md` | промпт очередной фазы (перезаписывается) |

Плагины перечислены в `.claude/settings.json`.

## Команды

```bash
# ядро
cd packages/poker-engine
.venv/Scripts/python -m pytest              # 304 passed, ~5.5 мин

# первый запуск на новой машине
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.lock
.venv/Scripts/python -m pip install -e ".[dev]" --no-deps

# референсные репо (322 МБ, вне git, пины в vendor-ref.lock)
bash scripts/fetch-vendor-ref.sh

# Nuxt
npm install && npm run dev
```

## Конвенции ядра

- Один коммит на задачу, правки ревью — отдельными `fix(engine): …`. Conventional Commits.
- Каждая задача проходит два ревью: сначала соответствие спеке, потом качество кода.
- Валидация аргументов живёт в движке, не в CLI: Task 9 делает `cli.py` чистым парсером, поэтому
  тексты `ValueError` из `src/poker_engine/_checks.py` — пользовательские сообщения об ошибках.
  Менять их нельзя без обновления тестов.
- Гарды в `_checks.py` названы по ограничению, не по домену: `check_positive`, `check_non_negative`,
  `check_probability`. Тексты собираются из параметра `name`, поэтому переименование гарда
  пользователю не видно, а вот текст самого сообщения — виден и менять его нельзя.
- Имя, передаваемое в `_checks.py`, обязано быть существительным **мужского рода**: шаблоны
  собраны как `{name} должен быть > 0` и `{name} не может быть отрицательным`. `приз за место 1`
  и `размер колла` встают грамматично, `выплата` и `сумма` — нет. Средний род тоже проходит с
  «не может быть отрицательным» (`вложение на месте 3`).
- Где несколько гардов модуля бросают `ValueError`, тест на отказ обязан пинить сообщение через
  `match=`: голый `pytest.raises(ValueError)` ловит любой гард, включая не тот. Мутационная
  приёмка должна включать класс «снести гард целиком», а не только развороты операторов.
- Общие гарды — только в `_checks.py`, не копировать в новые модули.
- Тесты — аналитические инварианты, проверяемые на бумаге, а не числа из памяти модели.
