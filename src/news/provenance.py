"""Event store: build it from the archive, read it back, materialise features with their provenance
(REQ-NEWS-011, REQ-NEWS-012). The build is deterministic: same archive, taxonomy, reliability registry and
parser version give the same store, row for row."""
import json, os, sqlite3
import pandas as pd
from src.news import aggregation, config, deduplication, events, ingestion
from src.news.normalization import text_hash
from src.news.parser import parse_title
from src.news.taxonomy import Reliability, Taxonomy

SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


def process(records, taxonomy=None, reliability=None):
    """raw archive records -> (articles, canonical events, links, rejected). Pure: no storage, no network."""
    taxonomy = taxonomy or Taxonomy(); reliability = reliability or Reliability()
    records = sorted(records, key=lambda r: (r["published_utc"], r["source_id"], r["native_id"]))
    articles, parsed = [], []
    for r in records:
        mentions, rejected, clean = parse_title(r["title_raw"], r["source_id"], taxonomy, reliability)
        aid = f"{r['source_id']}:{r['native_id']}"
        articles.append({"article_id": aid, **r, "title_clean": clean, "text_hash": text_hash(clean)})
        parsed.append((aid, mentions, rejected))
    deduplication.mark_duplicates(articles)
    dup = {a["article_id"]: a["duplicate_of"] for a in articles}; by_id = {a["article_id"]: a for a in articles}
    flat, rej = [], []
    for aid, mentions, rejected in parsed:
        a = by_id[aid]
        for m in mentions:
            flat.append({**m, "article_id": aid, "source_id": a["source_id"], "url": a["url"], "published_utc": a["published_utc"], "fetched_at": a["fetched_at"],
                         "is_duplicate": int(dup[aid] is not None)})
        rej += [(aid, x["event_type"], x["reason"], x["pattern"]) for x in rejected]
    canon, links = deduplication.cluster(flat)
    for ev in canon: ev["reliability_version"] = reliability.version
    return articles, canon, links, rej


def build_news_db(db_path=None, archive_dir=None):
    """Verify the archive against its manifest, parse, cluster and write a fresh event store. Returns counts."""
    db_path = db_path or config.NEWS_DB_PATH; archive_dir = archive_dir or config.ARCHIVE_DIR
    archive_hash = ingestion.verify_archive(archive_dir); taxonomy, reliability = Taxonomy(), Reliability()
    articles, canon, links, rej = process(ingestion.read_archive(archive_dir), taxonomy, reliability)
    os.makedirs(os.path.dirname(db_path), exist_ok=True); tmp = db_path + ".building"
    if os.path.exists(tmp): os.remove(tmp)
    conn = sqlite3.connect(tmp)
    try:
        with open(SCHEMA, encoding="utf-8") as f: conn.executescript(f.read())
        with conn:
            conn.executemany("INSERT INTO build_meta VALUES (?,?)", [("archive_hash", archive_hash), ("taxonomy_version", taxonomy.version), ("parser_version", config.PARSER_VERSION),
                                                                     ("reliability_version", reliability.version), ("schema_version", events.SCHEMA_VERSION), ("feature_set", config.FEATURE_SET)])
            conn.executemany("INSERT INTO raw_articles VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             [(a["article_id"], a["source_id"], a["native_id"], a["url"], a["title_raw"], a["title_clean"], a["text_hash"], a["published_utc"], a["modified_utc"],
                               a["fetched_at"], a["duplicate_of"]) for a in articles])
            conn.executemany(f"INSERT INTO canonical_events({','.join(events.CANONICAL_FIELDS)}) VALUES ({','.join('?' * len(events.CANONICAL_FIELDS))})",
                             [[json.dumps(ev[k]) if k in events.LIST_FIELDS else ev[k] for k in events.CANONICAL_FIELDS] for ev in canon])
            conn.executemany("INSERT INTO event_sources VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             [(eid, aid, m["published_utc"], m["event_type"], m["feature_group"], m["status"], m["direction"], m["severity"], m["extraction_confidence"],
                               m["source_reliability"], m["source_tier"], m["matched_text"], m["pattern"], m["is_duplicate"]) for eid, aid, m in links])
            conn.executemany("INSERT INTO rejected_matches VALUES (?,?,?,?)", rej)
        conn.close()
    except Exception:
        conn.close()
        if os.path.exists(tmp): os.remove(tmp)
        raise
    os.replace(tmp, db_path)
    return {"articles": len(articles), "duplicate_articles": sum(1 for a in articles if a["duplicate_of"]), "canonical_events": len(canon), "event_sources": len(links),
            "rejected_matches": len(rej), "archive_hash": archive_hash}


def connect(db_path=None):
    return sqlite3.connect(db_path or config.NEWS_DB_PATH)


def load_index(conn):
    """EventIndex over the stored events."""
    links = pd.read_sql_query("""SELECT s.event_id, s.article_id, s.publication_time, s.event_type, s.feature_group, s.status, s.direction, s.severity, s.extraction_confidence,
                                        s.source_reliability, s.is_duplicate, e.parent_category AS category, e.affected_mode, e.diversion_pressure
                                 FROM event_sources s JOIN canonical_events e ON e.event_id = s.event_id""", conn)
    arts = pd.read_sql_query("SELECT article_id, published_utc, duplicate_of FROM raw_articles", conn)
    return aggregation.EventIndex(links, arts)


def index_from_memory(canon, links, articles):
    """EventIndex straight from process() output (used by tests and by callers that do not need a file)."""
    ev = {e["event_id"]: e for e in canon}
    rows = [{"event_id": eid, "article_id": aid, "publication_time": m["published_utc"], "event_type": m["event_type"], "feature_group": m["feature_group"], "status": m["status"],
             "direction": m["direction"], "severity": m["severity"], "extraction_confidence": m["extraction_confidence"], "source_reliability": m["source_reliability"],
             "is_duplicate": m["is_duplicate"], "category": ev[eid]["parent_category"], "affected_mode": ev[eid]["affected_mode"], "diversion_pressure": ev[eid]["diversion_pressure"]}
            for eid, aid, m in links]
    cols = ["event_id", "article_id", "publication_time", "event_type", "feature_group", "status", "direction", "severity", "extraction_confidence", "source_reliability",
            "is_duplicate", "category", "affected_mode", "diversion_pressure"]
    return aggregation.EventIndex(pd.DataFrame(rows, columns=cols), pd.DataFrame([{"article_id": a["article_id"], "published_utc": a["published_utc"], "duplicate_of": a["duplicate_of"]} for a in articles],
                                                                               columns=["article_id", "published_utc", "duplicate_of"]))


def materialise_features(conn, as_of_list, windows=None):
    """Compute features for each cut-off and store them with the ids of the events behind each value."""
    idx = load_index(conn); n = 0
    with conn:
        for as_of in as_of_list:
            feats, prov = idx.features(as_of, windows); key = str(as_of)[:19].replace(" ", "T") + "Z"
            conn.execute("DELETE FROM event_features WHERE as_of = ?", (key,))
            for name, value in feats.items():
                if name.startswith("_"): continue
                base = name[:-5] if name.endswith("_rate") else name
                conn.execute("INSERT INTO event_features VALUES (?,?,?,?,?)", (key, name, None if value != value else float(value), json.dumps(prov.get(base, [])), config.FEATURE_SET)); n += 1
    return n
