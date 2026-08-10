# RQ3 v3 — Run Matrix: Compute Saturation Campaign

Part of [`experiment_plan.md`](experiment_plan.md). Per-run configuration for
the **n=7/arm compute saturation campaign** (config P4, tag
`rq3-sat-preflight-20260808`).

> **Status: PLANNED (2026-08-09) — campaign ready to launch.** The tuning
> matrix (P1–P4 + repro4, [`rq3_saturation/run_matrix.md`](../rq3_saturation/run_matrix.md))
> locked the config and demonstrated relief at n=2/arm; this matrix executes
> the full n=7/arm campaign.
> **Storage extension: CLOSED** — see
> [`run_matrix_storage_closed.md`](run_matrix_storage_closed.md).

## 1. Locked per-cell configuration (P4)

| Parameter | Value |
|---|---|
| env | `rq3sat_direct.env` / `rq3sat_discovery.env` (in `env/`, mirror of canonical `controller_env_overrides/`) |
| phases | `phases_rq3_saturation.json` (600 s `compute_plateau`, `service_pressure 1.0`) |
| EDGE_CPUS | **0.15** (launcher arg 4) |
| STORAGE_CPUS | 0.08 · rate 1.5 · CLIENTS 24/LAN (48) · INFLIGHT_WINDOW 1024 · DRAIN_S 30 · WAN_RTT_MS 185 · pool 6 |
| code pin | tag `rq3-sat-preflight-20260808` (controller == `d267099`, 75/75 verified) |

## 2. Campaign matrix (14 runs)

Counterbalance: [`counterbalance_order.csv`](counterbalance_order.csv) — 7
blocks of 2, block seeds 3001–3007 (direct leads 4, discovery leads 3).

| Block (seed) | Pos 1 | Pos 2 |
|---|---|---|
| 1 (3001) | `rq3sat_camp_direct_1` | `rq3sat_camp_disc_1` |
| 2 (3002) | `rq3sat_camp_disc_2` | `rq3sat_camp_direct_2` |
| 3 (3003) | `rq3sat_camp_direct_3` | `rq3sat_camp_disc_3` |
| 4 (3004) | `rq3sat_camp_disc_4` | `rq3sat_camp_direct_4` |
| 5 (3005) | `rq3sat_camp_direct_5` | `rq3sat_camp_disc_5` |
| 6 (3006) | `rq3sat_camp_disc_6` | `rq3sat_camp_direct_6` |
| 7 (3007) | `rq3sat_camp_direct_7` | `rq3sat_camp_disc_7` |

## 3. Launch

Run on `cloud-vm-rq3`, one at a time (per-run reset cycle), watchdog-monitored:

```bash
ssh cloud-vm-rq3 "cd ~/efficient-storage-in-edge-scenarios && \
  bash source/scripts/testing/rq3sat_launch_run.sh \
    rq3sat_direct.env rq3sat_camp_direct_<n> <block_seed> 0.15"
ssh cloud-vm-rq3 "cd ~/efficient-storage-in-edge-scenarios && \
  bash source/scripts/testing/rq3sat_launch_run.sh \
    rq3sat_discovery.env rq3sat_camp_disc_<n> <block_seed> 0.15"
```

## 4. Run log (COMPLETE — 14/14, n=7/arm)

