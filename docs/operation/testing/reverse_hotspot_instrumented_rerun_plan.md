# Plan - Reverse Hotspot Instrumented Probe And Recovery Hardening

**Status:** Proposed
**Scope:** reverse-hotspot failure investigation and the gate before any
frontier rerun
**Primary evidence:**

- [rep2 summary](../../../source/scripts/testing/metrics/20260524_203324_storage_trigger_ws600_rep2/run_summary.md)
- [rep3 summary](../../../source/scripts/testing/metrics/20260524_212327_storage_trigger_ws600_rep3/run_summary.md)
- [request-lease runtime](../../../source/docker/edge_server/source/vip_data_mongo_runtime.py)
- [monitoring workload routes](../../../source/docker/edge_server/source/monitoring_workload_routes.py)

---

## 1. Problem Summary

The storage-trigger profile already crosses the natural storage elasticity
boundary. The current blocker is not "increase load until storage finally
scales." The blocker is that `reverse_hotspot` drives a severe instability
with two distinct failure stages:

- `lan1` starts failing immediately with `503` because requests that need
  `lan2` data hit repeated recovery-epoch failure and then fail fast behind the
  breaker.
- `lan2` shifts later into `http_status=0` timeouts, and the earliest checked
  controller slice still shows ordinary backend selection rather than an
  explicit empty-pool or drop condition.

That means the next step must answer the narrow open question first: where do
the later `lan2` timeouts occur in the dataplane or response path?

---

## 2. Findings That Drive The Plan

| Finding | Evidence | Implication |
| --- | --- | --- |
| `lan2` repeatedly rotates into recovery epochs under reverse hotspot. | `rep3` shows `11 -> 12`, `17 -> 18`, and later `19 -> 20` recovery rotations in service logs. | The failure is recurring epoch churn, not a single spike. |
| The first `lan1` failures are app-level and recovery-linked. | `rep3` shows `ServerSelectionTimeoutError` on `10.0.1.252`, then `failure_terminal`, then many `CircuitOpenError exc=circuit open for lan2`. | The early `503` regime is already explained by the current request-lease and breaker logic. |
| The later `lan2` timeout regime is different. | Around the first `lan2` timeout, `rep3` still has many `lan2` `200`s while `lan1` is already dominated by `503`; later `lan2` flips to sustained `0` responses. | The timeout path needs dataplane evidence, not more aggregate summaries. |
| The earliest checked controller slice still looks normal. | At `2026-05-24 21:42:50`, [controller_lan2.log](../../../source/scripts/testing/metrics/20260524_212327_storage_trigger_ws600_rep3/controller_lan2.log) still selects `real=10.0.1.7` and installs `dnat/snat`. | The first timeout second is not yet explained by obvious pool exhaustion or controller-side drop logging. |

---

## 3. Recommended Execution Order

### 3.1 Run one unchanged instrumented probe

Use one unchanged run before any hardening so the failure shape stays directly
comparable with `rep2` and `rep3`.

**Run label:** `storage_trigger_ws600_probe_dataplane3`

**Keep unchanged:**

- `PHASES_CONFIG=testing/phases_experiment_storage_trigger.json`
- `CLIENTS=3`
- `DEVICES=600`
- `NODES=100`
- `SKIP_CLIENTS=1`
- `SKIP_SEED=1`
- `SKIP_SNAPSHOT=1`

**Execution order:**

Bring up the reusable environment first, then preflight the helper, then
launch the unchanged experiment run with the setup steps skipped inside
`run_experiment.sh`, detect the new run folder, and arm the helper against
that absolute run path.

**Environment bringup:**

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios; sudo -n make -C source/scripts setup_network create_clients setup_test_data CLIENTS=3 DEVICES=600 NODES=100"
```

**Experiment launch after helper preflight:**

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios; sudo -n make -C source/scripts run_experiment RUN_LABEL=storage_trigger_ws600_probe_dataplane3 PHASES_CONFIG=testing/phases_experiment_storage_trigger.json CLIENTS=3 DEVICES=600 NODES=100 SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1"
```

