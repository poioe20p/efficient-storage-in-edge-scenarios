---
name: thesis-figure-generation
description: >-
  Use when: creating, revising, exporting, or wiring thesis figure images
  (draw.io diagrams in tese/images/src/, PNG renders in tese/images/). Enforces
  the source-controlled draw.io pipeline, the STYLE.md visual standard, the
  ISCTE graphical norms for figures, the style checker, the export CLI, the
  versioning and unused/ policy, and the draw.io editing pitfalls learned in
  practice. Triggers on: new figure, edit figure, export figure, drawio,
  render figure, check_drawio_style, STYLE.md, tese/images, figure version,
  caption.
argument-hint: '<figure name or source path> [--new | --revise | --export | --verify]'
---

# Thesis Figure Generation

## Scope

Diagram figures drawn in draw.io — sources in `tese/images/src/<name>.drawio`,
renders in `tese/images/<name>[_vN].png`. Data-result plots from experiment
campaigns are produced by their own analysis scripts (see the
`cross-mode-comparison` skill for campaign graphs); this skill covers the
draw.io pipeline. The normative sources remain
`.github/instructions/thesis-figures.instructions.md` (rules) and
`tese/images/src/STYLE.md` (visual standard) — read both before drawing.
Existing sources such as `control_workflow.drawio` and
`architecture_overview_v2.drawio` are good style references.

## Iron rules

1. **No AI image models.** Never generate or alter a thesis figure with an
   image-generation model. Every figure is drawn in draw.io from a
   source-controlled `.drawio` file.
2. **Source is truth.** Edit `tese/images/src/<name>.drawio`; never edit the
   PNG render.
3. **Never overwrite a render.** A revised figure gets a new versioned name
   (`_v2`, `_v3`, …) and `main.tex` is updated accordingly; the superseded
   render moves to `tese/images/unused/` (superseded sources to
   `tese/images/src/superseded/`). `tese/images/` holds only images the build
   references.
4. **The checker must pass before export** — fix every FAIL; report any
   remaining WARNs.
5. **Propose before editing** (house rule): thesis visuals are author-owned —
   present the intended change first. If a source is flagged as the author's
   (e.g. "don't touch `demand_to_capacity_chain_v2.drawio`"), leave it alone.
6. **Scratch only in `temp/`** — previews, probes, calibration scripts; delete
   them after use.

## Workflow

1. Read `tese/images/src/STYLE.md` (palette, icon vocabulary, line language,
   typography, genres).
2. Edit the `.drawio` XML directly (hand edits are expected and legitimate).
3. Validate: `python tools/check_drawio_style.py tese/images/src/<name>.drawio`.
4. Export a preview:
   `& "C:\Program Files\draw.io\draw.io.exe" -x -f png -s 2 -o temp\<name>_preview.png tese/images/src/<name>.drawio`.
   The export is asynchronous (~seconds) — wait, then confirm the PNG exists.
5. Inspect the render visually (open the preview). Check label collisions,
   z-order, alignment, and the checker's label/icon rules.
6. Promote: copy to `tese/images/<name>[_vN].png`; wire `\includegraphics` in
   `main.tex` — caption below the figure, self-explanatory; the figure sits
   immediately after the paragraph that first references it (`[H]`).
7. Clean up `temp/` scratch.

## Style checker — what it enforces

`tools/check_drawio_style.py`:

- **Strokes**: only `#000000`, `#FF8000`, `#007FFF`, `#2E7D32`, or none. Red
  is not an allowed stroke — red words are text (`fontColor`) only.
- **No inline `<font>` markup** in labels; style text via cell attributes.
- **Coordinates**: no negatives; whole pixels preferred (fractional → WARN).
- **Page**: must cover the content bounding box + 20 px margin.
- **Icons**: every icon needs a text label below it (within max(90, w) px
  horizontally, −5..70 px vertically).
- **Edges**: every edge carries a label unless the frame is a process genre
  (`genre=` marker — see STYLE.md §8/§9).
- **Twin frames**: similar pale frames (`#F4FFFF` / `#F1F8F1`) must be
  congruent.

## Editing pitfalls (learned)

- **draw.io app re-saves normalize the XML** (attribute order, label
  positions). Re-read the current file before any anchored replacement, and
  after agent edits tell the author to **reload the file in draw.io** so a
  stale open session does not overwrite the changes.
- **Do not regenerate a hand-edited source** with
  `source/scripts/testing/analysis/diagram_thesis_drawio.py`. Its write guard
  keeps existing hand-edited files; the generator still draws the old designs
  and would not match reworked sources.
- **Huge base64 cells**: some sources embed an image as a single ~100 KB
  base64 line — never raw-read or grep the file; dump the XML with a small
  Python script that elides the `base64,` payload.
- **Two colours on one edge** need **separate label cells** (edgeLabel
  children or free cells with pixel offsets), each with its own `fontColor`.
  Label layout follows the edge path — calibrate offsets against a render,
  don't guess.
- **Z-order = document order** (later cells sit on top). A frame title crossed
  by a link must come after the link and carry `labelBackgroundColor` matching
  the frame fill.
- **Bulk text changes**: to change font sizes, edit every text-bearing cell's
  `fontSize` and byte-verify that nothing else changed (diff against a copy).
- **Export at `-s 2`** so the render stays crisp in print.

## LaTeX side (figure wiring)

- Caption **below** the figure, self-explanatory (ISCTE norms §2.2); figure
  captions are centred (preamble `\captionsetup[figure]`), table captions on
  top and justified like the text. Figures may be in colour (§2.1.ii).
- Numbering is chapter-indexed automatically
  (`\numberwithin{figure}{chapter}`) — never number figures by hand.
- Place each float immediately after the paragraph that first invokes it;
  reference it with `\label{fig:...}`/`\ref` and rebuild so the list of
  figures stays in sync.
