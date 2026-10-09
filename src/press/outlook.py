"""News-adjusted outlook (protocol 7.0, change record CL-028): the seasonal baseline as the prior, a trained model for how news shifts it.

    python -m src.press.outlook            # the pre-registered evaluation on the validated series; writes evaluation/news_tilt_*
    python -m src.press.outlook --now      # the same model fitted on everything known today, applied to the newest outlook

  SEA  the seasonal baseline (the official outlook), unchanged
  T0   logistic regression on the three log-probabilities of SEA            (recalibration only)
  T1   logistic regression on those three and NEWS_EVENT_FEATURES_V1         (the news-adjusted outlook)

Everything else is the frozen benchmark: target, labels, issuance dates, the training filter (final label known at
issuance), the minimum of 36 training labels, the metrics. The probabilities of SEA that T0 and T1 read are those SEA
gave at each row's own origin, so no row sees a seasonal count that includes its own outcome. News information time: a
forecast issued on day D uses only articles published before 00:00 UTC of day D.

Decision rule, fixed before the run: news adds value only if Brier(T1) is below Brier(SEA) and below Brier(T0) and both
95% paired-bootstrap intervals of the differences lie below zero. Whatever the result, SEA stays the official outlook.
This module reads the benchmark store and the event store and writes only its own files. EXPERIMENTAL."""
import argparse, csv, datetime, json, os
import numpy as np, pandas as pd
from src import config
from src.api import backtest as bt
from src.api.news_ablation import BOOTSTRAP_N, _brier_rows, add_news_features, coverage_start, ece, training_rows
from src.database import store
from src.evaluation import metrics
from src.forecasting.baselines import SeasonalBaseline
from src.forecasting.models import LogisticModel
from src.news import config as ncfg, provenance
from src.news.aggregation import NEWS_EVENT_FEATURES_V1

PRIOR = ["sea_logp_down", "sea_logp_flat", "sea_logp_up"]
FORECASTERS = {"T0": PRIOR, "T1": PRIOR + NEWS_EVENT_FEATURES_V1}
OUT = {"ledger": "news_tilt_ledger.csv", "experiments": "news_tilt_experiments.csv", "results": "news_tilt_results.json", "report": "news_tilt.md", "table": "news_tilt_training.csv"}
TABLE = ["target_month", "issued_at", *PRIOR, *NEWS_EVENT_FEATURES_V1, "final_label", "final_label_date"]
LABELS = {"geopolitical_shock": "Geopolitical events", "maritime_disruption": "Disruption at sea", "airspace_disruption": "Airspace disruption", "air_capacity_shock": "Air cargo capacity",
          "cargo_demand_shock": "Cargo demand", "airfreight_rate_signal": "Reported air-freight rates"}


def with_prior(frame):
    """Adds to every row the probabilities SEA gave at that row's own origin (NaN while SEA lacks its minimum of labels)."""
    P = np.full((len(frame), 3), np.nan); pred = [None] * len(frame)
    for i in range(len(frame)):
        train = training_rows(frame, i)
        if len(train) < config.MIN_TRAIN_LABELS: continue
        row = frame.iloc[i]; p_, p = SeasonalBaseline().fit(train["final_label"].tolist(), train[["month", "prev_rt_label"]].to_dict("records")).predict({"month": row["month"], "prev_rt_label": row["prev_rt_label"]})
        P[i] = p; pred[i] = p_
    out = frame.copy(); out[["sea_p_down", "sea_p_flat", "sea_p_up"]] = P; out[PRIOR] = np.log(np.clip(P, 1e-9, 1.0)); out["sea_pred"] = pred
    return out


def fit_predict(frame, i, columns):
    train = training_rows(frame, i); train = train[train[PRIOR[0]].notna()]
    if len(train) < config.MIN_TRAIN_LABELS: return None
    model = LogisticModel().fit(train[columns].to_numpy(dtype=float), train["final_label"].tolist())
    pred, p = model.predict(frame.iloc[i][columns].to_numpy(dtype=float)); return pred, p, len(train), model


def evaluate(conn, nconn, sid=None):
    sid = sid or config.PRIMARY_SERIES; index = provenance.load_index(nconn); hist = bt.load_histories(conn); start = coverage_start(nconn)
    frame = add_news_features(bt.prepare(conn, sid, hist), index); frame = with_prior(frame[pd.to_datetime(frame["issued_at"]) >= start].reset_index(drop=True)); recs = []
    for i in range(len(frame)):
        row = frame.iloc[i]; res = {k: fit_predict(frame, i, cols) for k, cols in FORECASTERS.items()}
        if any(v is None for v in res.values()) or row["sea_pred"] is None: continue
        res = {"SEA": (row["sea_pred"], row[["sea_p_down", "sea_p_flat", "sea_p_up"]].to_numpy(dtype=float), res["T0"][2]), **{k: v[:3] for k, v in res.items()}}
        for fid, (pred, p, n) in res.items():
            recs.append({"forecast_id": f"{sid}|{fid}|{row['target_month'][:7]}", "series": sid, "forecaster": fid, "target_month": row["target_month"], "issued_at": row["issued_at"], "news_info": row["news_info"] if fid == "T1" else "",
                         "p_down": float(p[0]), "p_flat": float(p[1]), "p_up": float(p[2]), "predicted": pred, "actual": row["final_label"], "n_train": int(n), "status": "SCORED" if row["final_label"] is not None else "PENDING"})
    return pd.DataFrame(recs), frame


