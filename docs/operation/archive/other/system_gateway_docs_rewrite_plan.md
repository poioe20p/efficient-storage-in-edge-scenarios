# System Gateway Docs Rewrite Plan

## Scope

Rewrite the two top-level operation gateway documents so they become short,
stable entry points instead of detailed implementation references.

This plan covers only these three file operations:

1. Update `docs/operation/system_mechanisms.md`
2. Update `docs/operation/system_scenarios.md`
3. Delete `docs/operation/document_lifecycle.md`

Do not edit subsystem overview documents in this pass.

---

## Review Workflow

1. Execute the steps in order.
2. Stop after each review checkpoint.
3. Do not batch multiple steps into one implementation pass.
4. Keep the scope limited to the three file operations above.
5. If validation finds a stale reference outside those three files, stop and
   ask before widening scope.

---

## Locked Requirements

1. `system_mechanisms.md` must become the stable gateway document for the
   operational architecture.
2. `system_scenarios.md` must become a concise workflow companion, not a deep
   scenario catalog.
3. `document_lifecycle.md` must be absorbed into `system_mechanisms.md` and
   then deleted.
4. The top-level docs must stop duplicating volatile subsystem detail that is
   already maintained in subsystem overview documents.
5. Tier 1 wording must match the current implemented baseline:
   - Tier 1 is client-side and manifest-driven.
   - Edge servers short-circuit eligible point reads locally.
   - Cold reads and writes still fall through the normal `VIP_DATA` path.
   - The controller does not perform Tier 1 backend selection through
     `VIP_DATA` routing.
6. VIP routing wording must match the current baseline:
   - VIP routing covers controller-side `VIP_SERVER` and `VIP_DATA` routing.
   - VIP routing documents Tier 0 and Tier 2 controller behavior.
   - Tier 1 is referenced from VIP routing docs but not implemented inside the
     VIP selector.
7. The subsystem overview documents remain the canonical source for detailed
   mechanisms, configuration-sensitive behavior, and implementation evolution.

---

## Authoritative References To Read Before Editing

Read these files before making the rewrite.

### Target files

1. `docs/operation/system_mechanisms.md`
2. `docs/operation/system_scenarios.md`
3. `docs/operation/document_lifecycle.md`

### Canonical overview references

1. `docs/operation/vip_routing/vip_routing_overview.md`
2. `docs/operation/telemetry/telemetry_overview.md`
3. `docs/operation/topology/topology_overview.md`
4. `docs/operation/elasticy_manager/elasticity_overview.md`
5. `docs/operation/selective_sync/selective_sync_overview.md`

The rewrite must align with those overview pages instead of preserving older
top-level wording that has drifted.

---

## Target Files

### Files To Update

1. `docs/operation/system_mechanisms.md`
2. `docs/operation/system_scenarios.md`

### File To Delete

1. `docs/operation/document_lifecycle.md`

### Reference Files To Keep Unchanged

1. `docs/operation/vip_routing/vip_routing_overview.md`
2. `docs/operation/telemetry/telemetry_overview.md`
3. `docs/operation/topology/topology_overview.md`
4. `docs/operation/elasticy_manager/elasticity_overview.md`
5. `docs/operation/selective_sync/selective_sync_overview.md`

---

## Terminology Rules

Apply these rules consistently in both rewritten top-level docs.

1. Use `Tier 0`, `Tier 1`, and `Tier 2` with the current meanings only.
2. Describe Tier 1 as a consumer-LAN standalone `mongod` reached through a
   controller-broadcast manifest and edge-server client-side short-circuiting.
3. Do not describe Tier 1 as a controller-routed `VIP_DATA` target.
4. Describe VIP routing as the controller-side handling of `VIP_SERVER` and
   normal `VIP_DATA` routing.
5. When summarizing a subsystem, end the summary by pointing to the
   authoritative overview document.
6. Treat `system_mechanisms.md` and `system_scenarios.md` as gateway docs.
   They should orient the reader and send them to the right detailed document.

---

## Step 0 - Confirm The Baseline Before Rewriting

Read the current target files and canonical overview pages listed above.

While reading, explicitly confirm these points before changing anything:

1. Tier 1 is manifest-driven and client-side in the edge server.
2. `VIP_DATA` remains the fallback path for cold reads and writes.
3. VIP routing overview pages already carry the detailed implementation of
   `VIP_SERVER` and `VIP_DATA` controller behavior.
4. The current `system_mechanisms.md` contains deep detail that should be
   removed rather than preserved.
5. `document_lifecycle.md` contains useful categories that should be merged
   into reader guidance, not copied as a separate standalone index.

### Review checkpoint 0

Verify:

1. The target files have been read.
2. The overview documents have been read.
3. The Tier 1 baseline is clear.
4. The rewrite goal is clear: shorten and delegate, not re-document.

---

## Step 1 - Rewrite `system_mechanisms.md` As The Gateway Document

