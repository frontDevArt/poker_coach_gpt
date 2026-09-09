# Handoff — resume poker-engine core at Task 7

Last updated: 2026-09-09. Branch `feat/poker-engine-core`, base `main` @ `e112e24`.

**Tasks 1–6 done. Start at Task 7.**
Plan: `docs/superpowers/plans/2026-09-09-poker-engine-core.md`
Spec: `docs/superpowers/specs/2026-09-09-poker-skillpack-design.md`
Full review log: `docs/superpowers/state/2026-09-09-poker-engine-execution-notes.md`

## 1. Machine setup on a fresh clone

```bash
git clone https://github.com/frontDevArt/poker_coach_gpt.git
cd poker_coach_gpt
git checkout feat/poker-engine-core

# Python core (this is where all remaining work happens)
cd packages/poker-engine
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.lock   # exact versions used so far
.venv/Scripts/python -m pip install -e ".[dev]" --no-deps
.venv/Scripts/python -m pytest                                  # expect: 48 passed

# Reference repos (322 MB, deliberately not in git — pinned by vendor-ref.lock)
cd ../..
bash scripts/fetch-vendor-ref.sh

# Nuxt shell (not touched by this plan)
npm install
```

Verified toolchain: Python 3.14.4, pokerkit 0.7.5, pytest 9.1.1 on Windows.
`pyproject.toml` says `requires-python = ">=3.11"` and `pokerkit>=0.5`; the lock file is what was
actually exercised. If the home machine resolves a different pokerkit, re-verify Task 7 —
`StandardHighHand.from_game(hole, board)` and `StandardHighHand(Card.parse(...))` were confirmed on
0.7.5 only.

## 2. Claude Code setup

`.claude/settings.json` is committed and enables the plugins this plan depends on. On first session
the home machine will prompt to trust the marketplaces; accept, then confirm with `/plugin`:

- `superpowers@claude-plugins-official` — **required.** The plan's header mandates
  `superpowers:subagent-driven-development` or `superpowers:executing-plans`, and each task uses
  `test-driven-development`, `verification-before-completion`, `requesting-code-review`.
- `context7@claude-plugins-official` — pokerkit API lookups.
- `caveman@caveman` — response-style only, optional.

Version used so far: superpowers 5.1.0.

Project skills `.claude/skills/poker-ontology/` and `.claude/skills/poker-math/` do not exist yet —
Tasks 10 and 11 create them, and they land in git like any other source file.

Nothing else lives outside the repo. There are no secrets, no `.env`, no API keys — the engine is
pure local computation.

## 3. Before writing Task 7 code — read these

Three items carried over. The first two are decisions already made and not yet applied.

### 3.1 Pre-existing bug that Task 7/8 will trip over

`hand_equity` (Task 7) has:

```python
elif len(deck) <= 20 and need <= 1:
```

On the turn the deck holds 44 cards, so this never fires and control falls into Monte-Carlo. Task 8's
`_exhaustive_turn_equity` calls the same path with `trials=1` and treats the answer as exact — it gets
one random river. `test_monte_carlo_converges_to_exhaustive_on_turn` (abs=0.01) will fail.

**Fix: the condition must be `need <= 1` alone.**

### 3.2 Waiting on a decision — exact float comparison in ICM

`risk_premium` and `bubble_factor` compare `win == lose` exactly. Flat payout ladders (satellites)
make the two mathematically equal but ~1e-15 apart through different recursion paths, so the guard
misses and a silently wrong number is returned:

| stacks | payouts | hero | villain | returned |
|---|---|---|---|---|
| `[50,30,20]` | `[50,50,50]` | 1 | 2 | `0.5` |
| `[100,90,80,70]` | `[25]*4` | 0 | 3 | `-0.5` |
| `[13,17,19,23,29,31]` | `[10]*6` | 0 | 5 | `-2.5` |

Same failure class as the Critical already fixed in `0666849`: wrong number, no exception.
Pre-existing, not a regression. One line: `math.isclose(win, lose, abs_tol=1e-9)` instead of `==`.
`bubble_factor`'s `money_up <= 0` guard has the same weakness.

### 3.3 The plan's test-count gate is stale

Plan Task 9 Step 6 asserts the suite must end at **53 passed** and says a mismatch means a test was
lost. That number predates the guard-coverage tests added during review.

**Expected total is 64**: 1 smoke + 7 types + 11 potodds + 16 icm + 13 bounty + 8 equity
+ 2 crosscheck + 6 cli. Measured so far: 35 after Task 5, 48 after Task 6. Do not go hunting for a
phantom missing test; recompute per module if Tasks 7–8 add more.

## 4. Convention established during Tasks 1–6

- One commit per task, plus follow-up `fix(engine): …` commits for review findings. Conventional
  Commits.
- Every task runs two reviews: spec compliance first, then code quality. Both must approve.
- Argument validation lives in the engine, not the CLI — Task 9 makes `cli.py` a pure parser, so
  `ValueError` strings from `_checks.py` are user-facing error text. Keep them stable.
- Shared guards go in `src/poker_engine/_checks.py` (an authorized addition not in the plan's file
  table). Do not re-duplicate them in `equity.py`.