def score(df, seed=config.RANDOM_SEED):
    sc = df[df["status"] == "SCORED"]; res, rng = {}, np.random.default_rng(seed); by = {f: g.sort_values("target_month") for f, g in sc.groupby("forecaster")}
    for fid, g in by.items():
        P = g[["p_down", "p_flat", "p_up"]].to_numpy(); m = metrics.score(g["actual"].tolist(), g["predicted"].tolist(), P); m["ece"] = ece(g["actual"].tolist(), g["predicted"].tolist(), P); m.pop("confusion"); res[fid] = m
    comp = {}
    for ref in ("SEA", "T0"):
        a, b = by[ref], by["T1"]; assert a["target_month"].tolist() == b["target_month"].tolist()
        d = _brier_rows(b["actual"].tolist(), b[["p_down", "p_flat", "p_up"]].to_numpy()) - _brier_rows(a["actual"].tolist(), a[["p_down", "p_flat", "p_up"]].to_numpy())
        boot = np.array([d[rng.integers(0, len(d), len(d))].mean() for _ in range(BOOTSTRAP_N)]); lo, hi = np.percentile(boot, [2.5, 97.5])
        ah = a["actual"].to_numpy() == a["predicted"].to_numpy(); bh = b["actual"].to_numpy() == b["predicted"].to_numpy()
        comp[f"T1_vs_{ref}"] = {"brier_diff": float(d.mean()), "ci95_low": float(lo), "ci95_high": float(hi), "months_T1_right_ref_wrong": int((bh & ~ah).sum()), "months_ref_right_T1_wrong": int((ah & ~bh).sum()),
                                "direction_changed_months": int((a["predicted"].to_numpy() != b["predicted"].to_numpy()).sum()), "better": bool(d.mean() < 0 and hi < 0), "worse": bool(d.mean() > 0 and lo > 0)}
    comp["news_adds_value"] = bool(comp["T1_vs_SEA"]["better"] and comp["T1_vs_T0"]["better"])
    return res, comp


