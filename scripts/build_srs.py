"""Build docs/SRS.pdf from docs/SRS.md and the rendered diagrams (docs/diagrams/*.svg).

    python scripts/build_srs.py            # writes docs/SRS.pdf (and prints the page count and where every figure and table is)

    docs/SRS.md  --(Markdown -> HTML, diagrams inlined, cover, contents)-->  headless Chrome or Edge  -->  docs/SRS.pdf

Two passes: the first finds the page of every heading, figure and table in the printed document, the second prints the
contents, the list of figures and the list of tables with those page numbers. The Markdown file is the authoritative
text; nothing is typed into the PDF that is not in it, except the cover and the three lists, which are derived from it.
Diagrams are edited in their .mmd sources and rendered by scripts/render_diagrams.py. Needs the packages Markdown and
pdfplumber (requirements.txt) and a locally installed Chrome or Edge; nothing is fetched from the network."""
import html, os, re, shutil, subprocess, sys, tempfile
import markdown

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC, OUT, DIAGRAMS = os.path.join(ROOT, "docs", "SRS.md"), os.path.join(ROOT, "docs", "SRS.pdf"), os.path.join(ROOT, "docs")
BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/microsoft-edge"]
PORTRAIT, LANDSCAPE = (168.0, 205.0), (255.0, 150.0)          # room for a figure in millimetres (width, height), caption excluded
MIN_POINTS = 7.5                                              # the build fails if a 16-unit diagram label would print smaller than this
MAX_SCALE = 0.200                                             # millimetres per diagram unit: a 16-unit label is never printed larger than about 9 points

CSS = """
@page { size: A4; margin: 22mm 21mm 22mm 21mm; @bottom-center { content: "AirPulse  |  Software Requirements Specification  |  " counter(page); font: 8.5pt Arial, Helvetica, sans-serif; color: #4b5563; } }
@page :first { @bottom-center { content: none; } }
@page wide { size: A4 landscape; margin: 18mm 20mm 18mm 20mm; }
html { font: 10.5pt/1.42 Georgia, 'Times New Roman', serif; color: #111827; }
body { margin: 0; }
h1, h2, h3, h4, th, figcaption, .cap, .toc, .cover, .lists { font-family: Arial, Helvetica, sans-serif; }
h2 { font-size: 15pt; margin: 20pt 0 7pt; padding-bottom: 3pt; border-bottom: 0.8pt solid #1f2937; break-after: avoid; }
h3 { font-size: 11.5pt; margin: 14pt 0 5pt; break-after: avoid; }
h4 { font-size: 10pt; margin: 12pt 0 4pt; break-after: avoid; }
p { margin: 0 0 7pt; text-align: justify; hyphens: auto; orphans: 3; widows: 3; }
ul, ol { margin: 0 0 7pt; padding-left: 18pt; } li { margin-bottom: 2.5pt; }
code { font: 8.8pt Consolas, 'Courier New', monospace; background: #f3f4f6; padding: 0 2pt; overflow-wrap: break-word; }
pre { font: 8.3pt/1.3 Consolas, 'Courier New', monospace; background: #f9fafb; border: 0.6pt solid #d1d5db; padding: 7pt 9pt; margin: 4pt 0 9pt; break-inside: avoid; white-space: pre; }
pre code { background: none; padding: 0; font: inherit; }
table { border-collapse: collapse; width: 100%; margin: 3pt 0 10pt; font: 8.6pt/1.32 Arial, Helvetica, sans-serif; }
th, td { border: 0.6pt solid #9ca3af; padding: 3pt 5pt; vertical-align: top; text-align: left; overflow-wrap: break-word; }
th { background: #e5e7eb; } tr { break-inside: avoid; } thead { display: table-header-group; }
table.req { break-inside: avoid; } table.req td:first-child { width: 23%; font-weight: bold; background: #f3f4f6; }
table.meta td:first-child { width: 26%; font-weight: bold; background: #f3f4f6; } table.meta thead { display: none; }
.cap { font-size: 8.8pt; font-style: normal; color: #1f2937; margin: 8pt 0 2pt; text-align: left; break-after: avoid; } .cap b { font-weight: bold; }
figure { margin: 8pt 0 11pt; text-align: center; break-inside: avoid; }
figure .panels { display: flex; justify-content: center; align-items: flex-start; gap: 6mm; }
figure .panels.stack { flex-direction: column; align-items: center; gap: 5mm; }
figure svg { display: block; flex: none; }
figure svg p, figure svg span, figure svg div { margin: 0; text-align: center; hyphens: manual; orphans: 1; widows: 1; line-height: 1.5; }
figure svg code, figure svg pre { background: none; }
figcaption { font-size: 8.8pt; margin-top: 5pt; text-align: left; color: #1f2937; } figcaption b { font-weight: bold; }
figure.landscape { page: wide; break-before: page; break-after: page; margin: 0; }
.cover { height: 247mm; display: flex; flex-direction: column; break-after: page; }
.cover .rule { border-top: 2.2pt solid #111827; margin-top: 34mm; }
.cover h1 { font-size: 34pt; margin: 9mm 0 2mm; letter-spacing: 0.5pt; } .cover .sub { font-size: 15pt; color: #1f2937; margin-bottom: 3mm; } .cover .kind { font-size: 12.5pt; color: #374151; margin-top: 14mm; text-transform: uppercase; letter-spacing: 1.4pt; }
.cover table { margin-top: auto; font-size: 9.5pt; } .cover td:first-child { width: 30%; font-weight: bold; background: #f3f4f6; }
.toc { break-after: page; } .lists { break-after: page; }
.toc h2, .lists h2 { margin-top: 0; }
.toc div, .lists div { display: flex; align-items: baseline; font-size: 9.6pt; margin: 2.2pt 0; } .toc .l3 { padding-left: 14pt; font-size: 9pt; color: #1f2937; }
.toc .dots, .lists .dots { flex: 1; border-bottom: 0.6pt dotted #6b7280; margin: 0 4pt; transform: translateY(-2.5pt); } .toc a, .lists a { color: inherit; text-decoration: none; }
.lists div { font-size: 9pt; } .lists h3 { margin-top: 12pt; }
a { color: #111827; }
"""