Replace the current deep implementation narrative with a shorter orientation
document.

This step should be a substantial rewrite. It is acceptable to replace most of
the existing content instead of editing section by section.

### Required section order for `system_mechanisms.md`

Use this section order in the rewritten file.

1. Title and purpose
2. What this repository contains
3. System architecture at a glance
4. Runtime responsibilities
5. Data placement tiers
6. Where to read next
7. Repository navigation
8. Documentation lifecycle

### Section-by-section requirements

#### 1. Title and purpose

State that this document is the entry point for the operational architecture
and that detailed behavior lives in subsystem overview pages.

#### 2. What this repository contains

Summarize the platform at a high level:

1. OS-Ken SDN controller
2. OVS-based network steering
3. containerized edge servers
4. MongoDB-based storage placement
5. telemetry aggregation and controller consumption
6. elasticity-driven compute and storage changes

Keep this section descriptive, not argumentative.

#### 3. System architecture at a glance

Explain the runtime architecture in short form:

1. the three controller execution contexts
2. the double-VIP traffic split
3. the separation between fast-path routing and slower infrastructure changes
4. the roles of edge servers, storage nodes, and telemetry aggregators

Explicitly name the traffic split:

1. `VIP_SERVER`
2. `VIP_DATA`
3. telemetry flow
4. elasticity actions

Do not include packet-level walkthroughs or selector formulas here.

#### 4. Runtime responsibilities

Include short summaries for these responsibilities:

1. controller fast path
2. telemetry observation path
3. elasticity and placement path
4. edge server role
5. storage role

Each summary must stay short and must end by pointing to the detailed overview
document that owns the topic.

#### 5. Data placement tiers

Describe the tier model only at orientation depth:

1. Tier 0: normal remote read path over `VIP_DATA`
2. Tier 1: client-side manifest-driven short-circuiting to the local selective
   sync node for eligible point reads
3. Tier 2: full replica placement for broader sustained demand

Be explicit that Tier 1 is not controller-side VIP routing.

#### 6. Where to read next

Include a short document map with one-line descriptions and links to:

1. VIP routing overview
2. telemetry overview
3. topology overview
4. elasticity overview
5. selective sync overview
6. testing and other operational docs, if useful

This section should behave like the main handoff surface for readers.

#### 7. Repository navigation

Add a short section that explains the main folders a new reader should know:

1. `source/`
2. `docs/`
3. `source/scripts/`
4. thesis materials, only as a short note if still helpful

Keep it short and practical.

#### 8. Documentation lifecycle

Merge the useful guidance from `document_lifecycle.md` into a reader-facing
closing section.

Preserve these categories:

1. current reference docs
2. active plans kept in place
3. implemented phase folders kept in place
4. archived historical plans
5. naming and archival guidance

Reframe the content as guidance for how to interpret the docs tree rather than
as a standalone index.

### Content that must be removed from `system_mechanisms.md`

Do not carry forward these categories of content:

1. formulas and equations
2. detailed WSM selector explanations
3. threshold tables
4. alert-priority tables
5. environment-variable catalogs
6. node addition and node removal internals
7. telemetry event schemas and detailed aggregation fields
8. packet-level walkthroughs and large rule-priority tables
9. server epoch and recovery runtime internals
10. deep subsystem implementation history
11. thesis-style final system definition prose

### Review checkpoint 1

Verify:

1. `system_mechanisms.md` is materially shorter than before.
2. The file reads as orientation, not as implementation reference.
3. The three controller execution contexts are summarized at a high level.
4. The `VIP_SERVER` / `VIP_DATA` / telemetry / elasticity split is present.
5. Tier 1 is described as client-side manifest-driven behavior.
6. Each subsystem summary points to its canonical overview document.
7. The documentation lifecycle guidance is present in this file.
8. None of the removed deep-detail categories remain.

---

## Step 2 - Rewrite `system_scenarios.md` As A Concise Scenario Companion

Replace the current long scenario list and large diagrams with a smaller set of
concise scenario summaries.

This document should accompany the gateway doc, not compete with subsystem
overview pages.

### Required section order for `system_scenarios.md`

Use this section order.

1. Title and purpose
2. Scenario 1: VIP interception and request routing
3. Scenario 2: telemetry propagation
4. Scenario 3: compute scale-up and scale-down
5. Scenario 4: storage scale-up and scale-down
6. Scenario 5: selective sync promotion and drain
7. Scenario map to authoritative docs

### Per-scenario template

Each scenario section should use the same compact structure:

1. what triggers it
2. which components participate
3. what the controller or edge node does
4. where the detailed subsystem reference lives

Prefer short prose paragraphs or tight bullets. Do not reproduce long sequence
diagrams unless a very small diagram is clearly necessary. The default should
be concise text.

### Scenario-specific requirements

#### Scenario 1 - VIP interception and request routing

Describe:

1. a client or edge-server connection hitting a VIP
2. controller-side selection on the first packet
3. flow installation for the chosen backend
4. steady-state traffic staying in the switch after the first decision

Point to the VIP routing overview for detail.

#### Scenario 2 - Telemetry propagation

Describe:

1. producer-side telemetry emission
2. aggregation in the per-network aggregator
3. publication to the controller
4. controller-side consumption for routing state and elasticity decisions

Point to the telemetry overview for detail.

#### Scenario 3 - Compute scale-up and scale-down

Describe:

1. the trigger from telemetry-derived compute pressure or idleness
2. the elasticity manager deciding to add or drain edge-server capacity
3. the effect on backend admission and removal

Point to the elasticity overview for detail.

#### Scenario 4 - Storage scale-up and scale-down

Describe:

1. the trigger from storage-side latency or underutilization
2. storage node addition or removal through the elasticity path
3. the effect on storage availability behind normal `VIP_DATA` routing

Point to the elasticity overview and VIP routing overview for detail.

#### Scenario 5 - Selective sync promotion and drain

Describe:

1. promotion trigger from sustained cross-region read demand
2. the consumer-side controller creating or reconfiguring Tier 1 state
3. edge servers receiving a manifest and short-circuiting eligible point reads
4. cold reads and writes continuing through normal `VIP_DATA`
5. drain behavior when the hot set cools, becomes stale, or is superseded in
   a future cross-LAN Tier 2 variant

Be explicit about what must not be said:

1. Do not say the controller routes `VIP_DATA` to the selective-sync node.
2. Do not say VIP routing performs Tier 1 backend selection.
3. Do not imply that Tier 1 replaces normal `VIP_DATA` fallback behavior.

Point to the selective sync overview for detail.

### Content that must be removed from `system_scenarios.md`

Do not carry forward these patterns:

1. scattered scenario variants beyond the five required scenarios
2. large sequence diagrams copied from subsystem references
3. stale Tier 1 wording that implies controller-side `VIP_DATA` routing to the
   selective-sync node
4. deep explanation of thresholds, formulas, or queue priority
5. detailed step-by-step controller internals that belong in subsystem docs

### Review checkpoint 2

Verify:

1. `system_scenarios.md` contains only the five required scenarios.
2. Each scenario follows the same compact template.
3. The file is shorter and easier to scan than before.
4. Tier 1 is normalized to the manifest-driven client-side model.
5. No scenario says that the controller routes `VIP_DATA` to Tier 1.
6. The document ends with a clear map to authoritative overview docs.

---

## Step 3 - Delete `document_lifecycle.md` After The Merge

Do not delete the file until the lifecycle guidance has already been merged
into `system_mechanisms.md`.

Before deletion, verify that `system_mechanisms.md` already includes reader
guidance covering:

1. current reference docs
2. active plans kept in place
3. implemented phase folders kept in place
4. archived historical plans
5. naming and archival guidance

Then delete `docs/operation/document_lifecycle.md`.

Do not recreate its content as a new standalone appendix or second index file.

### Review checkpoint 3

Verify:

1. `document_lifecycle.md` has been deleted.
2. Its useful guidance now lives inside `system_mechanisms.md`.
3. The lifecycle guidance reads like reader orientation, not like a duplicate
   standalone index.

---

## Step 4 - Run A Focused Validation Pass

After the three file operations are complete, run these checks in order.

### Validation check 1 - Stale lifecycle references

Search for `document_lifecycle` across the workspace.

Expected outcome:

1. no live top-level docs should still point to the deleted file
2. if stale references exist outside the three planned files, stop and ask
   before editing more files

### Validation check 2 - Tier 1 wording in the edited files

Search the edited files for `Tier 1`, `selective sync`, and `VIP_DATA`.

Expected outcome:

1. Tier 1 is described as manifest-driven and client-side
2. `VIP_DATA` remains the normal fallback path for cold reads and writes
3. there is no claim that the controller routes `VIP_DATA` to the selective
   sync node

### Validation check 3 - Internal links

Check that links in the two edited files still point to the correct overview
pages after the lifecycle merge.

Expected outcome:

1. subsystem links resolve correctly
2. no link still points to `document_lifecycle.md`

### Validation check 4 - Diff review

Review the resulting diff.

Expected outcome:

1. `system_mechanisms.md` is shorter and more navigational
2. `system_scenarios.md` is shorter and more scenario-focused
3. `document_lifecycle.md` is deleted
4. the top-level docs no longer duplicate detailed subsystem mechanisms

### Review checkpoint 4

Verify:

1. the lifecycle references are clean
2. the Tier 1 wording is current
3. the links are valid
4. the diff matches the intended scope and only covers the planned files

---

## Non-Goals

Do not do any of the following in this pass:

1. rewrite subsystem overview documents
2. retitle or move the overview files
3. update source code
4. introduce new diagrams unless absolutely necessary
5. expand the scope beyond the three planned file operations without approval
