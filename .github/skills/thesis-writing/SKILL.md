---
name: thesis-writing
description: 'Use when: adding, revising, or reviewing any content under tese/ (main.tex chapters, paragraphs, equations, tables, captions, terminology, notes) so that it complies with the thesis house standards. Aggregates the ISCTE graphical norms, reference-thesis conventions, the settled terminology ledger, claim-evidence discipline, citation and figure rules, and the propose-approve-verify workflow. Triggers on: write thesis, add section, revise paragraph, reframe, new equation, table, caption, terminology, wording, thesis standards, ISCTE norms.'
argument-hint: '<file/section and the intended change>'
---

# Thesis Writing Standards

## Outcome

Content added or revised anywhere under `tese/` conforms to the ISCTE
graphical norms (2020), the reference-thesis house conventions, the settled
terminology ledger, and the claim–evidence discipline. This skill is the
aggregated home of the writing standards defined across sessions. The two
instruction files `.github/instructions/thesis-citations.instructions.md`
and `.github/instructions/thesis-figures.instructions.md` remain the
normative sources for citations and figures and are referenced here, not
duplicated. Scope: `tese/**` content; `source/`, `docs/` and scripts follow
their own instructions.

## How this skill should be used

Invoke it whenever an agent is about to create or modify content in `tese/` —
a paragraph, an equation, a table, a caption, a terminology choice, a working
note — or when asked whether an edit "is standard / consistent with the
thesis".

Procedure, in order:

1. **Read first.** Re-read the target region of `tese/main.tex` immediately
   before changing anything — the author edits between sessions, so cached
   text may be stale. When documents disagree, `main.tex` is the source of
   truth.
2. **Check the rules.** Scan the Terminology Ledger below; check
   `tese/Notes/thesis_structure.md` for chapter and section conventions when
   adding or moving content.
