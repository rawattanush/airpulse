"""Data layer of the dashboard: everything the views show is computed here from the stores and the run records.
No network, no ingestion, no writes. The views in app.py only lay these results out.

States used on screen (never hard-coded per source; see src/observability/health.py):
  HISTORICAL    the validated walk-forward backtest (a replay of history from the frozen snapshot)
  SNAPSHOT      data that were fetched by hand or seeded; shown with their retrieval time
  AUTOMATED     a source whose latest successful run was started by a scheduler and is not stale
  LIVE          reserved for a source checked at least hourly; no AirPulse source qualifies
  EXPERIMENTAL  the event layer and the two models
  RESEARCH      sources examined by the project and not connected to the pipeline
Kinds of value: Observed, Forecast, Pending (forecast whose outcome is not published), Unavailable."""
import csv, json, os
import numpy as np, pandas as pd
from src import config
from src.api import backtest as bt
from src.database import store
from src.features.build import FEATURES, build_features
from src.observability import health, records, sources

PROXY_STATEMENT = ("The validated target is the BLS Asia→US air-freight price index, used as a public proxy. "
                   "It is a US-lane proxy, not a South Asia to Europe rate. How closely it follows India-Europe rates is unknown.")
BENCHMARK_SENTENCE = "Under the current dataset and validation protocol, the seasonal baseline remains the strongest benchmark."
NAMES = {F.forecaster_id: F.name for F in bt.FORECASTERS}
KIND = {F.forecaster_id: ("Benchmark" if F.forecaster_id in bt.BASELINES else "Experimental model") for F in bt.FORECASTERS}
FEATURE_TEXT = {"own_chg_1": "index change, last published month (%)", "own_chg_2": "index change, month before (%)", "own_chg_3": "index change, two months before (%)",
                "own_chg_3m": "index change over three months (%)", "own_abs_1": "size of the last change (%)", "peers_chg_1": "average change of the seven other indexes, last month (%)",
                "peers_chg_2": "average change of the seven other indexes, month before (%)", "jet_chg_1m": "jet fuel, 21-day mean against the 21 days before (%)",
                "jet_chg_3m": "jet fuel, 21-day mean against three months earlier (%)", "jet_vol_1m": "jet fuel, volatility of daily changes (%)",
                "brent_chg_1m": "Brent, 21-day mean against the 21 days before (%)", "month_sin": "calendar month (sine)", "month_cos": "calendar month (cosine)"}


def ensure_store(db_path=None, series=None):
    """Build the benchmark store and run the walk-forward backtest when the store is absent, so that the dashboard starts
    from a fresh clone or a deployed copy of the repository. Uses the frozen snapshot and the validated code, needs no
    network, and writes only the derived store: never an evaluation register. Returns True if it built the store.
    The store is assembled in a temporary file and moved into place when complete."""
    db_path = db_path or config.DB_PATH
    if os.path.exists(db_path): return False
    from src.ingestion.build import build_store
    tmp = db_path + ".bootstrap"
    if os.path.exists(tmp): os.remove(tmp)
    build_store(tmp); conn = store.connect(tmp)
    try: bt.run_backtest(conn, series, export=False)
    finally: conn.close()
    os.replace(tmp, db_path)
    return True


def series_label(sid, technical=False):
    return f"{sources.SERIES_NAMES[sid]} ({sid})" if technical else sources.SERIES_NAMES[sid]


def forecasts(conn, series, forecaster=None):
    w = "WHERE series_id = ?" + (" AND forecaster_id = ?" if forecaster else "") + " ORDER BY target_month, forecaster_id"
    return store.table(conn, "forecasts", w, (series, forecaster) if forecaster else (series,))


def value_kind(row):
    """Forecast whose outcome is known, or Pending, or Unavailable (no probability was produced)."""
    if row["status"] == "SCORED": return "Forecast (outcome known)"
    if row["status"] == "PENDING": return "Pending"
    return "Unavailable"


def latest_forecast(conn, series):
    """The forecasts of the newest target month in the store, one row per forecaster."""
    fc = forecasts(conn, series)
    if fc.empty: return fc
    last = fc[fc["target_month"] == fc["target_month"].max()].copy()
    last["forecaster"] = last["forecaster_id"].map(NAMES); last["kind"] = last["forecaster_id"].map(KIND); last["value_kind"] = [value_kind(r) for _, r in last.iterrows()]
    return last


