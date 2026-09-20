# Thesis figure standard

Authoritative visual and syntax standard for every figure under `tese/images/`.
Derived from, and validated against, `architecture_overview.drawio` — the reference
figure. Any new figure must pass `python tools/check_drawio_style.py <file>`.

## 0. Non-negotiable rules

1. One `.drawio` source per figure in `tese/images/src/`, one PNG render in `tese/images/`.
2. Never overwrite an existing image: a revised figure gets a new name.
3. No legend block and no prose paragraphs inside a figure. Meaning is carried by
   (a) the icon, (b) the colour of the connecting line, and (c) a short label on the
   line itself. The caption carries the prose.
4. Group frames are the only titles a figure may contain.

## 1. Canvas and geometry

| Property | Rule |
|---|---|
| Origin | content starts at positive coordinates; no negative `x`/`y` |
| Page | `pageWidth`/`pageHeight` cover the content bounding box plus a 40 px margin |
| Grid | `gridSize=10`, all coordinates snapped to whole pixels |
| Domain spacing | two domains are separated by a 290 px gap holding the WAN element |
| Congruence | mirror domains by **position only** (`x' = frame_span - (x + w)`); never flip or mirror icons or text |
| Stacking | icons sit on their own row; labels sit ~8 px below their icon |

Reference geometry, domain 1 frame `1111 x 700`, elements in frame-relative coordinates:

| Element | x | y | w | h |
|---|---|---|---|---|
| Client actor | 40 | 43 | 60 | 70 |
| OVS data plane icon | 470 | 60 | 111 | 50 |
| Edge servers icon | 850 | 40 | 73 | 95 |
| Storage icon (+ MongoDB overlay) | 470 (505) | 300 (320) | 95 (30) | 90 (70) |
| Telemetry aggregator icon | 841 | 300 | 70 | 85 |
| SDN controller bitmap | 470 | 545 | 97 | 90 |

## 2. Group frames

```
rounded=1;whiteSpace=wrap;html=1;dashed=1;fillColor=#F4FFFF;
fontFamily=Helvetica;fontSize=18;fontStyle=1;fontColor=#3F3F3F;
verticalAlign=top;align=left;spacingLeft=12;spacingTop=8;
```

Title text, centred at the top inside the frame: `Network domain 1 (LAN 1)`,
`Network domain 2 (LAN 2)`. Centring keeps mirrored domains congruent; a left-aligned
title would sit on the frame's outer edge in one domain and its inner edge in the other.

## 3. Icon vocabulary

Role → shape. Stencil icons keep their own artwork: `strokeColor=none`, no fill override,
except where stated.

| Role | Shape | Colour |
|---|---|---|
| Client workloads | `shape=actor` | `fillColor=#FF6666` |
| OVS data plane | `mxgraph.citrix.switch` | native |
| Containerised edge servers | `mxgraph.citrix.license_server` | native |
| MongoDB edge storage | `mxgraph.networks.storage` + `mxgraph.weblogos.mongodb` overlay | `#99FF99` / `#6881B3` |
| Telemetry aggregator | `mxgraph.office.servers.monitoring_sql_reporting_services` | `fillColor=#FF8000` |
| Emulated WAN link | `mxgraph.citrix.router` | native |
| SDN controller | `shape=image` — `src/assets/controller.png` (269x250, strong blue) | — |

Icons are never recoloured except as listed, never flipped, and never drawn from primitives.
Actor labels are the one exception that may live on the shape itself, via
`verticalLabelPosition=bottom;verticalAlign=top`.

## 4. Typography

| Text | Style |
|---|---|
| All labels and line labels | `fontFamily=Helvetica;fontSize=N;fontStyle=1;fontColor=#3F3F3F` |
| Line labels | same, but `fontColor` = the line's own colour |
| Group titles | `fontSize=N;fontStyle=1;fontColor=#3F3F3F` |

**The label size is relative to the canvas, not absolute.** A label must be at least
**1.6 % of the canvas width**, which prints at ~2.5 mm (7 pt) when the figure spans a
156 mm text block. So `N` is set from the canvas:

| Canvas width | Label size `N` |
|---|---|
| up to 1100 units | 18 |
| ~1650 units | 26 |
| ~2000 units | 32 |
| 2500 units and above | 40 — and the layout should be restructured instead, because at that width the labels needed for legibility start to collide with neighbouring columns |

Typography lives in the **style attribute**, never in inline HTML (`<font …>`) inside the
label value. `fontFamily` is always stated explicitly. Switching the whole family to a serif
face (to match the thesis body) is the single token `Helvetica` -> `Times New Roman`.

## 5. Line language

Colour is meaning. Dash and arrowhead are constants within a class.

| Path | Stroke | Dash | Arrowheads | Label |
|---|---|---|---|---|
| Request data path | `#000000` | solid | `classic` both ends | `http requests`, `data` |
| Observation / telemetry | `#FF8000` | dashed | `classic` at the consumer | `metrics`, `windowed summaries` |
| Control of the data plane | `#007FFF` | dashed | `classic` at the switch | `OpenFlow` |
| Controller ↔ controller | `#007FFF` | dashed | `classic` both ends | `peer topology exchange (host-local)` |
| Resource lifecycle management | `#007FFF` | dashed | `classic` at the resource | `lifecycle management` |

```
data       : edgeStyle=none;html=1;endArrow=classic;startArrow=classic;strokeColor=#000000;
telemetry  : edgeStyle=none;html=1;endArrow=classic;strokeColor=#FF8000;dashed=1;
control    : edgeStyle=none;html=1;endArrow=classic;strokeColor=#007FFF;dashed=1;
```

Lifecycle management shares the control colour on purpose: both are the controller acting,
and the two are separated by their label (`OpenFlow` vs `lifecycle management`). If a distinct
colour is ever wanted for the RQ3 interface, it must be added here first, then to the validator.

## 6. Edge construction

- **An arrow that connects to a component attaches to that component's label box, not to its
  artwork**, whenever the component is drawn as artwork plus a separate label. The same holds
  for any node whose caption is a separate text box. Group frames are the exception: an arrow
  that addresses a group addresses the frame itself, since the frame is a container rather than
  an icon with a caption.
- Labels are the edge's own `value`. Typing the label on the line is the default; a detached
  label cell is not used except when a label physically cannot sit on the line.
- One label may serve several links that cross or overlap — do not repeat the same text.
- Endpoints referencing another shape use `source`/`target`. When an endpoint is a *group*
  (a domain, a pool) rather than a shape, the edge is positioned absolutely with
  `mxPoint` `sourcePoint`/`targetPoint`.
- Orthogonal routing only via explicit waypoints; long runs go through the empty margins of a
  domain, never across an icon.

## 7. Label wording

Short noun phrases, lower case except proper nouns. In use across the family:

- components: `Client`, `OVS Switch`, `Containerised Edge Servers`, `MongoDB Edge Storage`, `Telemetry Aggregator`, `SDN Controller`, `Hosts`, `Edge server N`, `Storage member N`, `Primary`, `Secondary`
- links: `http requests`, `data`, `metrics`, `windowed summaries`, `OpenFlow`, `lifecycle management`, `peer topology exchange (host-local)`, `writes`, `reads`, `replicates oplog`, `heartbeats`, `demand`, `provisioning`, `usable capacity`
- interfaces: `Interface 1 (RQ1)`, `Interface 2 (RQ2)`, `Interface 3 (RQ3)` — drawn in the colour of the path they belong to (orange for observation, blue for control)
- the WAN element only: `Emulated Wide-Area Link (data path only)`

White (`#FFFFFF`) is the neutral fill for a node that has no component icon (a stage box,
a `+` placeholder); it is not a path colour.

## 8. Checklist before a figure ships

1. `python tools/check_drawio_style.py tese/images/src/<figure>.drawio` passes.
2. Export: `draw.io.exe -x -f png -s 2 -o tese/images/<figure>.png tese/images/src/<figure>.drawio`.
3. Every link carries a label; every icon carries a label.
4. Two domains, if present, are congruent.
5. No inline HTML styling, no legend block, no prose.
