# Poker-engine plan 1 — execution notes

Branch: `feat/poker-engine-core`, base `e112e24`.
**User asked to stop after Task 6.** Tasks 7-12 not started.

## Task status

| # | Task | Commits | Spec | Quality |
|---|---|---|---|---|
| 1 | scaffold | 5c6a404 | ✅ | ✅ |
| 2 | vendor-ref script | 39fa526, f9b2b83 | ✅ | ✅ |
| 3 | types.py | 255994b, ccd2fba | ✅ | ✅ (after aliasing fix) |
| 4 | potodds.py | 1744218, 9725e38 | ✅ | ✅ (after validation fix) |
| 5 | icm.py | 33780b2, 0666849 | ✅ | ✅ (after index/div-zero/docstring fixes) |
| 6 | bounty.py | a74b813, 6d44805, 331e3d1 | ✅ | ✅ (approved on second review) |
| 7–12 | — | not started | — | — |

Suite at stop: **48 passed**. Working tree clean.

## OPEN — decided by user, not yet fixed

**`risk_premium`'s `win == lose` guard is an exact float comparison.** It closes the exact-zero case
but not the near-degenerate one. Flat payout ladders — i.e. satellites — make `win` and `lose`
mathematically equal but differ by ~1e-15 through different recursion paths, so the guard misses and
a silently wrong number comes out:

```
stacks=[50,30,20]  payouts=[50,50,50]   hero=1 villain=2  -> risk_premium = 0.5
stacks=[100,90,80,70] payouts=[25]*4    hero=0 villain=3  -> risk_premium = -0.5
stacks=[13,17,19,23,29,31] payouts=[10]*6 hero=0 villain=5 -> risk_premium = -2.5
```

Same failure class as the Critical already fixed (silently wrong, no exception). Pre-existing, not a
regression from 0666849. Fix is one line: `math.isclose(win, lose, abs_tol=1e-9)` instead of `==`.
`bubble_factor`'s `money_up <= 0` guard has the same weakness.

## Plan defects found

1. **Task 3 — `positions_for(6)`.** Plan's tail-slice gives `[LJ,HJ,CO,BTN,SB,BB]`; plan's own test demands
   `[UTG,HJ,CO,BTN,SB,BB]`. Plan's "7 passed" was unachievable. Fixed with `_POSITION_OVERRIDES`
   (tuples for 2 and 6) + `list(...)` on return. Test unchanged.
2. **Task 3 — aliasing.** First fix returned the shared module-level list. Corrected in ccd2fba.
3. **Task 4 — validation asymmetry.** `required_equity` rejected bad amounts, `ev_call`/`ev_shove` didn't.
   Added `_check_amount`/`_check_pot` helpers + docstring note on the float-noise trap at break-even.
4. **Task 5 — `_equity_with_busts` returned a list from a `-> float` function** in the `busted == 0`
   branch. Reachable from the shipped tests; would `TypeError` in `_icm_branches`. Fixed to `[hero]`.
   Found by the implementer, independently confirmed by the spec reviewer.
5. **Task 5 — negative `hero`/`villain` silently wrap.** `bubble_factor([50,30,20],[50,30,20],-1,1)`
   returned `1.167` instead of raising. Silent wrong answer, worst failure mode so far. Bounds guard added.
6. **Task 5 — `risk_premium` divides by zero.** `risk_premium([10,10],[0,0],0,1)` → `ZeroDivisionError`,
   which Task 9's CLI does not catch. Guard added.
7. **Task 5 — complexity docstring is false.** Claims `O(n·2^n)`; measured growth is factorial,
   `n!/(n-depth)!`. n=9 → 0.47 s, n=10 → 4.97 s, n=11 → 56 s. Docstring rewritten. Matters because
   Task 10 republishes it to users.
8. **Task 7/8 — exhaustive-enumeration branch. NOT YET FIXED (task not started).**
   `hand_equity` has `elif len(deck) <= 20 and need <= 1:`. On the turn (4-card board) the deck is 44,
   so it falls through to Monte-Carlo. Task 8's `_exhaustive_turn_equity` calls it with `trials=1` and
   treats the result as exact — one random river. `test_monte_carlo_converges_to_exhaustive_on_turn`
   (abs=0.01) would fail. **Fix: condition must be `need <= 1` alone.**
9. **Task 6 — `covers_villain` credited a full head on a 1-chip call.** `villain_stack=-5` with
   `call_amount=1` gave `covers_villain=True`; threshold dropped to ~0.00095 instead of ~0.001.
   Silently wrong number. Guard added.
