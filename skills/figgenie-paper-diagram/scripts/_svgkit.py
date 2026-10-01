#!/usr/bin/env python3
"""Shared helpers for the figgenie-paper-diagram scripts: font map, Chromium measurement and rendering.

Everything works in SVG user units == pt (the skill's SVG contract: viewBox="0 0 W H", 1 unit = 1 pt).

  load_fonts()                      -> the fonts.json map (keys, aliases, files, stacks, system-resolved CJK families)
  resolve_font(name)                -> font key for a family name found in an SVG ("Calibri" -> "calibri")
  font_files(key)                   -> {weight: Path} for a key: shipped files, or system files for families
                                       declared with `system_files` (e.g. source-han-sans); {} when nothing is found
  font_face_css(keys, text=None)    -> @font-face CSS with base64 data URIs (subsetted to `text` when fonttools is present;
                                       system-resolved families are embedded only subsetted and only when `embeddable`)
  families_in_svg(svg_text)         -> set of font-family names referenced by the SVG
  keys_for_svg(svg_text)            -> font keys to embed for an SVG: its families, plus the CJK companion when the text has CJK
  has_cjk(text) / script_runs(text) -> CJK detection and (script, run) splitting for width measurement
  svg_text_content(svg_text)        -> every character that appears in <text>/<tspan>
  glyph_coverage(svg_text, keys)    -> characters that no resolvable face covers (None when fonttools is missing)
  image_refs(svg_text)              -> every <image> in document order: its link, the link's kind (data / local / external)
  load_image(href, base_dir)        -> the bitmap's bytes (data URI decoded, local path read); ImageError otherwise
  image_info(data)                  -> format (sniffed), pixel size as displayed, EXIF orientation
  inline_images(svg_text, base_dir) -> the delivery form: local PNG / JPEG files inlined as data URIs (xlink:href)
  svg_for_chromium(svg_text, base_dir) -> what the browser is given: local bitmaps inlined, URLs never fetched
  measure(svg_text, ...)            -> dict: viewBox, per-element boxes (root user units), path samples, font checks
  render_png(svg_text, out, scale)  -> PNG at `scale` px per pt

The measurement runs the SVG in headless Chromium (Playwright) and reads getBoundingClientRect() of every element
while the SVG is laid out at 1 CSS px per user unit, so boxes are exact in pt whatever transforms are used.
The page is loaded from about:blank and cannot read files, so `measure` / `render_png` take the SVG's folder
(`base_dir`) and hand Chromium every local <image> as a data URI, the way they hand it the fonts.
"""
import base64, glob, html as _html_mod, io, json, os, re, sys, tempfile
import urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
FONT_DIR = SKILL / 'assets' / 'fonts'
SUBSET_RE = re.compile(r'^[A-Z]{6}\+')
NUM = re.compile(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?')
# CJK: radicals/punctuation/kana/bopomofo/hangul-compat/unified ideographs, Hangul, compatibility ideographs,
# full-width forms, and the supplementary ideographic planes.
CJK_RE = re.compile('[⺀-鿿가-힯豈-﫿＀-￯\U00020000-\U0002fa1f]')
GENERIC = ('sans-serif', 'serif', 'monospace', 'system-ui', 'cursive', 'fantasy')

_fonts = None
_files_cache = {}


def load_fonts():
    global _fonts
    if _fonts is None:
        _fonts = json.loads((FONT_DIR / 'fonts.json').read_text(encoding='utf-8'))
        _fonts['_alias'] = {}
        for key, fam in _fonts['families'].items():
            for a in [fam['css_family']] + fam.get('aliases', []):
                _fonts['_alias'][a.lower()] = key
    return _fonts


def clean_family(name):
    n = SUBSET_RE.sub('', (name or '').strip().strip('\'"'))
    n = re.sub(r'\s*,.*$', '', n)  # first item of a stack
    return n.strip().strip('\'"')


def resolve_font(name, default=True):
    f = load_fonts()
    n = clean_family(name).lower()
    if not n: return f['default'] if default else None
    if n in f['_alias']: return f['_alias'][n]
    base = re.split(r'[-,]', n)[0].strip()
    if base in f['_alias']: return f['_alias'][base]
    for a, key in f['_alias'].items():
        if a in n or n in a: return key
    if n in f['generic']: return f['generic'][n]
    if 'mono' in n or 'courier' in n or 'consol' in n: return f['generic']['monospace']
    if 'serif' in n and 'sans' not in n: return f['generic']['serif']
    return f['default'] if default else None


def is_cjk_key(key):
    fam = load_fonts()['families'].get(key) or {}
    return fam.get('script') == 'cjk'


def cjk_default_key():
    return load_fonts().get('cjk_default', 'source-han-sans')


def font_files(key):
    """{weight: Path} for a font key. Shipped families come from assets/fonts; families declared with
    `system_files` are searched in `system_font_dirs` (glob patterns, first hit per weight). Cached."""
    if key in _files_cache: return _files_cache[key]
    f = load_fonts(); fam = f['families'].get(key) or {}; out = {}
    for w, fn in (fam.get('files') or {}).items():
        p = FONT_DIR / fn
        if p.exists(): out[w] = p
    if not out and fam.get('system_files'):
        dirs = [Path(os.path.expanduser(d)) for d in f.get('system_font_dirs', [])]
        for w, patterns in fam['system_files'].items():
            for pat in patterns:
                hit = None
                for d in dirs:
                    if not d.is_dir(): continue
                    m = sorted(glob.glob(str(d / pat)))
                    if m: hit = Path(m[0]); break
                if hit: out[w] = hit; break
    _files_cache[key] = out
    return out


def font_is_shipped(key):
    fam = load_fonts()['families'].get(key) or {}
    return bool(fam.get('files'))


def has_cjk(text):
    return bool(CJK_RE.search(text or ''))


def script_runs(text):
    """Split text into [(script, run)] with script in {'cjk', 'latin'}; spaces stay with the preceding run."""
    runs = []
    for ch in text or '':
        s = 'cjk' if CJK_RE.match(ch) else 'latin'
        if runs and (runs[-1][0] == s or ch == ' '): runs[-1][1] += ch
        else: runs.append([s, ch])
    return [(s, r) for s, r in runs]


def families_in_svg(svg_text):
    fams = set()
    for m in re.finditer(r'font-family\s*[:=]\s*("([^"]*)"|\'([^\']*)\'|([^;"\'>\s][^;"\'>]*))', svg_text):
        raw = m.group(2) or m.group(3) or m.group(4) or ''
        for part in raw.split(','):          # the first concrete family of each stack is the one that renders
            p = clean_family(part)
            if p and p.lower() not in GENERIC: fams.add(p); break
    return fams


def all_families_in_svg(svg_text):
    """Every concrete family name in every stack (not just the first), in order of appearance."""
    seen = []
    for m in re.finditer(r'font-family\s*[:=]\s*("([^"]*)"|\'([^\']*)\'|([^;"\'>\s][^;"\'>]*))', svg_text):
        raw = m.group(2) or m.group(3) or m.group(4) or ''
        for part in raw.split(','):
            p = clean_family(part)
            if p and p.lower() not in GENERIC and p not in seen: seen.append(p)
    return seen


def svg_text_content(svg_text):
    """Characters that appear inside <text>/<tspan> (with entities decoded)."""
    import html as _html
    out = []
    for m in re.finditer(r'<text\b[^>]*>(.*?)</text>', svg_text, flags=re.S):
        inner = re.sub(r'<[^>]+>', '', m.group(1))
        out.append(_html.unescape(inner))
    return ''.join(out)


def keys_for_svg(svg_text, cjk=None):
    """Font keys an SVG needs: the resolved first family of each stack, plus the CJK companion (a `script: cjk`
    family named anywhere in a stack, else `cjk` / fonts.json `cjk_default`) whenever the text contains CJK."""
    keys = []
    for fam in families_in_svg(svg_text):
        k = resolve_font(fam)
        if k and k not in keys: keys.append(k)
    if has_cjk(svg_text_content(svg_text)):
        ck = cjk
        if not ck:
            for fam in all_families_in_svg(svg_text):
                k = resolve_font(fam, default=False)
                if k and is_cjk_key(k): ck = k; break
        if not ck: ck = cjk_default_key()
        if ck not in keys: keys.append(ck)
    return keys


def _subset(font_path, text):
    """Return subsetted font bytes (ttf/otf) for the characters in text, or None if fonttools is missing."""
    try:
        from fontTools import subset as fsub
        from fontTools.ttLib import TTFont
    except ImportError:
        return None
    chars = set(text) | set(' 0123456789.,:;-+()[]/%×→←↔·…')
    font = TTFont(str(font_path), fontNumber=0) if font_path.suffix.lower() == '.ttc' else TTFont(str(font_path))
    opts = fsub.Options(); opts.layout_features = ['*']; opts.name_IDs = ['*']; opts.notdef_outline = True; opts.hinting = False
    s = fsub.Subsetter(options=opts); s.populate(unicodes=[ord(c) for c in chars]); s.subset(font)
    import io
    buf = io.BytesIO(); font.save(buf); return buf.getvalue()


def font_face_css(keys, text=None, weights=('regular', 'bold', 'italic', 'bolditalic')):
    """@font-face rules (data URIs) for the given font keys; css_family names are used as the family.
    Shipped faces are embedded whole when `text` is None. System-resolved faces (CJK) are only ever embedded
    subsetted (a full CJK face is 10–20 MB) and only when the family is marked `embeddable`; without fonttools
    they are skipped with a note on stderr (Chromium then uses the installed system font, which is fine for
    rendering and linting locally but not portable)."""
    f = load_fonts(); css = []
    for key in keys:
        fam = f['families'].get(key)
        if not fam: continue
        files = font_files(key)
        if not files: continue
        shipped = font_is_shipped(key)
        if not shipped and not fam.get('embeddable', False): continue
        for w in weights:
            p = files.get(w)
            if not p: continue
            if shipped:
                data = (_subset(p, text) if text else None) or p.read_bytes()
            else:
                data = _subset(p, text or svg_text_content('')) if text else None
                if data is None:
                    if text is None:
                        data = _subset(p, '')  # no text known: still subset to the default character set
                    if data is None:
                        print(f'note: {fam["css_family"]} found at {p} but fonttools is missing; not embedded (pip install fonttools)', file=sys.stderr)
                        break
            suf = p.suffix.lower()
            mime = 'font/otf' if suf in ('.otf', '.ttc') else 'font/ttf'
            fmt = 'opentype' if suf in ('.otf', '.ttc') else 'truetype'
            b64 = base64.b64encode(data).decode()
            css.append(f'@font-face{{font-family:"{fam["css_family"]}";font-weight:{"bold" if "bold" in w else "normal"};'
                       f'font-style:{"italic" if "italic" in w else "normal"};src:url(data:{mime};base64,{b64}) format("{fmt}");}}')
    return '\n'.join(css)


def glyph_coverage(svg_text, keys=None):
    """Characters of the SVG's text that none of the resolvable faces of `keys` (default keys_for_svg) covers.
    Returns (uncovered: sorted list of chars, faces: [(key, Path)] that were checked), or (None, faces)
    when fonttools is unavailable. Whitespace is ignored."""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return None, []
    keys = keys or keys_for_svg(svg_text)
    text = ''.join(c for c in svg_text_content(svg_text) if not c.isspace())
    cmaps, faces = [], []
    for k in keys:
        for w, p in font_files(k).items():
            try:
                font = TTFont(str(p), fontNumber=0) if p.suffix.lower() == '.ttc' else TTFont(str(p))
                cmaps.append(font.getBestCmap() or {}); faces.append((k, p))
            except Exception:
                continue
    uncovered = sorted({c for c in text if not any(ord(c) in cm for cm in cmaps)})
    return uncovered, faces


# ---------------------------------------------------------------- bitmaps (<image>)
# Bitmaps are allowed (a sample, photo, screenshot, rendered result, icon). While drawing a bitmap is a local
# PNG / JPEG referenced by a relative path; a URL is never allowed, because the delivered SVG must stand alone:
# embed_fonts.py inlines every bitmap as a data URI, exactly like the fonts.
XLINK_NS = 'http://www.w3.org/1999/xlink'
IMAGE_FORMATS = {'png': 'image/png', 'jpeg': 'image/jpeg'}          # what a delivered figure may carry
_MIME = dict(IMAGE_FORMATS, gif='image/gif', webp='image/webp', bmp='image/bmp', tiff='image/tiff', avif='image/avif',
             svg='image/svg+xml', pdf='application/pdf')
_IMAGE_TAG = re.compile(r'<image\b(?:[^>"\']|"[^"]*"|\'[^\']*\')*>')  # quoted values may contain ">"
_G_TAG = re.compile(r'<(/?)g\b((?:[^>"\']|"[^"]*"|\'[^\']*\')*)>')
_TAG_ATTR = re.compile(r'([\w:.-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')
_LINK_ATTR = re.compile(r'\s(?:(?:xlink:)?href|data-img)\s*=\s*(?:"[^"]*"|\'[^\']*\')')
_COMMENT = re.compile(r'<!--.*?-->', re.S)
_SVG_OPEN = re.compile(r'<svg\b(?:[^>"\']|"[^"]*"|\'[^\']*\')*>')


class ImageError(Exception):
    """An <image> whose bitmap cannot be used: no link, a URL, a malformed data URI, a missing or unreadable file."""


def href_kind(href):
    """'none' | 'data' (a data: URI) | 'external' (http(s), ftp, //host … — never allowed) | 'local' (a path or file: URL)."""
    h = (href or '').strip()
    if not h: return 'none'
    if h[:5].lower() == 'data:': return 'data'
    if h.startswith('//'): return 'external'
    m = re.match(r'([A-Za-z][A-Za-z0-9+.-]*):', h)
    if m and len(m.group(1)) > 1 and m.group(1).lower() != 'file': return 'external'   # one letter = a Windows drive
    return 'local'


def image_refs(svg_text):
    """Every <image> tag outside comments, in document order: [{k, start, end, tag, attrs, attr, href, kind, owner,
    name}]. `attr` is the attribute carrying the link ('href' wins over 'xlink:href', as in SVG 2), `href` its value
    with entities decoded, `kind` = href_kind(href), `owner` the id of the nearest enclosing <g id> (the spec element
    it belongs to), `name` what messages call it. The index k is what svg_for_chromium() stamps as data-img, so
    measured elements map back to their source tag."""
    text = svg_text or ''
    skip = [m.span() for m in _COMMENT.finditer(text)]
    out = []
    for m in _IMAGE_TAG.finditer(text):
        if any(a <= m.start() < b for a, b in skip): continue
        attrs = {a.group(1): _html_mod.unescape(a.group(2) if a.group(2) is not None else a.group(3))
                 for a in _TAG_ATTR.finditer(m.group(0)[len('<image'):])}
        attr = 'href' if 'href' in attrs else ('xlink:href' if 'xlink:href' in attrs else None)
        href = (attrs.get(attr) or '').strip() if attr else ''
        out.append(dict(k=len(out), start=m.start(), end=m.end(), tag=m.group(0), attrs=attrs, attr=attr, href=href,
                        kind=href_kind(href)))
    stack, groups = [], _G_TAG.finditer(text)
    g = next(groups, None)
    for r in out:                                        # the enclosing <g id> of each image: one pass over the <g> tags
        while g is not None and g.start() < r['start']:
            if any(a <= g.start() < b for a, b in skip): pass
            elif g.group(1):
                if stack: stack.pop()
            elif not g.group(2).rstrip().endswith('/'):
                i = re.search(r'\sid\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', g.group(2))
                stack.append((i.group(1) if i.group(1) is not None else i.group(2)) if i else None)
            g = next(groups, None)
        r['owner'] = next((i for i in reversed(stack) if i), None)
        r['name'] = r['attrs'].get('id') or (f'the <image> in {r["owner"]}' if r['owner'] else f'<image> #{r["k"] + 1}')
    return out


def _local_path(href, base_dir):
    if href[:5].lower() == 'file:':
        return Path(urllib.request.url2pathname(urllib.parse.urlparse(href).path))
    base = Path(base_dir) if base_dir else Path('.')
    p = Path(href) if Path(href).is_absolute() else base / href
    if not p.exists():                                   # an href is a URL: "my%20photo.png" names "my photo.png"
        u = urllib.parse.unquote(href)
        q = Path(u) if Path(u).is_absolute() else base / u
        if q.exists(): return q
    return p


def load_image(href, base_dir=None):
    """(bytes, where) for an <image> link: a data URI is decoded, a local path (relative to base_dir, the SVG's
    folder) or file: URL is read. Raises ImageError for an empty or external link, a malformed data URI, a missing file."""
    kind = href_kind(href)
    if kind == 'none': raise ImageError('has no href')
    if kind == 'external': raise ImageError(f'links to {href[:80]}')
    if kind == 'data':
        m = re.match(r'data:([^,]*),(.*)$', href.strip(), re.S)
        if not m: raise ImageError('has a malformed data URI')
        try:
            if ';base64' in m.group(1).lower():
                return base64.b64decode(re.sub(r'\s+', '', m.group(2)), validate=True), 'data URI'
            return urllib.parse.unquote_to_bytes(m.group(2)), 'data URI'
        except ValueError as ex:
            raise ImageError(f'has an undecodable data URI ({ex})')
    p = _local_path(href, base_dir)
    if not p.is_file(): raise ImageError(f'points at {href}, which is not there (looked for {p})')
    return p.read_bytes(), str(p)


def sniff_image(data):
    """Format from the first bytes, whatever the file name or data-URI type says: png, jpeg, gif, webp, bmp, tiff,
    avif, svg, pdf, or None."""
    d = data or b''
    if d[:8] == b'\x89PNG\r\n\x1a\n': return 'png'
    if d[:3] == b'\xff\xd8\xff': return 'jpeg'
    if d[:6] in (b'GIF87a', b'GIF89a'): return 'gif'
    if d[:4] == b'RIFF' and d[8:12] == b'WEBP': return 'webp'
    if d[:2] == b'BM': return 'bmp'
    if d[:4] in (b'II*\x00', b'MM\x00*'): return 'tiff'
    if d[4:12] in (b'ftypavif', b'ftypavis'): return 'avif'
    if d[:5] == b'%PDF-': return 'pdf'
    if b'<svg' in d[:1024].lower(): return 'svg'
    return None


def image_info(data):
    """{'format', 'w', 'h', 'orientation'}: the sniffed format and the pixel size as displayed (EXIF rotation applied).
    w / h are None when Pillow cannot decode the bytes (not a bitmap, or a broken file)."""
    info = dict(format=sniff_image(data), w=None, h=None, orientation=1)
    if info['format'] in (None, 'svg', 'pdf'): return info
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data)); w, h = im.size
        try: o = int(im.getexif().get(0x0112, 1) or 1)
        except Exception: o = 1
        info.update(w=h if o in (5, 6, 7, 8) else w, h=w if o in (5, 6, 7, 8) else h, orientation=o)
    except Exception:
        pass
    return info


