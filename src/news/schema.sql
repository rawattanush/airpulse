-- Event store of the event-intelligence layer (data/news.sqlite). Separate from the benchmark store:
-- src/database/schema.sql is frozen and build-db never touches this file. Rebuilt from research/news_archive/.
-- Times are ISO 8601 UTC text. List-valued fields are JSON arrays.
CREATE TABLE build_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- raw source metadata, one row per archived article; never altered by parsing
CREATE TABLE raw_articles (
    article_id      TEXT PRIMARY KEY,           -- source_id:native_id
    source_id       TEXT NOT NULL,
    native_id       TEXT NOT NULL,
    url             TEXT NOT NULL,
    title_raw       TEXT NOT NULL,
    title_clean     TEXT NOT NULL,
    text_hash       TEXT NOT NULL,
    published_utc   TEXT NOT NULL,              -- publication time = availability time
    modified_utc    TEXT NOT NULL,              -- publisher's last-modified time at fetch
    fetched_at      TEXT NOT NULL,              -- ingestion time
    duplicate_of    TEXT REFERENCES raw_articles(article_id)
);
CREATE INDEX ix_art_pub ON raw_articles(published_utc);
CREATE TABLE canonical_events (
    event_id TEXT PRIMARY KEY, schema_version TEXT NOT NULL, taxonomy_version TEXT NOT NULL, parser_version TEXT NOT NULL, reliability_version TEXT NOT NULL,
    event_type TEXT NOT NULL, parent_category TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'POTENTIAL', 'ENDED')), direction INTEGER NOT NULL,
    source_id TEXT NOT NULL, source_type TEXT NOT NULL, source_url TEXT NOT NULL,
    publication_time TEXT NOT NULL,             -- first article
    last_publication_time TEXT NOT NULL,
    event_time TEXT,                            -- NULL: not established by parser P1.0
    ingestion_time TEXT NOT NULL,
    geographic_scope TEXT NOT NULL, countries TEXT NOT NULL, regions TEXT NOT NULL, airports TEXT NOT NULL, ports TEXT NOT NULL, airlines TEXT NOT NULL, carriers TEXT NOT NULL,
    severity INTEGER NOT NULL CHECK (severity BETWEEN 1 AND 3), extraction_confidence REAL NOT NULL, source_reliability REAL NOT NULL,
    corroboration_count INTEGER NOT NULL, source_count INTEGER NOT NULL,
    affected_mode TEXT NOT NULL, capacity_effect TEXT NOT NULL, demand_effect TEXT NOT NULL, supply_effect TEXT NOT NULL, diversion_pressure TEXT NOT NULL,
    duration_class TEXT NOT NULL, raw_text_hash TEXT NOT NULL
);
CREATE INDEX ix_ev_pub ON canonical_events(publication_time);
-- every article that contributed to an event, with what the parser read from that article
CREATE TABLE event_sources (
    event_id TEXT NOT NULL REFERENCES canonical_events(event_id),
    article_id TEXT NOT NULL REFERENCES raw_articles(article_id),
    publication_time TEXT NOT NULL,
    event_type TEXT NOT NULL, feature_group TEXT NOT NULL, status TEXT NOT NULL, direction INTEGER NOT NULL,
    severity INTEGER NOT NULL, extraction_confidence REAL NOT NULL, source_reliability REAL NOT NULL, source_tier INTEGER NOT NULL,
    matched_text TEXT NOT NULL, pattern TEXT NOT NULL, is_duplicate INTEGER NOT NULL,
    PRIMARY KEY (event_id, article_id)
);
CREATE INDEX ix_es_pub ON event_sources(publication_time);
-- candidates the parser refused, with the reason (NEGATED, RETROSPECTIVE, MODE, POTENTIAL_END)
CREATE TABLE rejected_matches (
    article_id TEXT NOT NULL REFERENCES raw_articles(article_id), event_type TEXT NOT NULL, reason TEXT NOT NULL, pattern TEXT NOT NULL
);
-- materialised features: one row per (cut-off, feature); event_ids lists the canonical events behind the value
CREATE TABLE event_features (
    as_of TEXT NOT NULL, feature TEXT NOT NULL, value REAL, event_ids TEXT NOT NULL, feature_set TEXT NOT NULL,
    PRIMARY KEY (as_of, feature)
);
