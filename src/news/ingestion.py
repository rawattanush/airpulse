"""Ingestion: source adapters and the raw article archive (REQ-NEWS-001, REQ-NEWS-002).

An adapter returns raw article records and nothing else touches the network. Records are appended to
research/news_archive/<source>/<year>.jsonl, sorted and de-duplicated by native id, and a manifest with one
SHA-256 per file is rewritten. Only metadata is stored: title, link, publication and modification times.
No article body is fetched or stored.

Raw record: {source_id, native_id, url, title_raw, published_utc, modified_utc, fetched_at}
Standard library only, so the job can run on a minimal scheduled runner."""
import datetime, hashlib, json, os, re, time, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from src.news import config


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT, "Accept": "application/json, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), dict(r.headers)


def fetch_wordpress(source_id, base, after=None, max_pages=None, log=print):
    """All posts published after `after` (ISO, UTC), oldest first, 100 per request."""
    out, page = [], 1
    while True:
        q = {"per_page": 100, "page": page, "order": "asc", "orderby": "date", "_fields": "id,date_gmt,modified_gmt,link,title"}
        if after: q["after"] = after
        url = f"{base}/wp-json/wp/v2/posts?" + urllib.parse.urlencode(q)
        for attempt in range(4):
            try:
                body, headers = _get(url); break
            except urllib.error.HTTPError as e:
                if e.code == 400: return out                      # past the last page
                if attempt == 3: raise
                time.sleep(10 * (attempt + 1))
            except Exception:
                if attempt == 3: raise
                time.sleep(10 * (attempt + 1))
        posts = json.loads(body); fetched = _now()
        if not posts: return out
        for p in posts:
            out.append({"source_id": source_id, "native_id": str(p["id"]), "url": p["link"], "title_raw": p["title"]["rendered"],
                        "published_utc": p["date_gmt"] + "Z", "modified_utc": (p.get("modified_gmt") or p["date_gmt"]) + "Z", "fetched_at": fetched})
        total = int({k.lower(): v for k, v in headers.items()}.get("x-wp-totalpages", page))
        if page % 25 == 0: log(f"  {source_id}: page {page} of {total}")
        if page >= total or (max_pages and page >= max_pages): return out
        page += 1; time.sleep(config.REQUEST_PAUSE_SECONDS)


def parse_rss(source_id, xml_bytes, fetched_at):
    """RSS 2.0 items -> raw records. An item without a parseable pubDate is dropped (its availability time is unknown)."""
    out = []
    root = ET.fromstring(xml_bytes)
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip(); link = (item.findtext("link") or "").strip(); pub = item.findtext("pubDate")
        if not title or not link or not pub: continue
        try: dt = parsedate_to_datetime(pub).astimezone(datetime.timezone.utc)
        except Exception: continue
        iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append({"source_id": source_id, "native_id": hashlib.sha256(link.encode()).hexdigest()[:16], "url": link, "title_raw": title,
                    "published_utc": iso, "modified_utc": iso, "fetched_at": fetched_at})
    return out


def fetch_rss(source_id, url):
    body, _ = _get(url); return parse_rss(source_id, body, _now())


# ------------------------------------------------------------------ archive
def _year_file(source_id, year, archive_dir):
    return os.path.join(archive_dir, source_id, f"{year}.jsonl")


def read_archive(archive_dir=None, sources=None):
    """Every archived raw record, ordered by (published_utc, source_id, native_id)."""
    archive_dir = archive_dir or config.ARCHIVE_DIR; recs = []
    if not os.path.isdir(archive_dir): return recs
    for sid in sorted(os.listdir(archive_dir)):
        d = os.path.join(archive_dir, sid)
        if not os.path.isdir(d) or (sources and sid not in sources): continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".jsonl"):
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    recs += [json.loads(line) for line in fh if line.strip()]
    recs.sort(key=lambda r: (r["published_utc"], r["source_id"], r["native_id"]))
    return recs


