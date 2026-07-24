# Experiment Plan v4 — RQ2 Lifecycle Round-Robin Fix

**Status**: Designed · **Date**: 2026-07-24
**Predecessor**: [v3](../v3/experiment_plan_v3.md) — discovered warm-lease youngest-wins starvation
**Code change**: [`source/sdn_controller/_vip_routing/selection.py`](../../../../source/sdn_controller/_vip_routing/selection.py) + [`state.py`](../../../../source/sdn_controller/_vip_routing/state.py)

---

## 1. Why v4 Exists

### What v3 found

v3 measured the coordination gap — the delay between backend spawn and routing-plane awareness — across three policy modes:

| Mode | TTFT med | Mechanism |
|------|----------|-----------|
| Host | 10.7 s | Round-robin at t=0 — every backend gets traffic in window 1 |
| Slowstart | 51.0 s | Invisible until telemetry discovery — consistent ~50 s delay |
| Lifecycle | **30.6 s** | Warm lease at spawn — expected ~10 s, but measured 30.6 s with IQR 34.8 s |

The Lifecycle anomaly — 3× higher TTFT than expected with enormous variance — was traced to a single line in `_claim_warm_backend()`:

```python
mac, lease = max(candidates, key=lambda item: item[1].started_ts)
```

This picks the **most recently spawned** backend among all active warm leases. When backends A and B both hold warm leases, the younger (B) monopolises **all** warm-lease traffic until its 45 s TTL expires. The older (A) is starved — no requests reach it until B's lease ends, inflating A's TTFT to 50–60 s.

### What v4 changes

v4 replaces `max(started_ts)` with **round-robin**: each warm-lease request rotates to the next candidate, giving all warm backends a fair 1/N share of traffic from their first telemetry window.

### The question

Does fair distribution eliminate the starvation artefact? If yes, Lifecycle TTFT drops from 30.6 s to ~10 s, and the true coordination gap (Slowstart − Lifecycle) reveals itself at ~41 s rather than 20.4 s.

---

## 2. How the Code Change Modifies Behaviour

### The changed line

**`_vip_routing/selection.py`**, `_claim_warm_backend()`:

```diff
- mac, lease = max(candidates, key=lambda item: item[1].started_ts)
+ mac, lease = candidates[controller._warm_rr_idx % len(candidates)]
+ controller._warm_rr_idx += 1
```

Plus counter initialisation in **`_vip_routing/state.py`**: `controller._warm_rr_idx: int = 0`.

### Concrete behavioural difference

Consider two backends spawned 5 s apart with overlapping warm leases:

```
v3 (max started_ts):                    v4 (round-robin):

t=0s  A spawns, warm lease              t=0s  A spawns, warm lease
t=5s  B spawns, warm lease              t=5s  B spawns, warm lease
      B.started_ts > A.started_ts             Request 1 → A (idx 0)
      → ALL requests → B                     Request 2 → B (idx 1)
t=10s window: only B gets traffic            Request 3 → A (idx 0)
t=20s window: only B                         ...
t=30s window: only B                    t=10s window: A AND B get traffic
t=40s window: only B                         TTFT(A) ≈ 10 s ✓
t=50s B's lease expires                      TTFT(B) ≈ 5 s  ✓
t=60s A FINALLY gets traffic
      TTFT(A) = 60 s ← STARVED
      TTFT(B) = 5 s
```

### Expected metric impact

| Metric | v3 (measured) | v4 (predicted) | Why |
|--------|---------------|----------------|-----|
| Lifecycle TTFT med | 30.6 s | **~10 s** | Every warm backend gets traffic in window 1 |
| Lifecycle TTFT IQR | 34.8 s | **~5 s** | No starvation tail — all backends treated equally |
| Lifecycle TTFT max | 500 s | **~20 s** | Worst case = 2 windows (was 45 s starvation) |
| Coordination gap | 20.4 s | **~41 s** | Slowstart 51 s − Lifecycle ~10 s = true gap |
| Init time (TFR−TTFT) | −6.0 s | **~0 s** | Traffic arrives sooner → less idle-warm headroom |
| Initial share | 0.111 | **~0.2** | Fair distribution → more backends get non-zero share |
| Host/Slowstart TTFT | 10.7 / 51.0 s | unchanged | Code path gated; v3 data reused |