### 3.2 Capture a debug bundle during `reverse_hotspot`

The objective is to capture the first 210 seconds of `reverse_hotspot`. That
window covers the earlier `rep2` timeout onset and the later `rep3` timeout
onset without needing a longer full-phase packet capture.

Use the versioned helper
[capture_reverse_hotspot_probe.sh](../../../source/scripts/testing/capture_reverse_hotspot_probe.sh)
instead of an inline SSH heredoc. The helper writes only to a user-owned
capture root outside the active run folder, preserves runtime substitutions at
execution time, and can fail fast in preflight if a required dependency is not
available.

For the next unchanged recurrence probe, the only approved behavior delta is a
broader default packet-capture scope in the helper itself. The default
namespace-side filter now keeps the client-facing `VIP_SERVER` traffic and the
normal and recovery `lan2` `VIP_DATA` targets, while the host-side filter now
captures the `lan2` Mongo plane instead of pinning to one guessed backend IP.
The workload shape, controller policy, and runtime code stay unchanged.

Remote prerequisites that must be present before the rerun:

- `tcpdump`
- `conntrack`
- `docker`
- `ovs-ofctl` reachable through `docker exec ovs ...`
- either non-interactive `sudo` for `tcpdump`, `conntrack`, and
  `ip netns exec`, or a one-time interactive `sudo` launch of the helper as
  root

Preflight the capture environment on `cloud-vm` after the environment bringup.
This check is the canonical answer to "what else still needs to be installed"
versus "what only appears after `setup_network` and `create_clients`":

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios; sudo -n make -C source/scripts probe_capture_preflight PROBE_CAPTURE_ROOT=/home/testop/probe_captures/preflight_reverse_hotspot_probe"
```

If preflight fails, install or enable the missing dependency before the rerun.
Do not launch another unchanged probe until the preflight succeeds.

On the current `cloud-vm`, the command inventory already confirms that
`tcpdump`, `conntrack`, `docker`, `ip`, `sudo`, and `timeout` are installed.
The successful `storage_trigger_ws600_probe_dataplane2` rerun showed that no
additional package installation was needed. The working operational path is to
launch the helper through the repository Makefile so it inherits the already
working `sudo -n make -C source/scripts ...` path. For this recurrence probe,
do not replace that path with an ad hoc interactive helper launch unless the
runner first confirms that the Makefile-based preflight has regressed.

After the experiment is launched and the new run folder exists, arm the helper
as a detached process. Keep the run shape unchanged, but use a new label for
the corrected rerun so the artifacts are distinct from the failed
instrumentation attempt.

Use the repository Makefile target with an absolute run path once the new run
folder exists:

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios; sudo -n make -C source/scripts probe_capture_launch PROBE_CAPTURE_RUN_DIR=/home/testop/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/<run_id> PROBE_CAPTURE_ROOT=/home/testop/probe_captures/<run_id>"
```

Use an absolute `PROBE_CAPTURE_RUN_DIR`. The first corrected rerun showed that
repo-root-relative paths can silently point the helper at the wrong phase file
when the target executes from `source/scripts`.

