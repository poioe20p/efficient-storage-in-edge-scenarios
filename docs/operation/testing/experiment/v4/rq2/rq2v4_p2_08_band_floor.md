# RQ2 v4 — P2.8: Spread band floor (minimum fan-out per selection burst)

**Status:** implemented + verified 2026-10-12 (auto-review converged;
verification re-seat `_v3`: mechanism gates PASS, relief achieved in the
post-engagement steady state; decision D12, seat frozen — see §6). Parent: [`rq2v4_p2_03_relief_diagnosis.md`](rq2v4_p2_03_relief_diagnosis.md)
(funnel diagnosis) and
[`rq2v4_p2_02_knee_calibration.md`](rq2v4_p2_02_knee_calibration.md) §6 (P2.7
verdict).

## 1. Why — the P2.7 residual

The P2.6 ε-band broke the timeout regime (comp timeouts 229 → 0) but relief
still failed: the band collapses to **one member** in most selection bursts
whenever a unit is the strict argmin by more than ε — the common case under
load — or when the warm claim is the strict minimum (the append branch
cannot widen a band whose minimum *is* the warm unit). Burst histograms:
lan1 `{1:5, 2:2, 3:1, 5:1}`, lan2 `{1:8, 2:1}`. The single wide burst
(band = 5) coincided exactly with the only full-relief interval (lan1 p50
0.05–0.12 s): the mechanism is right, the dose was too small. Raising ε is
fragile (cost gaps under load exceed any fixed ε); the robust repair is a
**floor on the band size**.

## 2. Change

- **New knob** `_BACKEND_SELECTION_SPREAD_MIN_BAND` (`scaling_config.py`;
  env `BACKEND_SELECTION_SPREAD_MIN_BAND`, default **4**, `k ≤ 1` disables).
  Active only when the spread is active (`eps > 0`); with `eps = 0` the
  legacy path is untouched.
- **Selection** (`_vip_routing/selection.py`, `select_server`): after the
  ε-band is formed and a live warm claim is appended, if the band is smaller
  than k it is topped up to k members with the cheapest **eligible local**
  units not already in the band — eligible = finite cost, known backend IP,
  not peer, slow-start penalty fully decayed; cost ties break on MAC so the
  cut is deterministic across pool rebuilds. The floor never adds peers
  (even when a peer is cheaper than the next local — locality stays
  ε-gated) and clamps to the number of eligible locals. The log line gains
  `floor=%d`.
- **Selftest** (`source/scripts/testing/rq2v4_p2_06_selection_spread_selftest.py`,
  renamed in scope, not in path): 32 assertions green — the original ε-semantics
  assertions (floor pinned to 1 where they isolate ε), plus: floor widens a
  single-winner band to the 4 cheapest locals; units beyond the floor never
  receive clients; floor clamps to eligible locals; the floor never adds
  peers even when a peer is cheaper than the next local; `k ≤ 1` (and 0)
  restores the ε-only band; a warm claim counts toward the floor and
  receives a share, not a monopoly; the guard cases: the floor is a
  minimum, not a cap (wide ε-band untouched); NaN-cost locals are skipped;
  unknown-IP locals are never seated (ingress would drop them); units whose
  slow-start penalty has not fully decayed are never seated; a peer inside
  the ε-band stays and the floor tops the band up with locals; and the
  selection log format (`spread band=` / `floor=` / `warm=`) is pinned —
  it is the evidence instrument for the verification gate.
- **Provenance pins**: `BACKEND_SELECTION_SPREAD_EPS` and
  `BACKEND_SELECTION_SPREAD_MIN_BAND` added to
  `controller_env_overrides/current_state_integrated.env`, so the merged run
  env (and its captured snapshot) always carries the effective values.

## 3. Semantics

`band = {cost ≤ min + ε} ∪ {warm}`; if `|band| < k`, top the band up to k
members with the cheapest eligible locals not already in the band, where
eligible = finite cost, known backend IP, not peer, slow-start penalty
fully decayed; cost ties break on MAC (the scored order follows set
iteration, so
without the tie-break the cut could flip across pool rebuilds). Not a cap:
an ε-band wider than k stays as-is. The chooser is unchanged (md5(client
MAC) mod |band| over the band sorted by MAC), so per-client determinism
holds for a stable band; cost-rank churn can change band membership across
epochs (same accepted behaviour as P2.6). The band holds at least
min(k, eligible locals) members — the per-burst fan-out is hash-determined
(expected = band size), not a hard per-burst floor.

P2.6 supersessions: the "mean-cost rise bounded by ε" bound no longer holds
(the floor admits the k-th cheapest local regardless of its distance from
the minimum); the pre-P2.8 reproducibility baseline is the P2.6 commit
`57f58c3`.

Expected effect at the seat: the band holds ≥ 4 members per lane once four
locals are eligible (clamped to the two statics early in the episode), so
the expected fan-out is the band size: ≈ 24 clients × 0.23 rps ÷ 4 ≈
**1.4 rps/unit**, about 3.4× inside the measured single-unit knee
(~4.8 rps/lane); with only two eligible statics ≈ 2.8 rps/unit — still
inside the knee.

Repair discipline: default-active, like P2.6 and P1 — reproductions of
pre-P2.6 campaigns select differently on this commit; RQ1/RQ3 re-runs on
this commit are the repaired behaviour.

## 4. Verification plan (re-seat, `_v3` labels)