---

## 3. Why Lifecycle-Only

The code change is gated behind `if _BACKEND_SELECTION_POLICY == "topology_lifecycle"` in `_claim_warm_backend()`. Host and Slowstart skip warm-lease claiming entirely — their code path is unchanged. Rerunning them would produce identical results to v3. This plan runs **3 Lifecycle replicates only**, reusing v3 Host and Slowstart data for cross-mode comparisons.

---

## 4. What Changes vs v3

| Aspect | v3 | v4 |
|--------|-----|-----|
| Warm-lease selection | `max(started_ts)` — youngest wins | Round-robin — fair 1/N |
| Lifecycle TTFT (predicted) | 30.6 s med, 34.8 s IQR | ~10 s med, ~5 s IQR |
| Coordination gap (predicted) | 20.4 s | ~41 s |
| Controller code | v3 (youngest-wins) | v4 (round-robin, already deployed on cloud-vm) |
| Everything else | — | Identical to v3 |

---

## 5. Run Configuration

**3 Lifecycle runs only.** Host and Slowstart data reused from v3.

| # | Label | BACKEND_SELECTION_POLICY | Env Override |
|---|-------|--------------------------|-------------|
| 1–3 | `rq2_v4_tl_{1,2,3}` | `topology_lifecycle` | `rq2_v3_topology_lifecycle.env` |

**Prerequisite**: The v4 code change is already deployed on the cloud VM (`source/sdn_controller/_vip_routing/`). The controller code is volume-mounted at runtime (`-v "$PWD":/workspace` in `build_network_setup.sh`), so no Docker image rebuild is needed. The `osken_1` and `osken_2` containers will pick up the change on next launch.

All other parameters (`CLIENTS=96`, `WAN_RTT_MS=185`, `STORAGE_CPUS=0.08`, `CURL_MAX_TIME=30`, `RANDOM_SEED=42`, `CONTENT_ITEMS=6000`, `PHASES_CONFIG=testing/phases_override/phases_rq2.json`) unchanged from v3.

---

## 6. Focus & Evidence

**Primary**: Lifecycle TTFT distribution (G1) — compare v4 against v3 (30.6 s med / 34.8 s IQR).

**Secondary**: G2b (TTFT vs TFR scatter) — Lifecycle circles should cluster at TTFT ≈ 10 s.

**Tertiary**: G4 (initial share), G5–G8b (service quality) — expect unchanged or marginally improved.

Cross-mode graphs reuse v3 Host and Slowstart data.

---

## 7. Success Criteria

| Criterion | Threshold |
|-----------|-----------|
| Lifecycle TTFT med ≤ 15 s | v3 was 30.6 s — should drop to ~10 s |
| Lifecycle TTFT IQR ≤ 10 s | v3 was 34.8 s — starvation eliminated |
| Coordination gap (vs v3 Slowstart) ≥ 35 s | v3 was 20.4 s — true gap revealed |
| S1–S5 sanity checks pass | Same as v3 — env snapshot, spawn counts, no Tier 1 |

---

## 8. Validity Threats

| Threat | Mitigation |
|--------|-----------|
| Only 3 Lifecycle reps | If TTFT IQR still > 15 s after fix, consider additional reps |
| Controller image rebuild | Verify `BACKEND_SELECTION_POLICY=topology_lifecycle` in snapshot post-run |
| Round-robin counter not thread-safe without lock | `_claim_warm_backend` already holds `_warm_lock` — increment is protected |
| Cross-mode comparison reuses v3 data | Host/Slowstart code paths unchanged — reusing v3 is valid |

---

## 9. References

- v3 plan & results: [`../v3/experiment_plan_v3.md`](../v3/experiment_plan_v3.md), [`../v3/results.md`](../v3/results.md)
- v3 setup: [`docs/research_questions/rq2/rq2_setup_v3.md`](../../../research_questions/rq2/rq2_setup_v3.md)
- Code: [`source/sdn_controller/_vip_routing/selection.py`](../../../../source/sdn_controller/_vip_routing/selection.py)
- Warm-lease design: [`docs/operation/vip_routing/vip_routing_backend_selection_and_warm_leases.md`](../../../operation/vip_routing/vip_routing_backend_selection_and_warm_leases.md)
