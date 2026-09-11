# poker_coach_gpt

Nuxt-оболочка плюс Python-ядро `packages/poker-engine` (ICM, пот-оддсы, PKO bounty EV, эквити).
Вся текущая работа идёт в ядре; Nuxt-часть план не трогает.

## Текущее состояние

Планы 1 (`feat/poker-engine-core`) и 2 (`feat/screenshot-coach-engine`) закрыты и влиты
в `main`. План 2 исполнен целиком: Tasks 1–7, оба ревью на задачу, мутационная приёмка и
финальное ревью всей ветки, находки починены, 304 теста зелёные на слитом `main`.

Дальше — либо отдельный план по алгоритму ICM (перебор Malmuth-Harville не переносит реальные
лесенки выплат), либо `refactor(engine)` из журнала: семь вызовов ICM в три, копии
`check_positive` в `bounty.py`, единый источник предела узлов.

**Перед работой прочитать `docs/superpowers/state/2026-09-10-screenshot-coach-execution-notes.md`**,
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