def parse_par(value):
    """preserveAspectRatio -> (align, mode): align 'none' or xMinYMin … xMaxYMax, mode 'meet' | 'slice' (SVG defaults)."""
    toks = [t for t in (value or '').split() if t != 'defer']
    align = toks[0] if toks and (toks[0] == 'none' or re.fullmatch(r'x(Min|Mid|Max)Y(Min|Mid|Max)', toks[0])) else 'xMidYMid'
    mode = toks[1] if len(toks) > 1 and toks[1] in ('meet', 'slice') else 'meet'
    return align, mode


def data_uri(data, fmt):
    return f'data:{_MIME.get(fmt, "application/octet-stream")};base64,{base64.b64encode(data).decode()}'


def _set_link(tag, value, attr='href', extra=''):
    """The <image …> tag with every href / xlink:href replaced by one `attr="value"` (+ extra attributes)."""
    rest = _LINK_ATTR.sub('', tag[len('<image'):])
    return f'<image {attr}="{value}"{extra}' + (rest if rest[:1].isspace() or rest[:1] in ('/', '>') else ' ' + rest)


def inline_images(svg_text, base_dir=None):
    """The delivery form of the SVG's bitmaps. Every <image> becomes xlink:href="data:image/png|jpeg;base64,…"
    (the SVG 1.1 spelling that Office, Illustrator and older Inkscape read; xmlns:xlink is declared on the root):
    a local file is inlined byte for byte, a data URI is kept. Returns (svg_text, done, problems): done =
    [{href, format, bytes, inlined}], problems = messages for external links, missing or undecodable files and
    formats other than PNG / JPEG -- the caller must not deliver while problems is non-empty."""
    refs = image_refs(svg_text)
    if not refs: return svg_text, [], []
    out, done, problems, pos = [], [], [], 0
    for r in refs:
        try:
            data, _ = load_image(r['href'], base_dir)
        except ImageError as ex:
            problems.append(f'{r["name"]} {ex}' + ('; download it into the figure folder and link it by a relative path'
                                                  if r['kind'] == 'external' else ''))
            continue
        fmt = sniff_image(data)
        if fmt not in IMAGE_FORMATS:
            what = f'{fmt.upper()}' if fmt else 'not a known image format'
            problems.append(f'{r["name"]} ({r["href"][:60]}) is {what}, not PNG or JPEG; convert it first')
            continue
        uri = r['href'] if r['kind'] == 'data' else data_uri(data, fmt)
        out.append(svg_text[pos:r['start']]); out.append(_set_link(r['tag'], uri, 'xlink:href')); pos = r['end']
        done.append(dict(href=r['href'] if r['kind'] != 'data' else 'data URI', format=fmt, bytes=len(data),
                         inlined=r['kind'] != 'data'))
    if problems: return svg_text, done, problems
    out.append(svg_text[pos:]); svg = ''.join(out)
    m = _SVG_OPEN.search(svg)
    if m and 'xmlns:xlink' not in m.group(0):
        root = m.group(0); ns = re.search(r'\sxmlns\s*=\s*(?:"[^"]*"|\'[^\']*\')', root)
        cut = ns.end() if ns else len('<svg')
        svg = svg[:m.start()] + root[:cut] + f' xmlns:xlink="{XLINK_NS}"' + root[cut:] + svg[m.end():]
    return svg, done, problems


