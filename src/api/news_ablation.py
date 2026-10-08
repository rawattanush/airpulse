"""Ablation: does the experimental feature group NEWS_EVENT_FEATURES_V1 add predictive value? (REQ-NEWS-013)

    python -m src.api.news_ablation            # all eight series
    python -m src.api.news_ablation --series IC1312

  MODEL A = the validated features (src/features/build.py FEATURES)
  MODEL B = the same features + NEWS_EVENT_FEATURES_V1
for both validated model classes (logistic regression, boosted trees), unchanged and untuned.

Same target labels, issuance dates, label-date training filter, minimum training size, refit at every origin and
metrics as the frozen benchmark (evaluation/validation_protocol.md). Two things necessarily differ from the benchmark
run and apply to A and B alike: training rows start where the news archive has a full window of coverage, and the
first forecast origin is therefore later. The benchmark itself is not touched: this module only reads the benchmark
store and writes its own files (evaluation/news_ablation_*, evaluation/news_event_experiments.csv).

News information time: a forecast issued on day D uses only articles published before 00:00 UTC of day D.

Decision rule, fixed before the first run: B counts as better than A for a model class and series only if its
Brier score is lower AND the 95% paired-bootstrap interval of the difference (B - A) lies entirely below zero."""
import argparse, csv, datetime, json, os
import numpy as np, pandas as pd
from src import config
from src.api import backtest as bt
from src.database import store
from src.evaluation import metrics
from src.features.build import FEATURES
from src.forecasting.baselines import MajorityBaseline, PersistenceBaseline, SeasonalBaseline
from src.forecasting.models import GradientBoostedModel, LogisticModel
from src.news import config as ncfg, provenance
from src.news.aggregation import NEWS_EVENT_FEATURES_V1

MODELS = {"LOGIT": LogisticModel, "GBT": GradientBoostedModel}
BASELINES = [MajorityBaseline, PersistenceBaseline, SeasonalBaseline]
BOOTSTRAP_N = 5000
OUT = {"ledger": "news_ablation_ledger.csv", "experiments": "news_event_experiments.csv", "results": "news_ablation_results.json", "report": "news_ablation.md"}


def coverage_start(news_conn):
    """First cut-off at which every connected source has a full ablation window of archived history."""
    first = pd.read_sql_query("SELECT source_id, MIN(published_utc) first FROM raw_articles GROUP BY source_id", news_conn)
    return pd.to_datetime(first["first"].str.slice(0, 10)).max() + pd.Timedelta(days=ncfg.ABLATION_WINDOW_DAYS + 1)


