# Experiment Plan — Dual VIP_SERVER Validation

**Status**: 📋 Planned — 2026-07-06
**Depends on**: [dual_vip_server_plan](../../../vip_routing/dual_vip_server_plan.md)
**Prerequisite**: Dual VIP_SERVER implementation complete (8 files modified, images rebuilt, network reconfigured)

## Intent

Validate that the dual VIP_SERVER implementation correctly routes each LAN's client-facing HTTP traffic through its local SDN controller under realistic golden-config load. Before this change, `osken_2` (LAN2) routed **zero** VIP_SERVER packets — all client traffic from both LANs hit `10.0.0.253` on LAN1. After the change, LAN2 clients must hit `10.0.1.253` locally and `osken_2` must independently exercise the `BACKEND_SELECTION_POLICY`.

This is a **validation run**, not a comparative experiment. The question is binary: **does the dual VIP work correctly under load?**

## Hypothesis / Expected Outcome

If the dual VIP_SERVER implementation is correct:

1. **`osken_2` routes VIP_SERVER traffic**: `osken_2` controller log contains `"vip server n2 packet-in"` entries — proving LAN2's controller exercises the backend-selection policy for the first time.
2. **LAN2 clients do not cross the WAN for VIP**: zero LAN2-sourced requests to `10.0.0.253` appear in controller logs or client_requests.csv. LAN2 clients reach `10.0.1.253` on their local subnet.
3. **LAN1 regressions absent**: `osken` continues to route LAN1 client traffic through `10.0.0.253` normally. No drop in LAN1 success rate or increase in LAN1 latency vs. pre-change expectations.
4. **Cross-LAN backend selection functional**: both controllers select backends from the shared `vip_server_pool`. Cross-LAN selections (e.g., `osken_2` routing a LAN2 client to a LAN1 edge server) produce correct DNAT/SNAT flows via the inter-LAN router.
5. **No controller errors**: zero unhandled Python tracebacks, zero `VIP_SERVER`-related warnings (pool empty, IP unknown) in either controller log.

## RQ Linkage

- **RQ2** ("does SDN controller co-location eliminate routing-plane coordination gaps?"): This experiment proves the **routing substrate** is operational — both controllers independently exercise the configured `BACKEND_SELECTION_POLICY`. Without this validation, any RQ2 comparative experiment (topology_host vs. topology_slowstart vs. topology_lifecycle) would be measuring N1-only behavior, making the comparison invalid.

## Independent Variable & Held-Constant Set

This is a single-configuration validation run. There is no independent variable.

| Parameter     | Value                                      | Reason                                                                                         |
| ------------- | ------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| Policy mode   | `topology_lifecycle` (default)           | The default policy with warm leases — the normal operating mode                               |
| Workload      | Canonical`phases.json` (7 phases, 1440s) | Exercises all load regimes: local, cross-region, hotspot, compute spike, cooldown              |
| Clients       | 48 per LAN (96 total)                      | Golden config sizing — realistic load volume                                                  |
| Content items | 6000                                       | Golden config dataset cardinality                                                              |
| Users         | 100                                        | Golden config                                                                                  |
| WAN RTT       | 260ms                                      | Golden config WAN curve                                                                        |
| Edge CPUs     | 0.30                                       | Golden config                                                                                  |
| Env override  | `current_state_integrated.env`           | Golden config — all mechanisms active (`SS_ENABLED=1`, storage reserve, compute elasticity) |
| Phases file   | `testing/phases.json`                    | Canonical integrated profile                                                                   |
| Fault plan    | Omitted                                    | No synthetic failure injection                                                                 |

All golden-config thresholds, cooldowns, and mechanism toggles are held constant. The only change from pre-dual-VIP state is the implementation itself.

## Run Matrix

Single run:

| #  | Label            | Policy                 | Env Override                     | Purpose                                      |
| -- | ---------------- | ---------------------- | -------------------------------- | -------------------------------------------- |
| V1 | `dual_vip_val` | `topology_lifecycle` | `current_state_integrated.env` | Validate dual VIP_SERVER under golden config |

No replicates needed — this is a pass/fail validation, not a statistical comparison. If V1 produces ambiguous evidence (e.g., `osken_2` routes <10 VIP packets total), escalate to a diagnostic re-run with increased logging before concluding.

## Run Configuration

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=dual_vip_val \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=260 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

- `--phases-config`: `testing/phases.json` — canonical 7-phase integrated workload (1440s total).
- `--clients-per-lan`: `48` (48 per LAN, 96 total).
- `--fault-plan`: **omitted**.
- **Source code must be synced to the cloud VM** before this run — the `sdn_controller/` tree is volume-mounted into the controller containers (`-v "$PWD":/workspace`), not baked into the Docker image. Controller images do **not** need rebuilding.
- **Network must be rebuilt** (`setup_network`) so containers pick up the updated `osken-controller.env` with `VIP_SERVER_N2_*` variables.
- `SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1`: operational efficiency — namespaces, data, and snapshot already exist from prior runs. Note: `SKIP_CLIENTS=1` skips client creation inside `run_experiment.sh`, but the Makefile target `create_clients` (called before `run_experiment`) still creates them.

