---
name: edge-context-navigation
description: >-
  Shared context-navigation workflow for all edge-platform agents. Use when: any
  agent needs to explore architecture, mechanisms, or workflows in this repo.
  Navigates docs/ → overview → references → source/sdn_controller/ only when
  needed. Triggers on: exploring subsystems, understanding mechanisms, tracing
  architecture, finding relevant docs.
argument-hint: '<subsystem or topic to explore>'
---

# Edge Context Navigation

## Workflow

When exploring any subsystem, mechanism, or workflow in this repository, follow
this navigation order to minimize token usage and maximize relevance:

1. **Start with `docs/`** — begin with `docs/operation/`. Navigate to the
   specific subsystem folder (elasticity, telemetry, VIP routing, topology,
   selective_sync, testing) and read the **overview** doc first.

2. **Follow the overview's references** — after the overview, drill down into
   the specific files or folders it references, guided by your search purpose.
   Skip unrelated docs unless they provide relevant/meaningful context for the
   current question.

3. **Implementation plans are user-referenced** — do not search for
   implementation plans; they exist only when the user explicitly references
   one. Focus on overview docs and operational docs instead.

4. **Use `source/sdn_controller/` only when needed** — dive into controller
   code only when debugging a specific issue, the docs are known to be
   outdated, or the task requires tracing exact control flow. Prefer docs for
   architectural understanding.

5. **Avoid full-repo dumps** — do not read entire directories or grep widely
   without a target. Lead with the topic → find the doc → read selectively.
