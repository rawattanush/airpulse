"""Operational pipeline (Phase 7): refresh -> validate -> store -> features -> forecast -> ledger -> outcomes -> status.

    fetch/refresh      src.ops.adapters, one run record per source in operations/ingestion_log.jsonl
    validate, store    the validated benchmark code (src.ingestion.build.build_store) on operations/current
    features, forecast the validated benchmark code (src.api.backtest.prepare and forecast_origin): one code path
    ledger             operations/forecast_ledger.jsonl, append-only, hash-chained; an issued forecast is never changed
    outcomes           operations/forecast_outcomes.jsonl, appended when a label becomes known
    status             operations/status.json

The benchmark snapshot, the benchmark store and the benchmark ledger are never written here."""
import csv, datetime, json, os, shutil
import pandas as pd
from src import config as base
from src.api import backtest as bt
from src.database import store
from src.ingestion import loaders
from src.ingestion.build import build_store, snapshot_hash
from src.observability import health, records, sources
from src.ops import adapters, config


def detect_trigger():
    """'schedule' only when a scheduler says so (GitHub Actions sets GITHUB_EVENT_NAME); a person running the command is 'manual'."""
    ev = os.environ.get("GITHUB_EVENT_NAME", "")
    return "schedule" if ev == "schedule" else "manual-dispatch" if ev == "workflow_dispatch" else "manual"


def workflow_run():
    """Identity of the hosted workflow run, when there is one: GitHub Actions sets these variables on its runners.
    None for a run started on any other machine, so a record can never carry a run identifier that GitHub did not issue."""
    rid = os.environ.get("GITHUB_RUN_ID")
    if not rid or os.environ.get("GITHUB_ACTIONS") != "true" or not os.environ.get("GITHUB_REPOSITORY"): return None
    return {"run_id": rid, "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"), "workflow": os.environ.get("GITHUB_WORKFLOW"), "repository": os.environ.get("GITHUB_REPOSITORY"),
            "commit": os.environ.get("GITHUB_SHA"), "url": f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ.get('GITHUB_REPOSITORY')}/actions/runs/{rid}"}


def seed(log_path=None, current_dir=None, snapshot_dir=None, now=adapters.utc_now):
    """Copy the benchmark snapshot files into operations/current when they are not there yet. A seed is recorded as
    SEEDED with the snapshot's own retrieval time: it is a copy of an earlier manual fetch, not a new fetch."""
    log_path = log_path or sources.INGESTION_LOG; current_dir = current_dir or config.CURRENT_DIR; snapshot_dir = snapshot_dir or base.SNAPSHOT_DIR
    os.makedirs(current_dir, exist_ok=True); done = []
    for sid, cfg in sources.SOURCES.items():
        if not cfg["file"] or os.path.exists(os.path.join(current_dir, cfg["file"])): continue
        meta = loaders.verify_file(os.path.join(snapshot_dir, cfg["file"]))
        for ext in ("", ".meta.json"): shutil.copyfile(os.path.join(snapshot_dir, cfg["file"] + ext), os.path.join(current_dir, cfg["file"] + ext))
        if cfg["kind"] == "eia_series":
            df = adapters._fuel_frame(open(os.path.join(current_dir, cfg["file"]), "rb").read()).dropna(subset=["v"]); n, latest = int(len(df)), df["d"].max().strftime("%Y-%m-%d")
        else:
            _, vints, _ = loaders.parse_vintage_matrix(os.path.join(current_dir, cfg["file"])); n, latest = len(vints), vints[-1]
        rec = adapters._record(sid, cfg, meta["retrieved_at"], http_status=int(meta.get("http_status", 200)), result="SEEDED", record_count=n, latest_observation=latest, checksum=meta["sha256"],
                               validation="passed: checksum equals the benchmark snapshot's sidecar", url=meta["url"])
        rec.update({"trigger": "seed", "recorded_at": now(), "note": "copied from the benchmark snapshot research/data_samples; retrieved_at is the time of that manual fetch"})
        records.append(log_path, rec); done.append(sid)
    return done


