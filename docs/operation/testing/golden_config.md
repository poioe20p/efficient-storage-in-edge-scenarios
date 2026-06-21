# Golden Configuration

The canonical infrastructure sizing, mechanism toggles, and trigger thresholds
that exercise Tier 2 storage reserve, Tier 1 selective-sync, compute elasticity,
and conntrack VIP_DATA routing. These values were confirmed across stability
experiments spanning 2026-06-05 to 2026-06-10.

All toggles and thresholds are encoded in
[`current_state_integrated.env`](../../../source/scripts/testing/controller_env_overrides/current_state_integrated.env).

**Provenance**: each value was determined by a dedicated stability experiment.
Full results are in [`experiment/stability/`](experiment/stability/).

**⚠️ The workload shape is NOT part of this configuration.** The phases file
must be chosen or designed for each experiment's specific intent — different
questions need different demand profiles. The stability experiments that
established these thresholds used a 10-phase integrated workload, but that
workload is an *input to the tuning process*, not a default to be reused
blindly. See [Workload Sizing](#workload-sizing) below.

---

## Workload Sizing

| Parameter | Value | Determined By |
|---|---|---|
| `CLIENTS` | **8** | [`storage_reserve_load_sweep`](experiment/stability/storage_reserve_load_sweep/results.md): c08 stable (0.0–1.2% failure), c10 overloads edge server (~100 req/s ceiling). 8 is the highest stable count. |
| `DEVICES` | **600** | Dataset cardinality. Held constant in all stability experiments. Drives Tier 1 hot-set size and dashboard query diversity. |
| `NODES` | **100** | Infrastructure scale. Held constant in all stability experiments. |

### Phases File — No Default

**There is no canonical phases file.** The workload shape — which phases exist,
their durations, request rates, mixes, cross-region ratios, and hotspot
directions — must be evaluated and adapted to each experiment's intent.

The stability experiments that produced these golden thresholds used a 10-phase
integrated workload (`local_moderate` → `storage_stress` →
`cross_region_hotspot` → `inter_hotspot_cooldown` → `reverse_hotspot` →
`compute_ramp` → `compute_spike` → `sustained_plateau` → `demand_drop` →
`idle`, ~28 min). That workload was designed to exercise all four mechanisms
sequentially for tuning purposes. It is not appropriate for every experiment:

- **RQ1 (delivery cadence)**: needs a workload that produces enough scaling
  events for statistical reaction-latency comparison across modes. Both
  hotspot directions should be present so breaches occur on both LANs.
- **Storage reserve validation**: used a dedicated probe workload with 90%
  `device_status` mix and a `sustained_use` phase to verify reserve carries
  traffic.
- **Tier 1 activation**: used a bidirectional hotspot profile with compute
  and storage elasticity disabled to isolate Tier 1 behavior.

Before designing or launching an experiment, evaluate: which mechanisms does
this experiment need to exercise? How many scaling events are needed for
statistical power? Is LAN symmetry required, or is unidirectional load
acceptable? Choose or create the phases file that answers those questions.

## Mechanism Toggles

| Parameter | Value | Purpose |
|---|---|---|
| `STORAGE_PERSISTENT_RESERVE_ENABLED` | **1** | Tier 2 storage reserve enabled |
| `SS_ENABLED` | **1** | Tier 1 selective-sync enabled |
| `MAX_DYNAMIC_STORAGE` | **5** | Up to 5 dynamic storage nodes per LAN |
| `MAX_DYNAMIC_COMPUTE` | **6** | Up to 6 dynamic compute nodes across LANs |

## Storage Trigger Bundle

The activation boundary is $0.12 < \tau \leq 0.15$.
**t12 (0.12)** is the highest threshold that still activates the reserve under
the integrated workload — avoids over-sensitivity while ensuring the mechanism
fires. Determined by
[`storage_reserve_threshold_sweep`](experiment/stability/storage_reserve_threshold_sweep/results.md):
t08 cycles, t12 stable, t20 never activates.

| Parameter | Value | Notes |
|---|---|---|
| `SCALEUP_STORAGE_BASE_THRESHOLD` | **0.12** | Highest threshold that still activates |
| `SCALEUP_W_STORAGE_CPU` | 0.60 | Default |
| `SCALEUP_W_T_DB` | 0.40 | Default |
| `SCALEUP_STORAGE_CPU_FLOOR` | 1.5 | Default |
| `SCALEUP_STORAGE_CPU_SPAN` | 5 | Default |
| `SCALEUP_T_DB_FLOOR` | 60 | Default |
| `SCALEUP_T_DB_SPAN` | 250 | Default |
| `SCALEUP_STORAGE_REQUIRED` | 2 | Consecutive windows for trigger |
| `SCALEUP_STORAGE_WINDOW_SIZE` | 5 | Sliding window |
| `SCALEUP_STORAGE_COOLDOWN_S` | **120** | Default |

## Compute Trigger Bundle

The **cooldown is the load-bearing value**. Determined by
[`variance_reduction`](experiment/stability/variance_reduction/results.md):
at 120 s, scale-down removes nodes during peak load (47–88 % failure in
compute phases). At **180 s**, nodes survive the storage → compute phase
transition — compute phases drop to 0.04–0.63 %, overall 0.23 %.

| Parameter | Value | Why Not Default |
|---|---|---|
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | **0.20** | Lowered from 0.45 — needed for integrated workload where compute load is dashboard-heavy but distributed |
| `SCALEUP_CPU_FLOOR` | **3** | Lowered from 5 |
| `SCALEUP_T_PROC_FLOOR` | **15** | Lowered from 20 |
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | **180** | ⬆ Raised from 120. **The single most important value.** |
| `SCALE_DOWN_COMPUTE_REQUIRED` | **9** | Consecutive below-threshold windows |

## Infrastructure Fixes (Deployed, Not Tuneable)

These are code-level fixes confirmed by dedicated experiments — they are part of
the standard deployment, not configuration knobs:

| Fix | Experiment | Effect |
|---|---|---|
| Conntrack VIP_DATA routing | [`conntrack_routing`](experiment/stability/conntrack_routing/results.md) | Eliminates stale-rule → AutoReconnect cascade. Compute: 56–65 % → 1.4 %. Zero epoch rotations. |
| Cross-LAN veth TX queue (`txqueuelen=10000`) | [`wan_http0_root_cause`](experiment/stability/wan_http0_root_cause/results.md) | Eliminates TCP collapse on LAN2. 426× improvement. R2: 0.05 % overall. |

## Canonical Launch Command

The env override and sizing parameters are fixed. The phases file is always
experiment-specific — replace `<phases_file>` with the file chosen for the
experiment's intent.

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=<label> \
  PHASES_CONFIG=testing/<phases_file> \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```
