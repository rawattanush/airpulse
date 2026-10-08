"""Deduplication and corroboration (REQ-NEWS-007).

Two levels:
  1. Duplicate articles: an article whose normalised headline hash was already seen (any source) within
     DUPLICATE_WINDOW_DAYS is marked as a duplicate of the first one. A duplicate still points to its event but
     adds nothing to corroboration.
  2. Event clustering: mentions of the same event type and status are merged into one canonical event when
     their places overlap (or neither names a place) and their organisations overlap (or neither names one),
     and the event's latest article is at most CLUSTER_GAP_DAYS older.

Clustering is incremental in publication order: where an article goes depends only on articles published
before it. The clusters as of any date are therefore exactly what they would have been on that date."""
import datetime
from src.news import config, events

DUPLICATE_WINDOW_DAYS = 30


def _ts(iso):
    return datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")


def mark_duplicates(articles):
    """articles: dicts with article_id, text_hash, published_utc, in publication order. Adds 'duplicate_of' (id or None)."""
    seen = {}
    for a in articles:
        first = seen.get(a["text_hash"])
        if first and (_ts(a["published_utc"]) - _ts(first[1])).days <= DUPLICATE_WINDOW_DAYS: a["duplicate_of"] = first[0]
        else: a["duplicate_of"] = None; seen[a["text_hash"]] = (a["article_id"], a["published_utc"])
    return articles


def _places(m):
    specific = set(m["airports"]) | set(m["ports"]) | set(m["chokepoints"])
    return specific or set(m["countries"]) or set(m["regions"])


def _orgs(m):
    return set(m["airlines"]) | set(m["carriers"])


def _compatible(a, b):
    """Sets overlap, or both are empty. One empty and one not is treated as different events."""
    return bool(a & b) if (a and b) else (not a and not b)


def cluster(mentions, gap_days=None):
    """mentions: dicts in publication order, each with article_id, published_utc, is_duplicate and the parser fields.
    Returns (canonical_events, links) where links are (event_id, article_id, mention) triples."""
    gap = datetime.timedelta(days=gap_days if gap_days is not None else config.CLUSTER_GAP_DAYS)
    open_by_key, canon, links = {}, [], []
    for m in mentions:
        key = (m["event_type"], m["status"]); t = _ts(m["published_utc"]); places, orgs = _places(m), _orgs(m); target = None
        for ev in reversed(open_by_key.get(key, [])):                       # most recently updated first
            if t - ev["_last"] > gap: continue
            if _compatible(places, ev["_places"]) and _compatible(orgs, ev["_orgs"]): target = ev; break
        if target is None:
            target = {"event_id": events.event_id(m["event_type"], m["status"], m["article_id"], m["taxonomy_version"], m["parser_version"]),
                      "schema_version": events.SCHEMA_VERSION, "taxonomy_version": m["taxonomy_version"], "parser_version": m["parser_version"],
                      "event_type": m["event_type"], "parent_category": m["parent_category"], "status": m["status"], "direction": m["direction"],
                      "source_id": m["source_id"], "source_type": m["source_type"], "source_url": m["url"],
                      "publication_time": m["published_utc"], "last_publication_time": m["published_utc"], "event_time": None, "ingestion_time": m["fetched_at"],
                      "geographic_scope": m["geographic_scope"], **{k: list(m[k]) for k in events.LIST_FIELDS},
                      "severity": m["severity"], "extraction_confidence": m["extraction_confidence"], "source_reliability": m["source_reliability"],
                      "corroboration_count": 0, "source_count": 0, "affected_mode": m["affected_mode"],
                      "capacity_effect": m["effects"]["capacity"], "demand_effect": m["effects"]["demand"], "supply_effect": m["effects"]["supply"],
                      "diversion_pressure": m["effects"]["diversion_pressure"], "duration_class": m["duration_class"], "raw_text_hash": m["raw_text_hash"],
                      "_places": set(places), "_orgs": set(orgs), "_last": t, "_sources": set()}
            canon.append(target); open_by_key.setdefault(key, []).append(target)
        else:
            open_by_key[key].remove(target); open_by_key[key].append(target)   # keep the list ordered by last update
        target["_last"] = t; target["last_publication_time"] = m["published_utc"]
        if not m["is_duplicate"]:
            target["corroboration_count"] += 1; target["_sources"].add(m["source_id"]); target["source_count"] = len(target["_sources"])
            target["severity"] = max(target["severity"], m["severity"]); target["extraction_confidence"] = max(target["extraction_confidence"], m["extraction_confidence"])
            target["source_reliability"] = max(target["source_reliability"], m["source_reliability"])
            target["_places"] |= places; target["_orgs"] |= orgs
            for k in events.LIST_FIELDS: target[k] = sorted(set(target[k]) | set(m[k]))
            if target["duration_class"] == "UNKNOWN": target["duration_class"] = m["duration_class"]
            if target["geographic_scope"] == "UNKNOWN": target["geographic_scope"] = m["geographic_scope"]
        links.append((target["event_id"], m["article_id"], m))
    for ev in canon:
        for k in ("_places", "_orgs", "_last", "_sources"): ev.pop(k)
    return canon, links