| Run | Block | Arm | Seed | Result |
|---|---|---|---|---|
| `rq3sat_camp_direct_1` | 1 | direct | 3001 | ✅ exit 0, gates OK (`20260809_120125`) |
| `rq3sat_camp_disc_1` | 1 | discovery | 3001 | ✅ exit 0, gates OK (`20260809_124511`) |
| `rq3sat_camp_disc_2` | 2 | discovery | 3002 | ✅ exit 0, gates OK (`20260809_174834`) |
| `rq3sat_camp_direct_2` | 2 | direct | 3002 | ✅ exit 0, gates OK (`20260809_132439`) |
| `rq3sat_camp_direct_3` | 3 | direct | 3003 | ✅ exit 0, gates OK (`20260809_182800`) |
| `rq3sat_camp_disc_3` | 3 | discovery | 3003 | ✅ exit 0, gates OK (`20260809_190741`) |
| `rq3sat_camp_disc_4` | 4 | discovery | 3004 | ✅ exit 0, gates OK (`20260809_194653`) |
| `rq3sat_camp_direct_4` | 4 | direct | 3004 | ✅ exit 0, gates OK (`20260809_202538`) |
| `rq3sat_camp_direct_5` | 5 | direct | 3005 | ✅ exit 0, gates OK (`20260809_210419`) |
| `rq3sat_camp_disc_5` | 5 | discovery | 3005 | ✅ exit 0, gates OK (`20260809_214240`) |
| `rq3sat_camp_disc_6` | 6 | discovery | 3006 | ✅ exit 0, gates OK (`20260809_222103`) |
| `rq3sat_camp_direct_6` | 6 | direct | 3006 | ✅ exit 0, gates OK (`20260809_230021`) |
| `rq3sat_camp_direct_7` | 7 | direct | 3007 | ✅ exit 0, gates OK (`20260809_233935`) |
| `rq3sat_camp_disc_7` | 7 | discovery | 3007 | ✅ exit 0, gates OK (`20260810_001749`) |

> **Campaign status (2026-08-10):** **14/14 runs completed, all exit=0 and all
> base-requirements gates passed** (M1 scale-up fired per LAN in every run,
> M2 all added compute nodes served requests, D1 0×NotPrimary, D2 no
> restart/crash, D3 provenance snapshots present). Run folders retained on
> `cloud-vm-rq3` under `source/scripts/testing/metrics/`. **Analyzed
> 2026-08-10** — see [`results.md`](results.md) (T1/T2 timing: MWU p=0.007/0.004,
> d=−0.84/−0.88; R1 relief: ≥10 pp on 57 % direct / 79 % discovery admissions,
> per-run median 16.0/19.3 pp; C1/C2 null; all gates pass) and
> [`post_run_analysis.md`](post_run_analysis.md). Graphs archived to
> [`graphs/campaign/`](graphs/campaign/); per-run `run_summary.md` in each run
> folder; per-run windowlog relief CSVs + summary CSVs in
> [`analysis/`](analysis/).

> **Execution note (2026-08-09, approved):** Block 2 was executed in **inverted
> within-block order** — `rq3sat_camp_direct_2` ran before `rq3sat_camp_disc_2`
> (run 3 then run 4), whereas the counterbalance lists `disc_2` first. Seed
> pairing (both arms share block seed 3002) and all order-insensitive analyses
> (exact MWU, Cliff's δ, paired-by-seed block test) are unaffected. Consequence:
> direct leads 5 blocks, discovery leads 2 (vs designed 4/3) — still ≥ 2 each.
> Blocks 3–7 ran in the designed order.

## 5. Per-run gates

PG-1 driver clean · PG-2 re-anchored (sub-max CPU ≥ 30 %, ceiling ~40 %) ·
PG-3 scale-up fires · PG-6 no collapse · G1 measurability · G2 min-admissions
· G3 event fraction (direct ≥ 0.80) · G4 flow validation · G5 driver clean ·
G8 no plateau scale-down churn · D1 0×NotPrimary · D2 no restart · D3
snapshots · M1/M2 mechanism · V1 bottleneck · I1/I2 interpretability — per
`experiment_plan.md` §5 and `testing_requirements.md`.

## 6. Preflight evidence (already in hand — config validated)

| Run | Arm | Relief (old-CPU pre→post) | PG-1/3/6 | PG-2 | D1/D2/D3 |
|---|---|---|---|---|---|
| P4 direct `20260809_002533` | direct | −18.9 pp | ✅ | 41.6 % | ✅ |
| P4 disc `20260809_010421` | discovery | −32.5 pp | ✅ | 42.3 % | ✅ |
| repro4 direct `20260809_064945` | direct | −10.3 pp | ✅ | 40.5 % | ✅ |
| repro4 disc `20260809_072852` | discovery | −26.7 pp | ✅ | 39.9 % | ✅ |

Relief ≥ 10 pp in all four pre-campaign runs (mean ≈ −22 pp) → the campaign
is expected to reproduce the headline.