def model_table(conn, series, label_kind="FINAL", period="ALL"):
    """Benchmark comparison: hit rate, Brier score, sample count, evaluation period and status, one row per forecaster."""
    t = bt.metric_table(conn, series, label_kind, period)
    if t.empty: return t
    sc = store.table(conn, "forecasts", "WHERE series_id = ? AND status = 'SCORED'", (series,))
    a, b = bt.PERIODS[period]; sc = sc[(sc["target_month"] >= a) & (sc["target_month"] <= b)]
    span = f"{sc['target_month'].min()[:7]} to {sc['target_month'].max()[:7]}" if len(sc) else "none"
    status = {}
    p = os.path.join(config.EVAL_DIR, "model_registry.csv")
    if os.path.exists(p):
        with open(p, newline="", encoding="utf-8") as fh: status = {r["MODEL-ID"]: r["STATUS"] for r in csv.DictReader(fh)}
    out = pd.DataFrame({"forecaster": [NAMES[i] for i in t.index], "role": [KIND[i] for i in t.index], "hit rate": t["hit_rate"].round(3), "Brier score": t["brier"].round(3),
                        "balanced hit rate": t["balanced_hit_rate"].round(3), "log loss": t["log_loss"].round(3), "months scored": t["n"].astype(int),
                        "evaluation period": span, "status": [status.get(i, "UNKNOWN") for i in t.index]}, index=t.index)
    return out


def best_by(table, column, lower_is_better):
    """Forecaster id with the best value of a column; None for an empty table."""
    if table is None or table.empty: return None
    return table[column].idxmin() if lower_is_better else table[column].idxmax()


def replay_bundle(conn, series, target_month, news_conn=None, news_window_days=30):
    """What AirPulse knew when the forecast of `target_month` was issued. Everything in 'available_then' and 'features'
    is read as of the issuance date; 'later' holds what was published afterwards and was therefore not used."""
    t = pd.Timestamp(target_month).strftime("%Y-%m-01")
    fc = forecasts(conn, series); fc = fc[fc["target_month"] == t]
    if fc.empty: raise KeyError(f"no stored forecast for {series} {t[:7]}")
    issued = fc["issued_at"].iloc[0]; hist = bt.load_histories(conn); peers = [s for s in config.BLS_SERIES if s != series]
    then = hist[series].asof(issued); now = hist[series].asof("2999-01-01")
    months = [pd.Timestamp(t) - pd.DateOffset(months=k) for k in (4, 3, 2, 1)]
    rows = []
    for m in months:
        known = m in then.index; later = now.at[m, "value"] if m in now.index else np.nan
        rows.append({"input": series_label(series), "reference period": m.strftime("%Y-%m"), "published": then.at[m, "available_date"].strftime("%Y-%m-%d") if known else "not yet published",
                     "value known then": float(then.at[m, "value"]) if known else None, "value as revised later": None if pd.isna(later) else float(later),
                     "revised after issuance": bool(known and not pd.isna(later) and float(later) != float(then.at[m, "value"]))})
    for sid, label in ((config.JET_FUEL, "US Gulf Coast jet fuel"), (config.BRENT_CRUDE, "Brent crude")):
        k = hist[sid].asof(issued)
        if len(k):
            rows.append({"input": label, "reference period": k.index.max().strftime("%Y-%m-%d"), "published": k["available_date"].max().strftime("%Y-%m-%d"), "value known then": float(k["value"].iloc[-1]),
                         "value as revised later": None, "revised after issuance": False})
    feats, info = build_features(hist, series, t, issued, peers)
    lab = store.table(conn, "labels", "WHERE series_id = ? AND target_month = ?", (series, t)).set_index("kind")
    def outcome(kind):
        if kind not in lab.index or not isinstance(lab.at[kind, "label"], str): return {"label": None, "pct_change": None, "label_date": None}
        return {"label": lab.at[kind, "label"], "pct_change": float(lab.at[kind, "pct_change"]), "label_date": lab.at[kind, "label_date"]}
    f = fc.copy(); f["forecaster"] = f["forecaster_id"].map(NAMES); f["role"] = f["forecaster_id"].map(KIND)
    latest_input = max(r["published"] for r in rows if r["published"] != "not yet published")
    bundle = {"series": series, "series_name": series_label(series), "target_month": t[:7], "issuance_date": issued, "target_first_release": fc["target_time"].iloc[0],
              "available_then": pd.DataFrame(rows), "features": pd.DataFrame([{"feature": k, "meaning": FEATURE_TEXT[k], "value": None if pd.isna(feats[k]) else round(float(feats[k]), 4)} for k in FEATURES]),
              "latest_information_date": info, "forecasts": f[["forecaster", "role", "p_down", "p_flat", "p_up", "predicted", "n_train", "status", "forecaster_id"]].reset_index(drop=True),
              "outcome_first_release": outcome("REALTIME"), "outcome_final": outcome("FINAL"),
              "leakage_check": {"latest_input_publication": latest_input, "latest_feature_information": info, "issuance_date": issued,
                                "passed": bool(latest_input <= issued and info <= issued and (then["available_date"] <= pd.Timestamp(issued)).all())},
              "events": None}
    if news_conn is not None:
        cut = pd.Timestamp(issued).strftime("%Y-%m-%dT00:00:00Z"); start = (pd.Timestamp(issued) - pd.Timedelta(days=news_window_days)).strftime("%Y-%m-%dT00:00:00Z")
        ev = pd.read_sql_query("""SELECT e.publication_time, e.event_time, e.parent_category AS category, e.event_type, e.status, e.severity, a.title_clean AS first_headline
                                  FROM canonical_events e JOIN raw_articles a ON a.url = e.source_url WHERE e.publication_time < ? AND e.publication_time >= ? ORDER BY e.publication_time DESC""", news_conn, params=(cut, start))
        bundle["events"] = {"cutoff": cut, "window_days": news_window_days, "table": ev}
    return bundle


