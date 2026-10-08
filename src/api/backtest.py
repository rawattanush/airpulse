"""MOD-08 Backtest, forecast ledger and replay.
REQ-ML-006, 009, 012, 013, 014; REQ-FN-001, 002, 003, 005; REQ-REP-001; REQ-OBS-001.

One code path: `forecast_origin` produces the forecast of one (series, forecaster, target month) from the
canonical store. The backtest calls it for every origin; replay calls it for one and compares with the ledger."""
import csv, datetime, hashlib, json, os
import numpy as np, pandas as pd
from src import config
from src.database import store
from src.evaluation import metrics
from src.features.build import FEATURES, build_features
from src.forecasting.baselines import MajorityBaseline, PersistenceBaseline, SeasonalBaseline
from src.forecasting.models import GradientBoostedModel, LogisticModel
from src.ingestion.build import snapshot_hash
from src.preprocessing.labels import issuance_dates

FORECASTERS = [MajorityBaseline, PersistenceBaseline, SeasonalBaseline, LogisticModel, GradientBoostedModel]
BASELINES = {"BL-MAJ", "BL-PER", "BL-SEA"}
PERIODS = {"ALL": ("2016-01-01", "2099-12-01"), "2016-2019": ("2016-01-01", "2019-12-01"),
           "2020-2022": ("2020-01-01", "2022-12-01"), "2023-2026": ("2023-01-01", "2026-12-01")}
LEDGER_COLUMNS = ["FORECAST-ID", "SERIES", "FORECASTER", "FORECASTER_VERSION", "FEATURE_VERSION", "INPUT_DATA_VERSION", "TARGET_MONTH",
                  "ISSUED-AT", "MAX_FEATURE_INFO_TIME", "TARGET_TIME", "P_DOWN", "P_FLAT", "P_UP", "PREDICTION", "ACTUAL", "CORRECT",
                  "ACTUAL_REALTIME", "CORRECT_REALTIME", "N_TRAIN", "STATUS"]


