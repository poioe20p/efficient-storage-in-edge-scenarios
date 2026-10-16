# Thesis figure standard

Authoritative visual and syntax standard for every figure under `tese/images/`.
Derived from, and validated against, `architecture_overview.drawio` — the reference
figure. Any new figure must pass `python tools/check_drawio_style.py <file>`.

## 0. Non-negotiable rules

1. One **editable PNG** per figure in `tese/images/src/` — `<name>.drawio.png`, the
   render with the diagram XML embedded, so the draw.io app opens and re-exports
   it in place. `main.tex` includes that file directly; there is no separate
   render copy.
2. Revise a figure in place: the embedded diagram is the source and the git
   history holds the previous state. Legacy renders (and their `_vN` names) live
   in `tese/images/unused/`, superseded legacy sources in
   `tese/images/src/superseded/`.
3. No legend block and no prose paragraphs inside a figure. Meaning is carried by
   (a) the icon, (b) the colour of the connecting line, and (c) a short label on the
   line itself. The caption carries the prose. Two bounded exceptions define the
   newer genres: an **interaction figure** (§8) may carry at most two short footer
   lines stating semantics that the arrows cannot carry, and a **process figure**
   (§9) may carry one compact notation key strip.
4. Group frames are the only titles a figure may contain.

## 1. Canvas and geometry

| Property | Rule |
|---|---|
| Origin | content starts at positive coordinates; no negative `x`/`y` |
| Page | `pageWidth`/`pageHeight` cover the content bounding box plus a comfortable margin (the validator requires at least 20 px) |
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

Frames are tinted by the surface they delimit: the default is `#F4FFFF`; a frame
that delimits the data/storage surface uses the storage tint
(`fillColor=#F1F8F1;strokeColor=#4F7D4F`) — e.g. the `VIP_DATA` band of the routing
figure. Nothing else about the frame changes.

In a layered figure, each layer band carries its own pale tint in this order:
control `#F4FFFF`, data plane `#F0F0F0`, resource `#F1F8F1` (the
`platform_layers` figure sets this convention).

Frames of the newer genres declare the genre with a `genre=<name>` token in their
style (`genre=interaction`, `genre=process`). The token never renders; it tells the
validator that the figure is not a twin-domain figure, so the mirror congruence
check does not apply to it.

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
| SDN controller | `shape=image` — `src/assets/sdn_controller_logo.png` (269x250, strong blue; the generator falls back to `controller.png`) | — |

Icons are never recoloured except as listed, never flipped, and never drawn from primitives.
Actor labels are the one exception that may live on the shape itself, via
`verticalLabelPosition=bottom;verticalAlign=top`.

## 4. Typography

| Text | Style |
|---|---|
| All labels and line labels | `fontFamily=Helvetica;fontSize=N;fontStyle=1;fontColor=#3F3F3F` |
| Line labels | same, but `fontColor` = the line's own colour |
| Group titles | `fontSize=N;fontStyle=1;fontColor=#3F3F3F` |

**The label size is relative to the canvas, not absolute.** `N` is sized so the
printed label stays legible at the figure's include width: the family's canvases
(1400–2600 units) use 18–26 px primary labels, newer figures taking the larger
end; auxiliary text (subtitles, notation-key rows) uses 13–20 px. A canvas that
must grow beyond ~2600 units should be restructured instead, because the labels
needed for legibility start to collide with neighbouring columns.

| Canvas width | Label size `N` |
|---|---|
| up to 1100 units | 18 |
| 1400–2600 units | 18–26 (newer figures use 24–26) |
| 2600 units and above | restructure the layout |

Typography lives in the **style attribute**, never in inline HTML (`<font …>`) inside the
label value. `fontFamily` is always stated explicitly. Switching the whole family to a serif
face (to match the thesis body) is the single token `Helvetica` -> `Times New Roman`.

## 5. Line language

Colour is meaning. Dash and arrowhead are constants within a class.

| Path | Stroke | Dash | Arrowheads | Label |
|---|---|---|---|---|
| Request data path | `#000000` | solid | `classic` both ends | `http requests`, `data` |
| Observation / telemetry | `#FF8000` | dashed | `classic` at the consumer | `metrics`, `telemetry summaries` |
| Control of the data plane | `#007FFF` | dashed | `classic` at the switch | `forwarding rules` |
| Controller ↔ controller | `#007FFF` | dashed | `classic` both ends | `peer topology exchange (host-local)` |
| Capacity changes | `#007FFF` | dashed | `classic` at the resource | `capacity changes` |

```
data       : edgeStyle=none;html=1;endArrow=classic;startArrow=classic;strokeColor=#000000;
telemetry  : edgeStyle=none;html=1;endArrow=classic;strokeColor=#FF8000;dashed=1;
control    : edgeStyle=none;html=1;endArrow=classic;strokeColor=#007FFF;dashed=1;
```

Capacity changes share the control colour on purpose: both are the controller acting,
and the two are separated by their label (`forwarding rules` vs `capacity changes`). If a distinct
colour is ever wanted for the RQ3 interface, it must be added here first, then to the validator.
Figures drawn before the 2026-10 de-branding still read `OpenFlow` and `lifecycle management`.

The interaction and process genres (§8, §9) add the message/response classes, the
admission flow, and the lifeline mark:

| Path | Stroke | Dash | Arrowheads | Label |
|---|---|---|---|---|
| Message (interaction) | class colour — `#000000` data, `#007FFF` control | solid for a request | `classic` at target | `1 · HTTP request to VIP_SERVER` |
| Response (interaction) | same colour as its class | dashed | `classic` at target | `response`, `result (SNAT rewrites member → VIP_DATA)` |
| Admission / readiness (process) | `#2E7D32` | dashed | `classic` at the pool | `new replica admitted` |
| Lifeline (interaction) | `fillColor=#B9B9B9` (a 2 px vertex, not an edge) | solid | none | — |

```
message  : edgeStyle=none;html=1;endArrow=classic;startArrow=none;strokeColor=#000000;
response : edgeStyle=none;html=1;endArrow=classic;startArrow=none;strokeColor=#000000;dashed=1;
admission: edgeStyle=orthogonalEdgeStyle;html=1;endArrow=classic;strokeColor=#2E7D32;dashed=1;
```

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

- components: `Client`, `Switch`, `Edge Servers`, `Storage`, `Telemetry Aggregator`, `Controller`, `Hosts`, `Edge server N`, `Storage member N`, `Primary`, `Secondary` (figures drawn before the 2026-10 de-branding carry the branded names `OVS Switch`, `Containerised Edge Servers`, `MongoDB Edge Storage`, `SDN Controller`)
- links: `http requests`, `requests`, `data`, `metrics`, `telemetry summaries`, `telemetry summaries (host-local)`, `forwarding rules`, `capacity changes`, `peer topology exchange (host-local)`, `writes`, `reads`, `replicates oplog`, `heartbeats`, `demand`, `provisioning`, `usable capacity` (legacy figures: `OpenFlow`, `lifecycle management`, `windowed summaries`)
- interfaces: `Interface 1 (RQ1)`, `Interface 2 (RQ2)`, `Interface 3 (RQ3)` — drawn in the colour of the path they belong to (orange for observation, blue for control)
- interaction figures: band titles `VIP_SERVER — service routing surface`, `VIP_DATA — data routing surface`; step labels carry a `N · ` prefix (`1 · HTTP request to VIP_SERVER`) in the figure's own sequence order
- process figures: `demand shift`, `usable capacity`, `[sustained]`, `[not sustained]`, `[timeout]`, `[ready]`, `[compute-bound]`, `[data-access-bound]`, `new replica admitted`
- the WAN element only: `Emulated Wide-Area Link (data path only)`

White (`#FFFFFF`) is the neutral fill for a node that has no component icon (a stage box,
a `+` placeholder); it is not a path colour.

## 8. Interaction figures (sequence shape)

The routing figure (`vip_routing_sequence.drawio`) defines the genre.

- **Header row**: one component icon per column with its label beneath (§3), left to
  right in conversation order. Below each header a **lifeline** drops as a 2 px
  `#B9B9B9` vertical.
- **Surfaces**: each phase of the conversation is a group frame (§2) spanning the
  columns, titled `VIP_SERVER — service routing surface` / `VIP_DATA — data routing
  surface`; the data surface carries the storage tint, and both frames declare
  `genre=interaction`.
- **Messages**: single-headed arrows (§5) with `labelBackgroundColor=#FFFFFF`; a
  self-call is a white box attached to the owning lifeline.
- **Qualifiers** on a flow are note chips: white fill, `#8A8A8A` stroke, folded corner.
- At most two short **footer lines** may close the figure when they state system
  semantics the arrows cannot carry (e.g. SNAT rewriting on the return path).
- Numbers in the step labels belong to this figure's own sequence (1..N); they are
  not shared with the process figure's instrumented-event badges.

## 9. Process figures (context shape)

The control-workflow figure (`control_workflow.drawio`) defines the genre.

- **Columns** are the execution contexts: one group frame per context, title plus a
  one-line subtitle inside the top of the frame; frames declare `genre=process`
  (the validator then leaves plain activity flows unlabelled, and the congruence
  check does not pair the columns).
- Node vocabulary (Helvetica, no shadows):

| Role | Shape | Style |
|---|---|---|
| Action | white rounded rectangle | `fillColor=#FFFFFF;strokeColor=#3F3F3F` |
| Decision | rhombus | `strokeColor=#8A6D2A`; guard condition in brackets on each branch |
| Object node | grey rounded rectangle | `fillColor=#F0F0F0;strokeColor=#8A8A8A` |
| Note | note chip | white fill, `#8A8A8A` folded corner |
| Start node | solid black circle, 18 px | `fillColor=#000000` |
| Activity final | green ring with a filled dot | `strokeColor=#2E7D32` |
| Flow final | ring with an X | black |
| Instrumented event | numbered badge, white circle, `#2E7D32` ring | numbered in step order; the caption states what each number marks |

- **One compact notation key** (sample + `= meaning` as text pairs, one row at the
  bottom) is the only legend-like device permitted anywhere in the family (the
  bounded exception of §0.3).

## 10. Checklist before a figure ships

1. `python tools/check_drawio_style.py tese/images/src/<figure>.drawio` passes.
2. Export the editable PNG — cropped to the content, 1x scale, diagram embedded
   (draw.io app: Export, Crop + "include a copy of my diagram"). This build's
   CLI drops the closing IEND chunk when `-e` is used: export plain
   (`draw.io.exe -x -f png -o temp/<figure>.png <source>`) and embed the diagram
   with `python tools/build_editable_png.py temp/<figure>.png <source>
   tese/images/src/<figure>.drawio.png`, then reopen the result to confirm it
   loads.
3. Every link carries a label; every icon carries a label (genre figures: plain
   activity flows may stay unlabelled, by the genre marker).
4. Two domains, if present, are congruent; genre-marked frames are exempt.
5. No inline HTML styling; no legend block and no prose beyond §0.3's two exceptions.
