# RQ2 v5 — W2 pilot evidence (running log)

> **Status:** IN PROGRESS (W2). Compiled 2026-10-16 by the W2 executor (direct
> execution, no subagent). Plan: [`rq2v5_plan.md`](rq2v5_plan.md) S4.
> Seat under test: db `STORAGE_CPUS=0.09` + `EDGE_CPUS=1.20`, pins
> `rq2v5_pins.env` on every run; mx pair keeps `sc=0.05`, `ec=0.15`.

## P1 — `none`@db, sc=0.09 (P-A: seat calibration)

**Run:** `20261016_195111_rq2v5_p2_pilot_none_db_45` — status **completed, exit 0**
(19:51:11Z → 20:10:20Z).

**Hygiene:** D3 phases snapshot == db ref **True**; all six pins present in
`controller_env_snapshot.env` (STORAGE_POOL_RENEW_ENABLED=1, SPREAD_EPS=0.03,
SPREAD_MIN_BAND=2, EDGE_POOL_RENEW_ENABLED=1, WAVES=2, WAVE_GAP_S=45);
`triggering removal` 0/0; `reserve_activate` 0/0 (correct for `none`);
`ComputeAlert` 0/0; `pool_renew` 0/0 (no admissions — correct);
`storage_band=` marker present (9/13 lines; single-member band).

| P-A gate | Required | Measured (lan1 / lan2) | Verdict |
| --- | --- | --- | --- |
| member win-max mean (episode) | >= 90 % | **95.3 / 96.7 %** (median 97.5 / 98.3) | PASS |
| delivery deficit vs offered (~1200/win) | >= 8 pp | delivered 889 / 896 -> **~26 / 25 pp deficit** | PASS |
| `t_db` median | >= 120 ms | **2054 / 1892 ms** | PASS |
| edge CPU mean | < 70 % | 31.2 / 30.8 % | PASS |

