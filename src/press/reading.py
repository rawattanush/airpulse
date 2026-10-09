"""Reading of the trade press for the news-adjusted outlook (change record CL-028). EXPERIMENTAL.

    from src.press import reading as press;  press.refresh()      # one record per source in operations/press/ingestion_log.jsonl

What is kept, and what is not. For each of the two publications the article metadata of the last WINDOW_DAYS is fetched
from the publication's public interface, every headline is parsed by the rule-based parser, and ONLY the parsed events
are stored: event type, status, direction, severity, places and organisations named, the article's address and date, and
a hash of the normalised headline (for duplicate detection). The headline text is not stored, not committed and not shown;
the fragment of it that a pattern matched is dropped as well. The file of a source is replaced as a whole by each
successful reading, so it never holds more than the window. No archive is built here: the archive of the research
repository is a different thing and is not used at run time.

A reading that fails, is empty or does not validate leaves the file held untouched and is recorded with its reason."""
import datetime, hashlib, json, os
from src.news import config, deduplication, ingestion, provenance
from src.news.normalization import text_hash
from src.news.parser import parse_title
from src.news.taxonomy import Reliability, Taxonomy
from src.observability import records

PRESS_DIR = os.path.join(config.ROOT, "operations", "press")
LOG = os.path.join(PRESS_DIR, "ingestion_log.jsonl")
SOURCES = {"press_aircargoweek": "aircargoweek", "press_splash247": "splash247"}          # declared id -> publication (src.news.config.SOURCES)
WINDOW_DAYS = 45                                                                         # the 30-day feature window and the clustering gap before it
DROP = ("pattern", "matched_text")                                                       # parser fields that quote or describe the headline's wording
SCHEMA = "PRESS-1"

utc_now = lambda: datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
path_of = lambda source_id, press_dir=None: os.path.join(press_dir or PRESS_DIR, f"{SOURCES[source_id]}_events.json")


def parse(records_, taxonomy=None, reliability=None):
    """Article metadata -> the stored form: no headline text, the parsed mentions with their wording removed."""
    taxonomy = taxonomy or Taxonomy(); reliability = reliability or Reliability(); out = []
    for r in sorted(records_, key=lambda r: (r["published_utc"], r["source_id"], r["native_id"])):
        mentions, _, clean = parse_title(r["title_raw"], r["source_id"], taxonomy, reliability)
        out.append({"article_id": f"{r['source_id']}:{r['native_id']}", "source_id": r["source_id"], "url": r["url"], "published_utc": r["published_utc"], "text_hash": text_hash(clean),
                    "mentions": [{k: v for k, v in m.items() if k not in DROP} for m in mentions]})
    return out


def read_source(source_id, press_dir=None, fetch=ingestion.fetch_wordpress, now=utc_now):
    """Fetch, validate, parse and store one publication. Returns the run record (never raises)."""
    t = now(); started = iso(t); pub = SOURCES[source_id]; base = config.SOURCES[pub]["base"]; path = path_of(source_id, press_dir)
    rec = {"source": source_id, "group": "press", "retrieved_at": started, "url": base + "/wp-json/wp/v2/posts", "result": "FAILED", "error": "", "record_count": None, "latest_observation": None,
           "checksum": None, "validation": "", "new_records": 0, "schema_version": SCHEMA}
    held = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None
    if held: rec.update(checksum=held["sha256"], latest_observation=held["to"], record_count=len(held["articles"]))
    try:
        got = fetch(pub, base, after=iso(t - datetime.timedelta(days=WINDOW_DAYS))[:-1], max_pages=20, log=lambda *_: None)
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {str(e)[:160]}"; return rec
    lo, hi = iso(t - datetime.timedelta(days=WINDOW_DAYS + 1)), iso(t + datetime.timedelta(days=1))
    bad = [r for r in got if not (r.get("url", "").startswith(base) and r.get("title_raw") and lo <= r.get("published_utc", "") <= hi)]
    if not got or bad:
        rec.update(error="validation failed: " + ("no article in the window" if not got else f"{len(bad)} of {len(got)} records outside the window, without a title or not at the publication's address"), validation="FAILED"); return rec
    articles = parse(got); body = {"schema": SCHEMA, "source": source_id, "window_days": WINDOW_DAYS, "from": articles[0]["published_utc"], "to": articles[-1]["published_utc"], "articles": articles}
    sha = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    new = len({a["article_id"] for a in articles} - {a["article_id"] for a in (held or {"articles": []})["articles"]})
    rec.update(result="UNCHANGED" if held and held["sha256"] == sha else "UPDATED", record_count=len(articles), latest_observation=body["to"], checksum=sha, new_records=new,
               validation=f"passed: {len(articles)} articles, {sum(len(a['mentions']) for a in articles)} parsed mentions; headline text not stored")
    if rec["result"] == "UPDATED":
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".new", "w", encoding="utf-8", newline="\n") as f: json.dump({**body, "sha256": sha, "retrieved_at": started}, f, indent=1, sort_keys=True, ensure_ascii=False)
        os.replace(path + ".new", path)
    return rec


def refresh(press_dir=None, log_path=None, trigger=None, workflow_run=None, sources=None, **kw):
    """Read every publication; one record each in the press log, whatever happened."""
    out = []
    for sid in (sources or SOURCES):
        rec = read_source(sid, press_dir, **kw); rec.update(trigger=trigger, workflow_run=workflow_run); out.append(records.append(log_path or LOG, rec))
    return out


def held(press_dir=None):
    """The stored readings: {source id: file content}. Only files that exist."""
    return {sid: json.load(open(path_of(sid, press_dir), encoding="utf-8")) for sid in SOURCES if os.path.exists(path_of(sid, press_dir))}


def index(files):
    """Event index over the stored readings of all publications, built exactly as the event store builds it
    (duplicates across publications, clustering in publication order). Returns (index, canonical events, links, articles)."""
    arts = sorted((dict(a) for f in files.values() for a in f["articles"]), key=lambda a: (a["published_utc"], a["source_id"], a["article_id"]))
    deduplication.mark_duplicates(arts); flat = []
    for a in arts:
        for m in a["mentions"]:
            flat.append({**m, "article_id": a["article_id"], "source_id": a["source_id"], "url": a["url"], "published_utc": a["published_utc"], "fetched_at": a["published_utc"], "is_duplicate": int(a["duplicate_of"] is not None)})
    canon, links = deduplication.cluster(flat)
    return provenance.index_from_memory(canon, links, arts), canon, links, arts
