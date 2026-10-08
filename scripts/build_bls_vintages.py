"""Rebuild the vintage history of the eight air freight price indexes from the Bureau of Labor Statistics' own archived releases (CL-024).

    python scripts/build_bls_vintages.py fetch     # network: archived releases of the span and the database values (one request at a time, paused)
    python scripts/build_bls_vintages.py build     # offline, deterministic: the eight vintage matrices and the log of every reconstructed cell

fetch keeps of each release page the table of transportation services, with the checksum of the whole page, in
research/bls_releases/; build reads only what fetch kept. The rule that turns a release into a column is src.ops.bls (CL-024, rule 3)."""
import csv, datetime, gzip, hashlib, io, json, os, sys, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src import config                                               # noqa: E402
from src.ops import bls                                              # noqa: E402

OUT = os.path.join(ROOT, "research", "bls_releases")
TABLES, MANIFEST, FINALS, LOG = (os.path.join(OUT, n) for n in ("transport_tables.jsonl.gz", "releases_manifest.csv", "final_values.csv", "reconstruction_log.csv"))
FIRST_RELEASE = "2010-03-16"                                         # the span of the benchmark snapshot: unchanged
LAST_RELEASE = "2026-09-16"                                          # the newest release the benchmark snapshot holds
FIRST_YEAR = 1990
PAUSE = 2.5
HEADERS = {"User-Agent": "AirPulse/1.0 (air freight research; one request at a time)", "Accept": "text/html,application/json;q=0.9,*/*;q=0.8", "Accept-Language": "en"}
SERIES = list(bls.ROWS)
sha = lambda b: hashlib.sha256(b).hexdigest()
now = lambda: datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
snapshot = lambda s: os.path.join(config.SNAPSHOT_DIR, f"SRC-09_bls_{s}_all_vintages.csv")


def http(url, data=None):
    req = urllib.request.Request(url, data=data, headers={**HEADERS, **({"Content-Type": "application/json"} if data else {})})
    with urllib.request.urlopen(req, timeout=60) as r: return r.status, r.read()


def gz(text):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g: g.write(text.encode("utf-8"))
    return buf.getvalue()


def read_tables():
    with gzip.open(TABLES, "rt", encoding="utf-8") as f: return [json.loads(l) for l in f if l.strip()]