10. **Task 6 — negative `pot_before_call` bypassed `required_equity` on the bounty branch** and
    returned `0.556` instead of raising. Fixed by eager validation before branching.
11. **Task 6 — validation depended on a neighbouring argument's value.** `--chip-value -5` raised or
    passed silently depending on `--bounty`. Task 9 makes `cli.py` a pure parser, so this module *is*
    the CLI validation layer. Fixed.
12. **Task 6 — `split` was not covered at the top level.** Dropping the argument from
    `bounty_in_chips` survived all 12 tests; the reviewer re-ran the mutation after the fix and it
    now fails.

## Authorized deviation from the plan (Task 6)

New `src/poker_engine/_checks.py` (`check_amount`, `check_pot`, `check_probability`); `potodds.py`
and `bounty.py` import from it. Not in the plan's file table. Reason: two copies of identical guards,
and their `ValueError` strings are the CLI's user-facing error text — divergence would break the
contract. Tasks 7 and 9 would have made four copies. Boundaries (`<` / `<=`) and messages are
byte-for-byte unchanged; `test_potodds.py` untouched.

Three open Minors from that review, non-blocking:

1. `test_bounty.py:109-113` — comment over-generalizes ("pot + extra is non-negative since extra >= 0").
   False; the masking window is `[-extra, 0)`. The test itself is valid.
2. `_check_bounty` / `_check_chip_value` / `_check_villain_stack` in `bounty.py` are exact instances
   of the shared guards. Only the naming is off: want `check_positive` / `check_non_negative` rather
   than the domain-flavoured `check_pot` / `check_amount`.
3. The contract "same violation → same message" is not pinned by any test. A mutant that rewrites the
   f-string passes all 48.

## Watch-list for remaining tasks

- **Task 7** (`equity.py`): perf. `_best_hand` builds `StandardHighHand(Card.parse(...))` for all 21
  five-card combos per hand per runout — 20 000 trials x 2 hands x 21 = 840k evaluations. If the suite
  crawls, parse once and/or use `StandardHighHand.from_game(hole, board)`. Both APIs confirmed working
  on pokerkit 0.7.5 / py3.14.
- **Task 9** (`cli.py`): `--pot`/`--call` are bare `type=float`; engine guards are the only protection.
  Also: the `risk-premium` subcommand calls both `risk_premium` and `bubble_factor`, each of which runs
  `_icm_branches` → up to 6 full ICM passes per invocation. Fine at typical ladder depth, slow for a
  fully-paid field of 10+.
- **Task 11**: skill's position table must match `positions_for` for n = 2, 6, 8, 9. Verified it does.

## Test-count drift vs plan

Plan Task 9 Step 6 asserts a final total of **53**
(1 smoke + 7 types + 8 potodds + 13 icm + 8 bounty + 8 equity + 2 crosscheck + 6 cli).

Adjustments so far:
- Task 4: +3 (negative-pot guard, probability-range guard, amount guard). potodds 8 → 11.
- Task 5: +3 (negative index, undefined risk premium, 6-9 player bubble/risk). icm 13 → 16.
- Task 6: +5 (negative bounty, nonpositive villain_stack, negative pot on the credit branch,
  nonpositive call_amount, `split=1.0` reaching the threshold). bounty 8 → 13.

**Corrected expected total: 64** (1 smoke + 7 types + 11 potodds + 16 icm + 13 bounty + 8 equity
+ 2 crosscheck + 6 cli). Measured: **35** after Task 5, **48** after Task 6. The plan's "53" line is
stale — Task 9 / Task 12 dispatches must use 64, and recompute from per-module counts if Tasks 7–8
add more review-driven tests.

## Deliberately not fixed (plan cosmetics, surfaced to user)

- `ev_shove` reimplements the EV formula instead of delegating to `ev_call`.
- `pot_before_call` vs `pot_before_shove` — same concept, two names.
- `_check_probability` takes a hand-typed parameter-name string.
- `test_ev_shove_without_fold_equity_reduces_to_ev_call` never calls `ev_call`.
- `TableSnapshot.stacks` is a mutable `list[int]` inside a frozen dataclass; `tolerance` is absolute,
  not relative.
- `bubble_factor` / `risk_premium` duplicate the `chips_win`/`chips_lose` formulas.
- ~~Task 2's script prints reference-repo SHAs but persists them nowhere.~~ Closed: `vendor-ref.lock`
  now pins all five repos and `scripts/fetch-vendor-ref.sh` checks them out.
