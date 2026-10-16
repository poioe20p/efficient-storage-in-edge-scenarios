---
description: "Thesis figure generation rules: source-controlled drawio figures only, the STYLE.md visual standard, the ISCTE graphical norms, the checker + export pipeline, naming and the unused/ policy."
applyTo: "tese/**"
---

# Thesis Figures

All figures under `tese/images/` follow the same pipeline. Apply these rules
whenever a figure is created, revised, referenced, or moved.

## Generation

- **Never generate a thesis figure with an AI image model.** Every figure is
  drawn in draw.io and kept as one **editable PNG**:
  `tese/images/src/<name>.drawio.png`, the render with the diagram XML
  embedded. `main.tex` includes that file directly, so revising a figure never
  changes the LaTeX.
- The visual and syntax standard is `tese/images/src/STYLE.md` — read it before
  drawing and use its icon vocabulary, palette, line language, and typography.
  Figures of the interaction or process genre (§8/§9 of STYLE.md) carry a
  `genre=` marker in their frame styles; the validator applies the genre rules
  (unlabelled activity flows are allowed in process figures; frames are not
  paired for congruence) when it sees the marker.
- The ISCTE graphical norms
  (`tese/miscelineous/1594736316665isctenormasgraficas2020.pdf`) also apply:
  figures may be in colour (§2.1); every figure has a caption **below**,
  centred and self-explanatory (§2.2); figures appear near their invocation in
  the text.

## Validate and export

1. `python tools/check_drawio_style.py <source>.drawio` must pass. The editable
   PNG carries the diagram XML: extract it to a scratch `.drawio` (or keep the
   working source in `temp/`) to run the checker.
2. Export the editable PNG — cropped to content, 1x scale, diagram embedded —
   to `tese/images/src/<figure>.drawio.png`. The draw.io app's export (Crop,
   "include a copy of my diagram") is the reference; this build's CLI drops the
   trailing IEND chunk when `-e` is used, so export plain and embed the diagram
   with `python tools/build_editable_png.py <render.png> <source> <out.png>`,
   then reopen the result.

## Naming and placement

- Floats are placed adjacent to the paragraph that first references them:
  each figure and table sits immediately after its referencing paragraph,
  and floats are distributed through the section, never clustered at its
  end. `main.tex` uses `[H]` for figures, so source order is rendered order;
  tables that should not drift use `[H]` as well.
- Revise a figure in place: edit the diagram inside
  `tese/images/src/<figure>.drawio.png` and re-export over the same path, so
  `main.tex` never changes; git holds the previous state. The `_vN` naming
  applies to the legacy renders under `tese/images/`.
- `tese/images/` holds only images referenced by the build (`main.tex`,
  `preamble.sty`). Superseded legacy renders move to `tese/images/unused/`;
  superseded legacy sources move to `tese/images/src/superseded/`.