def fetch(cache=None):
    os.makedirs(OUT, exist_ok=True); cache = cache or os.path.join(OUT, ".cache"); os.makedirs(cache, exist_ok=True)
    status, body = http(bls.ARCHIVE_LIST); time.sleep(PAUSE)
    rel = [(d, u) for d, u in bls.releases(body.decode("utf-8", "replace")) if FIRST_RELEASE <= d <= LAST_RELEASE]
    print(f"{len(rel)} releases from {rel[0][0]} to {rel[-1][0]}", flush=True); rows = []
    for i, (d, u) in enumerate(rel):
        p = os.path.join(cache, d + ".htm"); m = p + ".json"
        if not (os.path.exists(p) and os.path.exists(m)):
            status, page = http(u)
            with open(p, "wb") as f: f.write(page)
            with open(m, "w", encoding="utf-8") as f: json.dump({"retrieved_at": now(), "http_status": status}, f)
            time.sleep(PAUSE)
        page = open(p, "rb").read(); meta = json.load(open(m, encoding="utf-8"))
        try: tab = bls.table_fragment(page.decode("utf-8", "replace"))
        except bls.ReleaseError: tab = ""                                                              # a listed release that prints no table (rule f): kept as such, with the checksum of its page
        if tab: bls.parse_release(tab)                                                                 # a table that cannot be read stops the fetch
        rows.append({"release_date": d, "url": u, "page_sha256": sha(page), "page_bytes": len(page), "retrieved_at": meta["retrieved_at"], "table": tab})
        if (i + 1) % 20 == 0: print(f"  {i + 1} of {len(rel)}", flush=True)
    with open(TABLES, "wb") as f: f.write(gz("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)))
    with open(MANIFEST, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(["release_date", "url", "page_sha256", "page_bytes", "table_sha256", "retrieved_at"])
        for r in rows: w.writerow([r["release_date"], r["url"], r["page_sha256"], r["page_bytes"], sha(r["table"].encode("utf-8")), r["retrieved_at"]])
    finals = {s: {} for s in SERIES}; reqs = []; last = int(LAST_RELEASE[:4])
    for y0 in range(FIRST_YEAR, last + 1, bls.API_YEARS):
        body = bls.api_request(SERIES, y0, min(y0 + bls.API_YEARS - 1, last)); status, ans = http(bls.API, json.dumps(body).encode("utf-8")); time.sleep(PAUSE)
        got = bls.parse_api(json.loads(ans)); reqs.append({"request": body, "http_status": status, "retrieved_at": now(), "answer_sha256": sha(ans)})
        for s in SERIES: finals[s].update(got.get(s, {}))
    with open(FINALS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(["series", "month", "value"])
        for s in SERIES:
            for mth in sorted(finals[s]): w.writerow([s, mth, f"{finals[s][mth]:.1f}"])
    with open(FINALS + ".meta.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump({"source": "U.S. Bureau of Labor Statistics, public data interface, version 1 (no key)", "url": bls.API, "requests": reqs, "sha256": sha(open(FINALS, "rb").read()),
                   "note": "values of the database on the day of retrieval; a month is final after the three releases that follow its first publication"}, f, indent=1)
    print(f"kept {len(rows)} release tables and {sum(len(v) for v in finals.values())} database values of {len(SERIES)} series")


def load_finals():
    out = {s: {} for s in SERIES}
    with open(FINALS, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f): out[r["series"]][r["month"]] = float(r["value"])
    return out


def reconstruct():
    """{series: (release dates, columns, log rows)} from the kept tables and database values."""
    tabs = sorted(read_tables(), key=lambda r: r["release_date"]); finals = load_finals(); out = {}
    parsed = [(t["release_date"], bls.parse_release(t["table"]) if t["table"] else None) for t in tabs]
    for s in SERIES:
        cols, log, prev = [], [], None
        for d, rel in parsed:
            col, how = bls.column(rel, s, finals[s], prev) if rel else bls.column_without_table(prev); cols.append(col); prev = col
            log += [(d, s, mth, "" if col.get(mth) is None else f"{col[mth]:.1f}", rule) for mth, rule in how]
        assert sum(1 for _, rel in parsed if rel is None) <= 1, "more than one release without a table: read them before going on"
        out[s] = ([d for d, _ in parsed], cols, log)
    return out, tabs


def build():
    rec, tabs = reconstruct(); manifest_sha = sha(open(MANIFEST, "rb").read()); finals_meta = json.load(open(FINALS + ".meta.json", encoding="utf-8")); logs = []
    retrieved = max(t["retrieved_at"] for t in tabs)
    for s in SERIES:
        dates, cols, log = rec[s]; body = bls.matrix_text(s, dates, cols).encode("utf-8"); logs += log
        with open(snapshot(s), "wb") as f: f.write(body)
        with open(snapshot(s) + ".meta.json", "w", encoding="utf-8", newline="\n") as f:
            json.dump({"source_id": "SRC-09", "url": f"{bls.ARCHIVE_LIST} (each of {len(dates)} archived releases); {bls.API} (series {bls.bls_id(s)})", "retrieved_at": retrieved, "sha256": sha(body), "http_status": 200, "bytes": len(body),
                       "note": f"Rebuilt from the Bureau of Labor Statistics' own archived releases {dates[0]} to {dates[-1]} and its database values (CL-024, rule 3): python scripts/build_bls_vintages.py build. "
                               f"Release tables: research/bls_releases/releases_manifest.csv (sha256 {manifest_sha[:16]}); database values: research/bls_releases/final_values.csv (sha256 {finals_meta['sha256'][:16]}). Column = series_YYYYMMDD release date."}, f, indent=1)
    with open(LOG, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(["release_date", "series", "month", "value", "rule"]); w.writerows(logs)
    rules = {}
    for r in logs: rules[r[4][:2]] = rules.get(r[4][:2], 0) + 1
    print(f"{len(SERIES)} matrices written, {len(rec[SERIES[0]][0])} releases each; cells by rule: {dict(sorted(rules.items()))}")
    return rules


def premise():
    """Does the Bureau print its monthly changes from the printed indexes? Checked on the one pair whose two indexes every table prints."""
    n = bad = 0
    for t in read_tables():
        if not t["table"]: continue
        rel = bls.parse_release(t["table"])
        for s in SERIES:
            r = rel["series"][s]
            if None in (r["previous"], r["current"], r["monthly"][3]): continue
            n += 1; bad += abs(100.0 * (r["current"] / r["previous"] - 1.0) - r["monthly"][3]) > 0.05 + 1e-9
    return n, int(bad)


if __name__ == "__main__":
    {"fetch": fetch, "build": build}[sys.argv[1]]()
