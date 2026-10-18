# RQ2 v5 — W3 Battery Contract (56 runs)

**Status:** ACTIVE (D22 frozen 2026-10-17; author approval "proceed")
**Parent:** [`rq2v5_plan.md`](./rq2v5_plan.md) — the design/fix contract. This
file is the *runnable* contract for the battery: what runs, in what order, with
which frozen values, and what stops the campaign.
**Pilot record:** [`rq2v5_p2_01_pilot_evidence.md`](./rq2v5_p2_01_pilot_evidence.md)
(P-A, P-B×3, P-C×2 — 6 of ≤7 pilot slots used; all pilot bars met or
explicitly decided).

---

## 1. Purpose and hard goals (D24 — author re-registration, 2026-10-17)

Measure, on the v5 platform segment (read-path renewal + storage ε-band +
recalibrated db seat), whether the action arms beat the comparison arms the
author designates. **D24 replaces the earlier gate set (D22); everything not
listed below is soft.**

### 1.1 HARD goals — db block (storage-bound press)

"Better" requires **`t_db` improvement AND same-tier relief** (both).

| # | Required direction |
| --- | --- |
| D1 | `both`@db **>** `none`@db |
| D2 | `stor`@db **>** `none`@db |
| D3 | `both`@db **>** `comp`@db |
| D4 | `stor`@db **>** `comp`@db |

`comp`@db vs `none`@db: **no requirement** (explicitly not a goal).

### 1.2 HARD goals — mx block (mixed press)

"Better" requires improvement in **at least one of** `t_db`, `t_proc`,
same-tier relief.

| # | Required direction |
| --- | --- |
| M1 | `stor`@mx **>** `none`@mx |
| M2 | `comp`@mx **>** `none`@mx |
| M3 | `both`@mx **>** `none`@mx |
| M4 | `both`@mx **>** `stor`@mx |
| M5 | `both`@mx **>** `comp`@mx |

### 1.3 Operationalisation (mechanism only — vetoable without changing intent)

- Per-seed **paired** direction; a cell passes when the required direction holds
  in **≥ 6 of 7 seeds**; ties count against. Cell medians reported alongside.
