# RQ2 v4 — P2.1: Hashing request kind (spec + implementation)

> **Status:** 2026-10-11 · implemented (P2.1) + selftest green; P2.2 build +
> P2.3 calibration pending.
> **Purpose (D3, F1):** give RQ2 an **honest compute press** — a workload whose
> per-request CPU cost is explicit, configurable and dominant, replacing the
> history-dependent `service_pressure` stressor whose apparent knee (v3) was
> inflated by the pre-fix platform's self-harm. Without it there is no
> compute-bound episode (gate (c) at 2.5 is dead — see
> [`rq2v4_p1_05_verification.md`](rq2v4_p1_05_verification.md) F1).
> **Companion:** [`rq2v4_plan.md`](rq2v4_plan.md) P2, [`preparation.md`](preparation.md) D3.

## 1. Contract

### 1.1 Edge endpoint — `GET /compute/hash?nonce=<string>`

- **CPU-bound hashing, no database access.** The handler runs
  `HASH_WORK_FACTOR` chained SHA-256 rounds over the nonce
  (`digest_0 = sha256(nonce)`; `digest_{i+1} = sha256(digest_i)`; total
  `rounds + 1` SHA-256 calls), then returns
  `{"rounds": N, "nonce": ..., "digest": <first 16 hex chars of the final digest>}`.
- **`nonce` is required** (400 `BadRequest` when absent) — the digest stays a
  per-request correctness witness: same nonce + rounds ⇒ same digest
  (deterministic), different nonce ⇒ different digest (defeats caching).
- Registered in `monitoring_workload_routes.py` beside the other workload
  routes; counted as a normal user request (not in `SKIP_COUNTING_PATHS`) and
  **staged into the edge-local request buffer** like `content_lookup` /
  `feed_ranking`, so `/service_pressure`'s summary and `request_kind_counts`
  include `hash_challenge` during a hash-only episode.
- Pure function `hash_chain(nonce, rounds)` lives in `compute.py` (already
  imports `hashlib`; used by the selftest).

### 1.2 Knob — `HASH_WORK_FACTOR`

- Env var on the edge container, integer SHA-256 rounds.
  **Single default source of truth: `edge_server_config.HASH_WORK_FACTOR_DEFAULT`
  = 25000** — measured (P2.1 selftest, host) ~1.04 µs/round ⇒ ≈ 26 ms/request
  (re-measure in-container at P2.3; re-seat the default there if the split
  against the ~2.3–2.6 ms non-handler overhead is unfavourable — at 26 ms the
  hash is already ~10× the overhead, well inside the target).
- Carrier mechanics (one knob at the launcher call; nothing defaults twice):
  - **two lift points make the guarantee invocation-independent.** The
    launcher lifts a caller export (or a merged-env value) into the make var;
    `build_network_setup.sh` additionally lifts `HASH_WORK_FACTOR` from the
    (merged) controller env file into the static-edge launchers' environment.
    So a value placed **only** in the canonical override reaches the static
    edges via the setup-script lift and the dynamic spawns via the controller
    reading the same file — under both documented invocation paths (launcher
    and direct `sudo make`).
  - when set, one resolved value is forwarded as a make var (→ static edges;
    the network scripts forward only when set) **and** is present in the
    merged controller override (→ controller env → dynamic spawns via
    `compute_node_manager`, which also forwards only when set);
  - unset everywhere ⇒ every container falls back to the one image default
    (`HASH_WORK_FACTOR_DEFAULT`).
- Surfaced in `EdgeServerConfig` (`hash_work_factor`), following the
  `FEED_INTEGRITY_WORK_FACTOR` precedent.
- **No per-request override** — cost changes require a re-deploy with a new
  value; the calibration ladder varies **rate**, not cost.
- **Freeze procedure (P2.3/P4), exact:** to change the value, either
  (a) export `HASH_WORK_FACTOR` in the shell before calling the launcher, or
  (b) place it in the canonical override and let the launcher lift it; both
  are equivalent (see below). To keep the image default, set nothing anywhere.
  Never hand-edit one carrier only — the launcher lift makes both carriers
  agree, and that is the enforcement point.

### 1.3 Generator kind — `hash_challenge`

- Mix key usable in `phases.json`: `"mix": {"hash_challenge": 1.0}`.
  **Mix weights must sum to 1.0** (the selector does not normalise — see
  `traffic_generator.md` Phase Schema); P2.3/P3 mix authoring uses normalised
  weights.
- `pick_target`: returns `{"content_id": "", "user_id": "", "target_region": <home>,
  "nonce": <16 hex chars>}` — fresh random nonce per request.
- `build_url`: `http://<vip>/compute/hash?nonce=<nonce>` (GET).
- Prompt-only: the mix is complete for this kind.

