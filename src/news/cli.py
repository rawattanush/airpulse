"""Command line of the event-intelligence layer. Run from the repository root.

    python -m src.news.cli ingest [--full] [--source ID ...]   # network: fetch new articles into research/news_archive/
    python -m src.news.cli build                                # archive -> data/news.sqlite (parse, deduplicate, cluster)
    python -m src.news.cli stats                                # counts by source, event type and status
    python -m src.news.cli features --as-of 2024-01-15          # print the features as of a cut-off (UTC midnight)
    python -m src.news.cli parse "Headline text" [--source ID]  # show what the parser reads from one headline

`ingest` and `build` are the two steps of the scheduled job; neither needs a GPU, a language model or a paid service."""
import argparse, json, os, sys
import pandas as pd
from src.news import config


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m src.news.cli", description="AirPulse event-intelligence layer (experimental; not part of the validated benchmark).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ingest", help="fetch new article metadata from the configured sources into the archive")
    i.add_argument("--full", action="store_true", help="fetch the whole history instead of only articles newer than the archive")
    i.add_argument("--source", nargs="*", choices=list(config.SOURCES))
    sub.add_parser("build", help="rebuild the event store from the archive")
    sub.add_parser("stats", help="counts in the event store")
    f = sub.add_parser("features", help="features as of a cut-off time"); f.add_argument("--as-of", required=True, help="YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS (UTC)")
    f.add_argument("--window", type=int, default=config.ABLATION_WINDOW_DAYS, choices=list(config.WINDOWS_DAYS))
    p = sub.add_parser("parse", help="parse one headline"); p.add_argument("title"); p.add_argument("--source", default="aircargoweek")
    a = ap.parse_args(argv)

    if a.cmd == "ingest":
        from src.news import ingestion
        r = ingestion.ingest(a.source or None, full=a.full); print(json.dumps(r))
    elif a.cmd == "build":
        from src.news.provenance import build_news_db
        r = build_news_db(); print(f"event store built at {config.NEWS_DB_PATH}"); [print(f"  {k}: {v}") for k, v in r.items()]
    elif a.cmd == "parse":
        from src.news.parser import parse_title
        from src.news.taxonomy import Reliability, Taxonomy
        m, rej, clean = parse_title(a.title, a.source, Taxonomy(), Reliability()); print(clean)
        for x in m: print(f"  EVENT    {x['event_type']:<28} status {x['status']:<9} severity {x['severity']} confidence {x['extraction_confidence']}  matched: {x['matched_text']!r}")
        for x in rej: print(f"  REJECTED {x['event_type']:<28} reason {x['reason']}")
        if not m and not rej: print("  no event")
    else:
        if not os.path.exists(config.NEWS_DB_PATH): sys.exit("Event store not found. Run: python -m src.news.cli build")
        from src.news import provenance
        conn = provenance.connect()
        if a.cmd == "stats":
            print(pd.read_sql_query("SELECT key, value FROM build_meta", conn).to_string(index=False))
            print(pd.read_sql_query("SELECT source_id, COUNT(*) articles, SUM(duplicate_of IS NOT NULL) duplicates, MIN(published_utc) first, MAX(published_utc) last FROM raw_articles GROUP BY source_id", conn).to_string(index=False))
            print(pd.read_sql_query("SELECT parent_category, event_type, status, COUNT(*) events, SUM(corroboration_count) articles FROM canonical_events GROUP BY 1,2,3 ORDER BY 1,2,3", conn).to_string(index=False))
            print(pd.read_sql_query("SELECT reason, COUNT(*) rejected FROM rejected_matches GROUP BY reason", conn).to_string(index=False))
        else:
            feats, prov = provenance.load_index(conn).features(pd.Timestamp(a.as_of), windows=[a.window])
            for k, v in feats.items():
                if not k.startswith("_"): print(f"  {k:<42} {v:.4f}" if isinstance(v, float) else f"  {k:<42} {v}")
            print(f"  latest event publication used: {feats['_latest_event_publication']}")


if __name__ == "__main__":
    main()