**Reading:** the seat recalibration works — at `sc=0.15` the v4 member sat at
~69 % with flat ~62 ms `t_db`; at `sc=0.09` it saturates at ~96 % with
`t_db` ~1.9-2.1 s. There is now real headroom for H1 (`stor` must bring `t_db`
below 0.80 x these values). Client metrics (soft): 78.2 % completion,
p50 4.72 s, 24 849 timeouts (l1+l2 episode rows; a much harder press than
v4's ~92 %).

## P2 — `stor`@db, sc=0.09 (P-B: first mechanism test)

**Run:** `20261016_202701_rq2v5_p2_pilot_stor_db_45` — completed, exit 0
(20:27:02Z → 20:45:40Z). **INCIDENT-AFFECTED: lan1** (see below); **lan2 clean.**

**Census:** lan2 = 5 admissions -> 5 broadcasts -> waves fired per admission
(20:26:52 / 20:29:24 / 20:31:33 / 20:33:44 / 20:35:54; four of them in-episode),
epoch ids advancing, supersession counted/logged, `deferred=0` throughout.
lan1 = 2 broadcasts (startup activation of dyn1 at 20:26:45 + one at 20:45:38
after the episode) — see incident. Edge logs show the exact wave pairs
(wave=1 -> wave=2 at +45 s) on both units. `storage_band=` marker active with
band=2, RR alternating between static (…:04) and dyn (…:01:06) on lan1.

**lan2 (clean lane) — mechanism works:**

| P-B direction | Measured (lan2) | vs P1 (`none`) | Verdict |
| --- | --- | --- | --- |
| `t_db` median (episode) | **69 ms** (T1 1112 ms -> T2 59 ms -> T3 178 ms) | 1892 ms -> ratio ~0.04 | PASS (H1 direction) |
| distribution | **4 members carrying load** (mean CPU 30-58 %, static member mean 40.8 %) | 1 member at 96 % | PASS (H2 direction) |
| delivered/window | ~1100-1230 (T2) | ~896 | recovered to ~offered |
| client (soft) | **93.0 % completion**, p50 1.23 s, 3941 timeouts | 78.2 %, p50 4.72 s | improved |

**lan1 incident (kernel-confirmed):** `edge_server_n1` was **OOM-killed by the
kernel at 20:28:34** (episode start; `journalctl`: "python3 invoked oom-killer";
container restarts=1; `FinishedAt 20:28:34.77 -> StartedAt 20:28:34.84`), then
stalled `app NOT ready: MongoDB ping failed within 180s` (logged 20:31:35).
Consequence: lan1 clients ~28.9 % completion / 46 % timeouts with 1 ms
fast-fails; edge telemetry near-empty for most windows. This is the
**known db-class edge-OOM incident** (v4 P5.04 S6; 256 MB cap under the lookup
press) — **not** the renewal fix: the lan1 rotations completed cleanly before
the kill (20:26:46/20:27:31) and no app errors involve pool_renew.

**P-B verdict:** lan2 = H1 + H2 directions demonstrated; lan1 = incident
(replacement run `_r1` launched). P-B stands on the replacement for the
both-lane reading.

## P2r — `stor`@db confirmation/replacement (`_r1`)

**Run:** `20261016_210640_rq2v5_p2_pilot_stor_db_45_r1` — completed, exit 0
(21:06:40Z → 21:25:43Z).

**H1 direction (t_db vs P1 baselines) — PASS both lanes:**
lan1 median **63 ms** (vs 2054; ratio 0.03); lan2 median **64 ms** (vs 1892;
ratio 0.03). Thirds: lan1 3204 -> 53 -> 58; lan2 343 -> 60 -> 52.

**H2 direction (same-tier relief) — PASS both lanes:** lan1 shows static member
mean 72.7 % (max 99.2) with dyn2 at 50.2 % cooperating; lan2 shows **six
members observed** with four carrying sustained load (static 38.5 % mean max 68,
dyns 20-48 %, one max 100) — reads moved off the initially-saturated members.

**Census:** lan1: 2 admissions / 2 broadcasts / 4 wave-fire lines; lan2: 4 / 4 /
8; supersession + debounce classes exercised in P2; `storage_band=` active
(band=2, RR). culls 0/0. Client (soft): lan1 56.1 % @ 2.69 s; lan2 79.1 % @
2.48 s.

**INCIDENT (repeats):** `edge_server_n1` OOM-killed again mid-episode
(**21:13:13**, kernel cgroup forensics: `docker-38b5f078b6c5…` =
P3's edge_server_n1; RSS ~245 MB vs the 256 MB cap). OOM census 19:30-21:45 =
exactly two kills: 20:28:34 (P2's `edge_server_n1`, container 92394da4…,
cgroup-confirmed) and 21:13:13 (P3's). **2/2 `stor`@db runs have now killed
`edge_server_n1`; the `none`@db run did not; n2 has never been hit** (v4's
victims were also exclusively `edge_server_n1`). Likely contributors at this
seat: ~2 s member throttle -> long client timeouts (20-46 %) + renewal epoch
churn (retiring clients under the press) inside a 256 MB cap.

**Decision (author-approved, 2026-10-16):** raise `EDGE_MEMORY` 256m -> 384m
for v5 runs (pins-file single source; static + dynamic edges both already read
`EDGE_MEMORY`), recorded as a D22 seat-robustness delta. Left unchanged, the db
block would be dominated by incident exclusions and the hard-goal evidence
would be unreliable. Rationale scope check: cb is unaffected (never hit the
256m cap — zero cb/mx OOMs in the entire v4 record; v5 pins are v5-scoped), so
the delta does not invalidate cb or trigger any cb reruns.

Implementation status (2026-10-16, verified before P4 launch): `EDGE_MEMORY=384m`
added to `rq2v5_pins.env` and lifted in `rq2v5_launch_run.sh`
(`MERGED_EDGE_MEMORY` -> make var -> static edge `-e`; controller env ->
dynamic-edge spawns). Local LF-clean, `bash -n` clean (Git bash), local sha256
`f8d2d523f9d4210e` (launcher) / `afe5e1c2f8c3c57e` (pins) **byte-exact on the
VM**. Post-launch check: `edge_server_n1` `HostConfig.Memory` = **402653184 B
(384 MiB)** — lift confirmed live on the static edge.

## P4 — `stor`@db confirmation (r2), final seat + raised cap

**Completed 2026-10-16 22:42 UTC** (`20261016_222259_rq2v5_p2_pilot_stor_db_45_r2`,
seed 45, sc=0.09 / ec=1.20, pins with `EDGE_MEMORY=384m`). Watchdog exit 0;
`.run_completed` present. Purpose: reproduce H1/H2 with **both lanes intact**
under the raised cap.

### P4 results — all pilot bars met

| Check | Expected | Measured | Verdict |
|---|---|---|---|
| H1 t_db (median, episode) | ≤ 0.80 × P1 per lane | lan1 **59.8 ms** vs 2058.8 (ratio **0.029**); lan2 **61.1 ms** vs 1892.6 (ratio **0.032**) | ✅ (27× under the gate) |
| H2 same-tier relief | direction on both lanes | static member median CPU lan1 97.6 %→**58.0 %**, lan2 98.4 %→**19.6 %**; added members carry **47 % / 82 %** of storage CPU; static below P1 median in **41/43 (95 %) / 48/48 (100 %)** windows | ✅ |
| Lanes intact (no OOM) | both lanes complete | **0** oom/kill lines in journalctl; `.run_completed`; both lanes' artifacts complete | ✅ (P2/P3 each lost n1 here) |
| Census | admissions → waves → fires exact | **11 admissions** (lan1 5, lan2 6) → **22/22 edge fires** (lan1 5+5, lan2 6+6 wave-1/wave-2) → 10 controller broadcasts; culls **0** | ✅ exact closure |
| Aggregated storage CPU | relief = redistribution under more aggregate work | P1 single member ~98 % ≈ 100 % capacity; P4 sum-of-members median **128.6 % (lan1) / 137.3 % (lan2)** across 5/6 members — more total storage work delivered, spread | ✅ |
| Clients (soft) | improve vs none | episode completion **82.3 % / 86.2 %** (none 77.5/78.1), p50 **3.28 s / 2.37 s** (none 6.10/5.94) | ✅ |

### P4 observations (recorded, non-blocking)

- **Renewal POST read-timeout 1.5 s trips on loaded edges**: 3 WARNINGS lan1 +
  1 lan2 (`POST .../pool_renew failed: Read timed out`), all while the edge was
  under the press. The edge processed every request server-side regardless —
  all 22 fires are present with correct wave timestamps (wave-2 exactly +45 s
  after wave-1 in every pair). The failure mode is a lost *confirmation*, not a
  lost renewal; a larger controller-side timeout (or async ack) would remove
  the misleading WARNING in W3 without changing behaviour.
- **Teardown-time admission on both lanes** (lan1 22:42:16, lan2 22:42:20,
  i.e. after `.run_completed` content was sealed): contributes the 5th/6th
  admission and the last wave pairs. Harmless for the episode metrics (all
  episode windows precede it) but census accounting in W4 must bucket it as
  post-run.
- `storage_band=` picks: 57 (lan1) / 53 (lan2); D12-anchored `spread band=`
  token untouched (450/405) — G1 anchor integrity confirmed.
- No dynamic edge containers were spawned in this run (expected: `stor`@db
  under storage press; `edge_server_n1/n2` both at 384 MiB cap, RSS ≤ ~137 MiB
  post-episode sample).

## P-C — mx pair

**Launched 2026-10-16 22:52 UTC** — `rq2v5_p2_pilot_none_mx_45` first
(sc=0.05 / ec=0.15, `HASH_WORK_FACTOR=25000`, pins with `EDGE_MEMORY=384m`),
then `stor`@mx after it completes. Pre-launch hygiene: `phases.json` swapped to
the mx ref (sha `e5301d3be40eee63dfb1`, byte-exact); **4 stale dynamic storage
members removed** (`edge_storage_lan1_dyn5/dyn6`, `edge_storage_lan2_dyn6/dyn7`)
— leftovers from P4's teardown-time admissions (see P4 observations). The v4
campaign driver never cleaned dyn containers between runs (it only audited
them), so this is stricter than the v4 baseline; recorded here for the W4
comparability notes. W3's driver should re-check `dyn==0` before each launch.

P-C checks (pilot bars): census (admissions → waves → fires) both lanes,
distribution direction (pressed-tier relief), per-lane t_db ratio stor/none
≤ 0.80 (feeds the H1-mx promote/report decision in D22).

**`none`@mx baseline (completed 2026-10-16 ~23:50 UTC,
`20261016_232122_rq2v5_p2_pilot_none_mx_45`, all 5 phases, `.run_completed`):**

| Lane | episode windows | t_db median | edge CPU | storage CPU | static member CPU |
|---|---|---|---|---|---|
| lan1 | 62 | **103.5 ms** | 77.5 % | 41.6 % | 42.0 % |
| lan2 | 62 | **103.0 ms** | 77.8 % | 40.6 % | 40.9 % |

H1-mx bar vs this baseline: stor lane ≤ **82.8 ms** (lan1) / **82.4 ms** (lan2).
Note the mx none baseline differs sharply from db none (t_db ~103 ms vs
~2000 ms; storage member ~41 % vs ~96 %): the mixed press does not saturate the
storage tier under `none`, so the H1-mx ratio is the meaningful bar here, not
absolute relief.

### P-C results — `stor`@mx (completed 2026-10-17 00:32 UTC, folder `20261017_000531_...`, all phases, `.run_completed`)

| Check | Measured | Verdict |
|---|---|---|
| H1-mx t_db ratio | lan1 **89.3 / 103.5 = 0.863**; lan2 **85.9 / 103.0 = 0.834** | ❌ vs the 0.80 pilot bar (real but sub-bar improvement: −13.7 % / −16.6 %) |
| H2-mx same-tier relief (direction) | static member 42.0 %→**24.6 %** (lan1), 40.9 %→**23.7 %** (lan2); **7–8 added members per lane** carrying 18–35 % each; aggregate storage CPU 42→**108 %** (lan1) / 41→**119 %** (lan2) | ✅ direction clear |
| Census | **7 admissions/lane** (`node_add_timing`), 2 of them debounce-merged → **5 renewal events → 10 fires/lane (5 w1 + 5 w2)** → 6 broadcasts/lane; `storage_band=` 47/42; culls **0**; `node_removing` **0** (v4 baseline identical: `rq2v4_stor_mx_44` = 7 adds, 0 removals; `rq2v4_none_mx_44` = 0 events); OOM **0** | ✅ (v4-equivalent) |
| Clients (soft) | episode completion **74.5 % / 74.5 %** (none 71.7/70.1); p50 **9.15 / 9.19 s** (none 9.95/10.43) | ✅ modest improvement |
| Renewal POST timeouts | 5 (lan1) / 4 (lan2) read-timeout WARNINGS, all served (fires present); same cosmetic pattern as P4 | noted |

Interpretation for D22: the magnitude of the t_db gain tracks whether the
storage tier is the binding resource. In db (member ~96 % under none) the fix
delivers ratio ≈0.03; in mx (member ~41 % under none — the mixed press binds the
edge at ~78 %) the same mechanism yields ≈0.83–0.86. Mx relief is a
redistribution under 2.5–2.9× more aggregate storage work, with both lanes and
census intact.

### D22 outcome (author approval 2026-10-17) — P-C consumed as registered

- **H1-mx = REPORT, not gate.** Measured 0.863/0.834 is a real improvement
  (−13.7 %/−16.6 %) but sub-bar; mx storage is not the binding tier under
  `none`, so a 0.80 gate would measure press intensity, not the fix.
- **H2-mx = gate.** Direction confirmed above; D14 protocol evaluated formally
  in W4.
- Census nuance: 7 admissions/lane, 2 debounce-merged into the 5 renewal
  events (debounce 15 s working as designed; the merge is why edge fires <
  admissions). Two of the 7 adds occurred pre-episode (controller bootstrap
  top-up, 00:01–00:04, before `mixed_episode` began ≈00:06:31).
- Renovation-hygiene finding: per-run `stor` strays (7/lane here) are removed
  by `setup_network → cleanup.sh -v`, which deletes **all** containers +
  transient volumes at every launch (v4 ran identically; `rq2v4` evidence
  shows 0 dyn at capture). Verified live at the first W3 launch:
  `Cleaning up Docker resources` with `dyn_pre=14` recorded by the driver.

### D24 — gate set replaced (author, 2026-10-17, after W3 launch)

The author re-registered the hard-goal battery that D22 had frozen:

- **db (storage press):** `both` and `stor` must beat **`none` and `comp`** on
  **t_db AND same-tier relief**. `comp` vs `none` is explicitly **not** a goal.
- **mx (mixed press):** `stor`, `comp`, `both` must each beat **`none`**, and
  `both` must beat **each single arm** — "better" = any of
  t_db / t_proc / tier relief.
- **Everything else is soft** (ratio ≤0.80 bars, D14 window intensity, client
  completion/p50, census extras).
- The frozen W3 batch already covers every required comparison (4 arms × 7
  seeds in both regimes) — no scope change, no restart.

Pilot numbers in this document remain pilot evidence; the authoritative gates
are `rq2v5_plan.md` changelog **D24** and `experiment_plan.md` §1.
