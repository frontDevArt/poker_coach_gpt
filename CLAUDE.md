# poker_coach_gpt

Nuxt-оболочка плюс Python-ядро `packages/poker-engine` (ICM, пот-оддсы, PKO bounty EV, эквити).
Вся текущая работа идёт в ядре; Nuxt-часть план не трогает.

## Текущее состояние

Ветка `feat/poker-engine-core`, все 12 задач плана закрыты, 80 тестов зелёные. Ветка не влита.

**Перед работой прочитать `docs/superpowers/state/HANDOFF.md`** — там сетап машины, что появилось
в Tasks 7–12, восемь решений, принятых против текста плана (план требовал недоказуемых инвариантов),
один пункт, ждущий решения пользователя, и список сознательно отложенных мелочей.

| Документ | Что |
|---|---|
| `docs/superpowers/plans/2026-09-09-poker-engine-core.md` | план, 12 задач |
| `docs/superpowers/specs/2026-09-09-poker-skillpack-design.md` | спека |
| `docs/superpowers/state/HANDOFF.md` | точка входа для новой сессии |
| `docs/superpowers/state/2026-09-09-poker-engine-execution-notes.md` | полный журнал ревью Tasks 1–6 |

Плагины перечислены в `.claude/settings.json`.

## Команды

```bash
# ядро
cd packages/poker-engine
.venv/Scripts/python -m pytest              # 80 passed, ~1 мин

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
- Общие гарды — только в `_checks.py`, не копировать в новые модули.
- Тесты — аналитические инварианты, проверяемые на бумаге, а не числа из памяти модели.
