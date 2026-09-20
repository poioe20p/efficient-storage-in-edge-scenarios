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
   adding or moving content; check
   `tese/miscelineous/plan_claim_aligment_with_measured_evidence.md` when the
   text makes empirical claims.
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
   working notes and tracking plans in the same change set.

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
- **Quadros e figuras**: placed near their invocation; chapter-indexed
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

## Terminology ledger

| Use | Never / retired | Notes |
| --- | --- | --- |
| **scale-up / scale-down** | scale-out (retired from prose) | defined in §2.4: adding a unit of capacity to a tier is scale-up, removing one is scale-down |
| **compute tier** | data tier, service tier | the two scaled dimensions are compute and storage |
| **storage tier** | data tier | generic form: "resource tier" |
| **edge-service replicas** (a.k.a. **backends** in the routing context) | — | first-use convention declared in §3.3 |
| **storage member** vs **replica** | — | "replica" = service replica or MongoDB copy; "member" = replica-set member |
| **domain** | site (except in the physical/geographic sense) | bridge sentence in §3.2 |
| **readiness / readiness state → readiness-admission** | boot (for RQ3) | RQ3 = readiness → admission → first serve; boot is out of scope |
| **activation of a prepared reserve** | cold replica creation on the reaction path | storage-action wording rule |
| **Tier~0 / Tier~1 / Tier~2** | unqualified "hot copy" | Tier 1 = capability, held constant where unevaluated |
| **prepared reserve, peer domain, spillover** | — | fixed vocabulary |
| **degradation score, adaptive threshold, telemetry window, idle condition** | — | equations and `where:` lists in `sec:scaling_policy` |
| **the reviewed state of the art / within the reviewed literature** | universal claims | corpus-bounded qualifiers |
| British English: organised, characterisation, utilisation, normalised, behaviour | US spellings in prose | comments may lag |

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
  secondary reads); describe shared-state ownership and handoff, never
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
- Prefer "." or "and" over ";" when splitting scope statements; keep
  sentences bounded; avoid absolutes ("always", "none") unless
  corpus-bounded; hedge unevaluated capabilities ("may be propagated");
  prefer operational verbs (routed through, admitted, withdrawn, drains).
- Formatting: `Tier~0`, `Section~\ref`, `Figure~\ref`, `Chapter~\ref` with
  non-breaking `~`; quotes via `\enquote{}`; en-dash as `--`.

## Verification protocol for every edit

1. Grep old form → zero matches; grep new form → present.
2. Check the file for errors; remind the author to reload `main.tex`.
3. If a claim or count changed, update `tese/Notes/purpose_evidence_map.md`
   and the tracking plans, with the date.
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
- Claim tracking —
  `tese/miscelineous/plan_claim_aligment_with_measured_evidence.md`
- Corpus — `tese/literature_review/README.md`
- Equation-style exemplar — `sec:scaling_policy` in `tese/main.tex`
