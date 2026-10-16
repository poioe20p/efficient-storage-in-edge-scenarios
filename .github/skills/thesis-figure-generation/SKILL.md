---
name: thesis-figure-generation
description: >-
  Use when: creating, revising, exporting, or wiring thesis figure images
  (editable draw.io PNGs in tese/images/src/). Enforces the draw.io pipeline,
  the STYLE.md visual standard, the ISCTE graphical norms for figures, the
  style checker, the embed-diagram export, the in-place revision policy, and
  the draw.io editing pitfalls learned in practice. Triggers on: new figure,
  edit figure, export figure, drawio, render figure, check_drawio_style,
  STYLE.md, tese/images, figure edit, caption.
argument-hint: '<figure name or source path> [--new | --revise | --export | --verify]'
---

# Thesis Figure Generation

## Scope

Diagram figures drawn in draw.io — one **editable PNG** per figure at
`tese/images/src/<name>.drawio.png` (the cropped render with the diagram XML
embedded), included directly by `main.tex`. Data-result plots from experiment
campaigns are produced by their own analysis scripts (see the
`cross-mode-comparison` skill for campaign graphs); this skill covers the
draw.io pipeline. The normative sources remain
`.github/instructions/thesis-figures.instructions.md` (rules) and
`tese/images/src/STYLE.md` (visual standard) — read both before drawing.
Existing figures such as `control_workflow.drawio.png` and
`vip_routing_sequence.drawio.png` are good style references.

## Iron rules

1. **No AI image models.** Never generate or alter a thesis figure with an
   image-generation model. Every figure is drawn in draw.io and kept as an
   editable PNG with its diagram XML embedded.
2. **Source is truth, and it lives in the PNG.** Edit the diagram XML
   embedded in `tese/images/src/<name>.drawio.png` (extract it, edit it,
   re-export with the diagram embedded); never paint the pixels.
3. **Revise in place.** Re-export over the same
   `tese/images/src/<name>.drawio.png`, so `main.tex` never changes and git
   holds the previous state. The `_vN` naming and the `unused/` /
   `src/superseded/` moves apply to the legacy renders under `tese/images/`.
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
2. Get the diagram XML: extract the embedded chunk from
   `tese/images/src/<name>.drawio.png` into a working `.drawio` under `temp/`
   (or start a new one for a new figure). Hand edits are expected and
   legitimate.
3. Validate: `python tools/check_drawio_style.py temp/<name>.drawio`.
4. Export: `& "C:\Program Files\draw.io\draw.io.exe" -x -f png -o temp\<name>.png temp/<name>.drawio`,
   preview it, then `python tools/build_editable_png.py temp\<name>.png temp/<name>.drawio tese/images/src/<name>.drawio.png`
   to produce the editable PNG (render + embedded diagram XML). The export is
   asynchronous (~seconds) — wait, then confirm the file exists and reopens.
5. Inspect the render visually (open the preview). Check label collisions,
   z-order, alignment, and the checker's label/icon rules.
6. Wire `\includegraphics{images/src/<name>.drawio.png}` in `main.tex` only
   for a new figure — caption below, self-explanatory, immediately after the
   paragraph that first references it (`[H]`). A revision changes nothing in
   the LaTeX.
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

- **Editing without a `.drawio` source.** The diagram travels inside the
  editable PNG: the `tEXt` chunk (keyword `mxfile`, percent-encoded XML) or
  the `zTXt` chunk (keyword `mxGraphModel`, deflated). Extract, edit, and
  re-export with the diagram embedded — the app does the same when it opens
  the file.
- **The CLI's embedded export truncates the PNG**: with `-e` the file ends
  without its closing IEND chunk. Export plain (`-x -f png`) and embed with
  `tools/build_editable_png.py`, or reopen and verify the result; the draw.io
  app writes a valid file.
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
- **Export at 1x, cropped to the content**, with the diagram embedded — that
  is the family's editable-PNG format; a 2x preview is for inspection only.

## LaTeX side (figure wiring)

- Include the editable PNG:
  `\includegraphics[width=…]{images/src/<name>.drawio.png}` — a revision is
  re-exported over the same file, so no LaTeX change is needed.
- Caption **below** the figure, self-explanatory (ISCTE norms §2.2); figure
  captions are centred (preamble `\captionsetup[figure]`), table captions on
  top and justified like the text. Figures may be in colour (§2.1.ii).
- Numbering is chapter-indexed automatically
  (`\numberwithin{figure}{chapter}`) — never number figures by hand.
- Place each float immediately after the paragraph that first invokes it;
  reference it with `\label{fig:...}`/`\ref` and rebuild so the list of
  figures stays in sync.
