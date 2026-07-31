# RQ1 — Theoretical Predictions

> Pure mechanism analysis. Disregards all experimental evidence.
> Predictions derived from the blind-spot model and system architecture only.

---

## 1. The Mechanism

The controller requires 3 of 5 consecutive 10-second telemetry windows to breach
a threshold before initiating a spawn decision. The delivery cadence determines
**when** the controller first learns about an overload:

```
Push:     learns at window close (t ≈ 10s). Sees every window.
          ──[W10]──[W20]──[W30]──[W40]──
          ✅       ✅       ✅       ✅

Poll-5s:  polls every 5s, windows every 10s. Sees every window
          (polls are faster than windows; duplicates occur but no windows missed).

Poll-12s: polls every 12s. Sees ~83% of windows
          (~2.5 polls per 3 windows; worst-case window missed if poll aligns poorly).

Poll-30s: polls every 30s. Sees ~33% of windows
          (1 of every 3; 2 of 3 windows are blind).
```

If overload appears at t = 15s (mid-way through W20):

| Mode | First learns | Blind-spot duration |
|------|-------------|-------------------|
| Push | t = 20s (W20 close) | ~5s |
| Poll-5s | t = 20s (W20 close, polled at t=20) | ~5s |
| Poll-12s | t = 24s (next poll after W20 closes) | ~9s |
| Poll-30s | t = 30s (next poll at 30s) | ~15s |

---

## 2. Theoretical Predictions by Metric

### 2.1 Staleness (Information Age)

| Mode | Prediction | Reasoning |
|------|-----------|-----------|
| Push | ~0s | Aggregator pushes at window close; controller receives immediately. |
| Poll-5s | ~5s | Poll interval; window may have been cached for up to 5s before fetch. |
| Poll-12s | ~10s | Same mechanism; average wait = poll_interval / 2. |
| Poll-30s | ~10s | Same as Poll-12s — staleness is bounded by the window duration (10s), not the poll interval. The cached window is always the latest completed one. |

**Key**: Staleness = polling cadence, not data staleness. The aggregator always
holds the freshest completed summary. The mechanism is **missed windows between
polls**, not stale data at consumption time.

### 2.2 Throughput

The blind spot consumes a fraction of each stress phase. During this fraction,
the controller takes no action — the system runs on pre-existing capacity.

```
Theoretical throughput penalty = blind_spot / phase_duration
```

For a 150s stress phase:

| Mode | Blind spot | Fraction | Expected Push ratio |
|------|-----------|----------|-------------------|
| Push | ~0s | 0% | 100% |
| Poll-5s | ~5s | 3% | ~97% |
| Poll-12s | ~12s | 8% | ~92% |
| Poll-30s | ~30s | 20% | ~80% |

**Prediction**: Push ≈ Poll-5s > Poll-12s > Poll-30s. Only Poll-30s should
produce a gap large enough to measure.

**Push and Poll-5s should be identical**: 5s poll interval < 10s window
duration — no windows are ever missed. This condition is critical: Poll-5s
proves the mechanism is **missed windows**, not stale data.

### 2.3 Latency

| Metric | Prediction | Reasoning |
|--------|-----------|-----------|
| **p50** | Flat across modes | Median is insensitive — most requests complete quickly under normal conditions. Blind-spot effects concentrate in the tail. |
| **p95** | P30 > P12 > P5 ≈ Push | Blind-spot queuing inflates the tail. Requests that arrive during the blind spot accumulate in the edge server queue. |
| **StdDev** | P30 > P12 > P5 ≈ Push | The blind spot introduces dispersion: some requests complete immediately (static nodes), others queue for seconds. |

**Caveat**: Synchronous client pacing creates a throughput-latency trade-off.
Push serves more requests (including marginal slow ones), which inflates its
mean and tail. P30 serves fewer requests — the ones that succeed are mostly
fast ones. The latency comparison should be throughput-adjusted.

### 2.4 Timeout Rate

```
Timeout = CURL_MAX_TIME exceeded = request queued > 30s
```

| Mode | Prediction | Reasoning |
|------|-----------|-----------|
| Push | Lowest | Earliest provisioning → queue drains fastest. |
| Poll-5s | ≈ Push | Same detection speed. |
| Poll-12s | Intermediate | Minor blind spot → slightly more queuing. |
| Poll-30s | Highest | 30s blind spot → requests queue for up to 30s before detection begins. |

**Caveat**: The relationship is step-like, not linear. CURL_MAX_TIME = 30s
creates a hard cliff — a request queuing 29s succeeds (200 OK), a request
queuing 31s times out (http_status=0). The blind spot straddles this cliff,
producing high per-replicate variance.