### Phase Profile (canonical `phases.json`)

| # | Phase                      | Dur  | Rate  | Cross | Clients | Dominant Stress                                    |
| - | -------------------------- | ---- | ----- | ----- | ------- | -------------------------------------------------- |
| 1 | `baseline`               | 60s  | 1 r/s | 0%    | 50%     | Tier 0 control                                     |
| 2 | `storage_storm`          | 240s | 4 r/s | 90%   | 100%    | Storage locality + write/aggregation amplification |
| 3 | `tier1_hotspot`          | 180s | 5 r/s | 95%   | 100%    | Tier 1 hotspot response (bidirectional)            |
| 4 | `inter_hotspot_cooldown` | 300s | 1 r/s | 0%    | 10%     | Drain and recovery observation                     |
| 5 | `reverse_hotspot`        | 180s | 5 r/s | 95%   | 100%    | Tier 1 hotspot response (reverse direction)        |
| 6 | `compute_spike`          | 180s | 4 r/s | 5%    | 100%    | Feed-ranking compute pressure                      |
| 7 | `demand_drop`            | 300s | 1 r/s | 0%    | 10%     | Cooldown-gated scale-in observation                |

**Total**: 1440s (24 min).

## Focus & Evidence

**Primary focus**: Controller logs (`controller_lan1.log`, `controller_lan2.log`). These are THE pass/fail signal.

**Secondary focus**: `client_requests.csv`, OVS flow dumps.

| Artifact                        | Shows                                                                                            | Priority          |
| ------------------------------- | ------------------------------------------------------------------------------------------------ | ----------------- |
| `controller_lan1.log`         | `"vip server packet-in"` count for LAN1 (must be >0), no tracebacks                            | **Primary** |
| `controller_lan2.log`         | `"vip server n2 packet-in"` count for LAN2 (must be >0 for the first time ever), no tracebacks | **Primary** |
| `client_requests.csv`         | Per-phase per-LAN success rate, p95 latency; confirms LAN2 clients produce normal HTTP traffic   | Secondary         |
| `resource_stats.csv`          | `server_count`, `storage_count` — pool churn during elasticity phases                       | Secondary         |
| `container_events.csv`        | Edge server add/remove events — verifies pool membership changes during the run                 | Tertiary          |
| `elasticity_events.csv`       | Scale-up/down timing — confirms elasticity operates normally                                    | Tertiary          |
| `controller_env_snapshot.env` | Confirms`VIP_SERVER_N2_*` variables are present in the merged env                              | Tertiary          |
| `phases_snapshot.json`        | Confirms the canonical 7-phase profile ran                                                       | Tertiary          |

### OVS Flow Verification (post-run)

After the run completes (containers still running), dump flows on both bridges:

```bash
# N1 VIP punt rules on ovs-br0
docker exec ovs ovs-ofctl dump-flows ovs-br0 | grep "10.0.0.253"

# N2 VIP punt rules on ovs-br1
docker exec ovs ovs-ofctl dump-flows ovs-br1 | grep "10.0.1.253"
```

Both must show:

- ARP punt rule: `priority=100,arp,arp_tpa=10.0.x.253`
- IP punt rule: `priority=100,ip,ipv4_dst=10.0.x.253`

## Metrics & Success Criteria

The experiment succeeds when ALL criteria are met. This is a pass/fail gate.

### C1 — LAN2 Controller Exercises VIP_SERVER (BLOCKING)

| Check                                           | Method                                                                   | Threshold                                                                                       |
| ----------------------------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| `osken_2` processes VIP_SERVER packets        | `grep -c "vip server n2 packet-in" controller_lan2.log`                | **≥100** (48 LAN2 clients × 1440s at varying rates — 100 is a conservative floor)      |
| `osken_2` installs VIP_SERVER DNAT/SNAT flows | `grep -c "dnat/snat installed.*vip=10\.0\.1\.253" controller_lan2.log` | **≥10** (each new client+backend pair triggers one install; reuse is via existing flows) |

**Rationale**: Before this change, `osken_2` routed **zero** VIP_SERVER packets — the log contained no `"vip server"` entries at all. Any count >0 proves the change is active. The ≥100 threshold ensures it's not a fluke.

**If C1 fails**: The implementation is not active. Check:

1. `controller_env_snapshot.env` contains `VIP_SERVER_N2_IP=10.0.1.253`
2. OVS flow dump on `ovs-br1` shows the punt rule for `10.0.1.253`
3. Traffic generator received `--vip-lan2 10.0.1.253:5000` (check `run_experiment.sh` output header)

