# RQ2 v4 — P3.1: Mixed ("both") regime levers study + P3.2 calibration-ladder proposal

> **Status:** 2026-10-12 · design artifact; decisions 1–10 approved; ladder
> v1 executed — all rungs + the contingency failed leg (iii) → D13
> member-quota rework (execution record in §6). Inputs from
> [rq2v4_plan.md](rq2v4_plan.md) Phase 3, the frozen P2 seat
> ([rq2v4_p2_08_band_floor.md](rq2v4_p2_08_band_floor.md) §6 / D12), and the
> v3 data-bound record. The run/verdict companion (frozen mix, quotas, rate)
> will be `rq2v4_p3_01_mixed_calibration.md` (plan P3.2). No file touched but
> this one; `phases.json` deltas are proposed textually. Ladder/pilot runs are
> single-run mechanism/manipulation gates (P2.8 §4 framing) — campaign cells
> are the evidence.

---

## 1. Input numbers (value + provenance)

| # | Value | Provenance |
| --- | --- | --- |
| C1 | Hash seat: R_s = 0.20 rps/client; seat rate 0.23 (×1.15); work factor 25000; edge quota 0.15; caps 6/6 dynamic per lane | [rq2v4_p2_02_knee_calibration.md](rq2v4_p2_02_knee_calibration.md) §1–2; band_floor §6 (D12) |
| C2 | 24 clients per lane → 0.23 × 24 = **5.5 rps/lane** hash | band_floor §3; `source/scripts/testing/rq2v4_launch_run.sh` (`CLIENTS=${CLIENTS:-24}`), `source/scripts/Makefile:50–56` (per-LAN count) |
| C3 | **One static edge per lane** (`edge_server_n1`, MAC …:02 / `edge_server_n2`, …:05; one `SERVER_MACS` per controller) + up to 6 dynamics = **7 eligible compute units/lane**. (band_floor §3's "two statics" conflicts with the code; treated as imprecise wording — flag for doc correction in P4) | `source/scripts/network/build_network_1.sh` (~L115–190) / `build_network_2.sh`; `source/scripts/build_network_setup.sh:494,515`; knee §2 ("rotation across **7 units/lane**" with 6 adds) |
| C4 | None-mode = the single static (band = min(4, 1) = 1, one-hot): at 5.5 rps/lane hash-only → **lock 100/100 % windows, p50 2.0/2.3 s** (stor `_v3`) | band_floor §6 |
| C5 | Single-unit lock onset ≤ 4.8 rps; serving ceiling 5–8 rps/lane at 50–58 % median serving CPU (hash_kind §1.2 records 5–10 rps — the narrower value is used) | knee §1; [rq2v4_p2_01_hash_kind.md](rq2v4_p2_01_hash_kind.md) §1.2 |
| C6 | Full dual: band = 4 of 7 eligible; at 5.5 rps → 1.375 rps/unit proven clean (comp `_v3`: p50 0.2 s, post-steady relief 83.3/82.1 % windows p95 < 1 s, T_proc 381 → 188 ms) | band_floor §6 |
| C7 | Hash cost split: wall p50 55–58 ms light-load vs raw 8.7–11 ms; CFS-throttled 54.6/69.6 % of periods | knee §4 |
| C8 | F1 (post-fix): `none`@2.5 rps/client of the old compute-bound shape served clean at **edge CPU ~80 %**. Assuming the battery's CLIENTS=24 per lane (C2's launcher), 60 rps/lane → 0.80 × 150 ms/s ÷ 60 rps = **≈2.0 ms/request** for that shape — an **upper bound** for `content_lookup` (the old shape is heavier; the lookup handler is ms-scale). Conservative pre-fix overhead bound 2.3–2.6 ms (C9). **Design range for lookup edge cost: [2.0, 2.6] ms** (2.0 = post-fix F1 anchor, preferred; 2.3–2.6 = pre-fix C9 band, conservative — the ladder measures the true value) | [rq2v4_p1_05_verification.md](rq2v4_p1_05_verification.md) §3; back-derived; labelled |
| C9 | Edge per-request overhead ≈ 2.3–2.6 ms at 0.15 core (thread churn + telemetry; pre-fix v3 measurement) — conservative upper anchor | preparation §2.1 |
| C10 | v3 data-bound shape: rate 5.0/client, `content_lookup 0.9 / feed_ranking 0.1`, EDGE_CPUS **1.20**, STORAGE_CPUS 0.15, pool 12 → 120 offered / ≈108 lookup rps/lane. By C9 that load needs ≈0.25–0.28 core of edge CPU → v3's 1.20 was provisioned ≥4× above the C9 minimum (exact minimum unrecorded; the direction is the point). v3 cb shape used 0.15/0.08 (same table, lines 275–283) | [../../v3/rq2/experiment_plan.md](../../v3/rq2/experiment_plan.md) §3 (lines 275–294); v3 phases variant `phases_override/phases_rq2_data_bound.json` (v3-era; v4 edits only the canonical `phases.json`, per P4); C9 |
| C11 | Member at ≈108 lookup rps/lane (quota 0.15, pre-add single serving member): 66–74 % CPU pre-add, p50 0.6–1.9 s, 1.8 % TO (F4a); rate 7.0 → backlog, 15.8–18.3 % TO; rate 5.0 ≈ 92 % of single-node capacity; at 0.15 "one node binds (66–74 %), two nodes fully relieve" | [../../v3/rq2/storage_bind_probe_record.md](../../v3/rq2/storage_bind_probe_record.md) §2–3, §5 |
| C12 | Storage never bound at v2 rate 1.5, lookup weight 0.6 → ≈22 lookup rps/lane (weak: v2 read path) | v3 experiment_plan §1 (line ~245) |
| C13 | Effective v4 signals (canonical over base): compute τ_eff = 0.18 + 0.10·dyn (+0.03 peer relief), cap 0.85; cpu floor 10/span 40, tproc floor 25/span **50** (base env), w 0.6/0.4, 3/5 win → fires at edge CPU ≥ **22 %** alone at dyn = 0. Storage τ_eff = 0.35 + Σ (0.10·0.5^i, min 0.05, indexed by **dynamic-node count** i), cap 0.55; cpu 10/30, tdb 10/50, w 0.6/0.4, 2/5 win → fires at member CPU ≥ **27.5 %** alone at dyn = 0 | `controller_env_overrides/current_state_integrated.env`; `source/scripts/osken-controller.env:74–105`; `scaling_policy.py:344–356` |
| C14 | Derived member model (bracketing estimate, not saturated-state evidence — C11's 66–74 % is below saturation, so 1/quota scaling is unproven): CPU ≈ 7.5 % idle + (0.58 ± 0.03) %/lookup-rps at quota 0.15 (idle from v3 experiment_plan §3 "storage idles at 6–9 %"; slope = two-point fit (70−7.5)/108). Fire point at 0.15 ≈ **34** rps; latency knee not recorded → bracket ≈ **(22, 108)** rps (22 = never-bound C12; 108 = past the knee C11). At quota **0.08** (×1.875): CPU ≈ 14 % + (1.09 ± 0.06) %/rps → fire point ≈ **12** rps, press floor 33 % at ≈ **17** rps; predictions carry ±3 pp | derived; labelled |
| C15 | Decision log: dual policy = 5 columns (no per-tier evidence); RQ2 arm policies = 20 columns incl. `compute_score_norm` / `storage_score_norm` / thresholds / `*_fired` per window. **At cap (`count ≥ MAX`) `fired` is forced False but the score columns are still written** in arm rows | `source/sdn_controller/main_n1.py:876–912, 1212–1281`; `source/sdn_controller/scaling_policy.py:260–272, 344–356` |
| C16 | Mode caps: `both` = 6/6, `comp` = 6/0, `stor` = 0/6, `none` = 0/0; `none` **and** `comp` also set `STORAGE_PERSISTENT_RESERVE_ENABLED=0` | `controller_env_overrides/rq2v4_mode_*.env` |

---

## 2. Co-press construction math (per lane, 24 clients)

Mix `hash_challenge : content_lookup = h : l` (h + l = 1), total rate
`R_m` rps/client. Hash part `r_h = h·R_m·24`; lookup part `r_l = l·R_m·24`;
at fixed r_h the lookup part is `r_l = r_h · l/h`.

**2.1 Hash part vs the none-mode capacity bound.** None-mode capacity is the
**single static edge** (band min(4,1) = 1, C3): onset ≤ 4.8, locked at 5.5
(C4/C5). Require **r_h ≥ 5.5** so `none` locks (p95 ≥ 1 s in ≥ 80 % of
windows **and** completion < ~95 % — the pinned P2.3 §1 lock definition,
applied **hash-kind-scoped** in the mixed episode, leg (i)).
Upper side: dual seats band = 4 of **7** eligible units (1 static + 6 dyn,
C3); the only *proven-clean* per-unit load is 1.375 rps (C6) → r_h ≤
4 × 1.375 = 5.5 is proven; the seat (5.66 → 1.42 rps/unit) and rung 3
(6.40 → 1.60 rps/unit, +16 %) probe beyond it and require the dual pilot's
verdict before freezing. Seat window **r_h ∈ [5.5, ~5.7]**. Caps:
6 dynamics + 1 static = 7 eligible; band floor ≥ 4 seats 4 per burst
(hash-determined fan-out); in `none` the band clamps to the single static.
Caveat: in the mixed episode the lock is not gated by the hash part alone
(the single static also carries lookups) — legs (i)/(iv) + the hash-kind
filter carry the attribution.

**2.2 Lookup part vs the storage-member knee.** Exact knee not recorded →
bracket ≈ **(22, 108)** lookup rps/lane at quota 0.15 (C14). The binding
constraint is the **edge budget** at quota 0.15: the seat consumes 50–58 % of
the single static (C5, = 75–87 ms/s) and each lookup costs 2.0–2.6 ms (C8
design range) → the deliverable under the ≤95 % guard is ≈ **21–34 lookup
rps/lane** across the joint corners ((95−58)×1.5/2.6 = 21.3 …
(95−50)×1.5/2.0 = 33.8); the seat (21.9) sits ≈0.6 rps above the
conservative corner → the ≈96 % / ≈1 pp breach stated in §2.3/§3. The range
spans the post-fix F1 anchor (2.0, preferred) and the pre-fix C9 band
(2.3–2.6, conservative) — the ladder measures the true value. At member
0.15 the fire point (≈34 rps) and the press floor (33 % at ≈44 rps) sit above
the deliverable → the **member** quota moves to **0.08** (fire ≈12, press
floor ≈17, C14), so r_l ≈ 22 presses the member (≈38 % model, ±3 — a
bracketing extrapolation of the unproven 1/quota scaling; legs (iii)/(iv)
are the measurement). Stated trade-off: this press is **mild** relative to
v3's 66–74 % fire state (C11) — the quota-relativity of the storage signal
is a design consequence and is escalated to the author (§5.8). The member
*latency* knee at 0.08 is unrecorded and not required: the co-press claim
rests on the signal/press legs and the pilots' CPU-based storage evidence
(v3's robust B2 leg). The ladder measures the two unrecorded quantities: the
lookup edge cost (rung 3, leg (iv)) and the member-0.08 press (leg (iii)).
**Measurement basis:** in `none` and `comp` the reserve is off (C16) → the
domain has exactly one storage node → `avg_storage_cpu_percent` (the score
input) *is* the single member; in `both`/`stor` the reserve standby is
heartbeat-included in the domain mean (`aggregator.py`, "Domain-average
storage CPU across all storage server entries") → the signal basis is
diluted by the idle standby (factor unrecorded, ≈1.5–2×). Consequence: the
co-press criterion lives in `none` (clean basis), but the **pilots' storage
engagement may need a deeper press than the none rung** — pre-registered
escalation ladder: if `mx_both`/`mx_stor` engagement fails on storage while
the none-rung press passed, re-seat at rung 3 (rate-deepen, in-ladder),
then `edge020` if rung 3 also fails; never a silent re-seat. Pilot storage
legs are **serving-node-scoped** (§4), never domain-scoped. Caveat: v3's "0.08 starves per-op (unrelievable)"
(probe §5.3) may be quota-per-op rather than rate-relative; the `mx_stor`
pilot is the arbiter — failure escalates, never a silent re-seat.

**2.3 Edge-quota interaction (the main design tension).** Both kinds share one
edge process and one quota; the quota cannot be split **per kind** inside the
mixed episode (one static edge serves both). v3's answer for the db-only
shape was EDGE_CPUS 1.20 (C10). For the mixed regime the edge stays 0.15 (the
frozen seat — raising it moves the hash press off the single-unit knee and the
hash part must be re-derived off the lock: a seat-breaking change). The
imbalance is absorbed by the **member quota**, the inverse of v3. Edge-budget
convention (used throughout): budget in **ms/s** — hash [75, 87] ms/s (C5's
50–58 % of the 150 ms/s quota, no per-rps scaling assumed) + r_l × [2.0, 2.6]
ms; quota-relative % = ms/s ÷ (EDGE_CPUS × 10). Seat (r_l 21.9):
(75–87 + 43.8–56.9)/1.5 = **[79, 96] %** — inside the ≤95 % guard except at
the (58 %, 2.6 ms) corner (≈96 %; additive model, CFS sub-saturation per C7
not modelled); rung 1 is the fallback seat **only if rung 1 passes all four
legs** — otherwise the fallback is escalation (a below-seat hash part is an
author call). Rung 3 (r_l 24.8): (75–87 + 49.6–64.5)/1.5 = **[83, 101] %** —
passes leg (iv) only if the true cost is at the low end of the range,
otherwise the edge binds first; ≥100 % values read as quota saturation. The
edge-quota-shift contingency (plan-sanctioned, author-gated, hash rescaled)
is the escape.

**2.4 Signals must be attributable per tier in `none`.** Compute: hash-kind
client p95 ≥ 1 s (hash ≈ 2 s dominates the mixed p95 at h = 0.205), plus the
decision-log compute score — the 20-column row carries only the **aggregate**
score, which is the gate (leg (ii)); the CPU-leg attribution is read from the
edge-CPU telemetry (`[telemetry] … cpu=…%` lines / window data) as context
(the T_proc leg is diluted: the window median over 80 % lookups ≈ handler
scale, ~0.2 ms measured in the compute shape, preparation §2.1). Storage:
member CPU leg. Legs (i) + (ii) are hash-kind-scoped and edge-gated by
leg (iv); a lookup-only edge press cannot pass all four legs (leg (iii)
requires the member press). `none` rungs run `SCALEUP_POLICY=bottleneck_aware`
so every delivered window writes a 20-column row with both `*_score_norm` and
`*_threshold` columns (`*_fired` stays 0 — cap-suppressed at 0/0 — and does
not gate; no elasticity ops exist in `none`, so rows cover every delivered
window).

---

## 3. Proposed starting configuration

| Knob | Value | Rationale |
| --- | --- | --- |
| Mix h : l | **0.205 : 0.795** (`hash_challenge` : `content_lookup`; no `feed_ranking` — keeps the levers clean; weights sum to 1.0 per [rq2v4_p2_01_hash_kind.md](rq2v4_p2_01_hash_kind.md) §1.3) | hash:lookup ≈ 1:3.9 |
| EDGE_CPUS | **0.15** (seat-frozen, §2.3) | launcher make-var |
| STORAGE_CPUS | **0.08** (§2.2: the balancing lever) | launcher make-var |
| Total rate R_m | **1.15 rps/client** | per lane: hash 5.66, lookup 21.9, total 27.6 rps/lane |
| Episode shape | Edit the canonical `phases.json` **episode phase in place** (the current 600 s phase, currently named `compute_plateau`; rename it `mixed_episode` — the name is informational, P4.1 defines the final regime phase files): `rate_per_client` = rung value, `mix` = {`hash_challenge`: 0.205, `content_lookup`: 0.795}; leave the other four phases untouched (their old-kind mixes run at ≤2.4 rps/lane — off-press by construction; P4.1 decides whether to strip `service_pressure`/`feed_ranking` from them); snapshot captured per run | `source/scripts/testing/phases.json` (5-phase file); launcher runs it via `run_experiment.sh` default |
| Frozen / untouched | `HASH_WORK_FACTOR` 25000 (image default), caps (C16), `BACKEND_SELECTION_SPREAD_EPS=0.03` / `MIN_BAND=4` | C1 |

**Margins at R_m = 1.15** (state them): hash lock 5.66 vs the frozen seat
rate 5.52 (+2.5 %; "5.5" is the rounded convention used in C2/C4) and vs
onset 4.8 (+18 %); dual per-unit 1.42 vs 1.375 proven clean (+2.9 % —
**tightest inherited margin**, the dual pilot decides); storage press ≈38 %
member CPU vs 33 % floor (1.15×, ±3) and vs 27.5 % fire point (1.4×,
single-node basis — the pilots' diluted signal basis is covered in §2.2);
edge **[79, 96] %** under the ≤95 % guard — ≈1 pp outside at the (58 %,
2.6 ms) corner (rung 3 probes it). The mixed seat r_h = 5.66 is +2.5 %
above the frozen compute-regime seat rate (5.52 — grid step 0.005); a rung-1
seat (4.92, −11 %) is a below-seat departure requiring author sign-off.
Reconciliations: the mixed cell runs member 0.08 while the data-bound regime
keeps v3's 0.15 — per-regime quotas are the v3 precedent (cb 0.08 / db 0.15,
C10), but the quota-relative signal makes the two regimes' storage presses
non-comparable (§5.8).

---

## 4. P3.2 calibration ladder (~6–8 runs)

Common: seed 42, full retention, host quiescence (F2 protocol),
`CLIENTS=24`, pool 6 (launcher default; assignments ≠ read spread — the
P1.4 `stor_db` 7/7-served evidence is assignment-level, v3 read-spread is
pool-12/48-era → residual risk, §5.7), episode shape of §3 with
`rate_per_client` = rung. Definitions: "window" = 10 s telemetry decision
window; "episode windows" = windows fully inside the episode phase;
"member CPU mean" = episode mean of `avg_storage_cpu_percent` (in `none` the
domain has one storage node — no fleet dilution; used only in the `none`
rung legs); "serving-member per-window CPU" = per-window CPU of the storage
primary pre-add / of each serving storage node post-add, from per-node
window stats ([rq2v4_p1_05_verification.md](rq2v4_p1_05_verification.md) §4
serving-unit scoping; used only in the pilot legs);
"edge CPU mean" = episode mean of the domain `average_cpu_percent`
(HTTP-event mean; equals the single static because `none` has one compute
node). Engagement/absence pilot criteria are episode-scoped. Client-CSV
p95 legs exclude phantom rows (status 000 / > timeout ceiling — the
RQ1-documented client-side phantom; P1/P2 analyzer convention).
`TELEMETRY_SOURCE` left at the controller default (zmq) — P4 pins it
(rq2v4_p1_05_verification.md §5.3 note). `none` rungs: extra
env file **`rq2v4_p3_scalepolicy_ba.env`** carrying ONLY
`SCALEUP_POLICY=bottleneck_aware` (a new P3 delta — never the superseded v3
`rq2_bottleneck_aware.env`, which would clobber caps, spans, storage
weights/floors and `TELEMETRY_SOURCE`); pilots: campaign policy (default
`dual`; P4 pins it).

**Pass/fail criterion per `none` rung (exact — all four legs, both lanes, all
legs episode-scoped):**
(i) compute press — hash-kind client p95 ≥ 1 s in ≥ 80 % of episode windows
(`client_requests.csv` filtered to `hash_challenge` rows; phantom rows
excluded) **and** hash-kind completion < ~95 % (P2.3 §1 clause, applied to
the hash subset so the 79.5 % lookup mass cannot carry it; if the hash class
serves ≈100 % while its p95 ≥ 1 s, the rung does **not** auto-pass leg (i) —
record and escalate to the author (§5.10) before seating); (ii) compute
signal — `compute_score_norm ≥ compute_threshold` in ≥ 60 % of episode rows
of the 20-column log; (iii) storage press — member CPU mean ≥ **33 %**
(artifact-defined floor: fire point 27.5 % + ≈5 pp; author decision §5.8;
the mean sets the level) **plus** window-level persistence
`storage_score_norm ≥ storage_threshold` in ≥ **40 %** of episode rows
(aligned with the 2/5 fire cadence — the score clause sets the window
share); (iv) edge attribution — edge CPU mean ≤ **95 %**
(artifact-defined guard: the intended seat-queue sits at 50–58 % (C5), so a
sustained ≈100 % edge with member CPU < 33 % means the queue is edge-bound).

**Rungs (ascending total rate; fixed mix 0.205/0.795, edge 0.15, member 0.08):**

| # | Label | R_m | r_h / r_l rps/lane | Member CPU pred. | Expected | Config delta | Criterion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `mx_none_r10` | 1.0 | 4.92 / 19.1 | ≈ 35 % | r_h ≈ the 4.8 onset where the P2.3 ladder locked 95.3/100 % (one-hot, hash-only) → leg (i) borderline incl. completion clause; storage legs borderline (35 % vs 33 % floor, ±3) | phases rate 1.0 | 4-leg criterion — may pass (cheapest co-press) or fail on legs (i)/(iii) |
| 2 | `mx_none_r115` | 1.15 | 5.66 / 21.9 | ≈ 38 % | **predicted co-press** | phases rate 1.15 | PASS = all four legs |
| 3 | `mx_none_r13` | 1.3 | 6.40 / 24.8 | ≈ 41 % | edge-bind probe: edge [83, 101] % — passes leg (iv) only if the true lookup cost is at the low end of the range (≥100 % = quota saturation); dual per-unit 1.60 (+16 % over proven) | phases rate 1.3 | PASS only if all legs hold; otherwise rung 1/2 seats |

Run order 1 → 2 → 3; seat the **lowest** passing rung. If rung 2 fails
leg (iv) (2.6 ms anchor reality), the fallback is rung 1 **only if rung 1
passes all four legs**; otherwise escalate to the author (a below-seat hash
part is an author call). A rung-3 seat requires the dual pilot to verify
1.60 rps/unit before freezing.

**Contingency (at most one quota-shift round, then stop and bring options to
the author — plan P3.2 gate):**

| # | Label | Shift | When |
| --- | --- | --- | --- |
| 4 | `mx_none_edge020` | `EDGE_CPUS=0.15 → 0.20` **with the hash part rescaled off the lock** (5.5 × 0.20/0.15 ≈ 7.33 → h·R_m ≥ 0.31; e.g. h 0.17, l 0.83, R_m 1.85 → r_h 7.55, r_l 36.9) and `STORAGE_CPUS=0.08 → 0.10` | leg (iv) fails at rungs 2/3 (edge-bound before member-bound) **or** the pilots' storage engagement fails on the diluted signal after rung 3 has been re-run as the engagement-fix step (see `mx_both` row). The lock/onset scaling with quota is unmeasured (onset measured only at 0.15) — the rung re-measures it; r_h 7.55 targets the scaled lock with the same +3 % margin as the seat. Edge budget in the §2.3 convention (ms/s ÷ EDGE_CPUS×10): raw hash ≈65.7 ms/s + 36.9 × [2.0, 2.6] ms → [70, 81] %; measured-occupancy hash [75, 87] ms/s + [73.8, 95.9] ms → [74, 91] %. It changes mix, rate and both quotas — it re-seats the construction (same four legs re-evaluated at the new point), not a comparable rung. Plan-sanctioned quota-shift rung, but it departs from the frozen seat → **author pre-authorization required** |

Member-quota retunes beyond the starting 0.08 (e.g. 0.06/0.12) are the
escalation menu, not rungs; never a silent substitution (the sequential D7
variant is a different treatment).

**Pilots at the seated co-press** (dual policy, mixed shape, seated rate;
single-run manipulation gates — n = 1 framing per P2.8 §4):

| Label | Mode | Criterion (D12-based, numeric) |
| --- | --- | --- |
| `mx_both` | both (`rq2v4_mode_both.env`) | engagement (episode-scoped): ≥1 `scale_up,ComputeAlert` decision row per lane **and** ≥1 storage engagement per lane (`reserve_activate,storage_lanN` row **or** `[reserve] activated` log line; the reserve path latches `waiting` until the standby is READY — the episode, not a fixed delay, is the budget; the storage signal basis is reserve-diluted — §2.2: failure here while the none-rung press passed re-seats at rung 3 first, then `edge020`). Relief: compute — hash-kind post-steady windows p95 < 1 s in ≥ 80 % both lanes (D12: first floor-complete burst → end; inherited from D12's hash-only 83.3/82.1 % on a lighter edge — the loaded-edge margin is unmeasured, the pilot decides). Storage — post-ready windows (ready + 120 s → episode end, v3 B2 POST anchor per `post_run_analysis.md` ~L11; minimum 10 windows — fewer = exception, judge on the CPU legs over available windows): serving-primary per-window CPU < 0.75 × pre-add peak (peak = max per-window serving-member CPU during the episode pre-add; serving-node-scoped per [rq2v4_p1_05_verification.md](rq2v4_p1_05_verification.md) §4) **and** the activated member serves **≥ 40 %** of lookup requests (per-node serving counts from the window routing stats; v3 M2 anchor ≈50 %, 40 % keeps the primary below the relief line — artifact-defined; rides on pool 6, which has no recorded read-spread evidence — §5.7). Time-to-relief per tier recorded |
| `mx_comp` | comp | hash relief ✓ (D12, as above); storage unrelieved (episode-scoped): NO `reserve_activate` row / `[reserve] activated` line, serving-member CPU stays pressed — last-180 s / first-180 s mean ratio ≥ 0.9 (no relief, direction fixed) **and** serving-member CPU mean ≥ 33 % persists in ≥ 60 % of episode windows (one storage node in `comp` — reserve off, domain = member) |
| `mx_stor` | stor | member relief ✓ (activation; serving-primary per-window CPU < 0.75 × pre-add peak; activated member serves ≥ 40 % of lookup requests — pool caveat as `mx_both`); compute unrelieved (episode-scoped): NO `ComputeAlert` decision rows and no compute spawns (under dual policy the only `scale_up` rows are the storage/reserve ones), hash-kind p95 ≥ 1 s in ≥ 90 % of episode windows, edge CPU mean ≥ 70 % post-engagement |

**Exact decision-log evidence names:** compute fire = controller log
`[scale-up] compute fired: 3/5 windows ≥ …` (scaling_policy.py) + decision row
`action_type=scale_up, action=ComputeAlert` + containers
`edge_server_lan{1,2}_dyn*`. Storage fire = `[scale-up] storage fired: 2/5
windows ≥ …` + `action_type=reserve_activate, action=storage_lan{1,2}`
(main_n1.py:454, logged in both policy paths) + `[reserve] activated lan=…`
(`scale_up,DataAlert` = cold-spawn fallback). None-rung scores: 20-column rows
(main_n1.py:1212–1281), columns 6–9 (`*_score_norm`, `*_threshold`).

---

## 5. Open questions for the author

1. **Storage knee:** accept the ≈ (22, 108) bracket at 0.15 (exact knee
   unrecorded) and the ladder's member-0.08 press measurement — or authorize
   1–2 storage-only knee probe runs first?
2. **Edge-quota tension:** confirm the §2.3 resolution — hold edge 0.15
   (frozen seat), move the member to 0.08 as the primary lever (inverse of
   the v3 edge-1.20 move) — and pre-authorize the single contingency slot
   `edge020` (seat-breaking, hash rescaled off the lock, member back to
   0.10); one round, then escalate.
3. **Lookup edge cost:** the design range ([2.0, 2.6] ms, C8) drives the edge
   budget and leg (iv) — the seat sits ≈1 pp outside the ≤95 % guard at the
   worst corner (58 % + 2.6 ms ≈ 96 %); accept ladder resolution (rung 3) or
   authorize a 1-run lookup-only edge-cost
   probe? Budget note: 3 rungs + 1 contingency + 3 pilots = 7 runs; any
   authorized probe consumes a slot, so at most ONE of the Q1/Q3 probes fits
   the plan's ~6–8 cap without dropping a rung.
4. **SCALEUP_POLICY:** confirm `none` rungs run `bottleneck_aware` for
   instrumentation via a new single-key delta (`rq2v4_p3_scalepolicy_ba.env` —
   evaluation mechanics identical across policies per `scaling_policy.py`
   docstring) while pilots run the campaign policy `dual`; campaign `none`
   cells will carry no per-tier evidence (co-press inherited from P3).
5. **Mix kinds:** confirm l = `content_lookup` only (no `feed_ranking`) and
   h:l = 0.205:0.795.
6. **Relief anchors:** confirm the two-anchor split — D12 (first
   floor-complete burst → end) for compute, v3 B2 POST (ready + 120 s) for
   storage.
7. **Pool:** confirm pool 6 (launcher default) for P3 — the 7/7-served P1.4
   `stor_db` evidence is assignment-level, and v3's member-CPU slope and
   read-spread come from pool-12/48 configs; if `mx_stor` shows no read
   spread (the ≥40 % serve-share leg fails for configuration, not mechanism,
   reasons), a pool-12 re-anchor run is the escalation and consumes a run
   slot — the 7-run budget does not cover it.
8. **Quota-relative press:** the mixed cell's storage press at member 0.08
   (≈38 % CPU, mild vs v3's 66–74 % fire state) is quota-relative and not
   load-comparable with the data-bound regime's 0.15 press, and the 33 %
   press floor + 40 % serve-share thresholds are artifact-defined — confirm
   acceptable for the 3×3 comparison, or authorize `edge020` as the primary
   construction (deeper member press at 0.10, but seat-departing) from the
   start. **Choosing `edge020` as primary re-seats the whole ladder at edge
   0.20 (rungs re-derived) — decide before the ladder runs.**
9. **TELEMETRY_SOURCE:** P3 runs inherit the controller default (zmq); P4
   pins it — confirm no P3-level pin is needed for calibration runs.
10. **Hash-kind completion clause (leg (i)):** under mixed edge competition
    the hash class may serve ≈100 % while its p95 ≥ 1 s (the quota-queue
    absorbs, the class completes) — confirm the escalation rule (the rung
    does not auto-pass leg (i); record and escalate before seating) or drop
    the clause now.

---

## Ready for review

Decide §5 items 1–10, then pass the seated config to the **Edge Experiment
Designer** to author `rq2v4_p3_01_mixed_calibration.md` (frozen mix/quotas/
rate, the exact `phases.json` episode delta, run order, per-run gate
checklist). Reviewer/author must decide: storage-knee bracket vs probe, the
member-quota-first contingency order under the edge-quota tension, the
lookup-cost bracket vs probe (and the ≈1 pp worst-corner breach), the
`SCALEUP_POLICY` instrumentation split, mix kinds, relief anchors, pool size,
the quota-relative press and artifact-defined thresholds (0.08 vs `edge020`),
the TELEMETRY_SOURCE pinning, and the hash-kind completion-clause escalation
rule.

---

## 6. P3.2 execution record — ladder v1 (2026-10-12)

Decisions 1–10 approved 2026-10-12. Ladder v1 executed (canonical
`phases.json` episode edited in place per §3; BA delta for the `none` rungs;
full retention; HEAD `8064d71`):

| Run | R_m | r_h / r_l | quotas e/m | hash p50 L1/L2 | hash compl. | edge mean | member CPU mean | legs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `…_r10` | 1.0 | 4.92 / 19.1 | 0.15 / 0.08 | 8.4 / 8.4 s | 79.8 / 79.7 % | 66.4 / 46.9 % | 25.4 / 24.8 % | (i)✓ (ii)✓ **(iii)✗** (iv)✓ |
| `…_r115` | 1.15 | 5.66 / 21.9 | 0.15 / 0.08 | 8.7 / 8.6 s | 70.5 / 70.1 % | 71.1 / 67.5 % | 24.9 / 24.7 % | (i)✓ (ii)✓ **(iii)✗** (iv)✓ |
| `…_r13` | 1.3 | 6.40 / 24.8 | 0.15 / 0.08 | 8.6 / 8.5 s | 63.9 / 63.1 % | 59.6 / 45.5 % | 24.9 / 24.9 % | (i)✓ (ii)✓ **(iii)✗** (iv)✓ |
| `…_edge020` (contingency) | 1.85 | 7.55 / 36.9 | 0.20 / 0.10 | 5.5 / 5.4 s | 70.1 / 71.4 % | 72.6 / 75.9 % | 24.5 / 25.3 % | (i)✓ (ii)✓ **(iii)✗** (iv)✓ |

Leg (iii) failed on the CPU floor (member mean ≥ 33 %) in every run while
its score clause passed (84.4–98.4 % of rows ≥ threshold). Legs (i), (ii)
and (iv) passed everywhere (hash lock 96.9–100 %; the "≈100 % completion
with p95 ≥ 1 s" escalation case did not occur; edge mean 45.5–75.9 %).
Culls 0/0, exceptions 0, no spawns, `phases.json` restored.

**Finding — the member is delivery-capped, not quota-limited.** Member CPU
is pinned at ≈25 % (idle ≈ 6.6–9.4 % → load-attributable press only
+15–18 pp), invariant to offered lookup rate (19.1 → 36.9 rps), member
quota (0.08 → 0.10) and edge quota (0.15 → 0.20). Demand queues at the
EDGE (hash p50 5.4–8.7 s; strict hash completions 64–80 %, ex-phantom
99.3–99.8 %), so raising the offered rate raises the queue, not the
arrivals at the member. Consequence: the 33 % press floor is unreachable
by rate at member 0.08 and C14's model over-predicts here. The mixed
regime at the frozen edge seat is **edge-delivery-limited** — a recorded
platform property (relevant to the write-up).

Contingency note: the single pre-authorized `edge020` round was executed
under the "edge-bound before member-bound" mechanism reading (the formal
leg-(iv) mean never crossed 95 %); it failed the same leg → the chain
stopped at the plan gate — no pilots, no improvisation.

**Decision D13 (author-approved 2026-10-12): member-quota rework** —
`STORAGE_CPUS` 0.08 → **0.05** (the designated balancing lever; per-regime
quotas follow the v3 precedent), one confirm rung at R_m = 1.15, then the
three pilots at that seat. Amended starting config: §3 with member 0.05
(predicted member reading ≈40 %). Comparability caveat (mixed@0.05 vs
data-bound@0.15) stands and deepens — carried into P4.

---

## 7. D13 confirm + pilots — verdicts (2026-10-12)

Confirm rung `rq2v4_p3_mx_none_r115_m05` (`20261012_133403…`): **all four
legs pass, both lanes** — member CPU 40.2/38.6 % (episode mean, 64
windows/lane, `domain_summary.avg_storage_cpu_percent`), hash lock
98.4/98.4 %, compute score 96.8/98.4 %, edge 74.9/67.2 %, culls 0/0.
**Seat frozen: R_m = 1.15, EDGE_CPUS 0.15, STORAGE_CPUS 0.05, mix
0.205/0.795, hash work factor 25000.** Per-kind client stats (pooled, no
phantom exclusion): lookup p50 10.03 s @ 71.3 % completion; hash 10.13 s
@ 70.8 % — the none-mode mixed press is edge-queue dominated for **both**
kinds.

Pilots (same seed/shape/seat; single-run manipulation gates):

| Pilot | Compute | Storage |
| --- | --- | --- |
| `mx_both` | engagement ✓ (3 alerts/lane, 6 spawns); relief ✓ 88.4/91.3 % (D12; time-to-relief ≈ 150 s) | engagement ✓ (activations +10/+21 s); **busiest pre-add member relieved in 82.0/95.7 % of post-ready windows** ✓; reads moved — activated member ≈ 30.8 % (lan1) / 23.0 % (lan2) of sampled reads (collective, beyond the two busiest ≈ 66/75 %) |
| `mx_comp` | relief ✓ 88.4/89.1 % | **unrelieved ✓** (own-peak ratio ≥ 0.96; member ≥ 33 % in ≈ 95 % of windows) |
| `mx_stor` | unrelieved ✓ (no alerts/spawns; lock 98.4 %) | **not relieved ✗** — busiest-member own-peak relief windows 2/51 (lan1, 3.9 %) and 0/49 (lan2, 0.0 %); activated members received ≈ 1–2 % (lan1) / 19–21 % (lan2) of sampled reads; one lan2 member did drop (`:02:07` 36/48) — partial, lane-inconsistent |

**D14 (approved 2026-10-12) — storage-relief criterion re-anchor.** The
v3-era "single activated member ≥ 40 % of reads" is structurally wrong for
multi-member splits, and the per-member counters are sampled (≈ 1
sample/window; shares are reported descriptively, never gated). Storage
relief is judged on the robust CPU leg: the **pre-add busiest member's
per-window CPU < 0.75 × its own pre-add peak in ≥ 80 % of post-ready
windows** (post-ready = first in-episode `[reserve] activated` + 120 s →
episode end). Under D14: `mx_both` ✓/✓ (82.0/95.7 %); `mx_stor` ✗/✗
(3.9/0.0 %).

**Finding — scaling storage alone does not fix the mixed storage press.**
In `stor` mode the added members were provisioned and accumulated
connections (≈ 16–21 each) yet the reads stayed on the pre-existing
members in lan1 (activated ≈ 1–2 %; lan2 partial, ≈ 20 %). What made reads
move in `mx_both` is **not established** — the simple
connection-replacement explanation is unsupported (connections and read
shares diverge across modes). The run artifacts carry **no per-read /
per-connection storage-member attribution**; adding it (member attribution
in the read/flow-install path) is the P4 instrumentation note. Campaign
expectation for `stor` mixed cells: storage-side relief is **not assumed**
— it is measured, and partial or no relief is a reportable outcome.

**Phase-3 exit (reached):** mixed regime constructible — `none` locks
both tiers; `dual` relieves both (D12 compute + D14 storage); `comp` leaves
storage unrelieved; `stor` relieves nothing reliably. Campaign pattern
refined: in a both-sided spike, **only scaling both fixed both**.