def refresh(groups, trigger=None, log_path=None, adapters_map=None, **kw):
    """Run the adapter of every source in the given groups. Always records one run per source; never stops at a failure."""
    log_path = log_path or sources.INGESTION_LOG; trigger = trigger or detect_trigger(); out = []
    for sid, cfg in sources.SOURCES.items():
        if cfg["group"] not in groups: continue
        fn = (adapters_map or adapters.ADAPTERS)[cfg["kind"]]
        t0 = datetime.datetime.now()
        try: rec = fn(sid, cfg, **kw.get(cfg["kind"], {}))
        except Exception as e:                                                    # an adapter bug must still leave a record
            rec = adapters._record(sid, cfg, adapters.utc_now(), error=f"adapter error: {type(e).__name__}: {e}")
        rec.update({"trigger": trigger, "duration_seconds": round((datetime.datetime.now() - t0).total_seconds(), 1), "workflow_run": workflow_run()})
        out.append(records.append(log_path, rec))
    return out


def build_operational_store(db_path=None, current_dir=None):
    """The validated ingestion code on the operational files: checksums, parsing, quality checks, calendar, labels."""
    return build_store(db_path or config.OPS_DB_PATH, current_dir or config.CURRENT_DIR)


def _training_rows(frame, row):
    return frame[(frame["target_month"] < row["target_month"]) & frame["final_label"].notna() & (frame["final_label_date"].fillna("9999") <= row["issued_at"])]


def source_versions(current_dir=None):
    """Checksum and retrieval time of every input file, from its sidecar: which data a forecast was computed from, file by file."""
    current_dir = current_dir or config.CURRENT_DIR; out = {}
    for sid, cfg in sources.SOURCES.items():
        if not cfg["file"] or not os.path.exists(os.path.join(current_dir, cfg["file"] + ".meta.json")): continue
        with open(os.path.join(current_dir, cfg["file"] + ".meta.json"), encoding="utf-8") as f: m = json.load(f)
        out[sid] = {"sha256": m["sha256"], "retrieved_at": m["retrieved_at"]}
    return out


def official_id():
    """The official forecaster by the selection rule, or None when the rule does not single one out (the forecasts are then issued unmarked)."""
    from src.ops import selection
    try:
        from src.dashboard import data as dd
        dd.ensure_store()                                                 # the evaluation the rule reads; built from the frozen snapshot when a fresh clone has none
        return selection.select()["official"]
    except Exception: return None


def issue_forecasts(db_path=None, current_dir=None, ledger_path=None, trigger=None, now=adapters.utc_now):
    """Append to the ledger the forecast of the newest target month of every series and forecaster that is not there yet.
    Uses the same functions as the backtest and the replay. Returns the records appended."""
    db_path = db_path or config.OPS_DB_PATH; current_dir = current_dir or config.CURRENT_DIR; ledger_path = ledger_path or sources.FORECAST_LEDGER
    conn = store.connect(db_path); have = {r["forecast_id"] for r in records.read(ledger_path)}; out = []
    snap = snapshot_hash(current_dir); code = bt.code_hash(); histories = bt.load_histories(conn); generated = now(); trigger = trigger or detect_trigger()
    versions = source_versions(current_dir); official = official_id()
    for sid in base.BLS_SERIES:
        frame = bt.prepare(conn, sid, histories)
        if frame.empty: continue
        i = len(frame) - 1; row = frame.iloc[i]; train = _training_rows(frame, row)
        late = (pd.Timestamp(generated[:10]) - pd.Timestamp(row["issued_at"])).days
        for F in bt.FORECASTERS:
            fid = f"{sid}|{F.forecaster_id}|{row['target_month'][:7]}"
            if fid in have: continue
            o = bt.forecast_origin(frame, i, F); p = o["proba"]; is_model = F.forecaster_id not in bt.BASELINES
            if o["status"] != "OK" or p is None: continue                         # nothing is issued without a probability
            rec = {"forecast_id": fid, "series": sid, "series_name": sources.SERIES_NAMES[sid], "forecaster_id": F.forecaster_id, "forecaster_name": F.name,
                   "model_version": F.version, "model_parameters": F.params, "feature_version": base.FEATURE_VERSION if is_model else "none",
                   "features": {k: (None if pd.isna(row[k]) else float(row[k])) for k in bt.FEATURES} if is_model else {},
                   "target_period": row["target_month"][:7], "issuance_date": row["issued_at"], "generated_at": generated,
                   "timing": "ON_TIME" if late <= config.ON_TIME_DAYS else "LATE", "days_after_issuance": int(late),
                   "data_cutoff": row["max_info"], "input_data_version": snap, "band_pct": base.FLAT_BAND_PCT,
                   "training_window": {"first_target_month": train["target_month"].min()[:7] if len(train) else None, "last_target_month": train["target_month"].max()[:7] if len(train) else None,
                                       "n": int(o["n_train"]), "latest_label_date": o["max_label_date"]},
                   "probabilities": {"down": float(p[0]), "flat": float(p[1]), "up": float(p[2])}, "prediction": o["predicted"], "status": "ISSUED",
                   "code_hash": code, "pipeline_version": config.PIPELINE_VERSION, "schema_version": config.FORECAST_SCHEMA_VERSION, "trigger": trigger, "workflow_run": workflow_run(),
                   "source_versions": versions, "configuration_version": config.CONFIGURATION_VERSION, "official_forecaster": official, "is_official": F.forecaster_id == official}
            out.append(records.append(ledger_path, rec))
    conn.close()
    return out


