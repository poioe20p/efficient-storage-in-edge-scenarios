---
description: "Thesis figure generation rules: source-controlled drawio figures only, the STYLE.md visual standard, the ISCTE graphical norms, the checker + export pipeline, naming and the unused/ policy."
applyTo: "tese/**"
---

# Thesis Figures

All figures under `tese/images/` follow the same pipeline. Apply these rules
whenever a figure is created, revised, referenced, or moved.

## Generation

- **Never generate a thesis figure with an AI image model.** Every figure is
  drawn in draw.io: a `.drawio` source in `tese/images/src/` and its PNG render
  in `tese/images/`.
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

1. `python tools/check_drawio_style.py tese/images/src/<figure>.drawio` must pass.
2. Export:
   `draw.io.exe -x -f png -s 2 -o tese/images/<figure>.png tese/images/src/<figure>.drawio`.
   Figures can also be regenerated via
   `source/scripts/testing/analysis/diagram_thesis_drawio.py`.

## Naming and placement

- Never overwrite an existing render: a revised figure gets a new versioned
  name (`_v2`, `_v3`, …) and `main.tex` (or the generator script) is updated.
- `tese/images/` holds only images referenced by the build (`main.tex`,
  `preamble.sty`). Superseded renders move to `tese/images/unused/`; superseded
  sources move to `tese/images/src/superseded/`.
