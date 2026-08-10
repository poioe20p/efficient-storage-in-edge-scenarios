# RQ2 v3 — Analysis Focus

Analysis priorities for the v3 campaign at the storage-bind locked config
(tag `rq2-v3-campaign-20260808`). **NOT launched** — focus is pre-registered.

## 1. Primary claim — storage scale-up benefit (B2)

For each data-bound cell (`cf_db`, `sf_db`, `ba_db`), quantify the user-visible
benefit of the first storage add:

- **Bind** (pre-add): `T_db` mean and p95 rise vs baseline; storage CPU rises
  toward the 0.15-core cap; per-node storage CPU shows the bottleneck member.
- **Relief** (post-add): `T_db` drops, timeouts fall to ~0, storage CPU per node
  drops. Report the pre/post window p50/p95 (SG-4 style) and the timeout
  trajectory (30 s buckets) — the F4a/F4b signature is: elevated p50/p95 +
  timeouts pre-add → sharp drop ~60–120 s after the replica is ready.
- **Pinned windows (fix 7):** pre-add = episode start → first storage add
  (`container_events` `added`); post-add = first add **ready** (`node_ready`
  log) + 120 s → episode end (fallback ready = add + 40 s). Report p50/p95 per
  window + the 30 s-bucket trajectory.
- **Scale-down (fix 3):** ≥ 1 storage teardown in `demand_drop` (elasticity
  bidirectional); record scale-down timing vs load drop.
- **Pool diagnostic (fix 1):** P3 (pool 12) outcome — if pool 12 also
  binds → relieves, pool 48 is not required and the config can simplify;
  otherwise pool 48 is the documented serving-path capacity mechanism.
- **Spread**: `client_requests.backend_id` distribution must show ≥ 2 active
  backends per LAN (the dynamic secondary carries a material share); per-node
  storage CPU must show load on primary **and** secondary.

Evidence artifact per run: bind/relief table + 30 s-bucket latency trajectory +
backend spread (see `tools/rq2_probe_gate.py`, `temp/temp_rq2_probe_analyze.sh`
pattern, `temp/temp_rq2_f4a_relief.sh`).

## 2. Compute scale-up benefit (B1)

For each compute-bound cell (`cf_cb`, `sf_cb`, `ba_cb`): static-edge CPU before
vs after the first compute add and the latency/timeout trajectory. Expected
(reproduced on cb_1/cb_2): static-edge CPU 66–81 % → 47–62 %, timeouts → 0.

## 3. Action-selection axis

`bottleneck_aware` must classify and scale the correct tier:
- `ba_cb`: compute fires (edge CPU rising), storage stays below threshold.
- `ba_db`: storage fires (T_db/storage CPU rising), compute stays below
  threshold.
Report `storage_fired`/`compute_fired` counts and the classification margin.

## 4. Secondary observations

- Scale-down/recovery in `demand_drop` (storage/compute teardown after load
  drop) — elasticity bidirectional evidence.
- LAN symmetry (F2): per-LAN spawns and storage CPU ≤ 3× asymmetry.
- Cost side: spawn counts, resource deltas (node-minutes) per arm.

## 5. Claim shaping (open-ended)

No single signal is pre-privileged. The claim follows the mechanism relation
— *worse trigger awareness ⇒ worse user service quality* — and the thesis is
shaped from whichever signals the data shows improve/decline when the correct
tier scales (latency, timeout, throughput, CPU), including results beyond
pre-registered expectations. Wrong-action cells are read for their designed
degradation. Pool-48 fan-out is framed as the serving-path capacity mechanism
(documented in [`storage_bind_probe_record.md`](storage_bind_probe_record.md)),
not as a separate claim.
