# Scope Boundaries & Assumptions

> **Status (2026-08-01):** aligns with `thesis_overview.md` §8–§9 and the
> evaluation-feasibility notes in `tese/literature_review/global_literature_review.md`
> §11.5. “Geo-distributed” here means **emulated** cross-region latency, not a real
> multi-region deployment.

## Intra-cloudlet latency

Controller↔switch, aggregator↔controller, and edge-server↔aggregator links use raw
veth pairs (sub-ms). This models a single-site cloudlet where control-plane
components are co-located — the standard SDN deployment model for edge/5G
(Hung et al., 2022 — corpus `01_telemetry_rq1/`). Only the inter-LAN router link
carries emulated WAN latency (fixed symmetric tc-netem, 185 ms RTT by default;
jitter/loss/rate knobs exist but default to 0). Since intra-cloudlet overhead is
constant across all experimental conditions, it cancels out for the relative
comparisons the RQs require. The control plane does NOT cross the emulated WAN —
control-plane distribution is deliberately out of scope (ledger §11.5).

## Reliability & failover

Controller redundancy exists (topology sync between Ctrl-1 and Ctrl-2) but leader
election and automated failover are out of scope. OVS, aggregator, and router are
treated as reliable. The evaluation targets steady-state orchestration quality,
not fault tolerance. Degradation-recovery under component failure is deferred
to future work.

## Single-host caveat (known limitation)

All regions run on one cloud VM (CPU-capped containers; shared memory/disk/loopback),
so a spike in one LAN can interfere with the other. Mitigations: per-container CPU
caps; state it as a limitation; a stronger option (future work) is separate VMs per
region with netem between them, plus an RTT/jitter/loss sensitivity sweep
(ledger §11.5).
