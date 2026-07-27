# OKF-ification Plan for `docs/operation/`

**Date**: 2026-07-27 · **Status**: 📋 Planned · **Based on**: [OKF v0.2 Spec](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)

## What OKF Is

Open Knowledge Format (OKF) v0.2 — a Google Cloud open specification that formalizes knowledge representation as directories of markdown files with YAML frontmatter. Designed for both human and agent consumption.

Core rules:
- Every `.md` file has YAML frontmatter with at minimum a `type` field
- `index.md` at each directory level for progressive disclosure (agents navigate hierarchically without loading everything)
- `log.md` optionally tracks change history
- Markdown cross-links between concepts form a navigable knowledge graph
- Reserved filenames: `index.md`, `log.md` (all other `.md` files are concept documents)

## Type Taxonomy

| `type` value | Applies to |
|---|---|
| `System Overview` | Top-level cross-cutting docs: `system_mechanisms.md`, `system_scenarios.md` |
| `Subsystem Overview` | Per-subsystem overviews: `elasticity_overview.md`, `telemetry_overview.md`, `topology_overview.md`, `vip_routing_overview.md`, `selective_sync_overview.md` |
| `Design Document` | Detailed mechanism docs: `compute_scale_down.md`, `vip_routing_interception_and_flow_rules.md`, `aggregator.md`, etc. |
| `Implementation Plan` | Docs under `implementation/` subdirectories |
| `Operational Guide` | Testing docs: `testing_overview.md`, `experiment_campaign_brief.md`, `traffic_generator.md` |
| `Reference` | Config/constants: `golden_config.md`, `analysis_toolchain.md` |
| `Experiment Plan` | `experiment_plan.md` files under `experiment/` |
| `Results` | `results.md` files |
| `Archive` | All docs under `archive/` |

## Frontmatter Template

Every concept document gets:

```yaml
---
type: <from taxonomy above>     # REQUIRED
title: <display name>           # Recommended
description: <one-line summary> # Recommended
tags: [<tag>, ...]              # Recommended — subsystem + topic keywords
status: stable                  # stable | draft | deprecated
---
```

Optional trust/lifecycle fields (OKF v0.2):
- `generated: { by: "human:<id>", at: "YYYY-MM-DDTHH:MM:SSZ" }` — who authored it
- `verified: { by: "human:<id>", at: "..." }` — who reviewed it
- `stale_after: "YYYY-MM-DD"` — when it becomes stale
- `sources:` — provenance with credibility signals

## Step-by-Step Implementation

### Phase 1: Root `index.md`

**Create `docs/operation/index.md`** — lists all subsystems with descriptions:

```markdown
# Subsystems

* [Elasticity Manager](elasticy_manager/) — Auto-scaling compute and storage nodes based on telemetry signals
* [Selective Sync](selective_sync/) — Tier-1 selective synchronization of hot content
* [Telemetry](telemetry/) — Metrics collection, aggregation, and controller-side consumption
* [Testing](testing/) — Experiment plans, configurations, and analysis toolchain
* [Topology](topology/) — Network topology, VIP pools, node discovery, and peer exchange
* [VIP Routing](vip_routing/) — Double-VIP routing model, backend selection, and cross-network forwarding

## Cross-Cutting

* [System Mechanisms](system_mechanisms.md) — How all mechanisms interact at the system level
* [System Scenarios](system_scenarios.md) — End-to-end scenario walkthroughs

## Archive

* [Archive](archive/) — Historical plans and retired documents
```

### Phase 2: Root Docs Frontmatter

Add YAML frontmatter to `system_mechanisms.md` and `system_scenarios.md`.

### Phase 3: Per-Subsystem `index.md`

Create one `index.md` per subsystem directory:
- `elasticy_manager/index.md`
- `selective_sync/index.md`
- `telemetry/index.md`
- `testing/index.md`
- `topology/index.md`
- `vip_routing/index.md`
- `other/index.md`
- `archive/index.md`

### Phase 4: Frontmatter on All Concept Docs

Add YAML frontmatter to every existing `.md` file under `docs/operation/`, assigning `type` per the taxonomy above.

### Phase 5: Cross-Links

Add markdown links between related concepts. Priority edges:

| From | To | Rationale |
|---|---|---|
| `system_mechanisms.md` | Each subsystem overview | Shows how mechanisms compose |
| Each subsystem overview | Its child docs | Navigation to detail docs |
| `testing_overview.md` | `experiment_campaign_brief.md`, `golden_config.md` | Testing workflow |
| `vip_routing_overview.md` | `dual_vip_server_plan.md`, topology docs | Routing depends on topology |
| `elasticity_overview.md` | `telemetry_overview.md` | Elasticity consumes telemetry |
| `telemetry_overview.md` | `aggregator.md`, `controller_telemetry_consumer.md` | Telemetry pipeline |

### Phase 6: Optional `log.md`

Create `docs/operation/log.md` for tracking major documentation changes.

## Files Affected

| Action | Count | Details |
|---|---|---|
| Create `index.md` | ~8 | Root + 7 subsystem dirs |
| Add frontmatter to `.md` | ~30+ | All existing concept docs |
| Add cross-links | ~15+ | Key relationship edges |
| Create `log.md` | 1 | Root level |

## What This Enables for Agents

After OKF-ification, agents can:
1. **Navigate progressively**: Read `index.md` → choose subsystem → read subsystem `index.md` → open only relevant docs
2. **Query by type/tag**: "Find all `Design Document` files tagged `elasticity`"
3. **Check freshness**: `stale_after` and `status` fields tell agents whether a doc is current
4. **Trace relationships**: Cross-links form a navigable knowledge graph
5. **Search efficiently**: Instead of loading all docs into context, agents follow the index hierarchy

## Estimated Effort

- Phase 1-2 (root files): ~10 min
- Phase 3 (index files): ~20 min
- Phase 4 (frontmatter): ~1-2 hours (requires reading each file)
- Phase 5 (cross-links): ~30 min
- Phase 6 (log.md): ~5 min