def ops_ledger():
    """Operational forecast ledger with outcomes joined; empty frames when nothing has been issued."""
    led = pd.DataFrame(records.read(sources.FORECAST_LEDGER)); out = pd.DataFrame(records.read(sources.FORECAST_OUTCOMES))
    if led.empty: return led, out
    for k in ("down", "flat", "up"): led[f"p_{k}"] = [p[k] for p in led["probabilities"]]
    led["train_n"] = [w["n"] for w in led["training_window"]]
    for kind in ("REALTIME", "FINAL"):
        m = {} if out.empty else {r["forecast_id"]: r for r in out[out["kind"] == kind].to_dict("records")}
        led[f"actual_{kind.lower()}"] = [m.get(i, {}).get("actual") for i in led["forecast_id"]]
    led["value_kind"] = ["Forecast (outcome known)" if a else "Pending" for a in led["actual_final"]]
    return led, out


def data_state():
    """The banner of the Overview: data mode, latest ingestion and what started it, from the run log and the clock."""
    rows = health.all_health(); prod = [h for h in rows if h["group"] in ("fuel", "bls")]
    ok = [h for h in prod if h["last_successful_fetch"]]
    latest = max(ok, key=lambda h: h["last_successful_fetch"]) if ok else None
    return {"data_mode": health.overall_mode(rows), "sources": rows, "research": health.research_sources(),
            "latest_ingestion": latest["last_successful_fetch"] if latest else None, "latest_ingestion_trigger": latest["last_trigger"] if latest else None,
            "scheduled_runs": sum(h["scheduled_runs"] for h in rows), "manual_runs": sum(h["manual_runs"] for h in rows),
            "chains": {n: records.verify(p) for n, p in (("ingestion log", sources.INGESTION_LOG), ("forecast ledger", sources.FORECAST_LEDGER), ("forecast outcomes", sources.FORECAST_OUTCOMES))}}


def parser_validation():
    """Status of the event parser from the validation results file; None when the file is absent."""
    p = os.path.join(config.EVAL_DIR, "news_parser_validation_reference.json")
    if not os.path.exists(p): return None
    r = json.load(open(p, encoding="utf-8")); d = r["decision"]; h = r["held_out"][d["configuration_in_place"]]
    return {"status": d["parser_status"], "configuration": d["configuration_in_place"], "held_out_headlines": r["split"]["held_out"], "precision": h["detection"]["sample"]["precision"],
            "recall": h["detection"]["sample"]["recall"], "kappa": h["detection_kappa"], "annotation_verified": d["annotation_independently_verified"]}


def event_export():
    """Canonical events exported by the operational pipeline (operations/news); used when the local event store is absent."""
    d = os.path.join(sources.OPS_DIR, "news"); p = os.path.join(d, "canonical_events.csv")
    if not os.path.exists(p): return None, None
    return pd.read_csv(p, keep_default_na=False), json.load(open(os.path.join(d, "event_store_meta.json"), encoding="utf-8"))


def expansion():
    """Tables of the expansion pass V2 (CL-015), read from its stored results. None when it has not been run. Nothing is computed here."""
    d = os.path.join(config.EVAL_DIR, "monthly"); p = os.path.join(d, "results_v2.json")
    if not os.path.exists(p): return None
    with open(p, encoding="utf-8") as fh: r = json.load(fh)
    promo = pd.DataFrame(r["promotion"]).T.replace({True: "yes", False: "no"}); promo.insert(0, "Holm p", [r["holm"].get(c) for c in promo.index])
    out = {"decision": r["decision"], "months": r["frame"]["scored"], "candidates": len(r["candidates"]), "confirmatory": len(r["confirmatory"]),
           "comparison": pd.read_csv(os.path.join(d, "model_comparison_v2.csv")), "ablation": pd.read_csv(os.path.join(config.EVAL_DIR, "ablations", "feature_ablation_v2.csv")),
           "promotion": promo, "weekly": None, "weekly_adopted": None}
    wp = os.path.join(config.EVAL_DIR, "weekly", "weekly_results_v2.json")
    if os.path.exists(wp):
        with open(wp, encoding="utf-8") as fh: w = json.load(fh)
        out["weekly"] = pd.DataFrame([{"forecaster": k, "releases": v["ALL"]["n"], "correct": v["ALL"]["correct"], "hit rate": round(v["ALL"]["hit_rate"], 3), "Brier score": round(v["ALL"]["brier"], 3),
                                       "log loss": round(v["ALL"]["log_loss"], 3), "calibration error": round(v["ALL"]["ece"], 3)} for k, v in w["evaluation"]["scores"].items()])
        out["weekly_adopted"] = bool(w["adoption"]["adopted"])
    return out