## 2. Why these choices

- **SHA-256 chain, not sleep/FS/allocation:** pure CPU, no I/O, no DB, no
  cache — the press is exactly the work factor, independent of data history
  (the `service_pressure` defect fixed at the root). Result returned (not
  discarded) so the cost cannot be optimised away by dead-code elimination.
- **Nonce-bearing GET:** request-bound witness + trivially cache-busting; the
  open-loop driver's fresh-TCP-per-request model stays untouched.
- **Work factor in env, rate in the plan:** the experiment varies demand
  (rate), not per-request work; work factor is a frozen platform constant like
  the CPU quotas.
- **Default 25000 rounds:** measured ≈ 1.04 µs/round on the host ⇒
  ≈ 26 ms/request — ≈ 10× the observed per-request non-handler overhead
  (2.3–2.6 ms at 0.15 core, autopsy #1), so the hash dominates the cost
  split by construction. Capacity implication at the campaign quota:
  150 ms/s ÷ 26 ms ≈ **5–6 rps/lane**, i.e. the campaign press sits at a
  low rate (~0.3 per client unit) where connection-level effects are a
  small fraction of the knee — the F2 confound is structurally excluded.
  P2.3 re-measures in-container and re-seats if needed.

## 3. Files touched

| # | File | Change |
| --- | --- | --- |
| 1 | `source/docker/edge_server/source/compute.py` | `hash_chain(nonce, rounds)` pure function |
| 2 | `source/docker/edge_server/source/monitoring_workload_routes.py` | `/compute/hash` route |
| 3 | `source/docker/edge_server/source/edge_server_config.py` | `hash_work_factor` (env `HASH_WORK_FACTOR`, default 25000) |
| 4 | `source/scripts/testing/traffic_generator.py` | `hash_challenge` in `pick_target` + `build_url` |
| 5 | `source/scripts/network/build_network_1.sh` | `-e HASH_WORK_FACTOR` (static edge) |
| 6 | `source/scripts/network/build_network_2.sh` | `-e HASH_WORK_FACTOR` (static edge) |
| 7 | `source/sdn_controller/elasticity/compute_node_manager.py` | forward `HASH_WORK_FACTOR` (dynamic edge) |
| 8 | `source/scripts/testing/rq2v4_p2_01_hash_kind_selftest.py` | new selftest (§4) |
| 9 | `docs/operation/testing/testing_workloads.md` | demand-model table + kinds (P2.4) |

## 4. P2.1 selftest (local, host Python) — GREEN 2026-10-11

`source/scripts/testing/rq2v4_p2_01_hash_kind_selftest.py`:
- `hash_chain` determinism (same nonce + rounds ⇒ same digest), nonce and
  rounds sensitivity, full 32-byte digest.
- Cost scaling: monotonic; per-round cost guarded into the plausible band
  (0.1–5 µs — catches unit/label regressions); **measured ≈ 1.0–1.5 ms/1k
  rounds ⇒ default `HASH_WORK_FACTOR_DEFAULT` (25000) ≈ 26–35 ms/request**
  (host; P2.3 re-measures in-container).
- Generator: 16-hex fresh nonce per request; URL targets
  `/compute/hash?nonce=…`; weighted selection is exercised with the new kind
  among existing ones (400 draws).
- Config: `HASH_WORK_FACTOR` env is read; the default comes from the module
  constant (real `EdgeServerConfig.from_env()` assertions; env restored
  afterwards).

## 5. P2.2/P2.3 notes

- **Evidence source for the cost split:** controller-side per-request
  telemetry derives `request_type` from the HTTP method only (all GETs are
  "read"), so `hash_challenge` is not distinguishable there. The cost-split
  evidence comes from the **client CSV** (`endpoint` column + `latency_s`)
  and the edge's `T_proc`/CPU in the window logs — use those in P2.3.

- P2.2 combines this with the P1 fix in the build (edge image changes now —
  both edge and `local_state_server` images rebuilt; the controller stays
  checkout-synced).
- P2.3 ladder starts **above 2.5** (F1): bracket ≈ 3.0–4.0 at the seated work
  factor; gates re-anchored (see `rq2v4_p1_05_verification.md` §5 and the plan
  P2.3): (i) press gate — `none` locks (p95 ≥ 1 s in ≥ 80 % of episode
  windows, completion degrades); (ii) relief gate — same-shape `comp`
  recovers both sides and stays recovered; (iii) margin; (iv) specificity —
  `stor` does not clear the compute lock; (v) hash cost dominates the
  pre-dispatch/connection overhead (cost split reported). All calibration runs
  under strict host quiescence (F2 protocol).