def svg_for_chromium(svg_text, base_dir=None):
    """The SVG as the headless browser gets it (measure, render_png, export_pdf.py, preview.py): each <image> is
    stamped data-img="k" (its index in image_refs) and a local file becomes a data URI, because a page loaded from
    about:blank cannot read files; an external link is emptied -- never fetched: the figure must not depend on it,
    and lint.py reports it. Unchanged when the SVG has no <image>."""
    refs = image_refs(svg_text)
    if not refs: return svg_text
    out, pos = [], 0
    for r in refs:
        link = r['href'] if r['kind'] == 'data' else ''
        if r['kind'] == 'local':
            try:
                data, _ = load_image(r['href'], base_dir)
                link = data_uri(data, sniff_image(data))
            except ImageError:
                link = ''
        out.append(svg_text[pos:r['start']]); out.append(_set_link(r['tag'], link, 'href', f' data-img="{r["k"]}"')); pos = r['end']
    out.append(svg_text[pos:])
    return ''.join(out)


def parse_viewbox(svg_text):
    m = re.search(r'<svg\b[^>]*\bviewBox\s*=\s*"([^"]+)"', svg_text)
    if m:
        v = [float(x) for x in NUM.findall(m.group(1))]
        if len(v) == 4: return v
    w = re.search(r'<svg\b[^>]*\bwidth\s*=\s*"([^"]+)"', svg_text); h = re.search(r'<svg\b[^>]*\bheight\s*=\s*"([^"]+)"', svg_text)
    if w and h: return [0.0, 0.0, float(NUM.findall(w.group(1))[0]), float(NUM.findall(h.group(1))[0])]
    return None


