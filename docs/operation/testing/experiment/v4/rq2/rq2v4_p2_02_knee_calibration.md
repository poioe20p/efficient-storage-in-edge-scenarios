# RQ2 v4 — P2.3: Knee calibration and seat runs (results)

> **Status:** 2026-10-11 · ladder + seat runs complete. **Press gate PASSED**
> (R_s = 0.20, both lanes); **relief gate FAILED** (comp engaged fully, lock
> persisted); margin + specificity PASSED. The compute side of RQ2 is **not
> yet demonstrable** — relief diagnosis opened (P2.5, read-only autopsy #3).
> **Runs (full retention):** `20261011_203530_rq2v4_p2_none_h020`,
> `20261011_211706_rq2v4_p2_comp_h023`, `20261011_214634_rq2v4_p2_stor_h023`
> (+ smoke `20261011_201900_rq2v4_p2_smoke`); VM HEAD `8eb6875`; edge image
> `12c9ef0dc4b7`.

## 1. Ladder (hash-only, quota 0.15, seed 42)

| Rung | Rate (rps/lane) | Lock % windows L1/L2 | Ep p50 L1/L2 | Ep p95 L1/L2 | Completion |
| --- | --- | --- | --- | --- | --- |
| `none_h020` | 0.20 (4.8) | **95.3 / 100** | 1.9 / 2.0 s | 3.4 / 3.5 s | 94.9 / 95.4 % |

0.25–0.35 skipped by the decision logic (first rung locked). **R_s = 0.20.**
Nuance recorded: completion 94.9/95.4 % sits a hair above the "< ~95 %" clause
of the pinned lock definition; the primary signal (p95 ≥ 1 s in 95–100 % of
windows, p50 ≈ 1.9 s ≈ 30× nominal) is unambiguous.

Capacity record: onset ≤ 4.8 rps/lane; per-window serving throughput 5–8 rps
at 50–58 % median serving CPU; **effective ceiling ≈ 5–8 rps/lane**.

## 2. Seat runs (rate 0.23 = R_s × 1.15)

| Run | Mode | Global effect | Gate outcome |
| --- | --- | --- | --- |
| `comp_h023` | compute-only (caps 6/6) | **6+6 scale_ups — 12 added units, all online ≤ 1.2 s, all engaged** (rotation across 7 units/lane; per-unit bursts ≈ full lane load) | **Relief FAILED** — lock persisted: 98.4/98.4 % windows ≥ 1 s; post-add p50 ≈ 1.7–2.3 s sustained to episode end (independent recomputation); min 00–01 = drain of the pre-add backlog (300 s-cap timeouts), min 02+ ≈ 100 % completion but still ≈ 1.8 s p50 |
| `stor_h023` | storage-only | none (no storage signal — mode-appropriate no-op) | **Specificity PASSED** — lock persists 100 % windows |

Margin: `none` stayed locked for the whole episode (no drift). Culls 0/0 in
all runs. F2 quiescence held in all episodes.

## 3. Mechanism (from the seat-run evidence)

- Serving units ran at **≤ 82 % CPU (median 50–58 %)** while client latency
  was 1.7–3.4 s — **the queue is not in serving-unit CPU**.
- Added units **engaged but did not add concurrent capacity**: traffic
  concentrates on one unit at a time for multi-window stretches, rotating
  every ~1–2 min — the same behaviour noted in the P1.4 battery ("assignments
  rotate per window; relief metrics must be serving-unit-scoped"), now shown
  to be **capacity-relevant**: N units time-share one hot seat instead of
  adding N seats.
- Confirmed independently from `client_requests.csv`: steady-state
  throughput = offered rate exactly (≈ 5.5 rps/lane, 100 % served) with
  ≈ 1.8 s p50 — a stable congested equilibrium at ~one-unit capacity.

**Consequence if unresolved:** the campaign's compute cells would show
engagement-without-relief; the RQ2 premise ("the controller presses where the
load presses") would be false for the compute tier. Note also (provenance):
v3-era compute "relief" claims were measured at loads **below one-unit
capacity** — relief through added concurrency has never been demonstrated on
this platform under any press. P1's repair plus the hash press made this
visible; it must now be resolved (or the RQ2 claim re-scoped, author's call).

## 4. Open items

1. **P2.5 (opened): read-only diagnosis** — why does traffic concentrate on
   one backend at a time despite N eligible units? Candidate classes:
   (a) client-binding lifecycle (per-request flow deletion not effective →
   sticky per-client assignments); (b) selection determinism with stale
   near-equal costs (argmin funnel + slow rotation); (c) warm-lease/cost
   interactions. Fix options depend on the class; a minimal selection-spread
   repair would restore concurrent serving and relief.
2. **Seat frozen 2026-10-12** (after the P2.8 verdict — see
   [`rq2v4_p2_08_band_floor.md`](rq2v4_p2_08_band_floor.md) §6): press seat
   R_s = 0.20 (rate 0.23), work factor 25000, quota 0.15, caps 6/6; relief
   definition per D12 (post-engagement steady state + time-to-relief).
3. **Cost split (recorded):** light-load hash p50 ≈ 55–58 ms vs raw 8.7–11 ms
   — CFS quota quantization (throttled 54.6/69.6 % of periods in the ladder
   runs) is the per-request wall floor below saturation; under press the
   dominant queue sits ahead of the serving handler.

## 5. Provenance

- Executor: VM session 2026-10-11 20:19–22:15 Z (smoke + 3 runs + evidence);
  `phases.json` restored; no commits; disk 72 G free; full retention.
- Independent verification (main session): h020 lock metrics, comp timeline
  per-minute recomputation, cull/removal counts re-checked with correct
  quoting (0/0).

## 6. P2.7 re-seat verdict — spread v2 (2026-10-11/12)

Runs (post-P2.6 `57f58c3`, hash-only shape, rate 0.23, seed 42, full
retention):

- `20261011_225528_rq2v4_p2_comp_h023_v2` (22:55:28–23:17:15 Z)
- `20261011_232451_rq2v4_p2_stor_h023_v2` (23:24:51–23:46:23 Z)

| Run | p50 L1/L2 | p95 L1/L2 (max) | Lock % windows | Completion | Timeouts |
| --- | --- | --- | --- | --- | --- |
| comp v2 | 0.8 / 2.0 s | 2.9 / 7.8 s (16.4) | 75.4 / 98.4 | 99.1 / 97.7 % | **0** (v1: 229) |
| stor v2 | 2.4 / 2.6 s | 30.0 / 28.1 s (300) | 100 / 100 | 96.3 / 95.3 % | 208 |

Burst fan-out (distinct MACs per 60 s epoch): lan1 `{1:5, 2:2, 3:1, 5:1}`,
lan2 `{1:8, 2:1}` (v1: one-hot everywhere). Concurrency census (units
> 30 % CPU per 30 s): lan1 max 4 (≥ 3 units in 3 buckets), lan2 max 2.

Verdicts: comp relief **FAILED** as pre-registered (0/15 post-add windows,
p95 < 1 s both lanes); stor specificity **PASSED**; timeouts 229 → 0 and
completion up in comp.

Diagnosis (burst logs + independent timeline recomputation):

1. **Band collapse** — the ε-band alone is size 1 in most bursts whenever a
   unit is the strict argmin by more than ε (or the warm claim is the strict
   minimum): lan1 5/9, lan2 8/9 epochs stayed one-hot, so the one-unit
   rotation persisted at epoch granularity.
2. **Mechanism validated where the band was wide** — the single band=5
   epoch (23:02:05 Z) maps exactly onto the only full-relief interval
   (23:02:01–23:03:11, lan1 p50 0.05–0.12 s): wide band ⇒ concurrent
   serving ⇒ relief, immediately. The fix works; the dose was too small.
3. Anomaly (recorded, no action) — simultaneous both-lane latency storm
   23:04:11–23:05:11 Z (p95 up to 16 s) with no controller error; host
   transient, F2 discipline upheld.

Consequence: P2.8 band floor (minimum k = 4 eligible local units in the
band) — see plan item 7 and
[`rq2v4_p2_08_band_floor.md`](rq2v4_p2_08_band_floor.md); the verification
re-seat re-runs this pair (labels `_v3`).

**Follow-up (2026-10-12):** the P2.8 verification resolved the funnel —
band = 4 in every steady-state epoch, 3–4 concurrent servers sustained,
steady-state relief on both lanes (83.3/82.1 % of windows), stor
specificity held; relief onset is one re-selection cadence after capacity
(≈ add+177 s), recorded as decision D12. Verdict:
[`rq2v4_p2_08_band_floor.md`](rq2v4_p2_08_band_floor.md) §6.
