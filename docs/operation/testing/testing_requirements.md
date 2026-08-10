# Testing — Base Requirements

**Purpose**: the single, minimal set of base requirements that any experiment
run must satisfy to count as thesis evidence. A gate reference for the runner
(fail-fast) and the analyzer (post-run verdict) — not a measurement manual.

**How to use**:

- Every run, experiment, or campaign is checked against this document.
- Experiment plans may add RQ-specific gates **on top**; this is the floor.
- Magnitudes are intentionally **relative and plan-defined** (see *Relative
  criteria* below) — this document fixes direction and comparability, not
  numbers.
- Levels: **hard gate** (fail ⇒ run is not evidence ⇒ rerun/rework) vs
  **flag** (⚠️ ⇒ report; may still count with justification).

## Cross-cutting principle — Reproducibility

Applies to **every** requirement below; no single-run claim is evidence:

- n ≥ 2 per cell/config (campaigns may pre-register a higher n, e.g. RQ2 n=6).
- Effect **direction consistent** across replicates.
- Seeds fixed (`RANDOM_SEED`), so replicates differ only in platform response.

## Hard gates

### B — Benefit of scaling (what the architecture buys)

- **B1. Compute scale-up benefit** — ≥1 of 2: request latency drops OR
  edge-tier CPU relief, comparing windows before vs after a compute add.
- **B2. Storage scale-up benefit** — ≥1 of 2: request latency drops OR
  storage-tier CPU relief, comparing windows before vs after a storage add.
- A claimed benefit must be measured **and** reproduce (per the principle
  above). A run pre-registered to show **no** benefit (mis-aligned arm,
  no-benefit verdict) is judged against its own claimed direction — it is a
  valid finding, not a gate failure.

### M — Mechanism exercised (precondition for any benefit claim)

- **M1. Claimed scale-up fires** — ≥1 add in the tier the plan claims to
  exercise, per LAN, during the pressure phase; includes scale-down when the
  plan claims recovery (elasticity is bidirectional).
- **M2. New capacity becomes usable** — each added node reaches
  app-ready → admitted → serves ≥1 successful request. Spawned ≠ usable.

### V — Workload validity (the treatment actually happened)

- **V1. Intended bottleneck evidenced** — the pressure the plan induces shows
  in telemetry: compute-bound phases show edge CPU rising; data-bound show
  `T_db`/storage CPU rising. Without the bottleneck there is no mechanism to
  test (RQ2 v2 load-calibration lesson).

### I — Interpretability floor (the numbers mean something)

- **I1. Enough demand** — ≥ N completed requests in the stress phase per LAN
  so latency percentiles are estimable (N is plan-defined).
- **I2. Outcome classification honest** — timeout is a distinct outcome class,
  never merged into failure; denominators consistent (offered vs completed vs
  timeout vs dropped/canceled).

### D — Data-path & process integrity

- **D1. Data-path clean** — 0× `NotPrimary`/`NotPrimaryOrSecondary`
  (read_preference lesson).
- **D2. No mid-run restart/crash** — no controller restart, no edge/storage
  container crash.
- **D3. Provenance snapshots present** — `phases_snapshot.json` +
  `controller_env_snapshot.env` in the run folder (reproducibility contract).

## Flags (report; do not invalidate without justification)

- **F1. Telemetry continuity** — resource windows present across the stress
  phase (no blackout ⇒ blind decisions). Hard for RQ1, where telemetry is the
  subject.
- **F2. LAN symmetry** — both LANs behave comparably (precedent ≤3× asymmetry).

## Explicitly NOT a gate

- **No-collapse ceiling** — runs are allowed to show worse outcomes. Mis-aligned
  arms (RQ2 wrong-action cost) and pre-registered no-benefit verdicts
  (RQ3-storage) are designed to do so. A collapsed run is only a concern as a
  harness/driver failure, judged at plan level.

## Relative criteria — numbers live in the plan

This document defines no absolute numbers. Each experiment plan pre-registers
its magnitudes: benefit threshold (%), minimum request count N, any ceilings,
LAN-symmetry bound, and the per-requirement evidence artifact. If a plan lacks
a needed magnitude, state it as a limitation — never invent a threshold here.