_MEASURE_JS = r"""
() => {
  const svg = document.querySelector('svg');
  const root = svg.getBoundingClientRect();
  const out = {elements: [], fonts: {}};
  const all = svg.querySelectorAll('*');
  let idx = 0;
  for (const el of all) {
    const tag = el.tagName.toLowerCase();
    if (['defs','style','title','desc','metadata','clippath','mask','marker','pattern','lineargradient','radialgradient','stop','symbol','filter','fegaussianblur','feoffset','femerge','femergenode','feflood','fecomposite','feblend'].includes(tag)) continue;
    if (el.closest('defs, marker, symbol, clipPath, mask, pattern')) continue;
    el.setAttribute('data-lint-idx', String(idx));
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const rec = {idx, tag, id: el.id || null, kind: el.getAttribute('data-kind'), x: r.left - root.left, y: r.top - root.top, w: r.width, h: r.height,
                 fill: cs.fill, stroke: cs.stroke, strokeWidth: parseFloat(cs.strokeWidth) || 0, opacity: parseFloat(cs.opacity),
                 markerEnd: cs.markerEnd && cs.markerEnd !== 'none' ? cs.markerEnd : null, markerStart: cs.markerStart && cs.markerStart !== 'none' ? cs.markerStart : null,
                 dash: cs.strokeDasharray && cs.strokeDasharray !== 'none' ? cs.strokeDasharray : null,
                 parentGroup: null, attrs: {}};
    for (const a of ['data-from','data-to','data-role','data-symbol','data-step','data-edge-kind','data-attached-to','data-anchor','data-order','data-panel','data-delta','data-at','data-replica','data-img','preserveAspectRatio','transform','text-anchor','font-weight','x','y','width','height']) { const v = el.getAttribute(a); if (v !== null) rec.attrs[a] = v; }
    if (tag === 'image') {
      try { const m = el.getCTM(); rec.img = {w: el.width.baseVal.value, h: el.height.baseVal.value, sx: Math.hypot(m.a, m.b), sy: Math.hypot(m.c, m.d)}; } catch (e) {}
    }
    const pg = el.parentElement && el.parentElement !== svg ? el.parentElement.closest('g[id]') : null;
    if (pg) rec.parentGroup = pg.id;
    const symAnc = el.parentElement ? el.parentElement.closest('[data-symbol]') : null;
    if (symAnc && svg.contains(symAnc)) rec.inSymbol = true;
    if (tag === 'text') {
      rec.text = (el.textContent || '').replace(/\s+/g, ' ').trim();
      rec.fontSize = parseFloat(cs.fontSize); rec.fontFamily = cs.fontFamily; rec.fontWeight = cs.fontWeight; rec.anchor = cs.textAnchor;
      try { const bb = el.getBBox(); rec.bboxLocal = [bb.x, bb.y, bb.width, bb.height]; } catch (e) {}
      try { const sp = el.getStartPositionOfChar(0); const q = new DOMPoint(sp.x, sp.y).matrixTransform(el.getCTM()); rec.baseline = q.y - root.top + window.scrollY; } catch (e) {}
      try { const m = el.getCTM(); rec.rotated = Math.abs(m.b) > 0.01 || Math.abs(m.c) > 0.01; } catch (e) {}
    }
    if (['path','line','polyline','polygon'].includes(tag)) {
      try {
        const L = el.getTotalLength(); rec.length = L;
        const ctm = el.getCTM(); const pts = [];
        const n = Math.max(2, Math.min(200, Math.ceil(L / 2)));
        for (let i = 0; i <= n; i++) { const p = el.getPointAtLength(L * i / n); const q = new DOMPoint(p.x, p.y).matrixTransform(ctm); pts.push([q.x - root.left + window.scrollX, q.y - root.top + window.scrollY]); }
        rec.points = pts;
      } catch (e) {}
    }
    out.elements.push(rec); idx++;
  }
  const fams = new Set();
  for (const el of svg.querySelectorAll('text')) { for (const f of getComputedStyle(el).fontFamily.split(',')) fams.add(f.trim().replace(/^["']|["']$/g, '')); }
  for (const f of fams) out.fonts[f] = document.fonts.check('10px "' + f + '"');
  out.width = root.width; out.height = root.height;
  return out;
}
"""