### 2.5 Degradation Bands (Latency > T)

For any threshold T, the fraction of requests exceeding T should increase with
polling interval:

| Threshold | Prediction |
|-----------|-----------|
| >5s | P30 > P12 > P5 ≈ Push |
| >10s | P30 > P12 > P5 ≈ Push |
| >20s | P30 > P12 > P5 ≈ Push |
| >30s (timeout) | P30 > P12 > P5 ≈ Push |

**Key**: The gap should be largest at intermediate bands (>10s, >20s) where most
blind-spot queuing lands. The >5s band captures all queued requests; the >30s
band only captures the extreme tail. Together they form a degradation staircase
showing how the blind spot shifts the latency distribution rightward.

### 2.6 Infrastructure Metrics

| Metric | Prediction | Reasoning |
|--------|-----------|-----------|
| **Compute node CPU** | P30 > P12 > P5 ≈ Push | Fewer nodes provisioned (delayed spawns) → remaining nodes serve more requests → higher per-node CPU. |
| **Storage node CPU** | P30 > P12 > P5 ≈ Push | Same mechanism: delayed storage spawns → existing storage nodes handle cross-region load longer. |
| **Controller CPU** | Flat across modes | ZMQ push vs HTTP polling are comparable overhead. Push marginally higher (ZMQ event loop). |
| **Controller RAM** | Flat across modes | Telemetry cache size is independent of delivery mechanism. |

### 2.7 Detection & Reaction

| Metric | Prediction | Reasoning |
|--------|-----------|-----------|
| **Reaction events detected** | Push = P5 = P12 > P30 | All modes observe the same overload. Only P30 misses the detection windows that trigger spawn decisions. |
| **Reaction latency (for detected events)** | P30 > P12 > P5 ≈ Push | Survivor-biased: undetected breaches have infinite latency and are excluded from the mean. |
| **Spawn count (compute)** | Push = P5 = P12 > P30 | P30 under-spawns because it misses breached windows. |
| **Spawn count (storage)** | Push = P5 = P12 ≥ P30 | Storage saturation persists longer — eventually detected even by P30. Gap is smaller. |

---

## 3. Central Theoretical Claim

> In a system where the controller must observe sustained overload across
> multiple telemetry windows before acting, the delivery cadence creates a
> **blind spot** whose duration is the polling interval. During this blind
> spot, the system runs on pre-existing capacity. The blind spot consumes
> a fraction of each demand event proportional to `poll_interval / phase_duration`.
> This fraction is the theoretical upper bound on the throughput penalty.

---

## 4. Testable Conditions

The theory makes four binary predictions that can be confirmed or rejected:

| # | Prediction | Tests |
|---|-----------|-------|
| T1 | Push and Poll-5s are indistinguishable | Throughput, latency, timeout rates within measurement noise of each other |
| T2 | Poll-12s shows a small but detectable gap | Throughput ~92% of Push; p95 mildly elevated |
| T3 | Poll-30s shows the largest gap | Throughput ~80% of Push; p95 substantially elevated; no range overlap with Push |
| T4 | The gap widens monotonically with polling interval | Push ≈ P5 > P12 > P30 in throughput and tail latency |

**T1** is the most critical — it isolates the mechanism to **missed windows**.
If Push and Poll-5s differ, the degradation is caused by something other than
window visibility (e.g., push vs poll overhead, ZMQ vs HTTP performance).

---

## 5. Where Theory May Break

Several real-world effects are not captured by the model:

1. **Residual capacity**: Static nodes absorb overload before provisioning is
   triggered. If static capacity suffices, the blind spot produces no gap.
2. **Cooldown carryover**: Nodes from previous phases may persist into the next
   stress phase, reducing the need for new spawns.
3. **Synchronous client pacing**: Latency throttles throughput — a P30 request
   that queues for 20s delays the next request from that client by 20s,
   compounding the throughput gap beyond the theoretical bound.
4. **Storage cascade non-linearity**: Storage saturation propagates through the
   edge tier's TCP accept queue. The relationship between storage load and edge
   throughput is non-linear — a small increase in storage latency can trigger a
   disproportionate throughput drop.
5. **CURL_MAX_TIME cliff**: The binary timeout at 30s introduces step-function
   variance. Requests straddling the cliff produce noisy per-replicate timeout
   rates.

These effects may compress or amplify the theoretical predictions, but they
should not invert them: Push should never be worse than Poll-30s on any metric.