def svg_inline(path, room, share):
    """The SVG file as inline markup, sized in millimetres so that it fits the room given to it."""
    text = open(path, encoding="utf-8").read(); text = text[text.index("<svg"):]
    x, y, w, h = (float(v) for v in re.search(r'viewBox="([^"]+)"', text).group(1).split())
    scale = min(room[0] * share / w, room[1] / h, MAX_SCALE)
    head = text[:text.index(">") + 1]; new = re.sub(r'\s(?:width|height|style)="[^"]*"', "", head).replace("<svg", f'<svg width="{w * scale:.1f}mm" height="{h * scale:.1f}mm"', 1)
    return new + text[len(head):], scale


def to_html(md_text, pages=None):
    meta = dict(kv.strip().split("=", 1) for kv in re.search(r"<!-- srs: (.*?) -->", md_text, re.S).group(1).split(";"))
    title, sub = re.search(r"^# (.+)$", md_text, re.M).group(1), re.search(r"^\*\*(.+)\*\*$", md_text, re.M).group(1)
    body_md = md_text[md_text.index("## 1."):]                                   # the title block of the Markdown file becomes the cover
    body = markdown.markdown(body_md, extensions=["tables", "fenced_code", "sane_lists"])
    heads, figs, tabs, scales = [], [], [], {}
    def head(m):
        level, text = int(m.group(1)), re.sub(r"<[^>]+>", "", m.group(2)); hid = "h-" + re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        if level <= 3: heads.append((level, text, hid))
        return f'<h{level} id="{hid}">{m.group(2)}</h{level}>'
    body = re.sub(r"<h([234])>(.*?)</h\1>", head, body)
    def figure(m):
        imgs = re.findall(r'<img alt="[^"]*" src="([^"]+)"(?: title="([^"]*)")? ?/?>', m.group(1)); cap = m.group(2); n = re.match(r"Figure (\d+)\.", cap).group(1)
        wide = any(t == "landscape" for _, t in imgs); stack = any(t == "stack" for _, t in imgs); room = LANDSCAPE if wide else PORTRAIT; parts = []
        widths = [float(re.search(r'viewBox="([^"]+)"', open(os.path.join(DIAGRAMS, s), encoding="utf-8").read()).group(1).split()[2]) for s, _ in imgs]
        gap = 6.0 * (len(imgs) - 1); usable = (room[0] - gap, room[1]); dims = [tuple(float(v) for v in re.search(r'viewBox="([^"]+)"', open(os.path.join(DIAGRAMS, s), encoding="utf-8").read()).group(1).split()[2:]) for s, _ in imgs]
        one = min(min(usable[0] / sum(widths), MAX_SCALE), *(usable[1] / float(re.search(r'viewBox="([^"]+)"', open(os.path.join(DIAGRAMS, s), encoding="utf-8").read()).group(1).split()[3]) for s, _ in imgs))
        if stack: one = min(MAX_SCALE, room[0] / max(w for w, _ in dims), (room[1] - 5.0 * (len(imgs) - 1)) / sum(h for _, h in dims))      # panels one above the other, at one common scale
        for (s, _), w in zip(imgs, widths):
            svg, sc = svg_inline(os.path.join(DIAGRAMS, s), (w * one, usable[1]), 1.0); parts.append(svg); scales[s] = sc
        figs.append((n, re.sub(r"<[^>]+>", "", cap)))
        return f'<figure id="fig-{n}" class="{"landscape" if wide else "portrait"}"><div class="panels{" stack" if stack else ""}">{"".join(parts)}</div><figcaption><b>Figure {n}.</b>{cap[len("Figure " + n + "."):]}</figcaption></figure>'
    body = re.sub(r"<p>((?:<img [^>]+>\s*)+)</p>\s*<p><em>(Figure \d+\..*?)</em></p>", figure, body, flags=re.S)
    def table_cap(m):
        n = m.group(1); tabs.append((n, f"Table {n}. " + re.sub(r"<[^>]+>", "", m.group(2)))); return f'<p class="cap" id="tab-{n}"><b>Table {n}.</b> {m.group(2)}</p>'
    body = re.sub(r"<p><em>Table (\d+)\. (.*?)</em></p>", table_cap, body, flags=re.S)
    body = re.sub(r"<table>(\s*<thead>\s*<tr>\s*<th>Field</th>)", r'<table class="req">\1', body)
    body = re.sub(r"<table>(\s*<thead>\s*<tr>\s*<th></th>\s*<th></th>)", r'<table class="meta">\1', body)
    pg = lambda key: str((pages or {}).get(key, "000"))
    toc = ['<div class="toc"><h2>Contents</h2>'] + [f'<div class="l{lv}"><a href="#{hid}">{html.escape(text)}</a><span class="dots"></span><span>{pg("h:" + text)}</span></div>' for lv, text, hid in heads] + ["</div>"]
    lists = ['<div class="lists"><h2>Figures and Tables</h2><h3>Figures</h3>'] + [f'<div><a href="#fig-{n}">{html.escape(cap)}</a><span class="dots"></span><span>{pg("f:" + n)}</span></div>' for n, cap in figs] + ["<h3>Tables</h3>"] \
        + [f'<div><a href="#tab-{n}">{html.escape(cap)}</a><span class="dots"></span><span>{pg("t:" + n)}</span></div>' for n, cap in tabs] + ["</div>"]
    short = lambda s: s if len(s) < 150 else s[:s.index(". ") + 1] if ". " in s[:150] else s
    cover = (f'<div class="cover"><div class="rule"></div><h1>{html.escape(title.split(":")[0])}</h1><div class="sub">{html.escape(sub)}</div><div class="kind">Software Requirements Specification</div>'
             f'<table><tr><td>Version</td><td>{html.escape(meta["version"])}</td></tr><tr><td>Date</td><td>{html.escape(meta["date"])}</td></tr><tr><td>Document status</td><td>{html.escape(meta["status"])}</td></tr>'
             f'<tr><td>Repository / version reference</td><td>{html.escape(meta["reference"])}</td></tr><tr><td>Source of this PDF</td><td>docs/SRS.md, built by scripts/build_srs.py; diagrams from docs/diagrams/*.mmd</td></tr></table></div>')
    doc = f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>AirPulse SRS</title><style>{CSS}</style></head><body>{cover}{"".join(toc)}{"".join(lists)}{body}</body></html>'
    return doc, heads, figs, tabs, scales