def _html_for(svg_text, extra_css=''):
    vb = parse_viewbox(svg_text) or [0, 0, 300, 200]
    W, H = vb[2], vb[3]
    # force layout at 1 CSS px per user unit
    svg2 = re.sub(r'<svg\b([^>]*?)\s(width|height)\s*=\s*"[^"]*"', r'<svg\1', svg_text, count=2)
    svg2 = re.sub(r'<svg\b', f'<svg width="{W}" height="{H}"', svg2, count=1)
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>html,body{{margin:0;padding:0;background:#fff}}'
            f'svg{{display:block}}{extra_css}</style></head><body>{svg2}</body></html>'), W, H


def _browser():
    from playwright.sync_api import sync_playwright
    return sync_playwright()


def _embed_css(svg_text):
    keys = keys_for_svg(svg_text)
    # subset system-resolved families to the figure's text; shipped ones are embedded whole (fast, cached by Chromium)
    text = svg_text_content(svg_text)
    shipped = [k for k in keys if font_is_shipped(k)]
    system = [k for k in keys if not font_is_shipped(k)]
    return font_face_css(shipped) + ('\n' + font_face_css(system, text=text) if system else '')


def measure(svg_text, embed_fonts=True, base_dir=None):
    """Run the SVG in Chromium and return geometry for every element (root user units). `base_dir` is the SVG's folder:
    relative <image> links resolve against it. Each <image> record carries attrs['data-img'] (its image_refs index)
    and `img` = its own width / height and the CTM scale, so print size = w × sx pt."""
    css = _embed_css(svg_text) if embed_fonts else ''
    html, W, H = _html_for(svg_for_chromium(svg_text, base_dir), css)
    with _browser() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={'width': int(W) + 2, 'height': int(H) + 2}, device_scale_factor=1)
        pg.set_content(html); pg.evaluate('document.fonts.ready.then(()=>1)'); pg.wait_for_timeout(120)
        data = pg.evaluate(_MEASURE_JS); b.close()
    data['viewBox'] = parse_viewbox(svg_text); data['W'] = W; data['H'] = H
    return data


def render_png(svg_text, out_png, scale=3.0, embed_fonts=True, crop=None, base_dir=None):
    """Render to PNG at `scale` px/pt. `crop` = (x0, y0, x1, y1) in pt keeps only that region (needs Pillow).
    `base_dir` is the SVG's folder, against which relative <image> links resolve (external links are not fetched)."""
    css = _embed_css(svg_text) if embed_fonts else ''
    html, W, H = _html_for(svg_for_chromium(svg_text, base_dir), css)
    with _browser() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={'width': int(W) + 1, 'height': int(H) + 1}, device_scale_factor=scale)
        pg.set_content(html); pg.evaluate('document.fonts.ready.then(()=>1)'); pg.wait_for_timeout(120)
        pg.locator('svg').first.screenshot(path=str(out_png)); b.close()
    if crop:
        from PIL import Image
        x0, y0, x1, y1 = crop
        im = Image.open(out_png)
        bx = (max(0, int(round(x0 * scale))), max(0, int(round(y0 * scale))), min(im.width, int(round(x1 * scale))), min(im.height, int(round(y1 * scale))))
        im.crop(bx).save(out_png)
    return out_png
