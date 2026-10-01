# scripts/ — tools the agent runs while drawing

All tools work on SVG files that follow the contract in `references/spec-guide.md` §4
(viewBox `0 0 W H` in pt, one `<g id="n:..|e:..|c:..|l:..|s:..|a:..|legend">` per spec element,
text kept as `<text>`, bitmaps as `<image>` linked to a local PNG / JPEG by a path relative to the SVG —
never a URL). Requirements: python3 with lxml, Pillow and playwright (+ `playwright install chromium`);
`fontTools` is optional (font subsetting; anaconda ships it). Formulas need `node` ≥ 18 (`mathjax/`, `npm install` once, done
automatically on first use); the PowerPoint export needs `python-pptx` and Office's `mathml2omml.xsl` for native equations.

| script | what it does | typical call |
|---|---|---|
| `spec_validate.py` | schema + referential + style-budget checks on a figure spec | `spec_validate.py fig.json` |
| `measure_text.py` | width/height in pt of labels in a shipped font, to size boxes before drawing; mixed text is split into script runs and CJK runs are measured with `--cjk` (default `cjk_default`); `--box` prints the box size | `measure_text.py --font source-sans --size 6.5 --box "KV 缓存"` |
| `render.py` | SVG → PNG in headless Chromium (fonts from `assets/fonts` injected, CJK companion auto-added; bitmaps loaded from the SVG's folder, URLs never fetched); `--crop x0,y0,x1,y1` zooms into one region; `--bbox` dumps every element's box | `render.py fig.svg --scale 6 --crop 220,110,296,176` |
| `lint.py` | geometry / style / spec linter: bleed, overflow, overlap, containment, alignment, centring, dangling edges, colours, density, spec ids (text is measured on its glyph ink band, 0.75 em above / 0.25 em below the baseline); since 2026-09-10 also `font.glyph` (characters no embedded face covers), `edge.head-overlap` / `edge.tail-near-line` (arrowhead or tail on a foreign line such as a tier divider), `replica.step` (uneven ledges on ×N card stacks), `title.centre` / `gutter.centre` (container title centred in its headroom, rotated gutter label centred in its gutter); since 2026-09-20, for `meta.kind = mechanism` (column band from `references/mechanism/style-thresholds.json`, budgets label-distinct, `n:<id>@<panel>` copies satisfy the spec checks) the advisory checks `panel.missing` / `panel.member` / `panel.identical` / `panel.copy` (info), `delta.target` / `delta.unmarked`, `value.missing`, `guard.unlabelled` — all warn or info, never errors: they check that the SVG says what the spec says, not how the figure is laid out; since 2026-09-28 bitmaps: `image.external` / `image.missing` / `image.format` / `image.box` / `image.xmlns` (errors: a URL, a missing file, not PNG / JPEG, no width / height), `image.resolution` / `image.aspect` / `image.orientation` (warn: < 150 ppi at print size, stretched or letterboxed, EXIF rotation), `spec.image`; a picture node's box is the picture and its label a caption | `lint.py fig.svg --spec fig.json --annotate fig.lint.svg` |
| `embed_fonts.py` | map font names to the shipped open fonts and embed them (subsetted) as `@font-face`; CJK text pulls in the system-resolved companion (`--cjk`, default `source-han-sans`), inserted into the stack after the Latin family; reports characters no embedded face covers (`--strict` fails on them); inlines every bitmap as a base64 data URI (`xlink:href`), byte for byte, and writes nothing while one is a URL, missing or not PNG / JPEG; `--strip` removes the fonts again | `embed_fonts.py fig.svg -o fig.final.svg` |
| `export_pdf.py` | SVG → PDF page of exactly the viewBox size with the same faces embedded (Chromium Type3 glyphs) and the bitmaps at full resolution; checks page size, font types and image count with PyMuPDF/pypdf | `export_pdf.py fig.svg -o fig.pdf` |
| `svg_edit.py` | shift whole groups (attributes, paths, rotate centres) and, with `--with-edges`, the touching ends of their edges; `bbox` prints measured boxes | `svg_edit.py shift fig.svg --ids n:block --dy -12 --with-edges` |
| `preview.py` | self-contained HTML debug page (fonts and local bitmaps embedded): zoom, 10 pt grid, hover for coordinates, click a finding to highlight | `preview.py fig.svg --lint fig.lint.json` |
| `check.py` | the self-check loop in one call: validate spec → lint → PNG + annotated PNG → preview page | `check.py fig.svg --spec fig.json` |
| `tex_measure.py` | width / ascent / descent of TeX formulas at a size (MathJax metrics) and, with `--mixed`, the layout of a label with inline formulas (`--emit` prints the `<text>` and placeholder elements) — only for figures that carry formulas | `tex_measure.py --size 6.5 --box '\pi_\theta^{(0)}'` |
| `tex_fill.py` | render every `<g data-symbol="tex">` placeholder into vector paths in place (idempotent; the TeX stays in `data-tex`); `--check` reports formulas that leave their box or collide with labels; run before `check.py` | `tex_fill.py fig.svg --check` |
| `svg2pptx.py` | optional, after delivery: the figure as an editable PowerPoint deck — one native shape per primitive, named groups per spec element, native equations, bitmaps as native pictures, SVG paint order | `svg2pptx.py fig.svg --spec fig.json` |
| `pptx_check.py` | paint-order, inventory (pictures included) and slide-size check of a deck against its SVG | `pptx_check.py fig.pptx --svg fig.svg` |
| `distill/` | how the references and assets were derived from the corpus (re-runnable; not needed for drawing) | see file headers |

## The loop

```
write spec.json ──► spec_validate.py ──► draw fig.svg ──► check.py fig.svg --spec spec.json
                                                              │ fig.png, fig.lint.png, fig.lint.json, fig.preview.html
                                                              ▼
                                        LOOK at fig.png (and fig.lint.png): emphasis, crossings, balance, readability
                                                              │
                                             fix the SVG (or the spec) ──► check.py again ──► deliver embed_fonts.py fig.svg
                                                                                                (fonts + bitmaps inlined)
```

`lint.py` exit code 1 = errors (bleed, overflow, overlap, unreadable text, missing spec elements); warnings
(alignment within 2 pt, off-centre labels, dangling arrows, colour budget) do not block but should be fixed unless
deliberate. Thresholds live in `references/style-thresholds.json` (`lint` section) and come from the corpus statistics.

## Units and fonts

1 SVG user unit = 1 pt. Single column ≈ 240 pt wide, double ≈ 504 pt (see `references/style-rules.md`).
Font keys (`meta.font` in the spec) are defined in `assets/fonts/fonts.json`: `helvetica` (TeX Gyre Heros, default),
`arial` (Arimo), `calibri` (Carlito), `times` (Tinos), `computer-modern`, `computer-modern-sans`, `dejavu`, `inter`,
`roboto`, `source-sans`; CJK companions `source-han-sans` (思源黑体, pairs with `source-sans`) and `source-han-serif` (思源宋体,
pairs with `times`) are not shipped but resolved from the system font directories (`system_font_dirs` in `fonts.json`),
subsetted and embedded when found — declare the Latin family first and the CJK family second in the root stack. Write the stack from `fonts.json` on the root `<svg font-family="…">`; `render.py`/`lint.py`
inject the matching `@font-face` automatically, and `embed_fonts.py` bakes it into the delivered file.
