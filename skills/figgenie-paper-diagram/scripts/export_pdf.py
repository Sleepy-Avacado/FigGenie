#!/usr/bin/env python3
"""Export an SVG figure to a PDF page of exactly the viewBox size, with fonts embedded (headless Chromium).

  python3 scripts/export_pdf.py fig.svg [-o fig.pdf] [--no-check]

* Page size = viewBox width × height in pt (Chromium's PDF API takes inches, so 300 pt = 4.16667 in).
* The same faces render.py/lint.py use are injected: shipped fonts whole, system-resolved CJK faces subsetted.
  Chromium writes every glyph it drew as an embedded Type3 program, so the PDF is self-contained even when the
  SVG itself has no @font-face block. Bitmaps: data URIs as they are, local files from the SVG's folder (URLs are
  never fetched); each lands in the PDF as an image at its full pixel size.
* --check (default) reopens the PDF and reports page size and the font types found (PyMuPDF `fitz` or pypdf;
  skipped when neither is installed). Non-embedded fonts (a system fallback for a glyph no embedded face has)
  show up here — fix those with embed_fonts.py / lint.py's font.glyph finding, not in the PDF.
Use the PDF for LaTeX (\\includegraphics) or Pages; Word takes the embedded SVG directly.
"""
import argparse, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _svgkit as K


def export(svg_text, out_pdf, base_dir=None):
    vb = K.parse_viewbox(svg_text)
    if not vb: raise SystemExit('the SVG has no viewBox; the contract needs viewBox="0 0 W H" in pt')
    W, H = vb[2], vb[3]
    css = K._embed_css(svg_text)
    svg2 = re.sub(r'<svg\b([^>]*?)\s(width|height)\s*=\s*"[^"]*"', r'<svg\1', K.svg_for_chromium(svg_text, base_dir), count=2)
    svg2 = re.sub(r'<svg\b', f'<svg width="{W}pt" height="{H}pt"', svg2, count=1)
    html = (f'<!doctype html><html><head><meta charset="utf-8"><style>@page{{size:{W}pt {H}pt;margin:0}}'
            f'html,body{{margin:0;padding:0;background:#fff}}svg{{display:block;width:{W}pt;height:{H}pt}}{css}</style></head><body>{svg2}</body></html>')
    with K._browser() as p:
        b = p.chromium.launch(); pg = b.new_page()
        pg.set_content(html); pg.evaluate('document.fonts.ready.then(()=>1)'); pg.wait_for_timeout(250)
        pg.pdf(path=str(out_pdf), width=f'{W / 72:.5f}in', height=f'{H / 72:.5f}in', print_background=True,
               prefer_css_page_size=True, margin={'top': '0', 'bottom': '0', 'left': '0', 'right': '0'})
        b.close()
    return W, H


def check(out_pdf):
    try:
        import fitz
        d = fitz.open(str(out_pdf)); pg = d[0]
        fonts = sorted({(f[3] or '(embedded)', f[2]) for f in pg.get_fonts(full=True)})
        return round(pg.rect.width, 2), round(pg.rect.height, 2), fonts, len(d), len(pg.get_images(full=True))
    except ImportError:
        pass
    try:
        from pypdf import PdfReader
        r = PdfReader(str(out_pdf)); pg = r.pages[0]; mb = pg.mediabox
        fonts = []
        res = pg.get('/Resources') or {}
        for k, v in (res.get('/Font') or {}).items():
            v = v.get_object(); fonts.append((str(v.get('/BaseFont', '(embedded)')), str(v.get('/Subtype'))))
        try: n_img = len(pg.images)
        except Exception: n_img = None
        return float(mb.width), float(mb.height), sorted(set(fonts)), len(r.pages), n_img
    except ImportError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('svg'); ap.add_argument('-o', '--out'); ap.add_argument('--no-check', action='store_true')
    a = ap.parse_args()
    svg = Path(a.svg).read_text(encoding='utf-8')
    out = Path(a.out) if a.out else Path(a.svg).with_suffix('.pdf')
    W, H = export(svg, out, base_dir=Path(a.svg).resolve().parent)
    print(f'wrote {out}  ({W:g} x {H:g} pt page)')
    if not a.no_check:
        r = check(out)
        if r is None: print('check skipped (pip install pymupdf or pypdf)'); return
        w, h, fonts, n, n_img = r
        ok = abs(w - W) < 0.5 and abs(h - H) < 0.5
        imgs = f'; images: {n_img}' if n_img is not None and (n_img or K.image_refs(svg)) else ''
        print(f'check: page {w} x {h} pt {"matches the viewBox" if ok else f"DIFFERS from the viewBox {W} x {H}"}; {n} page(s); fonts: {fonts or "none (no text?)"}{imgs}')
        bad = [f for f in fonts if f[1] not in ('Type3',) and not f[0].startswith('(embedded')]
        if bad: print(f'note: {len(bad)} font(s) other than Chromium Type3 glyph programs: {bad} — a system fallback for glyphs no embedded face covers; run lint.py / embed_fonts.py for the culprit characters', file=sys.stderr)


if __name__ == '__main__':
    main()