### C2 — LAN1 Controller Unchanged (BLOCKING)

| Check                                  | Method                                                    | Threshold                                                                                            |
| -------------------------------------- | --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `osken` processes VIP_SERVER packets | `grep -c "vip server packet-in" controller_lan1.log`    | **≥100** (regression check — LAN1 traffic must still work)                                   |
| `osken` shows no N2 VIP confusion    | `grep -c "vip server n2 packet-in" controller_lan1.log` | **0** (`osken` should NOT see N2 VIP traffic; if it does, LAN2 clients are crossing the WAN) |

**If C2 fails (osken shows 0 VIP_SERVER)**: LAN1 clients are not reaching the VIP. Regression in `traffic_generator.py` or `run_experiment.sh`.

**If C2 fails (osken shows N2 VIP traffic)**: LAN2 clients are crossing the WAN to reach `10.0.0.253` instead of using `10.0.1.253`. Check `traffic_generator.py` VIP dispatch logic.

### C3 — No Cross-WAN VIP Traffic from LAN2 Clients (BLOCKING)

| Check                          | Method                                                          | Threshold                                                                                |
| ------------------------------ | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| LAN2 clients do not hit N1 VIP | `grep -c "vip_server: client=10\.0\.1\." controller_lan1.log` | **0** (N1 controller log must NOT show LAN2-source VIP requests to `10.0.0.253`) |

**Rationale**: Before the change, ALL LAN2 clients hit `10.0.0.253` on LAN1 — the `osken` log was full of `vip_server: client=10.0.1.x -> vip=10.0.0.253`. After the change, LAN2 clients use `10.0.1.253` locally. Any residual cross-WAN VIP traffic indicates the traffic generator is still sending LAN2 clients to the wrong VIP.

### C4 — Control-Plane Health (BLOCKING)

| Check                             | Method                                                                                  | Threshold           |
| --------------------------------- | --------------------------------------------------------------------------------------- | ------------------- |
| No Python tracebacks              | `grep -c "Traceback (most recent call last)" controller_lan1.log controller_lan2.log` | **0** in both |
| No VIP_SERVER pool-empty warnings | `grep -c "vip_server: pool empty" controller_lan1.log controller_lan2.log`            | **0** in both |

**Note**: Pool-empty during `demand_drop` (10% client fraction) is acceptable if all dynamic edge servers have been scaled down and only the static one remains — but the static edge server should be in the pool. If pool-empty appears during high-client-fraction phases, it's a bug.

### C5 — Client Traffic Health (INFORMATIONAL)

| Check                            | Method                                                                                                     | Threshold                                                         |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Overall success rate             | `python3 source/scripts/tools/metrics_stats.py client_requests.csv` — `http_status=200` count / total | **≥95%**                                                   |
| LAN1 vs LAN2 success rate parity | Per-LAN success rate via`metrics_stats.py`                                                               | **LAN2 within 5pp of LAN1** (no systemic LAN2 disadvantage) |
| No phase with 0% success         | Per-phase per-LAN breakdown                                                                                | All phases >0% on both LANs                                       |

**If C5 fails**: Not necessarily a VIP_SERVER issue — could be workload saturation, elasticity timing, or WAN congestion. Diagnose but do not block the validation gate on C5 alone. The VIP routing correctness gates are C1–C4.

### C6 — OVS Punt Rules (INFORMATIONAL)

| Check                               | Method                                                                        | Threshold            |
| ----------------------------------- | ----------------------------------------------------------------------------- | -------------------- |
| ARP punt rule for N1 VIP on ovs-br0 | `docker exec ovs ovs-ofctl dump-flows ovs-br0 \| grep "arp_tpa=10.0.0.253"`  | 1 rule, priority=100 |
| IP punt rule for N1 VIP on ovs-br0  | `docker exec ovs ovs-ofctl dump-flows ovs-br0 \| grep "ipv4_dst=10.0.0.253"` | 1 rule, priority=100 |
| ARP punt rule for N2 VIP on ovs-br1 | `docker exec ovs ovs-ofctl dump-flows ovs-br1 \| grep "arp_tpa=10.0.1.253"`  | 1 rule, priority=100 |
| IP punt rule for N2 VIP on ovs-br1  | `docker exec ovs ovs-ofctl dump-flows ovs-br1 \| grep "ipv4_dst=10.0.1.253"` | 1 rule, priority=100 |

**If C6 fails**: The `_iter_vip_bindings()` change did not propagate to punt rule installation. Check `ingress.py` edits.

## Checkpoints

In-run triggers the operator may observe. All are report-only — no runner action needed unless a BLOCKING criterion is at risk.

