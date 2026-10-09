# Scope Boundaries & Assumptions

> **Status (2026-09-28):** aligns with `thesis_overview.md` §8–§9 and the
> evaluation-feasibility notes in `tese/literature_review/global_literature_review.md`
> §11.5. The evaluated testbed is a **two-domain single-host** deployment; the
> inter-domain link is emulated and only cross-domain data traffic traverses it.
> Thesis vocabulary (2026-09-28): “two-domain testbed”, “inter-domain link”,
> “cross-domain storage placement”. No geo-distributed or wide-area performance
> claim is made; the limitation itself is carried in Ch6.

## Intra-cloudlet latency

Controller↔switch, aggregator↔controller, and edge-server↔aggregator links use raw
veth pairs (sub-ms). This models a single-site cloudlet where control-plane
components are co-located — the standard SDN deployment model for edge/5G
(Hung et al., 2022 — corpus `01_telemetry_rq1/`). Only the inter-LAN router link
carries emulated inter-domain latency (fixed symmetric tc-netem, 185 ms RTT by default;
jitter/loss/rate knobs exist but default to 0). Since intra-cloudlet overhead is
constant across all experimental conditions, it cancels out for the relative
comparisons the RQs require. The control plane does NOT traverse the emulated inter-domain link —
control-plane distribution is deliberately out of scope (ledger §11.5).

## Reliability & failover

Controller redundancy exists (topology sync between Ctrl-1 and Ctrl-2) but leader
election and automated failover are out of scope. OVS, aggregator, and router are
treated as reliable. The evaluation targets steady-state orchestration quality,
not fault tolerance. Degradation-recovery under component failure is deferred
to future work.

## Single-host caveat (known limitation)

All domains run on one cloud VM (CPU-capped containers; shared memory/disk/loopback),
so a spike in one domain can interfere with the other. Mitigations: per-container CPU
caps; state it as a limitation; a stronger option (future work) is separate VMs per
domain with a tc-netem inter-domain link between them, plus an RTT/jitter/loss
sensitivity sweep
(ledger §11.5).

**Host inventory (2026-10-08).** The three campaign hosts (RQ1 `cloud-vm`,
RQ2 `cloud-vm-rq2`, RQ3 `cloud-vm-rq3`) are KVM virtual machines of the same
type (4 vCPU on an AMD EPYC-Genoa processor at 2.4 GHz, 8 GB RAM, Ubuntu
22.04.5 LTS, local SSD), identical apart from the
RQ1 host's smaller local disk (80 GB against 160 GB, because no instance
with the same disk size was available when it was provisioned). Registered
in the thesis at Ch4 §4.1 and Ch5 Table 5.1 (host profile) and Ch5 §5.1
(disk difference); full detail in `docs/operation/testing/vm_provisioning.md`.