def code_hash():
    h = hashlib.sha256(); src = os.path.join(config.ROOT, "src")
    for d, _, files in sorted(os.walk(src)):
        for f in sorted(files):
            if f.endswith((".py", ".sql")):
                with open(os.path.join(d, f), "rb") as fh: h.update(f.encode()); h.update(fh.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def load_histories(conn):
    return {s: store.History(conn, s) for s in list(config.BLS_SERIES) + list(config.FUEL_SERIES)}


def prepare(conn, series_id, histories):
    """One row per target month that has an issuance date: features as of issuance, labels and their dates."""
    lab = store.table(conn, "labels", "WHERE series_id = ?", (series_id,))
    fin = lab[lab["kind"] == "FINAL"].set_index("target_month"); rt = lab[lab["kind"] == "REALTIME"].set_index("target_month")
    cal = store.table(conn, "releases", "WHERE series_id = ?", (series_id,))
    first_release = dict(zip(cal["obs_month"], cal["first_release_date"]))
    last_released = cal["obs_month"].max()
    peers = [s for s in config.BLS_SERIES if s != series_id]
    rows = []
    for t, issued in sorted(issuance_dates(cal).items()):
        if t not in first_release and t < last_released: continue      # month that BLS never published (2025-10)
        feats, info = build_features(histories, series_id, t, issued, peers)
        prev = (pd.Timestamp(t) - pd.offsets.MonthBegin(1)).strftime("%Y-%m-%d")
        nominal = (pd.Timestamp(t) + pd.offsets.MonthEnd(2)).strftime("%Y-%m-%d")   # end of the following month
        g = lambda frame, col: (frame.at[t, col] if t in frame.index and pd.notna(frame.at[t, col]) else None)
        rows.append({"target_month": t, "issued_at": issued, "max_info": info, "target_time": first_release.get(t, nominal),
                     "month": pd.Timestamp(t).month,
                     "prev_rt_label": (rt.at[prev, "label"] if prev in rt.index and pd.notna(rt.at[prev, "label"]) else None),
                     "final_label": g(fin, "label"), "final_label_date": g(fin, "label_date"), "rt_label": g(rt, "label"), **feats})
    return pd.DataFrame(rows)


def forecast_origin(frame, i, forecaster_cls):
    """Forecast for row i of a prepared frame. Training rows: earlier months whose final label was known at issuance."""
    row = frame.iloc[i]
    train = frame[(frame["target_month"] < row["target_month"]) & frame["final_label"].notna()
                  & (frame["final_label_date"].fillna("9999") <= row["issued_at"])]
    out = {"n_train": int(len(train)), "status": "OK", "message": "", "predicted": None, "proba": None,
           "max_label_date": train["final_label_date"].max() if len(train) else None}
    is_model = forecaster_cls.forecaster_id not in BASELINES
    if len(train) == 0 or (is_model and len(train) < config.MIN_TRAIN_LABELS):
        out.update(status="SKIPPED", message=f"{len(train)} training labels"); return out
    y = train["final_label"].tolist(); ctx = train[["month", "prev_rt_label"]].to_dict("records")
    try:
        if is_model:
            f = forecaster_cls().fit(train[FEATURES].to_numpy(dtype=float), y)
            out["predicted"], out["proba"] = f.predict(row[FEATURES].to_numpy(dtype=float))
        else:
            f = forecaster_cls().fit(y, ctx)
            out["predicted"], out["proba"] = f.predict({"month": row["month"], "prev_rt_label": row["prev_rt_label"]})
    except Exception as e:                                             # a failed fit must not stop the run
        out.update(status="FAILED", message=f"{type(e).__name__}: {e}")
    return out


def _score_rows(df, actual_col):
    """Metrics per forecaster on the months for which every forecaster has a forecast and the label exists."""
    ok = df[df["proba_ok"] & df[actual_col].notna()]
    n_fc = df["forecaster_id"].nunique()
    months = ok.groupby("target_month")["forecaster_id"].nunique(); common = set(months[months == n_fc].index)
    ok = ok[ok["target_month"].isin(common)]
    res = {}
    for fid, g in ok.groupby("forecaster_id"):
        for period, (a, b) in PERIODS.items():
            p = g[(g["target_month"] >= a) & (g["target_month"] <= b)]
            res[(fid, period)] = metrics.score(p[actual_col].tolist(), p["predicted"].tolist(), p[["p_down", "p_flat", "p_up"]].to_numpy())
    return res


def run_backtest(conn, series_ids=None, export=True):
    series_ids = series_ids or list(config.BLS_SERIES)
    snap = snapshot_hash(); now = lambda: datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cfg = {"series": series_ids, "band_pct": config.FLAT_BAND_PCT, "first_test_month": config.FIRST_TEST_MONTH, "min_train": config.MIN_TRAIN_LABELS,
           "seed": config.RANDOM_SEED, "feature_version": config.FEATURE_VERSION, "features": FEATURES, "fuel_lag_days": config.FUEL_AVAILABILITY_LAG_DAYS}
    cur = conn.execute("INSERT INTO forecast_runs(started_at, config_json, snapshot_hash, code_hash) VALUES (?,?,?,?)",
                       (now(), json.dumps(cfg, sort_keys=True), snap, code_hash()))
    run_id = cur.lastrowid
    for F in FORECASTERS:
        conn.execute("INSERT OR REPLACE INTO model_versions VALUES (?,?,?,?,?)",
                     (F.forecaster_id, F.name, "BASELINE" if F.forecaster_id in BASELINES else "MODEL", F.version, json.dumps(F.params, sort_keys=True)))
    histories = load_histories(conn); total = 0
    for sid in series_ids:
        frame = prepare(conn, sid, histories); recs = []
        for i in range(len(frame)):
            row = frame.iloc[i]
            if row["target_month"] < config.FIRST_TEST_MONTH: continue
            for F in FORECASTERS:
                o = forecast_origin(frame, i, F); p = o["proba"]
                actual, art = row["final_label"], row["rt_label"]
                status = o["status"] if o["status"] != "OK" else ("SCORED" if actual is not None else "PENDING")
                recs.append({"forecast_id": f"{sid}|{F.forecaster_id}|{row['target_month'][:7]}", "run_id": run_id, "series_id": sid,
                             "forecaster_id": F.forecaster_id, "forecaster_version": F.version, "feature_version": config.FEATURE_VERSION,
                             "snapshot_hash": snap, "target_month": row["target_month"], "issued_at": row["issued_at"],
                             "max_feature_info_time": row["max_info"], "target_time": row["target_time"],
                             "p_down": None if p is None else float(p[0]), "p_flat": None if p is None else float(p[1]), "p_up": None if p is None else float(p[2]),
                             "predicted": o["predicted"], "actual": actual,
                             "correct": None if (actual is None or o["predicted"] is None) else int(actual == o["predicted"]),
                             "actual_realtime": art, "correct_realtime": None if (art is None or o["predicted"] is None) else int(art == o["predicted"]),
                             "n_train": o["n_train"], "status": status, "message": o["message"]})
        df = pd.DataFrame(recs); df["proba_ok"] = df["p_up"].notna()
        with conn:
            conn.execute("DELETE FROM forecasts WHERE series_id = ?", (sid,)); conn.execute("DELETE FROM evaluation_results WHERE series_id = ?", (sid,))
            cols = [c for c in df.columns if c != "proba_ok"]
            conn.executemany(f"INSERT INTO forecasts({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                             df[cols].astype(object).where(df[cols].notna(), None).values.tolist())
            for kind, col in (("FINAL", "actual"), ("REALTIME", "actual_realtime")):
                for (fid, period), m in _score_rows(df, col).items():
                    for k, v in m.items():
                        if k == "n": continue
                        if k == "confusion":
                            for a, arow in zip(config.CLASSES, v):
                                for b, cell in zip(config.CLASSES, arow):
                                    conn.execute("INSERT INTO evaluation_results VALUES (?,?,?,?,?,?,?,?)", (run_id, sid, fid, kind, period, f"cm_{a}_{b}", cell, m["n"]))
                        else:
                            conn.execute("INSERT INTO evaluation_results VALUES (?,?,?,?,?,?,?,?)", (run_id, sid, fid, kind, period, k, v, m["n"]))
        total += len(df)
    with conn:
        conn.execute("UPDATE forecast_runs SET finished_at = ?, n_forecasts = ? WHERE run_id = ?", (now(), total, run_id))
    if export: export_registers(conn, run_id, snap)
    return run_id, total


def export_ledger(conn, path=None):
    """Deterministic CSV of the ledger (REQ-FN-002, REQ-REP-001): no run identifiers or timestamps of the run itself."""
    path = path or os.path.join(config.EVAL_DIR, "forecast_ledger.csv")
    df = store.table(conn, "forecasts", "ORDER BY series_id, forecaster_id, target_month")
    f6 = lambda v: "" if pd.isna(v) else repr(float(v))   # full precision, so that every metric can be recomputed from this file
    s = lambda v: "" if (v is None or pd.isna(v)) else str(v)
    i = lambda v: "" if pd.isna(v) else str(int(v))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(LEDGER_COLUMNS)
        for r in df.itertuples():
            w.writerow([r.forecast_id, r.series_id, r.forecaster_id, r.forecaster_version, r.feature_version, r.snapshot_hash[:16], r.target_month[:7],
                        r.issued_at, r.max_feature_info_time, r.target_time, f6(r.p_down), f6(r.p_flat), f6(r.p_up), s(r.predicted), s(r.actual),
                        i(r.correct), s(r.actual_realtime), i(r.correct_realtime), r.n_train, r.status])
    return path


def metric_table(conn, series_id, label_kind="FINAL", period="ALL"):
    ev = store.table(conn, "evaluation_results", "WHERE series_id = ? AND label_kind = ? AND period = ?", (series_id, label_kind, period))
    if ev.empty: return ev
    t = ev[~ev["metric"].str.startswith("cm_")].pivot(index="forecaster_id", columns="metric", values="value")
    t["n"] = ev.groupby("forecaster_id")["n"].first()
    return t.reindex([F.forecaster_id for F in FORECASTERS]).dropna(how="all")


def export_registers(conn, run_id, snap):
    export_ledger(conn)
    today = datetime.date.today().isoformat(); fmt = lambda m: "; ".join(f"{k}={m[k]:.3f}" for k in ("hit_rate", "balanced_hit_rate", "macro_f1", "brier", "log_loss")) + f"; n={int(m['n'])}"
    exp, reg = [], []
    for sid in config.BLS_SERIES:
        t = metric_table(conn, sid)
        for F in FORECASTERS:
            if F.forecaster_id not in t.index: continue
            exp.append([f"EXP-{sid}-{F.forecaster_id}", today, F.forecaster_id, f"snapshot {snap[:16]}", config.FEATURE_VERSION if F.forecaster_id not in BASELINES else "none",
                        f"{sid} final label, band {config.FLAT_BAND_PCT}%", "walk-forward, monthly origins from 2016-01, expanding window, labels known at issuance",
                        json.dumps(F.params, sort_keys=True), config.RANDOM_SEED, fmt(t.loc[F.forecaster_id]), "evaluation/forecast_ledger.csv; data/airpulse.sqlite",
                        f"run {run_id}; {'primary' if sid == config.PRIMARY_SERIES else 'secondary'} series; scored on months common to all forecasters"])
    t = metric_table(conn, config.PRIMARY_SERIES)
    for F in FORECASTERS:
        base = F.forecaster_id in BASELINES
        reg.append([F.forecaster_id, F.name, f"{config.PRIMARY_SERIES} monthly direction, final label, band {config.FLAT_BAND_PCT}%",
                    "none (labels and calendar only)" if base else f"{config.FEATURE_VERSION}: {', '.join(FEATURES)}",
                    "final labels known at issuance, target months from 2010-04", "walk-forward, monthly origins from 2016-01", F.version, json.dumps(F.params, sort_keys=True),
                    "is a baseline" if base else "BL-MAJ; BL-PER; BL-SEA", fmt(t.loc[F.forecaster_id]) if F.forecaster_id in t.index else "NOT YET MEASURED",
                    "US-lane proxy target; small sample; hyperparameters fixed without tuning; see evaluation/metrics.md", "VALIDATED" if base else "EXPERIMENTAL"])
    for name, hdr, rows in (("experiments.csv", ["EXPERIMENT-ID", "DATE", "MODEL", "DATASET_VERSION", "FEATURE_VERSION", "TARGET_VERSION", "VALIDATION_PROTOCOL", "HYPERPARAMETERS", "RANDOM_SEED", "RESULTS", "ARTIFACTS", "NOTES"], exp),
                            ("model_registry.csv", ["MODEL-ID", "MODEL-NAME", "TARGET", "FEATURE-SET", "TRAINING-DATA", "VALIDATION-METHOD", "VERSION", "HYPERPARAMETERS", "BASELINE", "METRICS", "LIMITATIONS", "STATUS"], reg)):
        with open(os.path.join(config.EVAL_DIR, name), "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n"); w.writerow(hdr); w.writerows(rows)


def replay(conn, series_id, forecaster_id, target_month):
    """Recompute one stored forecast from the store and return (stored, recomputed, max abs probability difference)."""
    t = pd.Timestamp(target_month).strftime("%Y-%m-01")
    stored = store.table(conn, "forecasts", "WHERE series_id = ? AND forecaster_id = ? AND target_month = ?", (series_id, forecaster_id, t))
    if stored.empty: raise KeyError(f"no stored forecast for {series_id} {forecaster_id} {t[:7]}")
    frame = prepare(conn, series_id, load_histories(conn))
    i = int(np.flatnonzero(frame["target_month"].to_numpy() == t)[0])
    F = next(f for f in FORECASTERS if f.forecaster_id == forecaster_id)
    o = forecast_origin(frame, i, F); s = stored.iloc[0]
    if o["proba"] is None or pd.isna(s["p_up"]): return s, o, None
    diff = float(np.max(np.abs(np.asarray(o["proba"]) - np.array([s["p_down"], s["p_flat"], s["p_up"]]))))
    return s, o, diff
