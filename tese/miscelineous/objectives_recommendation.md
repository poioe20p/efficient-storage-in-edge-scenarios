 0

# Objectives Section — Recommendation

> **Purpose:** draft recommendation for `tese/main.tex` §1.2 (`sec:objectives`),
> produced 2026-08-14. **Not yet applied** — for review and approval.
> Companion blueprint: `tese/Notes/thesis_structure.md` (§1.2 row).
> Rationale grounded in three MSc theses from the same program and advisor
> lineage (José Moura / Rui Marinheiro).

---

## 1. The house standard (three ISCTE theses)

Three MSc theses from the same program (*Mestrado em Engenharia de
Telecomunicações e Informática*) and the same advisor lineage were inspected
for how they frame objectives:

| Thesis                                                                                                                                                                      | Objectives section                                                                | Research questions       | Method                                | Loop closure                          |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------ | ------------------------------------- | ------------------------------------- |
| **Polónio (2024)** — *Proactive Discovery and Mitigation of Security Vulnerabilities Leveraged by SDN* (local: `miscelineous/master_joao_rosa_polonio_Sdn.pdf`) | §1.2 —**1 primary + 2 secondary**                                         | §1.3 — separate, 4 RQs | §1.4 DSRM (named)                    | Ch.6 — RQ→answer**table**     |
| **Cardoso (2019)** — *A Software-Defined Network Solution for Managing Fog Computing Resources in Sensor Networks* (`hdl.handle.net/10071/22190`)                | §1.2 "Research Questions and Objectives" —**1 RQ + 1 main goal sentence** | same section, 1 RQ       | §1.3 Investigation Method (informal) | Ch.5 — restates RQ, answers in prose |
| **Cuco (2023)** — *Alternative Architecture Approaches for Distributed Control of Smart Buildings* (`hdl.handle.net/10071/30607`)                                | §1.5 "General Objective" —**one sentence**                                | §1.6 — separate, 3 RQs | §1.7 DSR (named, 6 activities)       | Ch.6 — restates RQs, answers each    |

**The common pattern (the standard):**

1. **One primary objective** — a single aim sentence stating the research
   contribution, not a list of process steps.
2. **Research questions in a separate section** — they drive the investigation
   and are answered in the conclusions.
3. **A named method** (DSR/DSRM) mapped onto the thesis.
4. **Loop closure** — the conclusions return to the RQs and answer each one.

None of the three theses lists a flat set of "objectives". The proposal's six
objectives (review → design → implement → experiment → evaluate → interpret)
are work-package milestones, not research objectives.

---

## 2. Implications for this thesis

- Keep the **single-sentence main objective** (the central-theme framing) as the
  aim; add a small set of secondary objectives (Polónio precedent).
- Use the thesis's **own interface vocabulary**: *telemetry delivery → scaling
  action selection → traffic admission* (RQ1–RQ3). Avoid the background triad
  *monitoring, load balancing, scaling* — that is the "unexamined default"
  framing, not the contribution.
- Frame **co-location as the experimental apparatus** that suppresses the
  coordination gap (the handoff delays between separate control loops), which
  exposes each interface to direct measurement. This is an apparatus-level
  property, not a superiority claim. Making each interface independently
  variable is itself a deliberate design of the apparatus, because co-location
  couples the components (varying one in isolation is harder than in a
  decoupled design).
- **Methodology/validation is not an objective** — it belongs to §1.4 (DSRM,
  Peffers et al.).
- Keep **§1.3 Research Questions separate**; the conclusions (§7.1) should map
  each RQ to its finding.

---

## 3. Proposed text

```latex
% PROPOSED: tese/main.tex §1.2 (sec:objectives)

\section{Objectives}\label{sec:objectives}

The main objective of this thesis is to investigate and characterise the
interfaces between telemetry delivery, capacity action selection, and traffic
admission in a stateful edge service operating under varying demand shifts.
The investigation rests on the idea that co-locating these functions in a
single control process suppresses the coordination gap, the handoff delays
that accumulate when monitoring, scaling, and routing run under separate
control loops, and thereby exposes each interface to direct measurement. With
no cross-component handoffs, the delay contributed by an interface can be
attributed to that interface alone. This is an apparatus-level property, not
a claim that co-location is superior. Because the co-located components are
coupled, making each interface independently variable is itself a deliberate
design of the apparatus, which lets each interface be varied in isolation
while the others are held constant, and its impact on the time from demand to
usable capacity measured across different demand scenarios.

To pursue this objective, the thesis addresses the following specific goals:
\begin{itemize}
    \item to design and implement a co-located SDN-based apparatus in which the
    three interfaces can be configured and varied independently;
    \item to characterise how telemetry delivery semantics affect the scaling
    and traffic-admission behaviour of the service;
    \item to characterise how the capacity action selected in response to the
    observed bottleneck (compute or storage scale-out) shapes service behaviour;
    \item to characterise how readiness propagation affects the time until
    newly provisioned capacity begins to serve traffic; and
    \item to reconstruct the demand-to-usable-capacity timeline and relate
    which interface matters under which scenario.
\end{itemize}
```

---

## 4. Notes

- The five secondary goals map one-to-one to the three RQs, the apparatus, and
  the synthesis. The original sixth item (methodology/validation) moves to §1.4.
- Vocabulary: "telemetry delivery / capacity action selection / traffic
  admission" are the measured interfaces (see `tese/Notes/thesis_overview.md`
  §6 and the title options in `tese/Notes/thesis_structure.md` §1).
- Typos to avoid from earlier drafts: "statefull" → stateful; "eliminates" →
  elements.
- Co-location vs decoupling trade-off: independent control loops give
  modularity (each component easy to swap) but keep the coordination gap; one
  shared control loop removes the gap but couples the components. The thesis
  deliberately trades modularity for measurability: co-location removes the
  handoffs as a confound, and independent variation is engineered into the
  apparatus, not a free consequence of co-location.