def append_to_archive(records, archive_dir=None):
    """Merge records into the archive. An article already archived is never overwritten: the first-seen title and
    times are kept, so a later edit by the publisher cannot change history. Returns the number of new records."""
    archive_dir = archive_dir or config.ARCHIVE_DIR; by_file = {}; new = 0
    for r in records:
        if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", r["published_utc"]): continue
        by_file.setdefault(_year_file(r["source_id"], r["published_utc"][:4], archive_dir), []).append(r)
    for path, recs in by_file.items():
        os.makedirs(os.path.dirname(path), exist_ok=True); have = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip(): x = json.loads(line); have[x["native_id"]] = x
        for r in recs:
            if r["native_id"] not in have: have[r["native_id"]] = r; new += 1
        rows = sorted(have.values(), key=lambda x: (x["published_utc"], x["native_id"]))
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            for x in rows: fh.write(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n")
    write_manifest(archive_dir)
    return new


def write_manifest(archive_dir=None):
    archive_dir = archive_dir or config.ARCHIVE_DIR; files = {}
    for sid in sorted(os.listdir(archive_dir)):
        d = os.path.join(archive_dir, sid)
        if not os.path.isdir(d): continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".jsonl"):
                with open(os.path.join(d, f), "rb") as fh: b = fh.read()
                files[f"{sid}/{f}"] = {"sha256": hashlib.sha256(b).hexdigest(), "records": b.count(b"\n")}
    with open(os.path.join(archive_dir, "manifest.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"files": files}, fh, indent=1, sort_keys=True)
    return files


def verify_archive(archive_dir=None):
    """Raise if any archive file differs from the manifest. Returns the archive hash (over names and checksums)."""
    archive_dir = archive_dir or config.ARCHIVE_DIR
    with open(os.path.join(archive_dir, "manifest.json"), encoding="utf-8") as fh: files = json.load(fh)["files"]
    h = hashlib.sha256()
    for name in sorted(files):
        with open(os.path.join(archive_dir, name), "rb") as fh: digest = hashlib.sha256(fh.read()).hexdigest()
        if digest != files[name]["sha256"]: raise ValueError(f"news archive file {name} does not match the manifest")
        h.update(name.encode()); h.update(digest.encode())
    return h.hexdigest()


def latest_published(source_id, archive_dir=None):
    recs = read_archive(archive_dir, sources=[source_id])
    return recs[-1]["published_utc"] if recs else None


CHUNK_PAGES = 40          # a WordPress source is fetched and archived 4,000 articles at a time, so an interrupted run loses little


def _minus_one_second(iso):
    t = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ") - datetime.timedelta(seconds=1)
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def ingest(source_ids=None, archive_dir=None, full=False, max_pages=None, log=print):
    """Fetch every configured source and append to the archive. Incremental unless full=True: only articles published
    after the newest archived one are requested (the request starts one second earlier, so that articles sharing
    that timestamp are not missed; known ones are ignored by the archive)."""
    result = {}
    for sid, s in config.SOURCES.items():
        if source_ids and sid not in source_ids: continue
        latest = None if full else latest_published(sid, archive_dir); fetched = new = 0
        if s["kind"] == "wordpress":
            after = _minus_one_second(latest) if latest else None
            while True:
                recs = fetch_wordpress(sid, s["base"], after=after, max_pages=max_pages or CHUNK_PAGES, log=log)
                added = append_to_archive(recs, archive_dir) if recs else 0; fetched += len(recs); new += added
                log(f"  {sid}: {fetched} fetched, {new} new" + (f", up to {recs[-1]['published_utc']}" if recs else ""))
                if max_pages or len(recs) < CHUNK_PAGES * 100 or added == 0: break
                after = _minus_one_second(max(r["published_utc"] for r in recs))
        elif s["kind"] == "rss":
            recs = fetch_rss(sid, s["url"]); fetched = len(recs); new = append_to_archive(recs, archive_dir)
        else: raise ValueError(f"unknown source kind {s['kind']}")
        result[sid] = {"fetched": fetched, "new": new}
    return result
