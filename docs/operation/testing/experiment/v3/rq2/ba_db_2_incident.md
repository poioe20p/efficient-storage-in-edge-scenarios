# Incident — `rq2_ba_db_2` (`20260808_171707`, run 7/36)

**Cell**: `ba_db` (bottleneck-aware, data-bound episode) · **Seed**: 42
**Verdict**: ❌ **Not evidence — harness/platform incident** (not designed ba cost).
**Run folder (VM, retained)**: `source/scripts/testing/metrics/20260808_171707_rq2_ba_db_2` on `cloud-vm-rq2`.
**Status**: excluded from the `ba_db` replicate pool; `ba_db` currently has n=1 valid (`ba_db_1`). Rerun planned with the config change below.

## 1. Gate trip (why it is not evidence)

Per `experiment_plan.md` §6 and `testing_requirements.md` (healthy cell — not a no-benefit arm):

| Gate | lan1 | lan2 | Criterion | Result |
|---|---|---|---|---|
| No-collapse (served-basis) | **78.2 %** | **84.4 %** | ≥ 95 % | ❌ (both LANs) |
| Timeout % (episode) | **12.835 %** | **13.803 %** | ≤ 5 % | ❌ (both LANs) |
| B2 | NOT met (p95 0.7→176 s; stor peak 67→96 %) | MET only via CPU leg (p95 0.6→15.4 s) | OR rule per LAN | mixed |
| D1 / D2 (traceback) / D3 | 0 / 0 / 2 | 0 / 0 / 2 | D1 0×, D2 0, D3 present | ✅ (data path clean) |
| M2 | 6/7 compute nodes served (lan1 `dyn5` spawn failed → never usable) | — | each added node serves ≥ 1 | ❌ (1 node spawned ≠ usable) |

Episode collapsed from t≈60 s to t≈450 s (p95 15–190 s; 10–66 % of offered requests timing out per 30 s bucket).

## 2. Root-cause chain (confirmed, evidence-based)

1. **Classifier warm-up divergence (policy contribution, not sufficient).** Decision log `decision_log_lan1.csv` shows the first non-none action at t≈+24 s was a **ComputeAlert** (`bottleneck_class=compute`, `storage_score_norm=0.059` — storage had not yet bound; it bound at t≈+45 s). `ba_db_1`'s first action was the **storage** activation at t≈+36 s. The p5fix suppression itself worked wherever both tiers fired (`rejected_action=compute` at t≈+215 s, `ba_db_2` lan1) — there were **no `classifier_suppressed` violations**. The divergence is a first-window artifact: on this replicate storage bound ~20 s later, so the classifier legitimately committed compute in a compute-classified window before the storage bottleneck manifested.
2. **Trigger — container MEMCG OOM-kill.** `edge_server_lan1_dyn2` (spawned at t≈+30 s from the t≈+24 s fire) was **OOM-killed at t≈+74 s** (17:19:20, exit 137). `dmesg` (17:19:23): `Memory cgroup out of memory: Killed process 749894 (python3)` with `constraint=CONSTRAINT_MEMCG, oom_memcg=/system.slice/docker-b12b8b12b556…scope`. This is a **container memory-limit kill, not host memory exhaustion** — the edge server runs under a **256 MB cap** (`EDGE_MEMORY`, default; `docker inspect` Memory=268435456); the process was at ~211 MB anon-RSS when killed. Only one MEMCG kill, no global OOM.
3. **Amplifier — broken cleanup → flow-plane rebuild.** The killed container's netns/veth cleanup failed (`cannot discover veth … container netns is gone`). The host-set change triggered a topology re-learn + **full flow reinstall (clearing 812 flow keys)** at 17:19:33. Consequence in `resource_stats.csv`: **`server_count → 0`, `T_db = 0` from t≈+90 s** — the lan1 edge serving path was down, so offered requests timed out.
4. **False-underutilization churn.** With no traffic reaching storage, storage looked idle → `[scale-down] storage underutilisation — removing` at t≈+150 s and again later, then re-activation → add/remove cycling (lan1 storage adds/removals: dyn3 added then removed, dyn1 reserve removed, dyn4/dyn6 re-added).
5. **Spawn failures from broken OVS/netns state.** `add_network_node.sh` failed for `edge_server_lan1_dyn5` at t≈+216 s; later `docker inspect` of a new node failed — the OVS/netns residue from the OOM cleanup broke subsequent spawns. `edge_server_lan1_dyn5` therefore never served (the M2 gap).

