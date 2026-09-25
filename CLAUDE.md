# poker_coach_gpt

Nuxt-оболочка плюс Python-ядро `packages/poker-engine` (ICM, пот-оддсы, PKO bounty EV, эквити).
Вся текущая работа идёт в ядре; Nuxt-часть план не трогает.

## Текущее состояние

**План 3 закрыт** (2026-09-25) — модель поля, настоящая лесенка, PKO и бюджет 2 секунды
(`docs/superpowers/plans/2026-09-12-icm-field-model.md`, спека
`docs/superpowers/specs/2026-09-12-icm-field-model-design.md`). Восемь задач, десять фаз,
каждая задача прошла ревью до `НАХОДОК НЕТ`; ветка `claude/serene-bell-yni6li` влита в `main`
fast-forward. 477 passed за ~8 с. Разбор `analyze` — 0.16 с при бюджете 2 с; оценщик
руки — `phevaluator` (не `eval7`, D21).

**Точка входа — раздел «Итог плана 3» журнала
`docs/superpowers/state/2026-09-12-icm-field-execution-notes.md`**: решения против текста плана
по всем задачам, удалённые тесты, замеры, ledger отложенного (D3, D11, D12, D13, D15, D19,
D21) и открытые вопросы спеки §11 (олл-ин на 0 BB, разброс стеков поля).

**Следующий — план 4:** push/fold советы (Nash + ICM-поправка). Промпт —
`docs/superpowers/state/plan3-next-prompt.md`. Правила нарезки на фазы брать из
`docs/superpowers/state/2026-09-24-plan3-phases.md` (§1, шаблоны §6–§7).

Планы 1 (`feat/poker-engine-core`) и 2 (`feat/screenshot-coach-engine`) закрыты и влиты
в `main`: оба ревью на задачу, мутационная приёмка, финальное ревью ветки. Удалить обе ветки
на GitHub — за пользователем (D15: из облачной сессии удаление обрывается).
Контекст планов 1–2 — `docs/superpowers/state/2026-09-10-screenshot-coach-execution-notes.md`,
разделы «Task 7» и «Дальше».

| Документ | Что |
|---|---|
| `docs/superpowers/plans/2026-09-09-poker-engine-core.md` | план 1, 12 задач |
| `docs/superpowers/specs/2026-09-09-poker-skillpack-design.md` | спека скиллпака (слои, `pushfold.py`, фазы) — вход плана 4 |
| `docs/superpowers/state/HANDOFF.md` | handoff плана 1 (историческое) |
| `docs/superpowers/state/2026-09-09-poker-engine-execution-notes.md` | журнал ревью Tasks 1–6 плана 1 (историческое) |
| `docs/superpowers/plans/2026-09-10-screenshot-coach-engine.md` | план 2, 7 задач |
| `docs/superpowers/specs/2026-09-10-screenshot-coach-design.md` | спека плана 2 |
| `docs/superpowers/state/2026-09-10-screenshot-coach-execution-notes.md` | журнал плана 2, Tasks 1–7 |
| `docs/superpowers/state/2026-09-11-task7-handoff-2.md` | handoff второй сессии Task 7 (историческое) |
| `docs/superpowers/state/2026-09-11-task7-handoff.md` | handoff первой сессии Task 7 (историческое) |
| `docs/superpowers/state/2026-09-11-next-session-prompt.md` | промпт третьей сессии (историческое) |
| `docs/superpowers/plans/2026-09-12-icm-field-model.md` | план 3, 8 задач (закрыт); решения каждой задачи внутри |
| `docs/superpowers/specs/2026-09-12-icm-field-model-design.md` | спека плана 3; §10 — границы, §11 — открытые вопросы |
| `docs/superpowers/state/2026-09-24-plan3-phases.md` | фазы плана 3: правила сессий, бюджет, реестр долгов, шаблоны промптов |
| `docs/superpowers/state/2026-09-12-icm-field-execution-notes.md` | **точка входа**: журнал плана 3, раздел на фазу, итоговый раздел |
| `docs/superpowers/state/plan3-next-prompt.md` | промпт плана 4 |

Плагины перечислены в `.claude/settings.json`.

## Команды

```bash
# ядро
cd packages/poker-engine
.venv/Scripts/python -m pytest              # 477 passed, ~8 с (Linux: .venv/bin/python)

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