This pair is a **mechanism verification** (engineering gate: does the
repair produce concurrent serving and relief), not campaign evidence — per
`testing_requirements.md` no single run is evidence; the relief *claim*
will rest on the 7-replicate campaign cells (Phase 5).

Re-run the seat pair on the VM (hash-only shape, rate 0.23, seed 42,
full retention):

- `rq2v4_p2_comp_h023_v3` — relief gate as pre-registered (post-add
  [+30 s, +180 s] p95 < 1 s in ≥ 80 % of windows both lanes, completion
  ≥ 95 %) + last-180 s persistence + band/fan-out check: in the post-add
  steady state every logged burst must draw from a band of ≥ 4 members
  (`band=`/`floor=` in the log) and, with 24 clients, reach all band members
  (per-member seat probability ≈ 1 − (1−1/4)^24 ≈ 99.9 %). A `band < k`
  log line fails the check only when at least k locals were eligible at
  that instant (read eligibility from the window logs / pool state — the
  selection log carries band, not eligibility); a clamped band (fewer
  eligible locals) is exempt. + concurrency census (expect ≥ 3 units
  > 30 % CPU per 30 s window, sustained).
- `rq2v4_p2_stor_h023_v3` — specificity: lock persists (p95 ≥ 1 s ≈ 100 %
  windows), no compute units spawned.

Fail criteria (evaluable from the artifacts): a logged burst with
`band < k` occurred while ≥ k locals were eligible (band is the
discriminating logged quantity — `band ≥ 4` rules out a one-hot band by
construction), a sustained distinct-serving-units census below 3 per lane
in the post-add steady state, or stor relief appearing. If the gate still
fails with the floor active and wide bands observed, escalate to the
structural option (per-connection server flows) with the author.

## 5. Review log

- Round 1 (2026-10-12, auto-review gate, `--implemented`): 0 critical,
  8 warnings, 8 observations — all resolved: known-IP + slow-start
  eligibility guards and MAC tie-break added to the floor; docs corrected
  (top-up semantics, cost-bound supersession, pre-P2.8 baseline, RQ3
  operating-point note, warm-claim path description, fan-out wording,
  single-run gate framing); env pins added; plan misnumbering fixed;
  selftest extended (31 assertions).
- Round 2 (2026-10-12): 0 critical, 3 warnings, 4 observations — resolved:
  §2/docstring wording synced to the top-up semantics + eligibility guards;
  plan clamp qualifier added; §4 fail criteria made artifact-evaluable
  (band, the logged quantity); eligibility term fixed to "slow-start
  penalty fully decayed" everywhere (the guard is exact equality on the
  decayed-to-zero penalty); §11 slow-start spread-inoperative note added;
  selection log-format assertion added (32 total).
- Round 3 (2026-10-12): 0 critical, 0 warnings, 2 observations (wording
  consistency: `band < k` exemption precedence made explicit; "cannot take
  a burst" qualified by the eligible-locals clamp everywhere) — resolved.
  Converged.

## 6. Verdict (re-seat `_v3`, 2026-10-12)

Runs (post-P2.8 `750ef12`, hash-only shape, rate 0.23, seed 42, full
retention):

- `20261012_003550_rq2v4_p2_comp_h023_v3` (00:35:50–00:57:05 Z)
- `20261012_010455_rq2v4_p2_stor_h023_v3` (01:04:55–01:26:41 Z)

| Run | p50 L1/L2 | p95 L1/L2 (max) | Lock % win | Completion | Timeouts |
| --- | --- | --- | --- | --- | --- |
| comp v3 | 0.2 / 0.2 s | 1.8 / 2.1 s (3.5) | 32.8 / 34.4 | **100 / 100 %** | **0** |
| stor v3 | 2.0 / 2.3 s | 16.7 / 15.0 s (35.6) | 100 / 100 | 98.1 / 98.1 % | 1 |

Mechanism gates — all PASS:

- band = 4 in **every** steady-state epoch (histogram `{1:1, 2:1, 4:8}`;
  the two sub-4 bursts were eligibility-clamped at episode start with only
  2–3 units admitted — the pre-registered exemption);
- every floor-complete burst seats **all four** band members, both lanes
  (v1: one-hot everywhere; v2: mostly band=1);
- sustained **3–4 concurrent servers in 48/61 windows** per lane (serving
  census; the >30 %-CPU proxy under-detects post-spread);
- stor specificity holds (100 % lock windows, zero compute spawns);
- culls 0/0, exceptions 0, timeouts 0 (comp), completion 100 %;
- per-request cost unchanged — T_proc halved (381 → 188 ms) by concurrency.

Relief timing — the honest reading:

- post-engagement steady state (add+180 → end): **PASS both lanes** —
  lan1 83.3 %, lan2 82.1 % of windows p95 < 1 s (medians 0.53 / 0.60 s);
- pinned post-add window ([add+30, +180]): 40.0 / 53.3 % — structurally
  transitional: the floor cannot engage before ≥ 4 units are admitted and
  the next 60 s re-selection burst arrives (first floor-complete burst ≈
  add+177 s). The window measured the platform's re-selection cadence, not
  the repair;
- last 180 s: lan2 84.2 % PASS; lan1 78.9 % — one window short.

Decision D12 (2026-10-12, author-approved): the campaign relief gate is
**re-anchored to the post-engagement steady state** (first floor-complete
burst → episode end), and **time-to-relief** (first add → first sustained
relief) is recorded as a measured endpoint of the compute cells. Seat
frozen: R_s = 0.20 (rate 0.23 seat), work factor 25000, edge quota 0.15,
caps 6/6.