The episode never recovered: `server_count` oscillated 0↔1↔2 through t≈450 s.

## 3. Attribution: policy vs platform

- **Platform (decisive):** the collapse mechanism is entirely infrastructure — a container hitting its 256 MB cap, failed OVS/netns cleanup, a full flow-plane rebuild dropping the serving path to 0, false-underutilization storage churn, and broken spawns. None of these are policy outputs.
- **Policy (contributory, not sufficient):** the ba classifier's warm-up window fired compute at t≈+24 s before storage bound, putting a compute node in play during the storage-bound window. Not sufficient — `ba_db_1` scaled compute to budget 3/4 under the same policy with zero collapse (B2 MET, 99.85 % served).
- **Reproducibility rule (plan §6) settles it:** one occurrence of a MEMCG kill is not a reproducible policy property. If `ba_db` reruns keep collapsing, the cell would be reframed as a ba-cost finding; until then `ba_db_2` is an incident.

## 4. Decision & config change (2026-08-08, user)

- **Exclude `ba_db_2` from evidence.** The `ba_db` cell now has n=1 valid (`ba_db_1`); rerun required to re-establish n≥2.
- **Raise the edge memory cap 256m → 512m** (`EDGE_MEMORY=512m`, ~2.4× the ~211 MB peak RSS at kill, consistent with the storage tier's 512m):
  - `docs/operation/testing/experiment/v3/rq2/env/*.env` (3 arm files) — dynamic edges via controller env.
  - `tools/run_rq2_campaign.py` `BASE_ENV` — static edges via `build_network_1/2.sh`.
  - Synced to `cloud-vm-rq2:~/rq2_env/` (md5-verified).
- **Config-axis note:** runs 1–14 ran at 256m; runs 15+ run at 512m. The cap is platform hardening, not a treatment; it is not expected to change the policy comparison directionally, but the analysis must (a) confirm no other run showed memory-adjacent events and (b) report the within-cell config split if a cell spans both caps.
- **Rerun plan:** relaunch the campaign at `rq2_ba_db_2`-equivalent position (or `--start-at` the next pending replicate) after the config change; gate-check and B2-check the rerun before resuming further `ba_db` replicates.

## 5. Open items (before the rerun is accepted as evidence)

1. **OOM cleanup robustness** — the cascade was driven by the killed container's broken netns/veth cleanup → flow-plane rebuild. The P5-fix covered graceful churn, not a killed container's residue. If `ba_db_2` is rerun and hits the 512 m cap under extreme churn, the same cleanup fragility could resurface; a controller-side cleanup hardening is a possible follow-up but **not** required to rerun.
2. **Warm-up classifier window** — whether to add a "storage not yet bound" guard to the ba first-fire path is a design decision for after the campaign, not before the rerun (ba_db_1 tolerated the same scaling pattern without issue).

## 6. Evidence artifacts (on the VM, retained)

- `dmesg` MEMCG OOM at 17:19:23 (killed pid 749894, cgroup `docker-b12b8b12b556…`).
- `container_events.csv`: `state_change edge_server_lan1_dyn2 exited Exited (137)` 17:19:20.
- `controller_lan1.log`: `node_add script failed` 17:22:17; `cannot discover veth` 17:23:11; `reinstalling all flows (clearing 812 existing keys)` 17:19:33.
- `resource_stats.csv`: `server_count=0`, `T_db=0` at t≈+90–150 s.
- `decision_log_lan1.csv`: ComputeAlert t≈+24 s (class=compute, storage_score 0.059); storage activation t≈+45 s; `rejected_action=compute` t≈+215 s.
- `client_requests.csv`: episode served-basis 78.2 % (lan1) / 84.4 % (lan2), timeout 12.8 % / 13.8 %.
