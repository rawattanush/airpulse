"""Serve a built site the way GitHub Pages serves a project site, for checking it before it is deployed.

    python scripts/serve_like_pages.py airpulse-web/dist --base /airpulse/ --port 8765

  /airpulse/                     -> index.html
  /airpulse/assets/x.js          -> the file, when it exists
  /airpulse/market/forecast      -> no such file: the site's 404.html, with status 404 (what Pages does; the page it
                                    sends is the application, which then shows the route)
  /airpulse                      -> redirect to /airpulse/
  anything outside /airpulse/    -> 404

A plain static server: no rewrite rule, no fallback other than 404.html. If a route works here after a reload, it works
because of the files in the build, not because of the server. This is a stand-in for Pages, not Pages: caching, HTTPS and
the content delivery network are not reproduced."""
import http.server, mimetypes, os, sys, urllib.parse

mimetypes.add_type("text/javascript", ".js"); mimetypes.add_type("application/json", ".json"); mimetypes.add_type("image/webp", ".webp")


def handler(dist, base):
    class H(http.server.BaseHTTPRequestHandler):
        def _send(self, status, path=None, body=b"", ctype="text/plain; charset=utf-8"):
            if path:
                with open(path, "rb") as f: body = f.read()
                ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            self.send_response(status); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store"); self.end_headers()
            if self.command != "HEAD": self.wfile.write(body)

        def do_GET(self):
            path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
            if path == base.rstrip("/") and base != "/":
                self.send_response(301); self.send_header("Location", base); self.send_header("Content-Length", "0"); self.end_headers(); return
            if not path.startswith(base): return self._send(404, body=b"not found (outside the site)")
            rel = path[len(base):]; target = os.path.normpath(os.path.join(dist, *rel.split("/"))) if rel else dist
            if not os.path.abspath(target).startswith(os.path.abspath(dist)): return self._send(404, body=b"not found")
            if os.path.isdir(target): target = os.path.join(target, "index.html")
            if os.path.isfile(target): return self._send(200, target)
            fallback = os.path.join(dist, "404.html")
            return self._send(404, fallback) if os.path.isfile(fallback) else self._send(404, body=b"not found")

        do_HEAD = do_GET

        def log_message(self, fmt, *args): sys.stderr.write("%s %s\n" % (self.command, fmt % args))
    return H


def main(argv):
    if not argv or argv[0].startswith("-"): print(__doc__); return 1
    dist = os.path.abspath(argv[0]); base = argv[argv.index("--base") + 1] if "--base" in argv else "/"; port = int(argv[argv.index("--port") + 1]) if "--port" in argv else 8765
    base = "/" + base.strip("/") + "/" if base.strip("/") else "/"
    if not os.path.isfile(os.path.join(dist, "index.html")): print(f"{dist} holds no index.html: build the site first"); return 1
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler(dist, base)); print(f"serving {dist} at http://127.0.0.1:{port}{base} (Ctrl+C stops)", flush=True)
    try: srv.serve_forever()
    except KeyboardInterrupt: pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
