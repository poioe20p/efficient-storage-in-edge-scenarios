# Campaign Findings — research_q3 (release-mechanism comparison)

**Date**: 2026-09-04 · **Status**: ⏹ **HALTED by user decision after 25 runs**
(24 early runs complete, 6/6 per arm; 1 late run `ol1`). The late half
(B7–B12, hold=900) was not run — see Limitations.

## Verdict in one paragraph

All four release mechanisms work exactly as designed, with a perfect safety
floor. The stabilized arm (retention + overload recall) delivers **zero
re-entry action** — 0 re-spawns, 0 missed recalls, churn 0–1 — at a measured
**~25% valley-occupancy premium** and a deterministic finalization (482 ± 1 s).
However, per-phase client-visible quality shows **no arm differentiation**:
every arm fails ~50% of requests during storms because the bottleneck is the
storage tier, not the release policy. The release-policy choice is therefore
**user-invisible in this regime**; its only measured differences are
operational (CPU, spawns, churn). Research substance is limited to the
mechanism validation, the measured trade-off, and a negative result.

## Run tally

| Scope | Result |
| --- | --- |
| Early cells (B1–B6, hold=480) | **24/24 GO** (6/6 per arm), 0 STOPs |
| Late cells | `ol1` GO (snapshot hold=900 verified); remaining 23 not run |
| DIAGNOSE events | 1 (de6 duplicate-submit → `orphan_begin=1`, root-caused, benign) |
| Safety floor | `NotPrimary=0`, `evict nonok=0`, `ghosts=0` in every run |

## Findings

### 1. Stabilized retention works end-to-end (mechanism validation)

Per run, per tier, per LAN: compute quarantine + storage retention in `hold`,
overload recall at `return_storm`, cycle-2 finalization in `demand_drop`.
`recall_missed = 0` in all 12 early tier-runs; finalize latency 481.6–482.9 s
(compute) and 491.7–493.1 s (storage) across 6 reps. The controller's
absence-cleanup no longer destroys parked nodes (v3 fix validated).

### 2. The zero re-entry trade-off (the one strong result)

| Metric (early cells) | stabilized | drained | immediate | off |
| --- | --- | --- | --- | --- |
| `return_spawns` | **0** (6/6) | 0–4 | 1–4 | 2–4 |
| churn pairs | **0–1** | 3–7 | 1–6 | n/a (incumbent) |
| C3_hold occupancy | **~5000** (4620–5628) | ~4100 | ~3920 | ~4080 |

Premium: **+25% valley occupancy** buys zero re-entry action. Note: the
preflight suggested ~2× occupancy gap — the campaign measures a much smaller
premium.

### 3. Per-phase client-visible quality — no arm differentiation (probe)

Probe over 12 early runs (3 reps × 4 arms), per phase:

- `return_storm` ok-rate: **27–53% across all arms** (median ~45%) — every
  policy fails roughly half of requests in the return window.
- stabilized serves 2.4–2.6 compute nodes during the return (recall) vs
  ~1.5 for eager arms, yet its ok-rate is the same: the bottleneck is the
  capped storage tier, not compute availability.
- `hold` (valley): all arms serve 90–97% ok — the occupancy premium buys no
  user-visible improvement there either.
- Operational difference that IS real: return-window compute CPU 35–43%
  (stabilized) vs 27–78% (eager arms); 0 spawns; 0 churn.

### 4. Expectations that did not materialize

- **Safety ablation (immediate)**: no hard-metric penalty (NotPrimary,
  non-ok evictions, ghosts all 0) — indistinguishable from drained.
- **Recovery time (ttsu)**: overlapping across arms (47–80 s) — no policy
  effect.
- **Churn ordering vs preflight reversed**: immediate (median 2) < drained
  (median 6); preflight had 7 vs 4.
- **Occupancy magnitude**: +25%, not the preflight ~2×.

## Conclusion

The campaign answers its mechanism question and produces one clean,
reproducible result (zero re-entry at +25% occupancy) plus an honest negative
result (release-policy choice is user-invisible under a storage-saturated
storm). It does not outrank the existing RQ3 saturation/scaling findings in
substance. Usable as mechanism validation and trade-off quantification for
the system chapter; not as an RQ3 headline.

## Limitations

- Late half (hold=900, finalize-before-return axis) unmeasured — only `ol1`
  ran (GO). The finalize-then-respawn contrast remains open.
- Per-phase quality probe is a runner-side exploratory analysis of 12 runs;
  formal per-arm per-phase statistics (CIs, safety-window analysis) are the
  analyzer's scope if ever required.
- Run folders for all 25 runs remain on the hosting VM (campaign archive).