def run():
    conn = store.connect(config.DB_PATH); nconn = provenance.connect(); df, frame = evaluate(conn, nconn); res, comp = score(df); sc = df[df["status"] == "SCORED"]
    meta = dict(nconn.execute("SELECT key, value FROM build_meta").fetchall()); today = datetime.date.today().isoformat(); snap = bt.snapshot_hash()
    with open(os.path.join(config.EVAL_DIR, OUT["ledger"]), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(["FORECAST-ID", "SERIES", "FORECASTER", "TARGET_MONTH", "ISSUED-AT", "NEWS_INFO_TIME", "P_DOWN", "P_FLAT", "P_UP", "PREDICTION", "ACTUAL", "N_TRAIN", "STATUS"])
        for r in df.sort_values(["forecaster", "target_month"]).itertuples(): w.writerow([r.forecast_id, r.series, r.forecaster, r.target_month[:7], r.issued_at, r.news_info or "", repr(r.p_down), repr(r.p_flat), repr(r.p_up), r.predicted, r.actual or "", r.n_train, r.status])
    fmt = lambda m: "; ".join(f"{k}={m[k]:.3f}" for k in ("hit_rate", "balanced_hit_rate", "macro_f1", "brier", "log_loss", "ece")) + f"; n={m['n']}"
    with open(os.path.join(config.EVAL_DIR, OUT["experiments"]), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(["EXPERIMENT-ID", "DATE", "MODEL", "DATASET_VERSION", "FEATURE_VERSION", "TARGET_VERSION", "VALIDATION_PROTOCOL", "HYPERPARAMETERS", "RANDOM_SEED", "RESULTS", "ARTIFACTS", "NOTES"])
        for fid, m in res.items():
            w.writerow([f"TILT-{config.PRIMARY_SERIES}-{fid}", today, fid, f"snapshot {snap[:16]}; news archive {meta['archive_hash'][:16]}", {"SEA": "none", "T0": "seasonal log-probabilities", "T1": f"seasonal log-probabilities + {ncfg.FEATURE_SET}"}[fid],
                        f"{config.PRIMARY_SERIES} final label, band {config.FLAT_BAND_PCT}%", f"protocol 7.0; walk-forward; origins {sc['target_month'].min()[:7]}..{sc['target_month'].max()[:7]}", "as benchmark, untuned", config.RANDOM_SEED, fmt(m),
                        f"evaluation/{OUT['ledger']}", "experimental; not the official outlook"])
    payload = {"generated": today, "protocol": "7.0", "series": config.PRIMARY_SERIES, "features": NEWS_EVENT_FEATURES_V1, "window_days": ncfg.ABLATION_WINDOW_DAYS, "snapshot_hash": snap, "news_archive_hash": meta["archive_hash"],
               "parser_version": meta["parser_version"], "scored_months": int(sc["target_month"].nunique()), "first_scored": sc["target_month"].min()[:7], "last_scored": sc["target_month"].max()[:7],
               "train_n_first_origin": int(df["n_train"].min()), "train_n_last_origin": int(df["n_train"].max()), "metrics": res, "comparison": comp, "bootstrap_n": BOOTSTRAP_N, "seed": config.RANDOM_SEED}
    with open(os.path.join(config.EVAL_DIR, OUT["results"]), "w", encoding="utf-8") as fh: json.dump(payload, fh, indent=1)
    tab = frame[frame[PRIOR[0]].notna()][TABLE]                                    # derived numbers only: what the model is fitted on at run time, where no headline archive is held
    tab.to_csv(os.path.join(config.EVAL_DIR, OUT["table"]), index=False, lineterminator="\n", float_format="%.10g")
    L = ["# News-adjusted outlook: evaluation (protocol 7.0)", "", f"Generated by `python -m src.press.outlook` on {today}. EXPERIMENTAL. The official outlook is the seasonal baseline whatever this table says.", "",
         f"Series {config.PRIMARY_SERIES}; {payload['scored_months']} scored months, {payload['first_scored']} to {payload['last_scored']}; training rows at the first and last origin: {payload['train_n_first_origin']} and {payload['train_n_last_origin']}.", "",
         "| Forecaster | Months | Hit rate | Balanced hit rate | Brier | Log loss |", "|---|---|---|---|---|---|"]
    names = {"SEA": "SEA: seasonal baseline (official)", "T0": "T0: recalibrated baseline, no news", "T1": "T1: news-adjusted"}
    for fid in ("SEA", "T0", "T1"): m = res[fid]; L.append(f"| {names[fid]} | {m['n']} | {m['hit_rate']:.3f} | {m['balanced_hit_rate']:.3f} | {m['brier']:.3f} | {m['log_loss']:.3f} |")
    L += ["", "| Comparison | Difference of the probability score (T1 minus reference) | 95% interval | T1 right, reference wrong | Reference right, T1 wrong | Months with another direction |", "|---|---|---|---|---|---|"]
    for k in ("T1_vs_SEA", "T1_vs_T0"): c = comp[k]; L.append(f"| {k.replace('_', ' ')} | {c['brier_diff']:+.4f} | {c['ci95_low']:+.4f} to {c['ci95_high']:+.4f} | {c['months_T1_right_ref_wrong']} | {c['months_ref_right_T1_wrong']} | {c['direction_changed_months']} |")
    L += ["", f"**By the rule fixed in advance, news adds value: {'YES' if comp['news_adds_value'] else 'NO'}.** A negative difference favours T1; the rule needs both intervals entirely below zero.", ""]
    with open(os.path.join(config.EVAL_DIR, OUT["report"]), "w", encoding="utf-8", newline="\n") as fh: fh.write("\n".join(L))
    return payload


def live(press_dir=None, table_path=None, ledger_path=None, out_path=None):
    """The news-adjusted view of the newest official outlook, from the stored readings of the press. Writes operations/press/outlook.json.
    The model is the T1 of the protocol, fitted on every row of the training table whose final label is known. Nothing here is the official outlook."""
    from src.press import reading as press
    from src.observability import records, sources
    files = press.held(press_dir); out_path = out_path or os.path.join(press_dir or press.PRESS_DIR, "outlook.json")
    led = [r for r in records.read(ledger_path or sources.FORECAST_LEDGER) if r["series"] == config.PRIMARY_SERIES and r.get("is_official")]
    if not files or not led: return None
    base = led[-1]; pb = np.array([base["probabilities"][k] for k in ("down", "flat", "up")], dtype=float); as_of = max(f["retrieved_at"] for f in files.values())
    tab = pd.read_csv(table_path or os.path.join(config.EVAL_DIR, OUT["table"])); tab = tab[tab["final_label"].notna()]; cols = FORECASTERS["T1"]
    model = LogisticModel().fit(tab[cols].to_numpy(dtype=float), tab["final_label"].tolist()); index, canon, links, arts = press.index(files)

    def view(when):
        f, _ = index.features(pd.Timestamp(when[:19]), windows=[ncfg.ABLATION_WINDOW_DAYS]); x = dict(zip(PRIOR, np.log(np.clip(pb, 1e-9, 1.0)))); x.update({k: f[k] for k in NEWS_EVENT_FEATURES_V1})
        pred, p = model.predict(np.array([x[c] for c in cols], dtype=float)); shifts = []
        for k in NEWS_EVENT_FEATURES_V1:                                           # what each group of news does: the same forecast with that group at its usual level
            y = dict(x); y[k] = float(tab[k].median()); _, q = model.predict(np.array([y[c] for c in cols], dtype=float)); g = k.rsplit("_", 2)[0]
            shifts.append({"group": g, "label": LABELS[g], "value": None if pd.isna(x[k]) else round(float(x[k]), 4), "usual": round(float(tab[k].median()), 4),
                           "shift_points": {c.lower(): round(100 * float(p[j] - q[j]), 1) for j, c in enumerate(config.CLASSES)}})
        return {"as_of": when, "articles_in_window": int(f[f"article_count_{ncfg.ABLATION_WINDOW_DAYS}d"]), "probabilities": {c.lower(): float(p[j]) for j, c in enumerate(config.CLASSES)}, "prediction": pred,
                "shift_points": {c.lower(): round(100 * float(p[j] - pb[j]), 1) for j, c in enumerate(config.CLASSES)}, "by_group": shifts}

    start = pd.Timestamp(as_of[:19]) - pd.Timedelta(days=ncfg.ABLATION_WINDOW_DAYS); by_art = {a["article_id"]: a for a in arts}; seen = {}
    for eid, aid, m in links:                                                       # one line per event: what was reported, where, when; no headline text
        if pd.Timestamp(m["published_utc"][:19]) < start or m["is_duplicate"]: continue
        e = seen.setdefault(eid, {"event_type": m["event_type"], "group": m["feature_group"], "status": m["status"], "direction": int(m["direction"]), "severity": int(m["severity"]), "first_reported": m["published_utc"],
                                  "source": by_art[aid]["source_id"], "url": by_art[aid]["url"], "reports": 0,
                                  "places": sorted(set(m.get("countries", []) + m.get("regions", []) + m.get("airports", []) + m.get("ports", []) + m.get("chokepoints", [])))[:4],
                                  "organisations": sorted(set(m.get("airlines", []) + m.get("carriers", [])))[:3]})
        e["reports"] += 1; e["last_reported"] = m["published_utc"]
    events_ = sorted(seen.values(), key=lambda e: e["last_reported"], reverse=True)
    out = {"schema": "NEWS-OUTLOOK-1", "experimental": True, "series": config.PRIMARY_SERIES, "target_period": base["target_period"], "issuance_date": base["issuance_date"], "official_forecaster": base["forecaster_id"],
           "baseline": {"probabilities": {k: float(base["probabilities"][k]) for k in ("down", "flat", "up")}, "prediction": base["prediction"]}, "news_adjusted": view(as_of),
           "model": {"name": "T1 of protocol 7.0: logistic regression on the seasonal log-probabilities and six news features", "trained_on_months": int(len(tab)), "trained_from": tab["target_month"].min()[:7],
                     "trained_to": tab["target_month"].max()[:7], "window_days": ncfg.ABLATION_WINDOW_DAYS},
           "sources": {sid: {"articles": len(f["articles"]), "from": f["from"], "to": f["to"], "retrieved_at": f["retrieved_at"]} for sid, f in files.items()}, "events": events_[:60], "events_in_window": len(events_)}
    text = json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n"; os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if not os.path.exists(out_path) or open(out_path, encoding="utf-8").read() != text:
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh: fh.write(text)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--live", action="store_true", help="read the press and write the news-adjusted view of the newest outlook"); ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--sources", nargs="*"); a = ap.parse_args()
    if a.live:
        from src.press import reading as press
        from src.ops import pipeline
        if not a.no_fetch:
            for r in press.refresh(trigger=pipeline.detect_trigger(), workflow_run=pipeline.workflow_run(), sources=a.sources or None): print(f"{r['source']}: {r['result']} {r['error'] or r['validation']}")
        o = live()
        print("no reading of the press is held, or no official outlook is on the ledger: nothing written" if o is None else
              json.dumps({"target": o["target_period"], "baseline": o["baseline"], "news_adjusted": {k: o["news_adjusted"][k] for k in ("as_of", "prediction", "probabilities", "shift_points")}, "events": o["events_in_window"]}, indent=1))
        raise SystemExit(0)
    p = run(); print(json.dumps({"months": p["scored_months"], "metrics": {k: {x: round(v[x], 3) for x in ("hit_rate", "brier", "log_loss")} for k, v in p["metrics"].items()}, "comparison": p["comparison"]}, indent=1))
