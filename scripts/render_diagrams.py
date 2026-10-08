"""Render the diagram sources of the documentation (docs/diagrams/*.mmd, Mermaid notation) to SVG files beside them.

    python scripts/render_diagrams.py <path to mermaid.min.js>

The sources are the editable form; the SVG files are committed, so that building the PDF (scripts/build_srs.py) needs no
renderer. To change a diagram: edit its .mmd file, run this script, run build_srs.py. Mermaid is not a dependency of the
product; any copy of version 11 serves (for example `npm install mermaid@11` in a scratch folder, then
node_modules/mermaid/dist/mermaid.min.js). The rendering is done by a locally installed Edge or Chrome without a window.
Nothing is fetched from the network."""
import html, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "docs", "diagrams")
BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",   # Chrome first: Edge prints no DOM on some builds
            "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/microsoft-edge"]
CONFIG = """{ startOnLoad: false, securityLevel: 'loose', theme: 'base', fontFamily: 'Arial, Helvetica, sans-serif',
  themeVariables: { fontSize: '16px', primaryColor: '#ffffff', primaryBorderColor: '#1f2937', primaryTextColor: '#111827', lineColor: '#374151', secondaryColor: '#f3f4f6', tertiaryColor: '#f9fafb',
                    clusterBkg: '#f9fafb', clusterBorder: '#6b7280', edgeLabelBackground: '#ffffff', actorBkg: '#ffffff', actorBorder: '#1f2937', noteBkgColor: '#f3f4f6', noteBorderColor: '#6b7280',
                    labelBoxBkgColor: '#f3f4f6', labelBoxBorderColor: '#6b7280', signalColor: '#111827', signalTextColor: '#111827', activationBkgColor: '#e5e7eb' },
  flowchart: { htmlLabels: true, curve: 'linear', nodeSpacing: 30, rankSpacing: 44, padding: 10, useMaxWidth: false, wrappingWidth: 340 },
  sequence: { useMaxWidth: false, mirrorActors: false, messageMargin: 26, actorMargin: 14, boxMargin: 8, width: 132, wrap: true, showSequenceNumbers: true },
  er: { useMaxWidth: false, fontSize: 16, layoutDirection: 'TB' }, state: { useMaxWidth: false } }"""


def main(argv):
    if len(argv) != 1 or not os.path.isfile(argv[0]): print(__doc__); return 1
    found = [b for b in BROWSERS if os.path.exists(b)]
    if not found: print("no Edge or Chrome found"); return 1
    names = sorted(f[:-4] for f in os.listdir(DIR) if f.endswith(".mmd"))
    blocks = "\n".join(f'<pre class="src" id="src-{n}">{html.escape(open(os.path.join(DIR, n + ".mmd"), encoding="utf-8").read())}</pre><div id="svg-{n}"></div><pre id="out-{n}"></pre>' for n in names)
    page = f"""<!doctype html><html><head><meta charset="utf-8"></head><body>{blocks}
<script src="file:///{os.path.abspath(argv[0]).replace(os.sep, '/')}"></script>
<script>
mermaid.initialize({CONFIG});
(async () => {{
  for (const pre of document.querySelectorAll('pre.src')) {{
    const n = pre.id.slice(4);
    try {{
      const {{ svg }} = await mermaid.render('d-' + n, pre.textContent);
      document.getElementById('svg-' + n).innerHTML = svg;
      const el = document.getElementById('svg-' + n).querySelector('svg'); const b = el.getBBox ? el.getBBox() : null;
      document.getElementById('out-' + n).textContent = new XMLSerializer().serializeToString(el);
    }} catch (e) {{ document.getElementById('out-' + n).textContent = 'ERROR ' + e; }}
  }}
  document.body.setAttribute('data-done', '1');
}})();
</script></body></html>"""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "diagrams.html")
        with open(src, "w", encoding="utf-8") as f: f.write(page)
        dom = ""
        for k, browser in enumerate(found):                                       # the first browser that returns the rendered page
            p = subprocess.run([browser, "--headless", "--disable-gpu", "--allow-file-access-from-files", f"--user-data-dir={os.path.join(tmp, 'profile' + str(k))}", "--virtual-time-budget=60000", "--dump-dom", "file:///" + src.replace(os.sep, "/")],
                               capture_output=True, timeout=300)
            dom = p.stdout.decode("utf-8", "replace")
            if 'data-done="1"' in dom: break
    bad = 0
    if 'data-done="1"' not in dom: print("the page did not finish rendering"); return 1
    for n in names:
        m = re.search(rf'<pre id="out-{re.escape(n)}">(.*?)</pre>', dom, re.S); text = html.unescape(m.group(1)) if m else "ERROR not found"
        if not text.startswith("<svg"): print(f"FAILED {n}: {text[:300]}"); bad += 1; continue
        with open(os.path.join(DIR, n + ".svg"), "w", encoding="utf-8", newline="\n") as f: f.write(text + "\n")
        size = re.search(r'viewBox="([^"]+)"', text); print(f"rendered {n}.svg ({len(text) // 1024} KB, viewBox {size.group(1) if size else '?'})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