def print_pdf(doc, out):
    browser = next((b for b in BROWSERS if os.path.exists(b)), None)
    if not browser: sys.exit("no Chrome or Edge found: the PDF cannot be printed")
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "srs.html")
        with open(src, "w", encoding="utf-8") as f: f.write(doc)
        subprocess.run([browser, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={os.path.join(tmp, 'profile')}", f"--print-to-pdf={out}", "file:///" + src.replace(os.sep, "/")], capture_output=True, timeout=300)
    if not os.path.exists(out) or os.path.getsize(out) < 50000: sys.exit("the browser wrote no PDF")


def locate(pdf, heads, figs, tabs):
    """Printed page of every heading, figure caption and table caption. The search starts after the lists at the front."""
    import pdfplumber
    flat = lambda s: re.sub(r"\s+", "", s)
    with pdfplumber.open(pdf) as doc: texts = [flat(p.extract_text() or "") for p in doc.pages]
    start = next(i for i, t in enumerate(texts) if flat("1.1 Purpose") in t and flat("Contents") not in t); pages, at = {}, start
    for lv, text, _ in heads:
        i = next((i for i in range(at, len(texts)) if flat(text) in texts[i]), None)
        if i is not None: pages["h:" + text] = i + 1; at = i
    for n, _ in figs:
        i = next((i for i in range(start, len(texts)) if flat(f"Figure {n}.") in texts[i]), None)
        if i is not None: pages["f:" + n] = i + 1
    for n, _ in tabs:
        i = next((i for i in range(start, len(texts)) if flat(f"Table {n}.") in texts[i]), None)
        if i is not None: pages["t:" + n] = i + 1
    return pages, len(texts)


def main():
    md_text = open(SRC, encoding="utf-8").read(); tmp = OUT + ".pass1.pdf"
    doc, heads, figs, tabs, scales = to_html(md_text); print_pdf(doc, tmp); pages, n1 = locate(tmp, heads, figs, tabs); os.remove(tmp)
    missing = [k for k in [*("h:" + t for _, t, _ in heads), *("f:" + n for n, _ in figs), *("t:" + n for n, _ in tabs)] if k not in pages]
    doc, *_ = to_html(md_text, pages); print_pdf(doc, OUT); pages2, n2 = locate(OUT, heads, figs, tabs)
    print(f"docs/SRS.pdf: {n2} pages ({os.path.getsize(OUT) // 1024} KB); headings {len(heads)}, figures {len(figs)}, tables {len(tabs)}")
    print("figures on pages:", ", ".join(f"{n}:{pages2.get('f:' + n)}" for n, _ in figs)); print("tables on pages:", ", ".join(f"{n}:{pages2.get('t:' + n)}" for n, _ in tabs))
    pts = {os.path.basename(s): v * 16 / 0.3528 for s, v in scales.items()}; small = sorted(k for k, v in pts.items() if v < MIN_POINTS)
    print(f"diagram labels (16 units) print at {min(pts.values()):.1f} to {max(pts.values()):.1f} points; smallest:", ", ".join(f"{k[:3]} {v:.1f}" for k, v in sorted(pts.items(), key=lambda kv: kv[1])[:5]))
    if small: print(f"TOO SMALL (below {MIN_POINTS} points): {small}. Split the diagram or give it a landscape page.")
    if missing: print("NOT FOUND in the printed text:", missing)
    if n1 != n2 or pages != pages2: print("WARNING: page numbers moved between the passes; run again")
    return 1 if missing or small or n1 != n2 or pages != pages2 else 0


if __name__ == "__main__":
    sys.exit(main())