- **Materiality of "better" — registered by D25 (author, 2026-10-18):
  direction only, no magnitude floor** ("if the overall direction stands then
  that's good enough"). The ≥ 5 % / ≥ 20 % readings are reported as sensitivity
  analysis, never as gates.
- `t_db` = window-log `domain_summary.avg_time_db_ms` (primary;
  `avg_time_db_read_ms` secondary, write-mixing caveat).
- `t_proc` = `avg_time_proc_ms`.
- Same-tier relief = pressed-member utilisation drop with added members
  carrying reads (D14-style windows; the ≥ 80 %-window *intensity* is soft —
  the hard part is the direction).

### 1.4 Soft goals (reported, manageable — no pass/fail)

Ratio magnitudes (the old ≤ 0.80 bars), D14 window-intensity protocol,
client completion % / p50, band/census extras beyond completeness, and any
statistical nicety not named in 1.1/1.2.

### 1.5 Validity inclusion (run-validity criteria, not goals)

Manipulation checks MC1–MC5, base-requirements floor, renewal-census
completeness, `culls == 0`, run `.run_completed` — a run failing these is
excluded/replaced under §7, it is not a "goal failure".

## 2. Frozen configuration (D22)

| Knob | db block | mx block |
| --- | --- | --- |
| `STORAGE_CPUS` | **0.09** | **0.05** |
| `EDGE_CPUS` | **1.20** | **0.15** |
| `EDGE_MEMORY` | 384m | 384m |
| Other | pins file `controller_env_overrides/rq2v5_pins.env` (7 keys incl. `EDGE_POOL_RENEW_*`, `EDGE_MEMORY`) | same |

- `HASH_WORK_FACTOR=25000`, `CLIENTS=24`, `CONTENT_ITEMS=3000`, `USERS=100`, `DATA_SEED=42`, `WAN_RTT_MS=185` — launcher defaults, unchanged from v4.
- Workload: `phases.json` edited in place per regime, byte-exact:
  - mx ref `rq2v5_ref_phases_mx.json` (sha256 `e5301d3be40eee63dfb1…`)
  - db ref `rq2v5_ref_phases_db.json` (sha256 `9b772c2b7b1ff110487d…`)
  - pre-campaign state `rq2v5_ref_phases_restore.json` — restored byte-exactly by the driver at campaign close.
- Platform: edge image `dd3032e30b92` (rebuilt with W1 code); controller code bind-mounted from `source/sdn_controller` (no image rebuild); network scripts carry the four `-e EDGE_POOL_RENEW_*`/`EDGE_MEMORY` passthroughs.

## 3. Run matrix (56 runs — v4-exact ordering)

Batch: `source/scripts/testing/rq2v5_batches/campaign.txt`
Format per line: `<mode> <label> <seed> <edge_cpus> <storage_cpus>`.

- **mx block** (28): seeds `45 46 47 48 42 43 44`, modes 4/seed.
- **db block** (28): seeds `43 44 45 46 47 48 42`, modes 4/seed.
- Per-seed mode order identical to v4 (paired comparability): seed 42/46 →
  `both comp stor none`; 43/47 → `comp stor none both`; 44/48 → `stor none
  both comp`; 45 → `none both comp stor`.
- Labels `rq2v5_<mode>_<regime>_<seed>`; run folders under
  `source/scripts/testing/metrics/` on the VM.

## 4. Execution

Driver: `source/scripts/testing/rq2v5_campaign_driver.sh` (VM:
`~/efficient-storage-in-edge-scenarios/…`). Single launcher invocation:

```bash
cd ~/efficient-storage-in-edge-scenarios
nohup bash source/scripts/testing/rq2v5_campaign_driver.sh \
  $PWD/source/scripts/testing/rq2v5_batches/campaign.txt \
  > ~/rq2v5_battery/driver_stdout.log 2>&1 < /dev/null &
```

Per run the driver:

1. sha-gates `phases.json` against the regime ref and swaps it if needed
   (`phases_swap` logged with both shas);
2. records `dyn_pre` (dynamic storage containers still up — swept by
   `setup_network → cleanup.sh -v` at every launch, so they never enter a run);
3. launches `rq2v5_launch_run.sh` with the batch seat, the pins file and
   `HASH_WORK_FACTOR=25000`, logging to `~/rq2v5_battery/run_<label>.out`;
4. writes evidence per run (`~/rq2v5_battery/evidence/<label>.txt`) and one
   row in `~/rq2v5_battery/rq2v5_run_status.csv`
   (`rc`, `run_completed`, `culls`, `oom_lines`, `phase_last`, `verdict`, `reason`).

**Halt conditions (fail fast, `DRIVER_HALTED` marker):** launcher rc ≠ 0;
missing run folder; missing `.run_completed`; `culls != 0`. OOM lines are
recorded per run but not fatal (v4 carry; the 384m cap removed the known class).
Between runs the driver sleeps 15 s and edits nothing else.

**Between-run edit scope:** none beyond the driver's own sha-gated
`phases.json` swap. No platform, pins, seat or workload changes during the
battery. Any change requires stopping the campaign (below) and a new decision ID.

## 5. Monitoring

- `tools/watch_campaign.py --host cloud-vm-rq2 --expected-runs 56
  --poll-interval 60 --timeout 144000` (Windows host, async). Four explicit
  exits (lessons-learned discipline): `0` CAMPAIGN_DONE · `2` DRIVER_HALTED ·
  `3` driver process gone without a marker · `4` timeout.
- Single source of truth: `~/rq2v5_battery/driver.log`. During an active run do
  **not** poll run artefacts, edit repo files, or touch the run folder; the
  watchdog is the status channel.
- Stop/restart authority: only on (a) a `DRIVER_HALTED` reason, (b) the user's
  explicit instruction, or (c) a run that has clearly failed and cannot produce
  useful evidence.

## 6. Checkpoints (per regime block)

1. **First run of each block** (mx: `rq2v5_none_mx_45`; db: `rq2v5_comp_db_43`):
   D3 provenance — `controller_env_snapshot.env` contains the pins values
   (`EDGE_POOL_RENEW_ENABLED=1`, `EDGE_POOL_RENEW_WAVES=2`, `EDGE_MEMORY=384m`)
   and `phases_snapshot.json` matches the regime ref sha.
2. **First `stor` run of each block**: renewal census sanity (admissions →
   broadcasts → edge fires; wave-2 ≈ wave-1 + 45 s) and `storage_band=` present
   in controller logs; `spread band=` count unaffected.
3. After each block: `rq2v5_run_status.csv` review — all rows `pending_review`,
   culls 0, OOM 0 expectations.

## 7. Replacement / top-up rules (v4 S5.5 + D20, verbatim)

Incident-class replacements only (OOM/crash/infra — never "bad numbers");
spares ≤ 14 with author sign-off; **> 4 replacements in one regime ⇒ stop and
escalate**; per-cell cap as registered in v4. Every replacement row in
`rq2v5_run_status.csv` with its reason. F2 floor quiescence and v4 stop
triggers carried.

### Replacement ledger

| Date | Run | Reason | Disposition |
| --- | --- | --- | --- |
| 2026-10-18 | `rq2v5_stor_db_43` | **Incident (OOM)**: edge process (`python3`, anon-RSS 370 MB) killed by the kernel at episode onset inside the 384 m cap; run completed but completion dropped to 48.7 % (t_db 446/380 ms ≠ fair stor value) | **Replaced** by `rq2v5_stor_db_43_r1` (batch `rq2v5_batches/replacement_db_43_r1.txt`), author-approved 2026-10-18 — spare **1/14**. The OOM'd original stays on disk as evidence. |
| 2026-10-18 | `rq2v5_stor_db_44` | lan-2 t_db 1932 ms vs lan-1 89 ms — no relief on one lane. **No infra event** in its window (the dockerd `ShouldRestart` lines are the normal end-of-run SIGTERM teardown) | **Retained** (behavioural outcome; §7 forbids replacing on numbers). Counts as the single allowed non-pass under ≥ 6/7. |
| 2026-10-18 | `rq2v5_stor_db_48`, `rq2v5_both_db_45` | Partial lan-2 relief (545 / 870 ms) — still ≥ 3× better than `none` on that lane | Retained; flagged as the **lan-2 renewal-intermittency finding** for W4 (per-lane fire auditing is impossible post-hoc: edge containers are recreated each run, edge logs not captured — recorded limitation). |
| 2026-10-18 | `rq2v5_both_db_48` | **Incident (OOM)**, same class as 43: edge `python3` killed at 367 MB anon-RSS ~1 min into the episode. **Hard metrics intact** — t_db **52.8/56.4 ms**, the best `both` reading of the block; only the soft metric is degraded (episode completion 69.6 % vs 89–99 % clean) | **Retained** by author decision 2026-10-18 ("if most runs follow the desired path then there is no issue"). Flagged in the W4 tables for the soft metric. Spares remain 1/14. |

| 2026-10-18 | `rq2v5_stor_db_43_r1` (replacement for the OOM'd 43) | Completed clean (`rc=0`, `.run_completed`, culls 0, **OOM 0**) but **weak relief**: t_db **1166/1796 ms** (healthy stor seeds: 60–69 ms), completion 69.2 %, members 3/2 | **Adopted** as the seed-43 `stor` measurement (supersedes the OOM'd original, which stays on disk). Still better than `none` on both lanes (0.54/0.88) so D2 counts it as a pass; it joins the **relief-intermittency cluster with 44 and 48** (3 of 8 `stor`@db runs show partial relief) — primary W4 finding. Spares used: **1/14**. |

**OOM census under `EDGE_MEMORY=384m` (recorded for post-campaign):** 2/28 db
runs, **both at episode onset** with ~367–370 MB peaks (`stor_db_43`,
`both_db_48`); at 256 m the class killed 2/2 pilot runs mid-episode. The cap is
marginal at press onset — 512 m is the evidence-backed candidate for a
post-campaign seat revision (NOT applied mid-campaign; comparability).

## 8. Post-run handoff

Run folders stay on the hosting VM (they are the campaign archive; never copy
whole run folders locally, never delete them). Hand off to the **Edge
Experiment Analyzer** for cleanup of transient request CSVs / controller logs,
per-run summaries, `rq2v5_cell_stats.csv`, `rq2v5_run_status.csv`, and the W4
deliverables named in `rq2v5_plan.md` §6.

## 9. Estimate

mx run ≈ 50–55 min wall (setup ~25 + schedule 27 + post) → mx block ≈ 25 h;
db run ≈ 40–45 min → db block ≈ 20 h. Campaign ≈ 45–50 h wall including
deploy overhead. Budget checkpoints at each block boundary.

## 10. Campaign outcome (2026-10-18) — CLOSED

- **56/56 runs completed** + 1 approved replacement (`rq2v5_stor_db_43_r1`).
  Every row: `rc=0`, `.run_completed`, culls 0. Wall time ≈ 31 h for the main
  battery (2026-10-17 05:23 → 2026-10-18 12:16 UTC), replacement 12:40–13:12.
- **D24 hard gates — ALL PASS (materiality = direction only, D25):**
  - db: **D1 7/7** · **D2 7/7** · **D3 7/7** · **D4 7/7**
  - mx: **M1 7/7 · M2 7/7 · M3 7/7 · M4 7/7 · M5 7/7**
  - Sensitivity (reported, not gates): D2 = 6/7 at a ≥ 5 % per-lane floor and
    5/7 at ≥ 20 % — driven by the three partial-relief `stor` seeds.
- Incidents (2, both edge-OOM at episode onset): `stor_db_43` (replaced),
  `both_db_48` (retained by author decision — hard metrics intact, soft
  completion 69.6 %). Spares used **1/14**.
- Workload restored byte-exactly (`phases.json` sha `57bccc12bebb98dfeb92`);
  campaign marker preserved as `CAMPAIGN_DONE_main56`.
- **Findings registered for W4:** (1) relief intermittency in 3/8 `stor`@db runs
  (`43_r1` 1166/1796, `44` 89/1932, `48` 68/545) with census complete —
  delivery-side, likely band/wave-B selection under stats lag (plan §7.3);
  (2) `comp`@db inverts t_db (2.8–4.8 s vs none 1.8–2.3 s) while improving
  t_proc/completion — the wrong-action signature; (3) edge-memory cap marginal
  at press onset (2/28 at 384 m, ~367–370 MB peaks; 512 m candidate).