3. **Propose before editing.** Present the exact old → new text and the
   reason, and name the rule that applies (e.g., "Terminology Ledger: storage
   tier"; "ISCTE §2.2: figure caption below"). Wait for explicit approval.
   Never edit a `tese/` file (or any non-`temp/` file) without it. Throwaway
   scratch files may go in `temp/` without approval and are deleted after
   use.
4. **Apply minimally.** Use anchored replacements; preserve surrounding
   style (indentation, `~`, `--`, labels); keep one logical change set per
   batch; delegate multi-file edits to subagents.
5. **Verify.** Grep the old form (must return zero matches) and the new form
   (must be present); check the file for errors; remind the author to reload
   `main.tex`.
6. **Sync notes.** If the change touched a term, count, or claim, update the
   working notes (`tese/Notes/`) in the same change set.

For literature claims, additionally run the **audit protocol**: verify every
claim against the paper's stored extraction (the `.txt` next to the PDF),
quote the supporting sentence verbatim, classify it (supported / partial /
not supported), and phrase the claim corpus-bounded — never generalise
beyond the reviewed works.

## Hard rules — ISCTE graphical norms (2020)

Source: `tese/miscelineous/1594736316665isctenormasgraficas2020.pdf`
(partial text: `normas_graficas.txt`).

- **Document order**: cover → sub-cover → dedication/acknowledgements →
  Resumo (PT) → Abstract (EN) → indices (including figures/tables) →
  glossary (acronyms/symbols — the `\acronyms{}` block) → body (Introduction
  → chapters → Conclusion) → sources → references → annexes A/B/C.
- Resumo and Abstract: ≤250 words, 3–6 keywords each.
- Typography (template-controlled; do not hand-format): Times New Roman
  11/12 or Arial/Calibri 11; black text; 2.5 cm margins; 1.5 spacing,
  justified. Writing rules: **bold only for headings; italics for
  emphasis**; no underline; the first paragraph after a heading is not
  indented.
- **Quadros e figuras**: placed near their invocation — each float (figure
  or table) sits immediately after the paragraph that first references it,
  and floats are distributed through the section, never clustered at its
  end; chapter-indexed
  numbering; **table captions on top (justified); figure captions below,
  centred, self-explanatory**. `main.tex` currently complies — keep it so.
- **Equations**: displayed, centred, numbered in parentheses with arabic
  numerals (chapter indexing allowed) — matches the template's numbering.
- **Annexes**: Anexo A, B, … with the same status as chapters.
- **References**: DCTI follows **IEEE** — the preamble's biblatex already
  uses `style=ieee`; do not change the style.
- **Dimension**: the body is page-limited for ISTA master's dissertations
  (≈50 pp; general-case row 60; references, sources and annexes excluded).
  Keep the body lean; run matrices, configs, code and tool background belong
  in the appendix.

## House structure conventions (reference theses)

- RQs live in their own §1.3 section, separate from the objectives (Polónio
  §1.3, Cuco §1.6). RQ labels are **italic lead-ins only in §1.3**
  (`\textit{RQ1}` … `\textit{RQ3}`); elsewhere they appear bare — "(RQ1)".
  The same pattern applies to DRs: italic enumerate labels in §3.1
  (`\textit{DR\arabic*:}`), bare references in prose ("DR3 and DR4").
  Direct RQ mentions are concentrated in Ch1, the Ch2 gap table, results
  headings and Ch6; the single §3.3.2 anchor ("the interface examined for
  RQ3") is intentional.
- Objectives: one compact paragraph. Contributions: a separate list (four
  items; the platform is the measurement instrument, not a defended
  deliverable).
- Methodology fills §1.4 (DSRM; Cuco §1.7, Polónio §1.4).
- Ch3 is conceptual design; Ch4 carries only implementation deltas — never
  describe the same mechanism twice (pairs §3.3/§4.2, §3.4/§4.3, §3.5/§4.4).
- Conclusions map each RQ to a finding (Polónio Ch6 answer table, Cuco §6.1
  numbered answers).
- Implementation text (`tese/miscelineous/some_guidelines.md`): pseudo-code
  first, then an explanatory figure, then key code; large code in the
  appendix; a positive experimental outcome supports a hypothesis but never
  "proves" it.
- Results: one summary table per claim, one representative figure per RQ;
  synthesise only from segments measured under a common workload/config.
- Chapter 5 graph-like figures: use
  `source/scripts/testing/analysis/thesis_figure_style.py`. Configuration
  colours follow one fixed order across RQ1, RQ2 and RQ3 — grey (position 1,
  the first configuration shown, i.e. the figure's reference rather than a
  methodological control label), blue (2), orange (3), green (4). Red is
  annotation-only, never a configuration colour. RQ2 colours by scaling
  policy; components and presses are separated by panel, not by a second
  colour set.
- Campaign design tables: the RQ1/RQ2/RQ3 design tables share one 5-row
  skeleton, same names and same order — Treatment, Workload, Replication,
  Test, Expectations. Cells may differ in length; the row set never does.
  Held constants are stated once in §5.1.4; the exclusions pointer there
  leads to the limitations section (§6.3). Neither is repeated per table.
  The experimental axis (RQ2's two presses, RQ3's three message
  conditions) lives in Workload (and is named in Treatment), not in an extra
  row.

## Terminology ledger

| Use | Never / retired | Notes |
| --- | --- | --- |
| **scale-up / scale-down** | scale-out (retired from prose) | defined in §2.4: adding a unit of capacity to a tier is scale-up, removing one is scale-down |
| **scaling action** | capacity action (retired 2026-10-03) | the unit the decision point selects and hands to the infrastructure (compute or storage scale-up); decision-side counterpart: **scaling decision** (retired attributive "scaling-action selection", 2026-10-10) |
| **action gate** | selection gate (retired 2026-10-10) | the gate in §4.3 that commits at most one scaling action per window; parallel to **readiness gate** |
| **arm** | cell (retired 2026-10-03); arm/arms in prose (retired 2026-10-18) | one tested configuration of a campaign. Name it with the campaign's own unit: telemetry mode (RQ1), scaling policy (RQ2), admission mode or condition (RQ3); "configuration" or "set" only when speaking across campaigns |
| **telemetry mode** (push, delayed push, polling, sampled push) | telemetry delivery semantics; delivery semantics; delivery mode; delivery treatment; event-preserving; delayed event-preserving; latest-state (all retired 2026-10-09); arm (2026-10-18) | RQ1's four modes, one per run; fixed RQ wording in §1.3 ("affect how the controller scales the service when load rises"); the RQ1 episode is "the load rise"; raw source literals (`event_preserving`, `delayed_event_preserving`, `poll`, `sampled_push`) only as config values in Table~\ref{tab:impl_delivery_sources} and the appendix |
| **run** | lane (retired 2026-10-03) | a single campaign execution; "replicate" = run within a design block |
| **load balancing** | backend selection, backend selector, selection policy, unit selection (retired 2026-10-10) | the function that chooses the backend for a new flow; the controller performs it with the cost function of §3.3.2; the readiness/vip sections say a unit "becomes eligible for load balancing". It is a held-constant mechanism, never an evaluated interface: no RQ varies the selection policy. The evaluated interface at that seam is **readiness admission**, i.e. how a backend enters the set selection draws from; §2.5 is titled "Readiness Admission in SDN Load Balancing" and states that selection among admitted backends is held fixed. Never let a section title or a review bucket imply load balancing is studied |
| **routing pool** | selector's eligible pool (retired) | the set a unit enters on admission and leaves on removal |
| **absorption margin** | absorbing margin (typo form) | the base fleet's spare capacity that absorbs delay while new capacity starts |
| **operating envelope** | evaluated envelope (retired) | the evaluated operating conditions; resource-side bounds are "resource limits" |
| **compute tier** | data tier, service tier | the two scaled dimensions are compute and storage |
| **storage tier** | data tier | generic form: "resource tier" |
| **compute replicas** (a.k.a. **backends** in the routing context) | edge-service replicas, service replicas (retired 2026-10-03) | the scaled units of the compute tier; the running container is the edge server; first-use convention declared in §3.3 |
| **storage member** vs **replica** | — | "replica" = compute replica or MongoDB copy; "member" = replica-set member |
| **domain** | site (except in the physical/geographic sense) | bridge sentence in §3.2 |
| **readiness / readiness state → readiness-admission** | boot (for RQ3) | RQ3 = readiness → admission → first serve; boot is out of scope; in its simplest form: a ready backend starts receiving traffic |
| **admission mode A / B / C / D** (backend notification; notification with a fallback check; periodic polling; notification with a confirmation check) | admission rule; message only; message with a bounded re-check; periodic check; direct lifecycle notification, lifecycle-coupled admission, probe fallback variant, hybrid, periodic discovery, reconcile, wake-and-verify, wake-verify (all retired from RQ3 prose; wake-and-verify un-parked and evaluated 2026-10-13 as mode D) | RQ3's four evaluated modes, the story told in the operational trio (A, C, D) with B as the recovery-without-verification control; "notification" names the backend's act of declaring readiness (survives only in the mode names), and "message" is that announcement as the object whose conditions the results describe; each matrix position is a mode × condition pairing over seven seed-matched blocks; letters A--D introduced once in the results design table; raw config literals (`direct`, `discovery`, `wake_verify`) only in the appendix |
| **readiness message** | readiness claim, readiness notification, readiness signal, readiness event (prose forms; `app_ready` remains the implementation literal) | the message the backend sends when its readiness predicate first succeeds; the word "notification" survives only in the admission-mode names, where it names the backend's act of declaring readiness |
| **check** (checking the backend) | probe, discovery (retired for RQ3 2026-10-11) | the controller's request to the backend's readiness endpoint; "fallback check" = the check a wait-then-check form runs when the message never arrives; the confirmation check = the check an arriving message wakes |
| **condition** (intact / lost / premature) | fault arm, fault cell (in RQ3 prose) | the three states of the readiness message evaluated in RQ3, each held for the whole run; first use is the arrival-property triple "the message arrives intact, never arrives, or arrives before the backend can serve", sometimes introduced as "three message conditions"; prose then uses "under a lost message", "under a premature message"; "premature" is the table shorthand; the evaluated lead is 10 s |
| **activation of a prepared reserve** | cold replica creation on the reaction path | storage-action wording rule |
| **storage admission** | reserve activation, storage add, added storage unit | the activation of a prepared reserve; a per-domain admission count includes the preparation of the replacement reserve and is an event count, not a concurrent member count |
| **Tier~0 / Tier~1 / Tier~2** | unqualified "hot copy" | Tier 1 = capability, held constant where unevaluated |
| **prepared reserve, peer domain, spillover** | — | fixed vocabulary |
| **handover** | handoff, hand-off | the step-to-step transition; attributive form: **handover delay** |
| **summary** (first use: **telemetry summary**) | window, telemetry window, windowed summary, update (retired 2026-10-10 for the delivered object) | one aggregator report covering the last 10~s; the object the modes deliver and the policy evaluates; "window" survives only for lengths of time (exposure, release, onset, in-flight, warm-lease, scale-up/down) |
| **degradation score, adaptive threshold, idle condition** | — | equations and `where:` lists in `sec:scaling_policy` |
| **pre-dispatch wait** | — | the first request-path interval; boundary at **dispatch** (where the edge service time starts); read only as a difference (user-visible latency minus edge service time); contents enumerated in §4.4 |
| **the reviewed state of the art / within the reviewed literature** | universal claims | corpus-bounded qualifiers |
| British English: organised, characterisation, utilisation, normalised, behaviour | US spellings in prose | comments may lag |
| **compute-only / storage-only** (fixed RQ2 policies) | compute-first, storage-first (retired from prose) | the fixed scaling policies scale a single tier only; introduced with the bottleneck gloss in §5.3 |
| **compute-bound press / mixed press / data-access press** (RQ2 demand episodes) | compute-bound episode, data-access-bound episode (retired 2026-10-18 for RQ2); compute-first/storage-first (retired) | the three evaluated presses: compute-bound = hash-only, no storage reads, processing binds first; mixed = interactive requests plus content lookups, processing binds first; data-access = read-heavy content serving, the storage member binds first |
| **scaling policy** (no scaling, compute-only, storage-only, bottleneck-aware) | adaptive policy, adaptive action, both-tier policy (as names); arm (2026-10-18) | RQ2's four configurations, one run per policy per demand episode; the policy that selects the pressed tier is always "bottleneck-aware" |
| **bottleneck-aware selection** | both-tier policy, adaptive policy, adaptive action (as names); arm | RQ2's adaptive policy; gloss "scales compute and storage according to the pressing demand"; commits one tier per action, so both tiers can be scaled in sequence |
| **no scaling** | no-action arm, no-action comparator, inaction (as a name) | RQ2's control policy, the platform without elasticity |

Hyphenation: attributive hyphen — "replica-set primary/membership/
extension", "edge-service capacity/replicas"; open as nouns — "MongoDB
replica set", "edge servers/services".

## Claim and evidence discipline

- Every claim maps to measured evidence, or is explicitly labelled design /
  capability / held-constant / context.
- No summed cross-experiment effect sizes; no "most important interface"
  claim; scope notes where relevant (emulated two-domain single-host
  testbed; **no geo-distributed WAN performance claim** — phrase as
  evaluation focus plus controlled conditions, and leave the limitation
  itself to Ch6; the evaluated data path is single-site).
- Honesty guards: report unmet gates and exclusions (storage p95 gate, RQ1
  bimodality, OOM exclusions, unmetered replica-sync bandwidth); qualify
  RQ3 admission timestamps (registered vs pool-included vs first flow);
  include the consistency contract (primary writes, eventually consistent
  secondary reads); describe shared-state ownership and handover, never
  claim "no shared mutable state"; Tier 2 topics (HA, security) get at most
  one §6.4 one-liner.
- Counts (works, runs, n) must reconcile with the corpus README and run
  folders before being written.

## Citations and figures

- Citations — `.github/instructions/thesis-citations.instructions.md`:
  cite only papers whose PDFs are in `tese/literature_review/**`; propose
  out-of-corpus candidates (title, DOI, relevance) for the author to
  download instead of adding them; add BibTeX only for cited works, via
  `tools/add_bib_from_doi.py`; use `\textcite` / `\parencite` (biblatex
  IEEE); never fabricate references.
- Figures — `.github/instructions/thesis-figures.instructions.md`: drawio
  source in `tese/images/src/`, STYLE.md visual standard, ISCTE graphical
  norms for captions, checker + export pipeline, new versions get new
  filenames (`_vN`), superseded renders move to `tese/images/unused/`;
  never use an AI image generator for a thesis figure.

## Equations and notation

- The shared tier-generic policy lives in `sec:scaling_policy`; other
  sections reference it and never duplicate formulas.
- Every equation gets `\label{eq:...}`; reference with `\eqref{}` or
  `Equation~\ref{}`.
- Each equation is followed by a `where:` item list — items formatted
  `$x$ -- description;` (final item ends with "."); no notation tables
  (Polónio convention).
- Decision logic that binds several formulas uses the fixed-order enumerate
  pattern (eligibility → score → scale-up condition → idle condition),
  linking each step to its equation.
- Label prefixes: `ch:`, `sec:`, `fig:`, `tab:`, `eq:`.

## Prose style

- British English throughout.
- Semicolons are reserved for separating items within a list (including
  table cells). Never join independent clauses with a semicolon. Use a
  full stop or rephrase instead.
- Colons are reserved for introducing a list. Never join a clause to its
  explanation, consequence, or restatement with a colon; use a full stop.
  For example, write "the storage tier is itself a live capacity. When the
  pressure sits in the data, adding instances does not relieve it", not
  "the storage tier is itself a live capacity: when the pressure sits in the
  data, adding instances does not relieve it".
- Prefer minimal, simpler terminology. Use the shortest word or
  construction that keeps the claim exact, and replace formal or inflated
  variants with plain ones wherever nothing is lost (for example, "starts
  later" over "inherits the difference in onset"). Keep established metric
  names as they are.
- Keep sentences bounded. Avoid absolutes ("always", "none") unless
  corpus-bounded. Hedge unevaluated capabilities ("may be propagated").
  Prefer operational verbs (routed through, admitted, withdrawn, drains).
- Formatting: `Tier~0`, `Section~\ref`, `Figure~\ref`, `Chapter~\ref` with
  non-breaking `~`; quotes via `\enquote{}`; en-dash as `--`.
- No ---
- Simple, clear and minimal wording.

## Verification protocol for every edit

1. Grep old form → zero matches; grep new form → present.
2. Check the file for errors; remind the author to reload `main.tex`.
3. If a claim or count changed, update `tese/Notes/purpose_evidence_map.md`
   with the date.
4. Never delete corpus extractions; new extractions are stored next to
   their PDF.

## Source pointers

- ISCTE norms — `tese/miscelineous/1594736316665isctenormasgraficas2020.pdf`
  (partial `normas_graficas.txt`)
- External guidelines — `tese/miscelineous/some_guidelines.md`
- Reference theses — `tese/miscelineous/master_*.md` (Polónio = primary
  house reference)
- Working notes — `tese/Notes/thesis_overview.md`, `thesis_structure.md`,
  `purpose_evidence_map.md`, `gaps_weakness.md`, `scope_assumptions.md`
- Claim tracking — retired 2026-10-07
  (`tese/miscelineous/plan_claim_aligment_with_measured_evidence.md`); use
  `tese/Notes/purpose_evidence_map.md` and git history
- Corpus — `tese/literature_review/README.md`
- Equation-style exemplar — `sec:scaling_policy` in `tese/main.tex`