The successful `storage_trigger_ws600_probe_dataplane2` rerun established the
launch pattern that the next recurrence probe should follow with the new label
`storage_trigger_ws600_probe_dataplane3`:

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios; sudo -n make -C source/scripts setup_network create_clients setup_test_data CLIENTS=3 DEVICES=600 NODES=100"
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios; sudo -n make -C source/scripts probe_capture_preflight PROBE_CAPTURE_ROOT=/home/testop/probe_captures/preflight_reverse_hotspot_probe"
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios; sudo -n make -C source/scripts run_experiment RUN_LABEL=storage_trigger_ws600_probe_dataplane3 PHASES_CONFIG=testing/phases_experiment_storage_trigger.json CLIENTS=3 DEVICES=600 NODES=100 SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1"
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios; sudo -n make -C source/scripts probe_capture_launch PROBE_CAPTURE_RUN_DIR=/home/testop/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/<run_id> PROBE_CAPTURE_ROOT=/home/testop/probe_captures/<run_id>"
```

The helper itself performs the following steps:

- validate command availability and `sudo -n` coverage,
- confirm the client namespace and OVS container exist,
- wait for `current_phase.txt` to reach `reverse_hotspot`,
- start the client-side and host-side `tcpdump` captures,
- snapshot OVS flows and conntrack state every 5 seconds for 210 seconds,
- write `helper.log` and `run_dir.txt` into the capture root.

Validate the armed helper before leaving it unattended:

```bash
ssh cloud-vm "tail -n 20 \"\$HOME/probe_captures/<run_id>/helper.log\""
```

The expected early log lines are:

- `preflight ok`
- `helper started`
- `watching phase marker ...`

For the successful corrected rerun, the helper also logged:

- `phase=reverse_hotspot`
- `reverse_hotspot reached`
- `debug capture complete`

Before the run completes, the log must also contain:

- `reverse_hotspot reached`
- `debug capture complete`

If those lines do not appear, treat the instrumentation as failed even if the
workload run itself completes.

### 3.3 Retain all probe artifacts

Keep the normal run artifacts plus the new debug bundle together:

- `resource_stats.csv`
- `per_node_stats.csv` when present
- `container_events.csv`
- `controller_lan1.log`
- `controller_lan2.log`
- `service_logs/`
- `debug_bundle/flows/`
- `debug_bundle/conntrack/`
- `debug_bundle/pcap/`

Do not trim or delete probe artifacts until:

1. the run summary exists,
2. the reduced retained evidence has been verified locally, and
3. log deletion has been explicitly confirmed.

---

## 4. Probe Questions

The probe is successful if it answers at least one of these questions with
retained evidence:

1. Do `lan2` client SYNs continue while return packets disappear?
2. Do OVS flow snapshots remain aligned with controller intent during the first
   timeout window?
3. Does conntrack state show repeated resets, expiry churn, or another obvious
   transport-level failure signature for the VIP or backend path?
4. Does the broadened host-side `lan2` Mongo-plane capture show replies from
  whichever `n2` backend is actually selected while the client-side capture
  still sees missing or delayed return traffic?

If the probe cannot answer those, do not widen load. Add more instrumentation
first.

---

## 5. Recovery Hardening Slice After The Probe

After the probe, keep the hardening scope narrow and local to the recovery
path. The expected owner file is
[vip_data_mongo_runtime.py](../../../source/docker/edge_server/source/vip_data_mongo_runtime.py).

### 5.1 Recovery-epoch stickiness

Do not rotate from recovery back to normal on `recovery_expired` alone while
the breaker is still open or before one successful probe against the recovery
path has completed. The current churn suggests the timer-only return to normal
is too eager under sustained asymmetric demand.

### 5.2 Breaker policy review

Recheck whether the current fail-fast window is too aggressive for this failure
shape. The early `503` regime is intentional protection, but the current fixed
open interval may be stretching a short connectivity miss into a broader
synthetic outage. An adaptive micro-breaker is the preferred direction if the
probe still shows backend reachability returning quickly.

### 5.3 Logging enrichment

Before the next rerun after hardening, make sure the runtime logs:

- explicit breaker state transitions with the LAN and epoch id,
- the reason for every `recovery_expired` rotation,
- whether the next epoch adopted after recovery was chosen by timer expiry or
  by a successful request-path probe.

Those additions make the next recurrence run easier to interpret without having
to keep the full raw logs indefinitely.

---

## 6. Post-Hardening Reruns

Do not jump straight to the frontier. First rerun the same storage-trigger
profile after the hardening change.

Suggested labels:

- `storage_trigger_ws600_recovery_hardened_rep1`
- `storage_trigger_ws600_recovery_hardened_rep2`

Keep the workload shape fixed so the comparison stays anchored to `rep2` and
`rep3`.

Reopen `storage_trigger_ws600_frontier_c4` only if the hardened repeats:

- remove or materially shrink the late `lan2` timeout regime,
- keep failures localized to brief recovery intervals,
- avoid broad spillover into `demand_drop`, and
- preserve natural storage scale-up.

Until then, the frontier remains closed.
