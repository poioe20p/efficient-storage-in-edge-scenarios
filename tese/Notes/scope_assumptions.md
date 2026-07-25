# Scope Boundaries & Assumptions

## Intra-cloudlet latency

Controller↔switch, aggregator↔controller, and edge-server↔aggregator links use raw
veth pairs (sub-ms). This models a single-site cloudlet where control-plane
components are co-located — the standard SDN deployment model for edge/5G
(Hung et al., 2022). Only the inter-LAN router link carries emulated WAN latency.
Since intra-cloudlet overhead is constant across all experimental conditions,
it cancels out for the relative comparisons the RQs require.

## Reliability & failover

Controller redundancy exists (topology sync between Ctrl-1 and Ctrl-2) but leader
election and automated failover are out of scope. OVS, aggregator, and router are
treated as reliable. The evaluation targets steady-state orchestration quality,
not fault tolerance. Degradation-recovery under component failure is deferred
to future work.
