# RQ3 Soundness — Preflight Campaign (P0 → P1)

**Host:** `cloud-vm-rq3` · **Plan:** [`experiment_plan.md`](experiment_plan.md)
· **Matrix:** [`run_matrix.md`](run_matrix.md)

P1 is a **go/no-go**: 3 core runs (+1 optional). E launches only after the
lock file exists. One checkpoint row per run in `preflight_log.md` (created at
execution time by the runner).

## Stage C0 — frozen runtime (no runs)

1. Confirm no experiment process, launcher, network setup or watchdog is
   active on the VM (Family 4 completed 2026-09-09/10 — archive only).
2. Commit the §7 implementation; create tag `rq3snd-preflight-<date>` at that
   commit; detached worktree `~/rq3snd_frozen`; verify `HEAD == tag`. No
   post-tag edits to protected-surface files — the single declared exception
   is the step-3 `phases.json` restore; after it and BEFORE step-4 manifest
   generation, `git status --porcelain` must show exactly that one
   modification; anything else = STOP. (Manifest/lock files created by P0
   tooling afterwards are exempt and recorded in the lock.)
3. Restore the Family-4 locked phase profile **inside the frozen worktree**
   `phases.json`, source rule (first available): (i) an archived
   `*_rq3tim_*/phases_snapshot.json` on the VM
   (`source/scripts/testing/metrics/`; any none-cell E run), (ii) the Family-4
   frozen worktree `phases.json` at its recorded tag. Neither found →
   STOP/escalate — never invent the profile. Assert `compute_plateau` 600 s /
   `rate_per_client` 2.0 / `service_pressure` 1.0 (mismatch = STOP); record
   source path + hash. This is the ONLY allowed tree-vs-tag difference.
4. `rq3snd_p0_01_prepare_tag.py --worktree <path> --tag <name>` → manifest
   over the FINAL frozen tree (post-restore; includes the restored
   `phases.json` hash); hashes verified (mismatch = STOP).
5. Confirm the shared image guard (`rq3lh_image_state.json` lineage) — no
   rebuild.
6. `rq3snd_p0_03_preflight.sh`: py_compile/pyflakes, `bash -n`, env-merge
   proof (off-path byte-identical), phase-profile assertion, quota 0.12
   default, manifest verify — all pass.
7. `rq3snd_p0_02_analyzer_selftest.py`: window extraction (`t_bind`; `t_claim`
   when the knob is active), `timeout`-first class order + 000 / 503 / slow
   boundaries, D math, lead fit, crossover — all green. Any red = STOP
   (currency not computable).
8. Repo canonical `phases.json` is edited in place at P1 **lock** only
   (plan §5/§7.5).

## Stage P1 — go/no-go runs

Commands per [`run_matrix.md`](run_matrix.md); seeds 6351–6354; one checkpoint
row per run.

| Run | Cell | Gates (pre-agreed) | Expected artifacts | Fail action |
| --- | --- | --- | --- | --- |
| **R1** `rq3snd_premature10_event_only_90` (seed 6351) | F2 reproduction | (a) in-window `[t_bind − N, t_bind]` `000` ≥10/LAN (window-offered denominator); (b) run-wide `000` ≥0.3 % of offered ∧ ≥50 rows (floor below the pre-fix 162–428-row range); (c) median admitted→first-**successful** flow ∈ [8, 12] s; (d) ≥1 `CHECK VIOLATION`; (e) attestation (`EDGE_READY_PREMATURE_S=10`) present; (f) measured claim→bind deferral ∈ [9, 11] s | `client_requests.csv`, app/controller logs, `rq3snd_fault_attestation.txt`, `phases_snapshot.json`, `controller_env_snapshot.env` | **STOP** — signature not reproducible; re-design before any spend |
| **R2** `rq3snd_premature10_reconcile_91` (seed 6352) | F2 immunity | (a) `000` ≤1 row ∧ ≤0.2 % offered; (b) 0 successful new-backend flows before `t_bind`; (c) 0 `CHECK VIOLATION`; (d) median claim→first-successful flow ∈ [10, 22] s (`t_claim = t_bind − N`; descriptive `t_admit→first flow` ∈ [0, 2] s); (e) admission source = `probe` | same as R1 | **STOP** — structural claim broken; E must not launch |
| **R3** `rq3snd_semantic_event_only_92` (seed 6353) | F3 signature | (a) lie window (clipped to plateau) ⊇ ≥90 % plateau (S=1200 fixed — the clip means S is no lever; shortfall = late bind → DIAGNOSE: one same-config rerun; repeat → STOP/re-spec); (b) ≥90 % of completed rows attributed to lying backends are 5xx ∧ ≥15 attributed completed rows/LAN (the denominator itself); (c) transport `000` ≤1 % of window offered; (d) 0 `CHECK VIOLATION` | same as R1 + lie-window timestamps + backend-attributed rows | **Scope reduction** — descope/re-spec F3; E only under amended plan |
| **R3b** *(optional)* `rq3snd_semantic_reconcile_93` (seed 6354) | F3 × reconcile | same gates as R3 | same as R3 | Informative; not a kill |

Checkpoint row fields: label · seed · arm · fault · knob attestation
(env snapshot + attestation file; measured claim→bind deferral for F2) ·
quota snapshot (`requested_edge_cpus == 0.12`) · mechanism (admits/abandons;
`mode=all` for `loss_all`; admission source counts
`event|probe_fallback|probe|wake_verify_probe`) · floors (§4.5) · driver
cancel_rate <5 % · verdict GO / STOP / DIAGNOSE. P1 reruns: harness
invalidity or DIAGNOSE only, max 1 per R-run — never for a fail direction or
a none-cell breach (plan §4.5/§5). Rerun labels: same ordinal + trailing `r`
(e.g. `_90r`); analyze the rerun with `--rerun-attempted` so a persisting
shortfall STOPs (exit 3) instead of re-diagnosing.

## Lock (after R1 ∧ R2 pass and R3 lands)

```
readiness_robustness.py soundness-preflight --run-dir <90–93 folders> \
  --out rq3snd_preflight_results.json --lock-out rq3snd_preflight_lock.json
```

Exit 0 → lock: `rq3snd_preflight_lock.json` gates E (S=1200 recorded for all
E F3 runs); apply the in-place repo
canonical `phases.json` restore (plan §7.5); write changelog line. Exit 2 →
DIAGNOSE: gates inconclusive — rerun allowance (max 1 per R-run; no E). Exit
3 → STOP: kill-rule fail or unrepaired invalidity (report; no E).

E runs only after the lock file exists. Do not create `results.md` or later
artifacts before the campaign runs.