| Trigger                       | Question                                                    | Evidence                                                                                                             |
| ----------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| End of`baseline` (~60s)     | Are both controllers routing VIP_SERVER?                    | `grep "vip server" controller_lan1.log controller_lan2.log` — both should show entries                            |
| Mid`storage_storm` (~180s)  | Is`osken_2` still routing under cross-region load?        | `grep -c "vip server n2" controller_lan2.log` — count should be growing                                           |
| Mid`tier1_hotspot` (~350s)  | Is pool churn (elasticity) causing any VIP_SERVER warnings? | `grep "pool empty\|IP unknown" controller_lan*.log` — should be 0                                                  |
| Mid`compute_spike` (~1200s) | Are both controllers routing under compute-heavy load?      | Both controller logs still show active VIP dispatch                                                                  |
| End of run (~1440s)           | Final dispatch counts                                       | `grep -c "vip server packet-in" controller_lan1.log` and `grep -c "vip server n2 packet-in" controller_lan2.log` |

## Validity Threats & Limitations

| Threat                                       | Mitigation                                                                                                                                                                                                                                                                                                |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Single run, no replicate**           | This is a pass/fail validation, not a statistical comparison. A second run adds no information unless the first produces borderline evidence. If C1 count is 5–99 (below threshold but >0), re-run with`--run-label dual_vip_val_r2` to confirm.                                                       |
| **Host state drift**                   | No host reboot mandated. The golden config has been run many times on this host; state accumulation is a known quantity.                                                                                                                                                                                  |
| **Observer effect**                    | Controller logs are captured continuously (`docker logs -f`). No additional instrumentation is added — the existing log lines (`"vip server packet-in"`, `"vip server n2 packet-in"`) are the evidence.                                                                                            |
| **Can't compare pre/post in same run** | The pre-change state no longer exists in the codebase. The "before" baseline is the known fact that`osken_2` previously routed 0 VIP_SERVER packets. The ≥100 threshold is conservative relative to 0.                                                                                                 |
| **Pool churn interaction**             | The shared`vip_server_pool` is rebuilt every topology tick from `_server_macs`. During elasticity scale-up/down, pool membership changes. If VIP_SERVER warnings appear during churn phases, it may indicate a race between pool rebuild and warm-lease registration — not a VIP routing bug per se. |

## Artifact Contract

Standard run-folder layout per `docs/operation/testing/testing_overview.md`:

```
metrics/<batch_dir>/<run_id>/
├── client_requests.csv
├── resource_stats.csv
├── resource_stats_debug.csv
├── per_node_stats.csv
├── controller_lan1.log
├── controller_lan2.log
├── controller_env_snapshot.env
├── phases_snapshot.json
├── container_events.csv
├── elasticity_events.csv
├── policy_state.csv
├── current_phase.txt
├── service_logs/
└── controller_stats.csv
```

**Experiment-specific expectations** (no additional files):

| Expected in controller_lan2.log                                 | Expected in controller_lan1.log                                 |
| --------------------------------------------------------------- | --------------------------------------------------------------- |
| `"vip server n2 packet-in"` (≥100)                           | `"vip server packet-in"` (≥100)                              |
| `"vip_server: client=10.0.1.x -> vip=10.0.1.253 -> real=..."` | `"vip_server: client=10.0.0.x -> vip=10.0.0.253 -> real=..."` |
| `"dnat/snat installed: vip=10.0.1.253 -> real=..."` (≥10)    | `"dnat/snat installed: vip=10.0.0.253 -> real=..."` (≥10)    |
| Zero`"vip_server: pool empty"`                                | Zero`"vip_server: pool empty"`                                |
| Zero`"Traceback"`                                             | Zero`"Traceback"`                                             |
| Zero`"vip server packet-in"` for dst_ip `10.0.0.253`        | Zero`"vip server n2 packet-in"`                               |

**Post-run analysis**: No `analysis/` outputs expected. The validation verdict is determined by grepping controller logs against the C1–C6 criteria above. `python3 source/scripts/tools/metrics_stats.py` is used for C5 (client traffic health) only.

## Implementation Prerequisites (verify before launch)

- [ ] Dual VIP_SERVER code changes (A1–A4) merged and images rebuilt
- [ ] `osken-controller.env` contains `VIP_SERVER_N2_IP=10.0.1.253` and `VIP_SERVER_N2_MAC=aa:bb:cc:dd:ee:04`
- [ ] `traffic_generator.py` uses per-LAN VIP (`--vip-lan1`/`--vip-lan2`)
- [ ] `run_experiment.sh` passes both `--vip-lan1` and `--vip-lan2`
- [ ] Network rebuilt with updated env: `make setup_network OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env`
- [ ] `docker exec osken env | grep VIP_SERVER_N2` returns the N2 IP and MAC
- [ ] `docker exec osken_2 env | grep VIP_SERVER_N2` returns the N2 IP and MAC