def record_outcomes(db_path=None, ledger_path=None, outcomes_path=None, now=adapters.utc_now):
    """Append the first-release and the final outcome of an issued forecast once each, when the label exists in the operational store."""
    db_path = db_path or config.OPS_DB_PATH; ledger_path = ledger_path or sources.FORECAST_LEDGER; outcomes_path = outcomes_path or sources.FORECAST_OUTCOMES
    conn = store.connect(db_path); done = {(r["forecast_id"], r["kind"]) for r in records.read(outcomes_path)}; out = []
    lab = store.table(conn, "labels"); lab = {(r.series_id, r.target_month[:7], r.kind): r for r in lab.itertuples() if isinstance(r.label, str)}
    for f in records.read(ledger_path):
        for kind in ("REALTIME", "FINAL"):
            r = lab.get((f["series"], f["target_period"], kind))
            if r is None or (f["forecast_id"], kind) in done: continue
            out.append(records.append(outcomes_path, {"forecast_id": f["forecast_id"], "kind": kind, "actual": r.label, "pct_change": float(r.pct_change), "label_date": r.label_date,
                                                      "correct": int(r.label == f["prediction"]), "recorded_at": now()}))
    conn.close()
    return out


def restore_ablation_feature_rows(nconn, ledger_path=None):
    """A rebuild of the event store starts with an empty feature table. This puts back the feature rows of the recorded
    news ablation: the same features, recomputed as of the same issuance dates (read from the ablation ledger). The
    ablation itself is not rerun and none of its files is written. The archive only grows, so the values are the same."""
    from src.news import config as ncfg, provenance
    ledger_path = ledger_path or os.path.join(base.ROOT, "evaluation", "news_ablation_ledger.csv")
    if not os.path.exists(ledger_path): return 0
    with open(ledger_path, newline="", encoding="utf-8") as fh: dates = sorted({r["ISSUED-AT"] for r in csv.DictReader(fh)})
    provenance.materialise_features(nconn, [pd.Timestamp(d) for d in dates], windows=[ncfg.ABLATION_WINDOW_DAYS])
    return int(nconn.execute("SELECT COUNT(*) FROM event_features").fetchone()[0])


EVENT_COLUMNS = ["event_id", "publication_time", "last_publication_time", "parent_category", "event_type", "status", "severity", "extraction_confidence", "geographic_scope",
                 "countries", "regions", "source_id", "corroboration_count", "source_count", "affected_mode", "source_url", "taxonomy_version", "parser_version"]


