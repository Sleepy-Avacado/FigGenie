# Reusable parts library (`assets/symbols/`)

2853 parts: icon 581, motif 1177, shape 275, device 820.
Each file is a standalone SVG in **print pt** (viewBox `0 0 W H`), wrapped in `<g data-symbol="name">`;
copy the inner `<g>` into a figure (`<g data-symbol="name" transform="translate(x,y)">…`) and recolour fills/strokes
by palette role. Colours are as drawn in the source paper. Parts with `provenance: corpus` were cut from
published figures (see `source` in index.json) and are style references only; `original` parts were drawn for this skill.

**The library is a reference, not a limit.** Draw any component the figure needs; match the stroke width,
corner radius and colour roles of the rest of the figure (references/style-rules.md, references/parts-styles.md).

**Mechanism parts** (2261, `subtype: "mechanism"` in index.json) were cut from mechanism figures (walkthroughs,
before/after sequences, state machines, comparisons, component anatomy). They carry a `family` (the drawing idiom,
155 consolidated families listed under `families` in index.json), a `theme`, a `variant` note and
`figure_kinds` (which figure groups the idiom serves). The `device` kind holds the narrative devices of such figures:
ghost copies, frame arrows, delta highlights, check/cross marks, pointers into slots, step badges, lane dividers …
Browse them by theme: `catalog-mech-structures.png`, `catalog-mech-annotations.png`, `catalog-mech-icons.png`, `catalog-mech-logic-time.png`, `catalog-mech-data-flow.png`, `catalog-mech-frames-change.png`, `catalog-mech-graphs.png`, `catalog-mech-steps-traces.png`, `catalog-mech-containers.png`, `catalog-mech-math-code.png`, `catalog-mech-other.png`; search index.json by family / tags / depicts.

Browse: `catalog-icon.png`, `catalog-motif.png`, `catalog-shape.png` (architecture parts); search: `index.json` (name, category, tags, depicts).

| kind | category | count |
|---|---|---|
| device | annotation | 7 |
| device | circuit | 2 |
| device | compute | 75 |
| device | concurrency | 2 |
| device | control | 324 |
| device | data | 125 |
| device | hardware | 27 |
| device | math | 1 |
| device | memory | 41 |
| device | ml | 1 |
| device | network | 93 |
| device | people | 2 |
| device | software | 1 |
| device | status | 83 |
| device | status-misc | 2 |
| device | time | 34 |
| icon | circuit | 1 |
| icon | cloud-infra | 20 |
| icon | compute | 87 |
| icon | control | 13 |
| icon | data | 107 |
| icon | graphics | 1 |
| icon | hardware | 65 |
| icon | memory | 10 |
| icon | memory-storage | 27 |
| icon | ml | 19 |
| icon | network | 51 |
| icon | people | 37 |
| icon | security | 20 |
| icon | software | 19 |
| icon | status | 41 |
| icon | status-misc | 58 |
| icon | time | 5 |
| motif | circuit | 4 |
| motif | compute | 160 |
| motif | control | 145 |
| motif | data | 281 |
| motif | graphics | 1 |
| motif | hardware | 70 |
| motif | math | 3 |
| motif | memory | 125 |
| motif | ml | 3 |
| motif | motif | 180 |
| motif | network | 124 |
| motif | people | 8 |
| motif | software | 3 |
| motif | status | 37 |
| motif | status-misc | 2 |
| motif | time | 31 |
| shape | annotation | 1 |
| shape | compute | 6 |
| shape | control | 78 |
| shape | data | 16 |
| shape | hardware | 16 |
| shape | memory | 1 |
| shape | memory-storage | 1 |
| shape | network | 7 |
| shape | shape | 125 |
| shape | status | 20 |
| shape | status-misc | 1 |
| shape | time | 3 |
