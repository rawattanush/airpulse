"""Event schema, version E1 (REQ-NEWS-004).

Two record kinds:
  mention          one event type found in one article (what the parser emits)
  canonical event  one underlying event, built from one or more mentions by src/news/deduplication.py

A value that the parser cannot establish stays None / "UNKNOWN" / an empty list. Nothing is guessed.
In particular `event_time` is None in parser version P1.0: a headline rarely states when the event happened,
and the layer never needs it, because availability is governed by `publication_time`."""
import hashlib

SCHEMA_VERSION = "E1"
STATUSES = ("ACTIVE", "POTENTIAL", "ENDED")
STATUS_WEIGHT = {"ACTIVE": 1.0, "POTENTIAL": 0.5, "ENDED": 0.0}     # ENDED events are counted as relief, never as a shock

CANONICAL_FIELDS = [
    "event_id", "schema_version", "taxonomy_version", "parser_version", "reliability_version",
    "event_type", "parent_category", "status", "direction",
    "source_id", "source_type", "source_url",                      # of the first article that reported the event
    "publication_time", "last_publication_time", "event_time", "ingestion_time",
    "geographic_scope", "countries", "regions", "airports", "ports", "airlines", "carriers",
    "severity", "extraction_confidence", "source_reliability", "corroboration_count", "source_count",
    "affected_mode", "capacity_effect", "demand_effect", "supply_effect", "diversion_pressure",
    "duration_class", "raw_text_hash",
]
LIST_FIELDS = ("countries", "regions", "airports", "ports", "airlines", "carriers")


def event_id(event_type, status, first_article_id, taxonomy_version, parser_version):
    key = "|".join([event_type, status, first_article_id, taxonomy_version, parser_version])
    return "EV-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