def add_news_features(frame, index):
    """Adds NEWS_EVENT_FEATURES_V1 and news_info (latest article time used) as of 00:00 UTC of each issuance date."""
    rows = []
    for d in frame["issued_at"]:
        f, _ = index.features(pd.Timestamp(d), windows=[ncfg.ABLATION_WINDOW_DAYS])
        rows.append({**{k: f[k] for k in NEWS_EVENT_FEATURES_V1}, "news_info": f["_latest_event_publication"], "news_articles": f[f"article_count_{ncfg.ABLATION_WINDOW_DAYS}d"]})
    return pd.concat([frame.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def training_rows(frame, i):
    """Identical to the benchmark rule in src/api/backtest.py forecast_origin."""
    row = frame.iloc[i]
    return frame[(frame["target_month"] < row["target_month"]) & frame["final_label"].notna() & (frame["final_label_date"].fillna("9999") <= row["issued_at"])]


def model_forecast(frame, i, cls, columns):
    train = training_rows(frame, i)
    f = cls().fit(train[columns].to_numpy(dtype=float), train["final_label"].tolist())
    return f.predict(frame.iloc[i][columns].to_numpy(dtype=float)), len(train)


def ece(actual, predicted, proba, bins=5):
    """Expected calibration error of the top-class probability, equal-width bins on [1/3, 1]."""
    conf = np.max(proba, axis=1); hit = np.array([a == p for a, p in zip(actual, predicted)], dtype=float); edges = np.linspace(1 / 3, 1.0, bins + 1); e = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf >= lo) & ((conf < hi) | (hi == 1.0))
        if m.any(): e += m.mean() * abs(hit[m].mean() - conf[m].mean())
    return float(e)


def _brier_rows(actual, proba):
    oh = np.array([[1.0 if a == c else 0.0 for c in config.CLASSES] for a in actual]); return ((np.asarray(proba) - oh) ** 2).sum(axis=1)


def run_series(conn, sid, hist, index, start):
    frame = add_news_features(bt.prepare(conn, sid, hist), index)
    frame = frame[pd.to_datetime(frame["issued_at"]) >= start].reset_index(drop=True)
    recs = []
    for i in range(len(frame)):
        row = frame.iloc[i]; train = training_rows(frame, i)
        if len(train) < config.MIN_TRAIN_LABELS: continue
        y = train["final_label"].tolist(); ctx = train[["month", "prev_rt_label"]].to_dict("records")
        out = {}
        for B in BASELINES: out[B.forecaster_id] = B().fit(y, ctx).predict({"month": row["month"], "prev_rt_label": row["prev_rt_label"]})
        for name, cls in MODELS.items():
            out[f"A-{name}"], _ = model_forecast(frame, i, cls, FEATURES)
            out[f"B-{name}"], _ = model_forecast(frame, i, cls, FEATURES + NEWS_EVENT_FEATURES_V1)
        for fid, (pred, p) in out.items():
            info = row["max_info"] + "T00:00:00"
            if fid.startswith("B-") and row["news_info"]: info = max(info, row["news_info"][:19])
            recs.append({"forecast_id": f"{sid}|{fid}|{row['target_month'][:7]}", "series": sid, "forecaster": fid, "target_month": row["target_month"], "issued_at": row["issued_at"],
                         "max_info": info, "target_time": row["target_time"], "p_down": float(p[0]), "p_flat": float(p[1]), "p_up": float(p[2]), "predicted": pred,
                         "actual": row["final_label"], "n_train": len(train), "status": "SCORED" if row["final_label"] is not None else "PENDING"})
    return pd.DataFrame(recs), frame


def score_series(df, seed):
    sc = df[df["status"] == "SCORED"]; res = {}
    for fid, g in sc.groupby("forecaster"):
        g = g.sort_values("target_month"); P = g[["p_down", "p_flat", "p_up"]].to_numpy(); m = metrics.score(g["actual"].tolist(), g["predicted"].tolist(), P)
        m["ece"] = ece(g["actual"].tolist(), g["predicted"].tolist(), P); m.pop("confusion"); res[fid] = m
    comp = {}; rng = np.random.default_rng(seed)
    for name in MODELS:
        a = sc[sc["forecaster"] == f"A-{name}"].sort_values("target_month"); b = sc[sc["forecaster"] == f"B-{name}"].sort_values("target_month")
        assert a["target_month"].tolist() == b["target_month"].tolist()
        d = _brier_rows(b["actual"].tolist(), b[["p_down", "p_flat", "p_up"]].to_numpy()) - _brier_rows(a["actual"].tolist(), a[["p_down", "p_flat", "p_up"]].to_numpy())
        boot = np.array([d[rng.integers(0, len(d), len(d))].mean() for _ in range(BOOTSTRAP_N)]); lo, hi = np.percentile(boot, [2.5, 97.5])
        ah = (a["actual"].to_numpy() == a["predicted"].to_numpy()); bh = (b["actual"].to_numpy() == b["predicted"].to_numpy())
        comp[name] = {"brier_diff_B_minus_A": float(d.mean()), "ci95_low": float(lo), "ci95_high": float(hi), "months_B_right_A_wrong": int((bh & ~ah).sum()),
                      "months_A_right_B_wrong": int((ah & ~bh).sum()), "B_better": bool(d.mean() < 0 and hi < 0), "B_worse": bool(d.mean() > 0 and lo > 0)}
    return res, comp


def run(series_ids=None):
    series_ids = series_ids or list(config.BLS_SERIES)
    conn = store.connect(config.DB_PATH); nconn = provenance.connect(); index = provenance.load_index(nconn); hist = bt.load_histories(conn)
    start = coverage_start(nconn); meta = dict(nconn.execute("SELECT key, value FROM build_meta").fetchall()); ledgers, results = [], {}
    issuance = set()
    for sid in series_ids:
        df, frame = run_series(conn, sid, hist, index, start); ledgers.append(df); issuance |= set(df["issued_at"])
        res, comp = score_series(df, config.RANDOM_SEED); sc = df[df["status"] == "SCORED"]
        results[sid] = {"metrics": res, "comparison": comp, "scored_months": int(sc["target_month"].nunique()), "first_scored": sc["target_month"].min()[:7], "last_scored": sc["target_month"].max()[:7],
                        "first_training_month": frame["target_month"].min()[:7], "train_n_first_origin": int(df["n_train"].min()), "train_n_last_origin": int(df["n_train"].max())}
    provenance.materialise_features(nconn, sorted(pd.Timestamp(d) for d in issuance), windows=[ncfg.ABLATION_WINDOW_DAYS])
    led = pd.concat(ledgers).sort_values(["series", "forecaster", "target_month"])
    with open(os.path.join(config.EVAL_DIR, OUT["ledger"]), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(["FORECAST-ID", "SERIES", "FORECASTER", "TARGET_MONTH", "ISSUED-AT", "MAX_FEATURE_INFO_TIME", "TARGET_TIME", "P_DOWN", "P_FLAT", "P_UP", "PREDICTION", "ACTUAL", "N_TRAIN", "STATUS"])
        for r in led.itertuples(): w.writerow([r.forecast_id, r.series, r.forecaster, r.target_month[:7], r.issued_at, r.max_info, r.target_time, repr(r.p_down), repr(r.p_flat), repr(r.p_up), r.predicted, r.actual or "", r.n_train, r.status])
    snap = bt.snapshot_hash(); today = datetime.date.today().isoformat(); fmt = lambda m: "; ".join(f"{k}={m[k]:.3f}" for k in ("hit_rate", "balanced_hit_rate", "macro_f1", "brier", "log_loss", "ece")) + f"; n={m['n']}"
    with open(os.path.join(config.EVAL_DIR, OUT["experiments"]), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(["EXPERIMENT-ID", "DATE", "MODEL", "DATASET_VERSION", "FEATURE_VERSION", "TARGET_VERSION", "VALIDATION_PROTOCOL", "HYPERPARAMETERS", "RANDOM_SEED", "RESULTS", "ARTIFACTS", "NOTES"])
        for sid in series_ids:
            for fid, m in results[sid]["metrics"].items():
                fv = "none" if fid.startswith("BL-") else config.FEATURE_VERSION if fid.startswith("A-") else f"{config.FEATURE_VERSION} + {ncfg.FEATURE_SET}"
                w.writerow([f"NEWSEXP-{sid}-{fid}", today, fid, f"snapshot {snap[:16]}; news archive {meta['archive_hash'][:16]}", fv, f"{sid} final label, band {config.FLAT_BAND_PCT}%",
                            f"benchmark walk-forward; training rows from {results[sid]['first_training_month']} (news coverage); origins {results[sid]['first_scored']}..{results[sid]['last_scored']}",
                            "as benchmark, untuned", config.RANDOM_SEED, fmt(m), f"evaluation/{OUT['ledger']}", f"taxonomy {meta['taxonomy_version']}; parser {meta['parser_version']}; reliability {meta['reliability_version']}; ablation, not a benchmark result"])
    counts = dict(nconn.execute("SELECT 'articles', COUNT(*) FROM raw_articles UNION ALL SELECT 'canonical_events', COUNT(*) FROM canonical_events").fetchall())
    mod = pd.read_sql_query("SELECT source_id, published_utc, modified_utc FROM raw_articles", nconn)
    late = (pd.to_datetime(mod['modified_utc'].str.slice(0, 19)) - pd.to_datetime(mod['published_utc'].str.slice(0, 19))) > pd.Timedelta(days=1)
    counts['modified_later_pct'] = {s: round(100 * float(late[mod['source_id'] == s].mean()), 1) for s in sorted(mod['source_id'].unique())}
    counts['articles_by_source'] = {s: int((mod['source_id'] == s).sum()) for s in sorted(mod['source_id'].unique())}
    payload = {"generated": today, "feature_set": ncfg.FEATURE_SET, "features": NEWS_EVENT_FEATURES_V1, "window_days": ncfg.ABLATION_WINDOW_DAYS, "coverage_start": str(start.date()),
               "snapshot_hash": snap, "news": {**meta, **counts}, "bootstrap_n": BOOTSTRAP_N, "seed": config.RANDOM_SEED, "primary_series": config.PRIMARY_SERIES, "series": results}
    with open(os.path.join(config.EVAL_DIR, OUT["results"]), "w", encoding="utf-8") as fh: json.dump(payload, fh, indent=1)
    write_report(payload)
    return payload


def write_report(p):
    """evaluation/news_ablation.md, generated so that every figure is copied from the results file."""
    L = []; w = L.append; head = p["primary_series"] if p["primary_series"] in p["series"] else next(iter(p["series"])); prim = p["series"][head]; order = ["BL-MAJ", "BL-PER", "BL-SEA", "A-LOGIT", "B-LOGIT", "A-GBT", "B-GBT"]
    better = [(s, k) for s, r in p["series"].items() for k, c in r["comparison"].items() if c["B_better"]]; worse = [(s, k) for s, r in p["series"].items() for k, c in r["comparison"].items() if c["B_worse"]]
    total = sum(len(r["comparison"]) for r in p["series"].values()); lower = sum(1 for r in p["series"].values() for c in r["comparison"].values() if c["brier_diff_B_minus_A"] < 0)
    w("# News-Event Ablation\n")
    w(f"STATUS: MEASURED ({p['generated']}). Generated by `python -m src.api.news_ablation` from `evaluation/{OUT['results']}`; do not edit by hand. These are BACKTEST results of an experiment. They are not benchmark results and they change nothing in `evaluation/metrics.md`.\n")
    w("## Question\n")
    w(f"Does the experimental feature group `{p['feature_set']}` add predictive value to the validated features? AirPulse contains an event-intelligence layer designed to test whether structured news and geopolitical information provides incremental predictive value beyond quantitative market and fuel features. This file reports the first such test.\n")
    w("## Design\n")
    w("| Item | Setting |\n|---|---|")
    w("| Model A | the 13 validated features (feature version F1) |")
    w(f"| Model B | the same 13 features plus {len(p['features'])} event features: " + ", ".join(f"`{f}`" for f in p["features"]) + " |")
    w("| Model classes | logistic regression and boosted trees, exactly as in the benchmark, untuned |")
    w("| Target, labels, issuance dates, label-date training filter, minimum of 36 training labels, refit at every origin, metrics | as the frozen validation protocol |")
    w(f"| Event information time | articles published before 00:00 UTC of the issuance date; {p['window_days']}-day window |")
    w(f"| Training rows | target months issued on or after {p['coverage_start']}, the first date with a full window of archived news from every connected source. Applies to A and B alike |")
    w(f"| News corpus | {p['news']['articles']} archived headlines, {p['news']['canonical_events']} canonical events; taxonomy {p['news']['taxonomy_version']}, parser {p['news']['parser_version']}, archive `{p['news']['archive_hash'][:16]}` |")
    w(f"| Uncertainty | paired bootstrap over months of the difference in Brier score (B − A), {p['bootstrap_n']} resamples, seed {p['seed']} |")
    w("| Decision rule (fixed before the run) | B counts as better only if its Brier score is lower and the 95 percent interval of the difference lies entirely below zero |\n")
    w("Because the training window is shorter than in the benchmark, the Model A figures here differ from the benchmark figures of the same model classes. The comparison that matters is B against A inside this table.\n")
    w(f"## {'Primary series' if head == p['primary_series'] else 'Series'} {head}: {prim['scored_months']} scored months, {prim['first_scored']} to {prim['last_scored']}\n")
    w("| Forecaster | hit rate | balanced hit rate | macro F-score | Brier | log loss | calibration error |\n|---|---|---|---|---|---|---|")
    for f in order:
        m = prim["metrics"][f]; w(f"| {f} | {m['hit_rate']:.3f} | {m['balanced_hit_rate']:.3f} | {m['macro_f1']:.3f} | {m['brier']:.3f} | {m['log_loss']:.3f} | {m['ece']:.3f} |")
    w(f"\nTraining labels: {prim['train_n_first_origin']} at the first origin, {prim['train_n_last_origin']} at the last.\n")
    w("| Model class | Brier difference (B − A) | 95% interval | months only B right | months only A right | verdict |\n|---|---|---|---|---|---|")
    for k, c in prim["comparison"].items():
        v = "B better" if c["B_better"] else "B worse" if c["B_worse"] else "no detectable difference"
        w(f"| {k} | {c['brier_diff_B_minus_A']:+.3f} | {c['ci95_low']:+.3f} to {c['ci95_high']:+.3f} | {c['months_B_right_A_wrong']} | {c['months_A_right_B_wrong']} | {v} |")
    w("\n## All series\n")
    w("| Series | months | A-LOGIT | B-LOGIT | difference [95% interval] | A-GBT | B-GBT | difference [95% interval] |\n|---|---|---|---|---|---|---|---|")
    for s, r in p["series"].items():
        m, c = r["metrics"], r["comparison"]
        w(f"| {s} | {r['scored_months']} | {m['A-LOGIT']['brier']:.3f} | {m['B-LOGIT']['brier']:.3f} | {c['LOGIT']['brier_diff_B_minus_A']:+.3f} [{c['LOGIT']['ci95_low']:+.3f}, {c['LOGIT']['ci95_high']:+.3f}] | "
          f"{m['A-GBT']['brier']:.3f} | {m['B-GBT']['brier']:.3f} | {c['GBT']['brier_diff_B_minus_A']:+.3f} [{c['GBT']['ci95_low']:+.3f}, {c['GBT']['ci95_high']:+.3f}] |")
    w("\nThe four score columns are Brier scores (lower is better).\n")
    w("## Result\n")
    w(f"- Of {total} comparisons (eight series, two model classes), Model B has the lower Brier score in {lower}. Under the decision rule B is better in {len(better)}" + (f" ({', '.join(f'{s} {k}' for s, k in better)})" if better else "") + f" and worse in {len(worse)}" + (f" ({', '.join(f'{s} {k}' for s, k in worse)})" if worse else "") + "; the rest show no detectable difference.")
    pb = [k for k, c in prim["comparison"].items() if c["B_better"]]
    w(f"- On {head} " + ("Model B is better for " + " and ".join(pb) + " under the decision rule." if pb else "the event features did not improve either model class under the decision rule."))
    best = min(order, key=lambda f: prim["metrics"][f]["brier"]); w(f"- The forecaster with the lowest Brier score on {head} in this experiment is {best}.")
    w("- **Conclusion: " + ("this experiment gives some evidence of incremental value, to be confirmed on new data before any production use." if (pb and not worse) else "this experiment does not show that the event features add predictive value. NEWS_EVENT_FEATURES_V1 stays experimental and is not added to the validated model.") + "**\n")
    w("## Limits of this test\n")
    w("- Headlines only, from two trade publications (air cargo and shipping); no general news wire, no article bodies.")
    w("- The parser is rule-based and has not been validated against human labels; its error rate is unknown.")
    w("- Publishers can edit a headline after publication; the archive holds the headline as it stood when first fetched, not as first published. Share of archived articles whose modification time is more than a day after publication: "
      + "; ".join(f"{s} {v}%" for s, v in p["news"]["modified_later_pct"].items()) + ". A modification time does not say whether the headline or only the body changed. Publication times are the publishers' own.")
    w("- Six event features are added to thirteen on a training set of a few dozen to about 140 rows; a real effect of modest size could go undetected, and with this many comparisons one nominally significant result could arise by chance.")
    w("- The feature group, window and decision rule were fixed before the run and nothing was tuned afterwards. Any later variant is a new experiment and must be recorded as such.")
    w("- The target is the Asia→US proxy index. Nothing here concerns South Asia→Europe rates.")
    with open(os.path.join(config.EVAL_DIR, OUT["report"]), "w", encoding="utf-8") as fh: fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="python -m src.api.news_ablation"); ap.add_argument("--series", nargs="*", choices=list(config.BLS_SERIES))
    a = ap.parse_args(); r = run(a.series or None); prim = r["series"].get(r["primary_series"]) or next(iter(r["series"].values()))
    print(f"ablation written to evaluation/{OUT['report']}; {prim['scored_months']} scored months on the first series")
    for k, c in prim["comparison"].items(): print(f"  {k}: Brier difference B-A {c['brier_diff_B_minus_A']:+.4f}  95% interval [{c['ci95_low']:+.4f}, {c['ci95_high']:+.4f}]")