def export_event_store(export_dir=None, build=True):
    """Rebuild the event store from the archive and write its canonical events as a tracked text file, so that a
    scheduled run keeps its result (the SQLite store itself is derived and not tracked)."""
    from src.news import provenance
    export_dir = export_dir or config.NEWS_EXPORT_DIR; os.makedirs(export_dir, exist_ok=True)
    counts = provenance.build_news_db() if build else {}
    conn = provenance.connect(); meta = dict(conn.execute("SELECT key, value FROM build_meta").fetchall())
    if build: counts["feature_rows_restored"] = restore_ablation_feature_rows(conn)
    df = pd.read_sql_query(f"SELECT e.{', e.'.join(EVENT_COLUMNS)}, a.title_clean AS first_headline FROM canonical_events e JOIN raw_articles a ON a.url = e.source_url ORDER BY e.publication_time, e.event_id", conn)
    df.to_csv(os.path.join(export_dir, "canonical_events.csv"), index=False, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    info = {"events": int(len(df)), "articles": int(conn.execute("SELECT COUNT(*) FROM raw_articles").fetchone()[0]), "latest_article": conn.execute("SELECT MAX(published_utc) FROM raw_articles").fetchone()[0],
            **{k: meta[k] for k in ("archive_hash", "taxonomy_version", "parser_version", "schema_version")}, "status": "EXPERIMENTAL: not an input of any forecast"}
    with open(os.path.join(export_dir, "event_store_meta.json"), "w", encoding="utf-8", newline="\n") as f: json.dump(info, f, indent=1, sort_keys=True)
    conn.close()
    return {**info, **({"build": {k: int(v) if isinstance(v, (int, float)) else v for k, v in counts.items()}} if counts else {})}


def write_status(now=None, status_path=None, log_path=None, ledger_path=None, outcomes_path=None):
    """Ingestion and forecast status for anyone who cannot run the dashboard. Health is computed from the log and the clock."""
    now = now or health.now_utc(); rows = health.all_health(log_path, now); ledger = records.read(ledger_path or sources.FORECAST_LEDGER); outs = records.read(outcomes_path or sources.FORECAST_OUTCOMES)
    last = max(ledger, key=lambda r: (r["target_period"], r["seq"])) if ledger else None
    status = {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "pipeline_version": config.PIPELINE_VERSION,
              "forecast_inputs_data_mode": health.overall_mode(rows), "sources": rows,
              "chains_intact": {n: not records.verify(p) for n, p in (("ingestion_log", log_path or sources.INGESTION_LOG), ("forecast_ledger", ledger_path or sources.FORECAST_LEDGER), ("forecast_outcomes", outcomes_path or sources.FORECAST_OUTCOMES))},
              "forecasts": {"issued": len(ledger), "outcomes_recorded": len(outs), "latest_target_period": last["target_period"] if last else None, "latest_issuance_date": last["issuance_date"] if last else None,
                            "latest_generated_at": last["generated_at"] if last else None, "latest_timing": last["timing"] if last else None},
              "written_by_workflow_run": workflow_run(),
              "not_live_statement": "No AirPulse source is fetched continuously. A source is AUTOMATED only while a scheduler has recently run it; otherwise its data are a SNAPSHOT."}
    path = status_path or sources.STATUS_FILE; os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f: json.dump(status, f, indent=1, sort_keys=True)
    return status


def run(groups=("fuel", "bls"), fetch=True, trigger=None):
    """One pipeline run. Returns (summary, exit code); the exit code is 1 if any source failed or a later step raised."""
    trigger = trigger or detect_trigger(); summary = {"trigger": trigger, "seeded": seed(), "runs": [], "forecasts_issued": 0, "outcomes_recorded": 0, "errors": []}
    if fetch: summary["runs"] = [{k: r[k] for k in ("source", "result", "new_records", "latest_observation", "error")} for r in refresh(groups, trigger)]
    failed = [r["source"] for r in summary["runs"] if r["result"] == "FAILED"]
    if {"fuel", "bls"} & set(groups):
        try:
            build_operational_store()
            summary["forecasts_issued"] = len(issue_forecasts(trigger=trigger)); summary["outcomes_recorded"] = len(record_outcomes())
        except Exception as e: summary["errors"].append(f"forecast step: {type(e).__name__}: {e}")
        try:                                                              # only where forecasts are issued: a run of the headlines alone needs no selection
            from src.dashboard import data as dd
            from src.ops import selection
            dd.ensure_store(); rec = selection.select(); selection.write(rec); summary["official_forecaster"] = rec["official"]
        except Exception as e: summary["errors"].append(f"selection of the official forecaster: {type(e).__name__}: {e}")
    if "news" in groups:
        try: summary["event_store"] = export_event_store()
        except Exception as e: summary["errors"].append(f"event store step: {type(e).__name__}: {e}")
    status = write_status(); summary["forecast_inputs_data_mode"] = status["forecast_inputs_data_mode"]; summary["failed_sources"] = failed
    return summary, (1 if failed or summary["errors"] else 0)
