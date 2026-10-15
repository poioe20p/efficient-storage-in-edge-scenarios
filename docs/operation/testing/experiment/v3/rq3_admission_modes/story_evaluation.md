# RQ3 — Concentrated evaluation of the core story

Scope: does the completed campaign tell this story, and where it does not,
what exactly explains the divergence. Numbers are from `results.md`
(verified against the screen JSONs; reconciliation 264 checks, 0 mismatches).

## 1. The story to be told

Three admission modes:

- **E — event only**: admit on the backend's readiness event.
- **P — periodic polling**: admit when the controller's periodic check finds
  the backend ready.
- **C — event + confirmation**: admit only when a confirmation check, woken
  by the event, passes.

Three conditions, with the expected orderings:

| Condition | Expected |
|---|---|
| intact | E (fastest, no cost) > P ~ C |
| lost (event dropped) | P ~ C (both recover) > E (fails) |
| premature (event 10 s early) | P ~ C (both safe) > E (fails); in admission speed C >= P (C admits at true servability, P at its next poll) |

## 2. What was actually measured

The campaign's matrix rules are **A = event only** (= E), **B = event with a
bounded re-check** (the recorded `hybrid`: admit on the event; a 20 s
timer re-checks only when *nothing* arrives), and **C = periodic**
(= P, the recorded `reconcile`, 10 s poll). The implemented
**event + confirmation** rule is **wake-and-verify** (event wakes a check;
admission requires the check to pass; the same 20 s fallback when no event
arrives). It was parked after a three-seed premature pilot and is **not
evaluated at the seven-block standard**.

## 3. Verdict per condition

| Condition | Expected | Observed (7 blocks) | Verdict |
|---|---|---|---|
| intact | E > P ~ C | E (A 4.08 s fast / 13.69 s slow) and B (3.09 / 13.67) versus P (9.98 / 19.78): P pays one check period (+5.9 s fast, +6.1 s slow to first success); no user harm in any rule; C's intact price unmeasured | **Holds for E > P**; C's own price unmeasured |
| lost | P ~ C > E | E: 0 admitted, 34 candidates abandoned, user cost +7.64 pp median plateau / +28 pp onset. P recovers within one poll (spawn→admit ~17 s); B recovers at ~21 s (its fallback path); no harm for either | **Holds in kind** (both recover, E fails); in speed P beats the fallback path that C would use |
| premature | P ~ C > E | E: +14.38 pp damage. **B: +11.66 pp damage** (it admits the false claim). P: -0.05 pp, immune. C: three-seed pilot flat/immune at a small no-fault cost (up to +3.1 pp on two seeds) | **Holds for P > E**; C unmeasured at standard; **B fails where the story's C would not** |

Mechanism readings behind the verdicts: under loss, A's log shows zero
admissions and the abandon/teardown path, B recovers 100 % via its
`probe_fallback`, C 100 % via its `probe`. Under the premature fault the
claim is the *event* (10 s early) while the controller's own check stays
truthful (it passes only once the backend can serve); so every mode that
admits on the event alone is exposed, and every mode that checks before
admitting is safe by construction.

## 4. The divergences, explained

1. **"The third mode isn't the one that ran."** B looks like event +
   confirmation but is only event + absence recovery: its timer fires when
   *nothing* arrives, never to verify a claim that arrived. The observed
   premature ordering is therefore P > B ~ E, not P ~ C > E. This is not a
   failure of the design: it is the campaign's sharpest result, *recovery is
   not verification*. A mode that repairs absence is not a mode that checks
   claims.
2. **P and C differ by clock, not by protection.** Both are safe in every
   condition. They differ in when they admit: under premature, C (wake-and-
   verify) would admit at the first passing check, i.e. at true servability,
   up to one check period before P; under loss, C would recover after its
   ~20 s fallback wait, one period after P. So the story's "~" reads:
   *same protection, different clock* — C is the earliest safe admission,
   P the steadier one.
3. **The intact ordering holds as expected** (trust is fastest; checking
   pays its wait), and the measured price of checking was never
   user-visible, which is what lets "P ~ C" cost nothing against users in
   healthy operation.

## 5. Completing the exact story

To evaluate the story's third mode at the standard rather than by pilot:

- run **wake-and-verify (C)** at 7 blocks x {intact, lost, premature-10 s}:
  none at seeds 5201-5207 (7 runs; the intact evidence and the lost
  partners), loss at seeds 5201-5207 (7), premature-10 s at seeds
  6304-6307 (+4; the three pilot seeds are reused), and their matched
  no-fault partners at seeds 6304-6307 (+4) --- **22 new runs, ~15-17 h**;
- pre-registered expectations: premature immune (pilot-supported); lost
  recovers ~21 s through the fallback path (as B); intact at event speed
  plus one check, with no expected user harm;
- then all three story modes have seven-block evidence in all three
  conditions and both orderings can be stated with numbers.

Alternative without runs: tell the story with the evaluated rules — event
only / event with absence recovery / periodic — with *recovery is not
verification* as the pivot, and B as the instructive near-miss. The story
then reads P > B ~ E for the false claim, with the mechanism explanation
above.

## 6. Bottom line

The campaign tells the core of the story already: trusting the event fails
under both faults; periodic checking survives both; checking costs one
period and that cost was never user-visible. The only untested element is
the third mode as specified (event + confirmation): its one job — being
faster than polling while still safe — is architecturally supported and
pilot-consistent, but not yet evidenced at the seven-block standard.

## 7. Plain-language summary (4 modes x 3 scenarios)

The four modes, one line each:

- **event only** -- believe the message; admit instantly; nothing else.
- **event + re-check** -- believe the message; but if it never arrives, check
  after 20 s.
- **periodic** -- never believe the message; check every 10 s; admit when the
  check passes.
- **event + confirmation** -- the message wakes a check; admit only when the
  check passes; if the message never arrives, the same 20 s fallback.

The three scenarios, expected and (where measured) observed:

| Scenario | event only | event + re-check | periodic | event + confirmation |
|---|---|---|---|---|
| Everything works | fastest (0 s) | fastest (0 s) | waits up to one round (~7 s median) | one quick check (to be measured) |
| Message lost | fails silently (0 admitted, capacity dark) | recovers (~21 s) | recovers (<=10 s) | recovers (~21 s, expected) |
| Message lies (10 s early) | fooled (+14.4 pp) | fooled (+11.7 pp) | safe (-0.05 pp) | safe, earliest safe admission (expected) |

The story in one sentence: believing the message is fastest but blind to both
faults; re-checking only silence fixes the lost message but not the lie;
checking on a timer is safe but pays a round; confirming the message gives
safety at event speed.
