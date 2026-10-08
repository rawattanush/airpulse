"""Configuration of the event-intelligence layer. Separate from src/config.py, which is frozen with the benchmark.
Nothing here is read by the benchmark pipeline."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARCHIVE_DIR = os.path.join(ROOT, "research", "news_archive")          # tracked: raw article metadata, one JSONL per source and year
NEWS_DB_PATH = os.path.join(ROOT, "data", "news.sqlite")              # derived; rebuilt from the archive
TAXONOMY_PATH = os.path.join(ROOT, "research", "event_taxonomy_v1.yaml")
RELIABILITY_PATH = os.path.join(ROOT, "research", "source_reliability.yaml")

PARSER_VERSION = "P1.0"
EVENT_SCHEMA_VERSION = "E1"
FEATURE_SET = "NEWS_EVENT_FEATURES_V1"
WINDOWS_DAYS = (1, 3, 7, 14, 30)
ABLATION_WINDOW_DAYS = 30            # fixed before the ablation was run: the target is monthly
CLUSTER_GAP_DAYS = 3                 # an article joins an open event of the same key if the event's last article is at most this old
USER_AGENT = "AirPulse-research/1.0 (academic project; headline metadata only)"
REQUEST_PAUSE_SECONDS = 1.0

# Article sources. kind 'wordpress' = public WordPress REST API (titles, dates, links only); kind 'rss' = RSS feed.
# history=True: the adapter can page back through the full archive. A source is listed here only if its robots.txt
# does not disallow the endpoint (checked 2026-10-04); see research/source_reliability.yaml for tiers.
SOURCES = {
    "aircargoweek": {"kind": "wordpress", "base": "https://aircargoweek.com", "history": True, "registry_id": "SRC-23"},
    "splash247": {"kind": "wordpress", "base": "https://splash247.com", "history": True, "registry_id": "SRC-24"},
}
