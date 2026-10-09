"""Frontend adapter, engine side: export what the AirPulse engine has persisted to static JSON for the customer application.

    AirPulse engine  ->  persisted outputs  ->  this adapter  ->  public/data/*.json  ->  React application

Read-only with respect to the AirPulse repository: it opens the derived stores, calls the engine's own data layer
(src/dashboard/data.py, src/api/backtest.py) and writes only into airpulse-web/public/data. Nothing is fetched. No forecast
is computed here that the engine has not already stored.

TWO STORES, TWO JOBS.
  the operational store   built by the scheduled pipeline from operations/current: everything OBSERVED (index history,
                          releases, outcomes, fuel prices) and, through the operational ledger, every forecast issued since
                          the evaluation. This is what moves when a source publishes.
  the benchmark store     built from the frozen snapshot: the EVALUATED record (the scored months and their scores, the
                          replay). It does not move; it is the evidence the official forecast rests on.

NOTHING IS PUBLISHED HALF-WRITTEN. The files are written to a staging folder, checked, and only then moved into
public/data. If any step fails the site keeps the data it had, and its own clock shows that they have aged.

ONE CUSTOMER FORECAST. The engine evaluates five forecasters; the customer application shows one. Which one is not chosen
here by taste and not by complexity: it is the forecaster the engine's own walk-forward evaluation supports on the validated
target (the best of the forecasters whose registry status is VALIDATED, by probability score and by hit rate; the two
criteria must agree, otherwise this script stops). The other forecasters are not exported. They remain in the Control Center
(the Streamlit application of the repository), where model comparison belongs.

Run from anywhere with the repository's interpreter:
    AirPlus/.venv/Scripts/python.exe airpulse-web/scripts/export_data.py
"""
import csv, json, os, shutil, sqlite3, sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.dirname(HERE)
def _engine(web):
    """The engine repository: AIRPULSE_ROOT when set; the parent folder when this application lives inside the engine's repository
    (single repository); otherwise the folder AirPlus beside it (two folders side by side)."""
    if os.environ.get("AIRPULSE_ROOT"): return os.environ["AIRPULSE_ROOT"]
    parent = os.path.dirname(web)
    return parent if os.path.isdir(os.path.join(parent, "src", "ops")) else os.path.join(parent, "AirPlus")


ROOT = _engine(WEB)
PUBLISHED = os.environ.get("AIRPULSE_WEB_DATA") or os.path.join(WEB, "public", "data")
OUT = PUBLISHED + ".staging"                                         # written here first; moved into place only after the checks at the end
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import numpy as np, pandas as pd                                    # noqa: E402
from src import config                                              # noqa: E402
from src.api import backtest as bt                                  # noqa: E402
from src.dashboard import data as dd                                # noqa: E402
from src.database import store                                      # noqa: E402
from src.observability import policy, records as recs, registry, sources   # noqa: E402
from src.ops import config as opscfg, pipeline as ops_pipeline, selection   # noqa: E402

if os.path.isdir(OUT): shutil.rmtree(OUT)

PERIOD_LABELS = {"ALL": "All years", "2016-2019": "2016–2019", "2020-2022": "2020–2022", "2023-2026": "2023–2026"}
SIGNALS = ("own_chg_1", "own_chg_3m", "peers_chg_1", "jet_chg_1m", "jet_chg_3m", "brent_chg_1m")     # market context shown to customers


def records(df):
    """DataFrame -> list of dicts with NaN as null and timestamps as ISO strings."""
    return json.loads(df.to_json(orient="records", date_format="iso", double_precision=15))        # the default keeps ten decimals; probabilities are exported as stored


def plain(o):
    if isinstance(o, dict): return {str(k): plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [plain(v) for v in o]
    if isinstance(o, pd.DataFrame): return records(o)
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, (np.floating, float)): return None if (o != o) else float(o)
    if isinstance(o, (np.bool_,)): return bool(o)
    if isinstance(o, pd.Timestamp): return o.strftime("%Y-%m-%d")
    return o


def write(name, obj):
    p = os.path.join(OUT, name); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh: json.dump(plain(obj), fh, ensure_ascii=False, separators=(",", ":"))
    print(f"{name}: {os.path.getsize(p) / 1024:.0f} KB")


def ro(path):
    return sqlite3.connect(f"file:{path.replace(os.sep, '/')}?mode=ro", uri=True)


if not os.path.exists(config.DB_PATH): sys.exit("the benchmark store is absent: run the production pipeline first (python scripts/production_run.py --offline in the engine)")
if not os.path.exists(opscfg.OPS_DB_PATH): sys.exit("the operational store is absent: run the production pipeline first (python scripts/production_run.py --offline in the engine)")
POLICY = policy.load()                                              # what may reach the public product: config/production_sources.yaml of the engine
if policy.check(): sys.exit("the production policy is inconsistent: " + "; ".join(policy.check()[:5]) + ". Nothing is exported.")
ALLOWED = set(policy.publishable_sources(POLICY)); FEATURES = set(policy.public_features(POLICY))
PLAIN_STATE = {"REMOVE FROM PUBLIC PRODUCT": "Removed", "NEEDS LICENCE": "Needs a licence", "NEEDS VALIDATION": "Not validated", "BLOCKED": "Not possible today"}
for need_ in ("market_index", "monthly_outlook", "fuel_prices", "data_status"):
    if need_ not in FEATURES: sys.exit(f"the production policy refuses the feature {need_} ({policy.feature_refusal(need_, POLICY)}): the public product cannot be exported without it")
conn = ro(config.DB_PATH)                                           # the evaluated record (frozen)
hist = bt.load_histories(conn)
oconn = ro(opscfg.OPS_DB_PATH)                                      # what is observed now (moves with every refresh)
ohist = bt.load_histories(oconn)
PRIMARY = config.PRIMARY_SERIES

# ---------------------------------------------------------------- the one official forecast, from the engine's evaluation
table = dd.model_table(conn, PRIMARY)                               # final labels, all scored months
if table is None or table.empty: sys.exit("the store holds no evaluation for the validated target; run the backtest first")
try: SELECTION = selection.select(conn)                             # the rule lives in the engine (src/ops/selection.py); this script does not choose
except selection.NoSelection as e: sys.exit(f"no official forecast: {e}. Decide it in the repository before exporting; this script does not choose.")
OFFICIAL = SELECTION["official"]
stored = selection.read()
if stored is not None and stored != SELECTION: sys.exit("the selection record operations/official_forecast.json differs from the evaluation: run the production pipeline before exporting")
V2_RESULTS = os.path.join(ROOT, "evaluation", "monthly", "results_v2.json")
v2 = json.load(open(V2_RESULTS, encoding="utf-8")) if os.path.exists(V2_RESULTS) else None


from guards import valid_forecast                                   # noqa: E402  a forecast that is not a valid distribution is refused

others = table.drop(index=OFFICIAL)
better = [i for i in others.index if others.at[i, "Brier score"] < table.at[OFFICIAL, "Brier score"] or others.at[i, "hit rate"] > table.at[OFFICIAL, "hit rate"]]
METHODS = {"BL-SEA": ("seasonal_record", "Seasonal record", "For each calendar month, how often the index rose, held or fell in that month in earlier years."),
           "BL-MAJ": ("overall_record", "Overall record", "How often the index rose, held or fell across all earlier months."),
           "BL-PER": ("persistence", "Persistence", "The direction of the latest published month, weighted by how often it repeated.")}
kind, method_name, method_text = METHODS.get(OFFICIAL, ("model", dd.NAMES[OFFICIAL], "A fitted model; see the methodology."))
print(f"official customer forecast: {OFFICIAL} ({method_name}); hit rate {table.at[OFFICIAL, 'hit rate']}, {int(table.at[OFFICIAL, 'months scored'])} months; "
      f"other forecasters evaluated in the Control Center: {len(others)}; outperforming it on either criterion: {better or 'none'}")

# ---------------------------------------------------------------- per lane: observed history only
lanes = []
for sid in config.BLS_SERIES:
    now = ohist[sid].asof("2999-01-01")
    rel = store.table(oconn, "releases", "WHERE series_id = ?", (sid,)).set_index("obs_month")
    lab = store.table(oconn, "labels", "WHERE series_id = ?", (sid,))
    lf = lab[lab["kind"] == "FINAL"].set_index("target_month"); lr = lab[lab["kind"] == "REALTIME"].set_index("target_month")
    rows = []
    for m, r in now.iterrows():
        k = m.strftime("%Y-%m-01")
        rows.append({"m": k[:7], "v": float(r["value"]), "rel": rel.at[k, "first_release_date"] if k in rel.index else None,
                     "pf": float(lf.at[k, "pct_change"]) if k in lf.index and pd.notna(lf.at[k, "pct_change"]) else None,
                     "lf": lf.at[k, "label"] if k in lf.index and isinstance(lf.at[k, "label"], str) else None,
                     "pr": float(lr.at[k, "pct_change"]) if k in lr.index and pd.notna(lr.at[k, "pct_change"]) else None,
                     "lr": lr.at[k, "label"] if k in lr.index and isinstance(lr.at[k, "label"], str) else None})
    write(f"market/{sid}.json", {"id": sid, "name": sources.SERIES_NAMES[sid], "title": config.BLS_SERIES[sid][0], "primary": sid == PRIMARY, "history": rows})
    lanes.append({"id": sid, "name": sources.SERIES_NAMES[sid], "title": config.BLS_SERIES[sid][0], "primary": sid == PRIMARY,
                  "latest_month": rows[-1]["m"], "latest_value": rows[-1]["v"], "latest_release": rel["first_release_date"].max(),
                  "first_month": rows[0]["m"], "spark": [r["v"] for r in rows[-60:]]})

# ---------------------------------------------------------------- the outlook: official forecaster, validated target
fc = dd.forecasts(conn, PRIMARY); fc = fc[fc["forecaster_id"] == OFFICIAL].sort_values("target_month")
frame = bt.prepare(conn, PRIMARY, hist).set_index("target_month", drop=False)
oframe = bt.prepare(oconn, PRIMARY, ohist).set_index("target_month", drop=False)       # the same code on the operational files


def basis(target_month, fr=None):
    """What the official forecast of this month rests on. For the seasonal record: the directions of the same calendar month in
    earlier years whose final value was published by the issuance date. Checked against the stored probabilities."""
    if kind != "seasonal_record": return None
    fr = frame if fr is None else fr; row = fr.loc[target_month]
    train = fr[(fr["target_month"] < row["target_month"]) & fr["final_label"].notna() & (fr["final_label_date"].fillna("9999") <= row["issued_at"])]
    same = train[train["month"] == row["month"]]
    return {"kind": kind, "calendar_month": int(row["month"]), "years": int(len(same)), "first_year": int(same["target_month"].min()[:4]) if len(same) else None,
            "last_year": int(same["target_month"].max()[:4]) if len(same) else None, **{c.lower(): int((same["final_label"] == c).sum()) for c in config.CLASSES}}


def reproduces(b, d, f_, u, where):
    """The explanation shown to customers must be the stored forecast, not a re-derivation that drifted."""
    if not b or u is None: return
    n = b["years"] + 3
    for c, p in (("down", d), ("flat", f_), ("up", u)):
        assert abs((b[c] + 1) / n - p) < 1e-9, f"seasonal record of {where} does not reproduce the stored probability ({c})"


def observed(t):
    """Outcome of a target month as the operational store holds it now: (final, first release); None while not published."""
    if t not in oframe.index: return None, None
    r = oframe.loc[t]; g = lambda v: v if isinstance(v, str) else None
    return g(r["final_label"]), g(r["rt_label"])


outlook_rows = []
for r in records(fc):
    b = basis(r["target_month"]); reproduces(b, r["p_down"], r["p_flat"], r["p_up"], r["target_month"])
    valid_forecast(r["p_down"], r["p_flat"], r["p_up"], r["predicted"], f"monthly outlook {r['target_month'][:7]}")
    row = {"t": r["target_month"][:7], "i": r["issued_at"], "o": r["target_time"], "d": r["p_down"], "f": r["p_flat"], "u": r["p_up"], "p": r["predicted"],
           "a": r["actual"], "c": r["correct"], "ar": r["actual_realtime"], "cr": r["correct_realtime"], "n": r["n_train"], "s": r["status"], "basis": b, "src": "evaluation"}
    if r["status"] != "SCORED" and r["predicted"]:                   # a month the evaluation left open: its outcome is taken from what has been published since
        fin, rt = observed(r["target_month"])
        if rt and row["ar"] is None: row.update(ar=rt, cr=int(rt == r["predicted"]))
        if fin and row["a"] is None: row.update(a=fin, c=int(fin == r["predicted"]), s="SCORED", resolved_after_evaluation=True)
    outlook_rows.append(row)

led, outs = dd.ops_ledger(); operational = None; issued_since = 0
if not led.empty:
    mine = led[(led["series"] == PRIMARY) & (led["forecaster_id"] == OFFICIAL)].sort_values(["target_period", "generated_at"])
    have = {r["t"] for r in outlook_rows}
    for rec in mine.to_dict("records"):                              # forecasts issued by the pipeline for months after the evaluated record
        t7 = rec["target_period"]; key = t7 + "-01"
        if t7 in have or key not in oframe.index: continue
        p = rec["probabilities"]; b = basis(key, oframe); reproduces(b, p["down"], p["flat"], p["up"], t7)
        valid_forecast(p["down"], p["flat"], p["up"], rec["prediction"], f"operational monthly outlook {t7}")
        fin, rt = observed(key)
        outlook_rows.append({"t": t7, "i": rec["issuance_date"], "o": oframe.at[key, "target_time"], "d": p["down"], "f": p["flat"], "u": p["up"], "p": rec["prediction"],
                             "a": fin, "c": None if not fin else int(fin == rec["prediction"]), "ar": rt, "cr": None if not rt else int(rt == rec["prediction"]), "n": int(rec["training_window"]["n"]),
                             "s": "SCORED" if fin else "PENDING", "basis": b, "src": "operations", "generated_at": rec["generated_at"], "timing": rec["timing"], "forecast_id": rec["forecast_id"]})
        have.add(t7); issued_since += 1
    if len(mine):
        last = mine.sort_values("generated_at").iloc[-1]
        operational = {"issued": int(len(mine)), "target_period": last["target_period"], "issuance_date": last["issuance_date"], "generated_at": last["generated_at"], "timing": last["timing"],
                       "days_after_issuance": int(last["days_after_issuance"]), "outcome_recorded": bool(last["actual_realtime"] or last["actual_final"]), "issued_after_the_evaluated_record": issued_since, "trigger": last["trigger"],
                       "forecast_id": last["forecast_id"], "code_hash": last["code_hash"][:12], "input_data_version": last["input_data_version"][:12]}
due_month = oframe.index.max()[:7] if len(oframe) else None        # the newest month for which an issuance date exists in the operational data
outlook_current = {"month_due": due_month, "month_shown": outlook_rows[-1]["t"] if outlook_rows else None,
                   "is_current": bool(outlook_rows) and outlook_rows[-1]["t"] == due_month}             # false: a forecast is due and has not been issued; the page must say so

ev_all = store.table(conn, "evaluation_results"); ev_all = ev_all[(ev_all["series_id"] == PRIMARY) & (ev_all["forecaster_id"] == OFFICIAL)]
record = {}
for (label_kind, period), g in ev_all.groupby(["label_kind", "period"]):
    d = {r["metric"]: r["value"] for _, r in g.iterrows()}; n = int(g["n"].max())
    record.setdefault(label_kind, []).append({"period": period, "label": PERIOD_LABELS.get(period, period), "hit_rate": d.get("hit_rate"), "months": n, "correct": int(round(d.get("hit_rate", 0) * n))})
for k in record: record[k].sort(key=lambda x: list(PERIOD_LABELS).index(x["period"]) if x["period"] in PERIOD_LABELS else 99)
span = str(table.at[OFFICIAL, "evaluation period"])


PLAIN = {"SEATREND": "Seasonal record plus the recent trend", "SEA-SHRUNK": "Seasonal record, smoothed towards the all-month record", "PLATT(SEA)": "Seasonal record with recalibrated probabilities",
         "RLOGIT[ALL]": "Statistical model on every data group", "GBT[ALL]": "Machine-learning model on every data group",
         "ENS-EQ(SEA,RLOGIT[ALL],GBT[ALL])": "Average of the seasonal record and the two models", "FTL": "Switching each month to whichever approach had done best so far"}
GROUP_PLAIN = {"FUEL": "Fuel prices", "PRICES": "Import and export price indexes", "TRADE": "US imports from Asia", "MACRO": "US demand indicators", "AVIATION": "Air freight activity and capacity",
               "ASIA": "Asian export values", "MARKETS": "Exchange rates and financial markets", "EVENTS": "Reported events (experimental)"}
# How well the probabilities of the official forecaster have held: a property of the outlook that is shown. Results of experiments
# (other approaches, groups of data, alternatives under watch) are research and are not exported; they stay in research/ and evaluation/.
# how the probabilities shown have held, per direction: counted on the published record of the official approach (the ledger the product
# publishes), over the months it scored. Nothing here is read from a research file.
reliability = None
_led = pd.read_csv(os.path.join(ROOT, "evaluation", "forecast_ledger.csv"), keep_default_na=False)
_led = _led[(_led["SERIES"] == PRIMARY) & (_led["FORECASTER"] == OFFICIAL) & (_led["STATUS"] == "SCORED")]
if len(_led):
    reliability = [{"dir": k, "given": float(pd.to_numeric(_led[f"P_{k}"]).mean()), "happened": float((_led["ACTUAL"] == k).mean())} for k in config.CLASSES]

write("outlook.json", {
    "lane": PRIMARY, "lane_name": sources.SERIES_NAMES[PRIMARY],
    "official": {"engine_id": OFFICIAL, "method": kind, "method_name": method_name, "method_text": method_text,
                 "selection": "The forecasting approach with the best record in the walk-forward evaluation of the validated target, among the approaches the engine marks as validated. "
                              "It was not chosen for being more complex.",
                 "hit_rate": float(table.at[OFFICIAL, "hit rate"]), "months_scored": int(table.at[OFFICIAL, "months scored"]), "evaluation_period": span, "chance_rate": 1 / 3,
                 "other_approaches_evaluated": int(len(others)), "other_approaches_with_a_better_record": len(better)},
    "flat_band_pct": config.FLAT_BAND_PCT, "revision_releases": config.REVISION_RELEASES, "first_forecast_month": config.FIRST_TEST_MONTH[:7],
    "forecasts": outlook_rows, "record": record, "operational": operational, "current": outlook_current, "reliability": reliability,
    # how the one outlook was chosen, in plain words; the scores and the other approaches stay in the Control Center
    "selection": {"rule": "Of the approaches the evaluation validated, the one with the best probability score and the best hit rate on the scored months. Both must agree, and every later test must name the same one.",
                  "evaluation_period": SELECTION["evaluation_period"], "approaches_evaluated": len(SELECTION["candidates"]), "approaches_validated": sum(1 for c in SELECTION["candidates"] if c["status"] == "VALIDATED"),
                  "later_tests": [{"test": d["experiment"], "date": d["date"], "changed_the_outlook": d["changed"], "alternatives_that_met_the_rule": len(d["candidates_that_passed"])} for d in SELECTION["later_decisions"]]},
})

# ---------------------------------------------------------------- weekly fuel-cost outlook (a fuel target, not a freight price)
FT = os.path.join(ROOT, "evaluation", "weekly", "fuel_predictive_test_v3.json"); carry_forward = None
if os.path.exists(FT):                                               # what the weekly outlook is called follows from the stored test, not from a typed label
    ft_ = json.load(open(FT, encoding="utf-8"))
    carry_forward = {"date": ft_["generated"], "weeks": ft_["scored_releases"], "is_a_carry_forward": not bool(ft_["verdict"]["predictive_value_beyond_averaging"])}
W_RES = os.path.join(ROOT, "evaluation", "weekly", "weekly_results_v2.json"); weekly = {"available": False, "reason": "The weekly study has not been run."}
if "weekly_fuel_outlook" not in FEATURES: weekly = {"available": False, "reason": (POLICY["features"].get("weekly_fuel_outlook") or {}).get("reason") or "Not part of the product."}
elif os.path.exists(W_RES):
    from src.v2 import ops as wops, weekly as wk, config as v2cfg
    wr = json.load(open(W_RES, encoding="utf-8")); ad = wr["adoption"]
    if not ad["adopted"]:
        weekly = {"available": False, "reason": "The weekly fuel-cost outlook did not meet the rule set for it before it was tested, so it is not offered."}
    else:
        led_w = pd.read_csv(os.path.join(ROOT, "evaluation", "weekly", "weekly_ledger_v2.csv"), keep_default_na=False)
        g = led_w[led_w["FORECASTER"] == ad["primary"]].copy()
        for c in ("P_DOWN", "P_FLAT", "P_UP"): g[c] = g[c].astype(float)
        cur_dir = wops.CURRENT if os.path.isdir(wops.CURRENT) else None
        wf, band, wchecks = wk.build_frame(cur_dir)                                        # the engine's own frame: release windows as published
        means = {pd.Timestamp(r.issued_at).strftime("%Y-%m-%d"): r for r in wf.itertuples()}
        rows_w = []
        for r in g.itertuples():
            valid_forecast(r.P_DOWN, r.P_FLAT, r.P_UP, r.PREDICTION, f"weekly fuel outlook {r.ISSUED_AT}")
            m = means[r.ISSUED_AT]; tw = r.TARGET_WINDOW.split("..") if r.TARGET_WINDOW else None
            rows_w.append({"i": r.ISSUED_AT, "rw": r.REFERENCE_WINDOW.split(".."), "tw": tw, "o": r.OUTCOME_DATE or None, "d": r.P_DOWN, "f": r.P_FLAT, "u": r.P_UP, "p": r.PREDICTION,
                           "a": r.ACTUAL or None, "pc": float(r.PCT_CHANGE) if r.PCT_CHANGE != "" else None, "s": r.STATUS, "rm": float(m.ref_mean), "lp": float(m.last_price), "gap": float(m.gap)})
        sc = g[g["STATUS"] == "SCORED"]; top = sc[["P_DOWN", "P_FLAT", "P_UP"]].max(axis=1); hit = (sc["PREDICTION"] == sc["ACTUAL"])
        bands = [("Low", 0.0, 0.45), ("Moderate", 0.45, 0.60), ("High", 0.60, 1.01)]
        ev_w = wr["evaluation"]["scores"]
        st_w = wops.status(write=False) if cur_dir else None; lf = st_w["latest_forecast"] if st_w else None
        if lf: valid_forecast(lf["p_down"], lf["p_flat"], lf["p_up"], lf["predicted"], f"operational weekly fuel outlook {lf['issued_at']}")
        weekly = {
            "available": True, "kind": "fuel_cost", "series": "US Gulf Coast jet fuel spot price (EIA)", "unit": "USD per gallon", "band_pct": band,
            "statement": "A weekly outlook for the cost of jet fuel. It is not a weekly air-freight price forecast: no public weekly freight-rate series exists that AirPulse may use.",
            "method": {"name": "Latest price against the week's average",
                       "text": "A weekly average lags the daily price. When the latest published price already stands above the average of the week just published, the next weekly average is more likely to be higher, and the reverse."},
            "first_scored": wr["first_scored_issuance"], "last_scored": wr["last_scored_issuance"], "releases": wr["releases"],
            "record": {"scored": int(len(sc)), "correct": int(hit.sum()), "not_scored_irregular": wr["evaluation"]["not_scored_irregular"],
                       "by_period": [{"label": p.replace("-", "–"), "scored": ev_w[ad["primary"]][p]["n"], "correct": ev_w[ad["primary"]][p]["correct"]} for p in v2cfg.WEEKLY["periods"] if p != "ALL"],
                       "by_call": [{"dir": k, "n": int((sc["PREDICTION"] == k).sum()), "correct": int(((sc["PREDICTION"] == k) & hit).sum())} for k in config.CLASSES],
                       "by_strength": [{"label": lab, "from": lo, "to": min(hi, 1.0), "n": int(((top >= lo) & (top < hi)).sum()), "correct": int((((top >= lo) & (top < hi)) & hit).sum())} for lab, lo, hi in bands],
                       "simple_rules": [{"rule": "Repeating the direction of the week before", "correct": ev_w["W-PER"]["ALL"]["correct"], "scored": ev_w["W-PER"]["ALL"]["n"]},
                                        {"rule": "Always naming the most common direction", "correct": ev_w["W-MAJ"]["ALL"]["correct"], "scored": ev_w["W-MAJ"]["ALL"]["n"]}],
                       "happened": {k: float(v) for k, v in wr["class_shares_scored"].items()}},
            "revisions": {"changed": wr["revisions"]["observations_with_more_than_one_value"], "of": wr["revisions"]["observations_in_windows"]},
            "carry_forward": carry_forward,
            "forecasts": rows_w[-160:],
            "windows": [{"i": pd.Timestamp(r.issued_at).strftime("%Y-%m-%d"), "a": pd.Timestamp(r.ref_first_day).strftime("%Y-%m-%d"), "b": pd.Timestamp(r.ref_last_day).strftime("%Y-%m-%d"),
                         "m": round(float(r.ref_mean), 4), "lp": float(r.last_price)} for r in wf.tail(104).itertuples()],
            "current": None if not lf else {"issued_at": lf["issued_at"], "generated_at": lf["generated_at"], "timing": lf["timing"], "days_after_issuance": lf["days_after_issuance"],
                                            "reference_window": lf["reference_window"], "reference_mean": lf["reference_mean"], "last_price": lf["last_price"], "gap_pct": lf["gap_pct"],
                                            "d": lf["p_down"], "f": lf["p_flat"], "u": lf["p_up"], "p": lf["predicted"], "status": lf["status"], "trigger": lf["trigger"],
                                            "expected_outcome": (pd.Timestamp(lf["issued_at"]) + pd.Timedelta(days=7)).strftime("%Y-%m-%d")},
            "state": None if not st_w else {k: st_w[k] for k in ("data_mode", "latest_release", "days_since_latest_release", "stale", "stale_after_days", "last_fetch", "last_fetch_trigger", "failed_runs",
                                                                 "scheduled_runs", "forecasts_issued", "outcomes", "scored", "correct", "records_intact")},
        }
write("weekly.json", weekly)

# ---------------------------------------------------------------- news-adjusted outlook (experimental; beside the official outlook, never in its place)
N_OUT, N_RES, N_LED = (os.path.join(ROOT, *x) for x in (("operations", "press", "outlook.json"), ("evaluation", "news_tilt_results.json"), ("evaluation", "news_tilt_ledger.csv")))
news = {"available": False, "reason": (POLICY["features"].get("news_adjusted_outlook") or {}).get("reason") or "Not part of the product."}
if "news_adjusted_outlook" in FEATURES and all(os.path.exists(x) for x in (N_OUT, N_RES, N_LED)):
    with open(N_OUT, encoding="utf-8") as fh: no = json.load(fh)
    with open(N_RES, encoding="utf-8") as fh: nr = json.load(fh)
    nl = pd.read_csv(N_LED, keep_default_na=False); pk = lambda q, pred: {"d": q["down"], "f": q["flat"], "u": q["up"], "p": pred}
    valid_forecast(no["news_adjusted"]["probabilities"]["down"], no["news_adjusted"]["probabilities"]["flat"], no["news_adjusted"]["probabilities"]["up"], no["news_adjusted"]["prediction"], "news-adjusted outlook")
    rows = {}; sc_ = nl[nl["STATUS"] == "SCORED"]
    def side(fid):                                                       # in plain terms: how many months, how many right, and how sure it was on average of the direction it named
        g = sc_[sc_["FORECASTER"] == fid]; return {"n": int(len(g)), "correct": int((g["PREDICTION"] == g["ACTUAL"]).sum()), "sure": float(g[["P_DOWN", "P_FLAT", "P_UP"]].astype(float).max(axis=1).mean())}
    for r in nl.itertuples():
        if r.FORECASTER in ("SEA", "T1"): rows.setdefault(r.TARGET_MONTH, {"m": r.TARGET_MONTH, "a": r.ACTUAL or None})[r.FORECASTER.lower()] = {"d": float(r.P_DOWN), "f": float(r.P_FLAT), "u": float(r.P_UP), "p": r.PREDICTION}
    news = {"available": True, "experimental": True, "target_period": no["target_period"], "issuance_date": no["issuance_date"],
            "baseline": pk(no["baseline"]["probabilities"], no["baseline"]["prediction"]), "adjusted": pk(no["news_adjusted"]["probabilities"], no["news_adjusted"]["prediction"]),
            "as_of": no["news_adjusted"]["as_of"], "articles_in_window": no["news_adjusted"]["articles_in_window"], "shift_points": no["news_adjusted"]["shift_points"], "by_group": no["news_adjusted"]["by_group"],
            "reports": [{"type": e["event_type"], "group": e["group"], "status": e["status"], "direction": e["direction"], "severity": e["severity"], "first": e["first_reported"], "last": e["last_reported"], "n": e["reports"],
                         "source": e["source"], "url": e["url"], "places": e["places"], "organisations": e["organisations"]} for e in no["events"]],
            "reports_in_window": no["events_in_window"], "model": {k: no["model"][k] for k in ("trained_on_months", "trained_from", "trained_to", "window_days")}, "read": no["sources"],
            "test": {"months": nr["scored_months"], "first": nr["first_scored"], "last": nr["last_scored"], "adds_value": nr["comparison"]["news_adds_value"],
                     "seasonal": side("SEA"), "with_news": side("T1"), "call_changed_months": nr["comparison"]["T1_vs_SEA"]["direction_changed_months"],
                     "news_right_seasonal_wrong": nr["comparison"]["T1_vs_SEA"]["months_T1_right_ref_wrong"], "seasonal_right_news_wrong": nr["comparison"]["T1_vs_SEA"]["months_ref_right_T1_wrong"]},
            "history": [rows[m] for m in sorted(rows) if "sea" in rows[m] and "t1" in rows[m]]}
write("news.json", news)

# ---------------------------------------------------------------- fuel (observed)
fuel = {}; FUEL_KEY = {config.JET_FUEL: "jet", config.BRENT_CRUDE: "brent"}      # the pages name the two prices, not a publisher's series key
for sid, (title, _) in config.FUEL_SERIES.items():
    o = pd.read_sql_query("SELECT obs_date, value, available_date FROM observations WHERE series_id = ? ORDER BY obs_date", oconn, params=(sid,))
    o["obs_date"] = pd.to_datetime(o["obs_date"]); o = o.dropna(subset=["value"])
    monthly = o.set_index("obs_date")["value"].resample("MS").mean().dropna()
    monthly = monthly[monthly.index >= "2005-12-01"]
    daily = o[o["obs_date"] >= o["obs_date"].max() - pd.Timedelta(days=730)]
    fuel[FUEL_KEY[sid]] = {"title": title, "series": sid, "latest_date": o["obs_date"].max().strftime("%Y-%m-%d"), "latest_value": float(o["value"].iloc[-1]),
                 "monthly": [{"m": k.strftime("%Y-%m"), "v": round(float(v), 4)} for k, v in monthly.items()],
                 "daily": [{"d": d.strftime("%Y-%m-%d"), "v": float(v)} for d, v in zip(daily["obs_date"], daily["value"])]}

# ---------------------------------------------------------------- events (experimental layer; context, never an input of the outlook)
# ---------------------------------------------------------------- replay (validated target, official forecast only)
replay = {"lane": PRIMARY, "lane_name": sources.SERIES_NAMES[PRIMARY], "months": []}
by_month = {r["t"]: r for r in outlook_rows}
for t in sorted(fc["target_month"].unique()):
    b = dd.replay_bundle(conn, PRIMARY, t)
    mine = b["forecasts"][b["forecasts"]["forecaster_id"] == OFFICIAL].iloc[0]
    cut = pd.Timestamp(b["issuance_date"]).strftime("%Y-%m-%dT00:00:00Z"); start = (pd.Timestamp(b["issuance_date"]) - pd.Timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z")
    feats = {r["feature"]: r for r in records(b["features"])}
    replay["months"].append({
        "target_month": b["target_month"], "issuance_date": b["issuance_date"], "target_first_release": b["target_first_release"], "latest_information_date": b["latest_information_date"],
        "available_then": [{"input": r["input"], "period": r["reference period"], "published": r["published"], "value": r["value known then"], "later": r["value as revised later"], "revised": r["revised after issuance"]}
                           for r in records(b["available_then"])],
        "signals": [{"id": k, "meaning": feats[k]["meaning"], "value": feats[k]["value"]} for k in SIGNALS if k in feats],
        "outlook": {"d": float(mine["p_down"]) if pd.notna(mine["p_down"]) else None, "f": float(mine["p_flat"]) if pd.notna(mine["p_flat"]) else None,
                    "u": float(mine["p_up"]) if pd.notna(mine["p_up"]) else None, "p": mine["predicted"], "n": int(mine["n_train"]), "s": mine["status"], "basis": by_month[b["target_month"]]["basis"]},
        "outcome_first_release": b["outcome_first_release"], "outcome_final": b["outcome_final"], "leakage_check": b["leakage_check"],
    })

# ---------------------------------------------------------------- data state
state = dd.data_state()
snap = store.table(oconn, "source_files")
fresh = []
for s in config.BLS_SERIES:
    cal = store.table(oconn, "releases", "WHERE series_id = ?", (s,)); f = snap[snap["file_name"] == config.BLS_SERIES[s][1]].iloc[0]
    fresh.append({"id": s, "name": sources.SERIES_NAMES[s], "latest_month": cal["obs_month"].max()[:7], "latest_release": cal["first_release_date"].max(), "retrieved": f["retrieved_at"][:10]})
status = json.load(open(sources.STATUS_FILE, encoding="utf-8")) if os.path.exists(sources.STATUS_FILE) else None
from src.ingestion.build import snapshot_hash
REG = registry.build()                                              # every declared source with its state now: from the run logs and the clock, nothing typed
REG_KEYS = ("id", "name", "type", "frequency", "active", "license", "last_success", "last_attempt", "latest_data", "stale_after_days", "data_stale_after_days", "check_every_days", "status", "error", "coverage", "notes",
            "layer", "production", "feeds", "last_result", "last_trigger", "scheduled_runs", "manual_runs", "data_mode", "record_count", "validation")
# only sources the policy allows are listed, each with one of the five public states and the attribution its terms ask for
reg_rows = [{**{k: r_.get(k) for k in REG_KEYS}, "status": policy.public_status(r_), "checksum": (r_.get("checksum") or "")[:12] or None, "license": POLICY["sources"][r_["id"]]["license_class"],
             "authority": POLICY["sources"][r_["id"]]["authority"], "attribution": POLICY["sources"][r_["id"]]["attribution"],
              "licence_status": POLICY["sources"][r_["id"]]["licence_status"], "awaiting": ("the publisher's confirmation that its prices may be reused" if POLICY["sources"][r_["id"]]["licence_status"] != "CLEARED" else None)} for r_ in REG["sources"] if r_["id"] in ALLOWED]
reg_summary = {"sources": len(reg_rows), **{s_: sum(1 for r_ in reg_rows if r_["status"] == s_) for s_ in policy.PUBLIC_STATUS},
               "scheduled_runs": sum(r_["scheduled_runs"] for r_ in reg_rows), "manual_runs": sum(r_["manual_runs"] for r_ in reg_rows)}


def schedules():
    """The schedules as written in the workflow files of the engine: read from the files, so the page cannot describe a schedule that is not defined."""
    import glob, re
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml"))):
        text = open(p, encoding="utf-8").read(); name = re.search(r"^name:\s*(.+)$", text, re.M)
        for m in re.finditer(r"-\s*cron:\s*\"([^\"]+)\"\s*(?:#\s*(.*))?", text):
            out.append({"workflow": name.group(1).strip() if name else os.path.basename(p), "file": os.path.basename(p), "cron": m.group(1), "meaning": (m.group(2) or "").strip()})
    return out


runs_p = os.path.join(sources.OPS_DIR, "production_runs.jsonl"); prod_runs = recs.read(runs_p)
RUN_KEYS = ("run_id", "started_at", "finished_at", "status", "trigger", "sources_attempted", "sources_succeeded", "sources_failed", "data_changed", "forecast_issued")
last_run = None if not prod_runs else {**{k: prod_runs[-1].get(k) for k in RUN_KEYS}, "gate_passed": prod_runs[-1]["gate"]["passed"], "runs_on_record": len(prod_runs),
                                       "scheduled_runs_on_record": sum(1 for x in prod_runs if x.get("trigger") == "schedule")}
if last_run:                                                         # the public status names only sources of the product; what else a run asked is in the engine's own record
    for k_ in ("sources_attempted", "sources_succeeded", "sources_failed"):
        if last_run.get(k_) is not None: last_run[k_] = [i_ for i_ in last_run[k_] if i_ in ALLOWED]
if prod_runs and not prod_runs[-1]["gate"]["passed"]: sys.exit("the last production run did not pass its gate (" + "; ".join(prod_runs[-1]["gate"]["critical"]) + "): nothing is exported; the site keeps the data it had")
try:
    import subprocess
    commit = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip() or None
except Exception: commit = None
PUBLISH = {"expected_every_days": 1, "stale_after_days": 3}        # configuration of the publication (the production workflow runs daily); the pages compare the export time with this limit
export_info = {"version": "6.0", "engine_commit": commit, **PUBLISH,
               "datasets": {"benchmark_snapshot": snapshot_hash()[:16], "expansion_snapshot": v2["v2_snapshot"][:16] if v2 else None,
                            "weekly_fuel_vintages": wops.dataset_version()[:16] if weekly.get("available") and weekly.get("state") else None},
               "policy_audited": POLICY["audited"], "features": sorted(FEATURES)}
through = {"index": lanes[[l["id"] for l in lanes].index(PRIMARY)]["latest_month"], "fuel": fuel["jet"]["latest_date"],
           "weekly_fuel_release": weekly["state"]["latest_release"] if weekly.get("available") and weekly.get("state") else None}

write("core.json", {
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "primary": PRIMARY, "proxy_statement": dd.PROXY_STATEMENT, "flat_band_pct": config.FLAT_BAND_PCT, "revision_releases": config.REVISION_RELEASES, "fuel_lag_days": config.FUEL_AVAILABILITY_LAG_DAYS,
    "lanes": lanes, "fuel": fuel,
    "state": {"data_mode": state["data_mode"], "latest_ingestion": state["latest_ingestion"], "latest_ingestion_trigger": state["latest_ingestion_trigger"],
              "records_intact": all(not v for v in state["chains"].values()) and all(REG["logs_intact"].values()),
              "not_live_statement": status["not_live_statement"] if status else None},
    "status": last_run,                                               # a safe subset of the newest production run record
    # what started this export. The publish job deploys only after the export, the tests and the build have passed, so a
    # deployed page that names a hosted run is the record that its export was published, built and deployed by that run.
    "publish": {"trigger": ops_pipeline.detect_trigger(), "workflow_run": ops_pipeline.workflow_run()},
    "not_in_product": [{"name": f_["name"], "state": PLAIN_STATE[f_["status"]], "why": f_["reason"]} for f_ in POLICY["features"].values() if f_["status"] != "PRODUCTION READY"],
    "registry": {"generated_at": REG["generated_at"], "summary": reg_summary, "sources": reg_rows},
    "schedule": schedules(), "counts": {"lanes": len(lanes), "lanes_with_outlook": sum(1 for l in lanes if l["primary"])},
    "freshness": fresh, "snapshot_retrieved": sorted({r[:10] for r in snap["retrieved_at"]})[-1], "export": export_info, "through": through,
})
write("replay.json", replay)
import export_aviation                                              # noqa: E402  observed air traffic: only what the production policy allows
aviation = export_aviation.build(ROOT); write("aviation.json", aviation)

# ---------------------------------------------------------------- publish gate: nothing half-written reaches the site
import hashlib                                                       # noqa: E402
VOLATILE = {"generated_at", "mode", "registry", "state", "age_days", "age_hours", "days_since_latest_release", "stale", "export", "update", "last_production_run", "status", "publish", "collected"}   # fields that follow the clock or the run, not the data


def logical(o):
    if isinstance(o, dict): return {k: logical(v) for k, v in sorted(o.items()) if k not in VOLATILE}
    if isinstance(o, list): return [logical(v) for v in o]
    return o


staged = sorted(os.path.relpath(os.path.join(d, f_), OUT).replace(os.sep, "/") for d, _, fs in os.walk(OUT) for f_ in fs)
need = {"core.json", "outlook.json", "weekly.json", "news.json", "replay.json", "aviation.json", *(f"market/{s}.json" for s in config.BLS_SERIES)}
if need - set(staged): sys.exit(f"export incomplete, nothing published: missing {sorted(need - set(staged))}")
h = hashlib.sha256(); loaded = {}
for name in staged:
    with open(os.path.join(OUT, name), encoding="utf-8") as fh: loaded[name] = json.load(fh)      # every staged file must be valid JSON
    h.update(name.encode()); h.update(json.dumps(logical(loaded[name]), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
problems = []
if not loaded["outlook.json"]["forecasts"]: problems.append("the outlook holds no forecast")
if loaded["outlook.json"]["official"]["engine_id"] != OFFICIAL: problems.append("the outlook names another forecaster than the selection")
if any(not l_["spark"] for l_ in loaded["core.json"]["lanes"]): problems.append("a lane has no history")
# nothing that did not pass the production gate may be in the public files: checked on what was actually written
import re as _re                                                     # noqa: E402
BANNED = (r"EXPERIMENTAL", r"RESEARCH[-_ ]ONLY", r"DATA[-_ ]LIMITED", r"UNVERIFIED", r"NOT PREDICTIVE", r'"band"\s*:', r'"expected"\s*:', r'"z"\s*:', r"capacity_proxy", r"eurocontrol", r'"events"\s*:', r'"positions"\s*:')
for name in staged:
    text_ = json.dumps(loaded[name], ensure_ascii=False)
    for b_ in BANNED:
        if _re.search(b_, text_): problems.append(f"{name} holds {b_}: not a production field")
listed = {r_["id"] for r_ in loaded["core.json"]["registry"]["sources"]}
if listed - ALLOWED: problems.append(f"sources listed that the policy refuses: {sorted(listed - ALLOWED)}")
if any(r_["status"] not in policy.PUBLIC_STATUS for r_ in loaded["core.json"]["registry"]["sources"]): problems.append("a source is listed with a state that is not one of the five public states")
if problems: sys.exit("export refused, nothing published: " + "; ".join(problems))
loaded["core.json"]["export"]["content_hash"] = h.hexdigest()        # equal for two exports of unchanged data, whenever they run
loaded["core.json"]["export"]["files"] = len(staged)
with open(os.path.join(OUT, "core.json"), "w", encoding="utf-8") as fh: json.dump(loaded["core.json"], fh, ensure_ascii=False, separators=(",", ":"))
os.makedirs(PUBLISHED, exist_ok=True)
for name in staged:
    dst = os.path.join(PUBLISHED, name); os.makedirs(os.path.dirname(dst), exist_ok=True); os.replace(os.path.join(OUT, name), dst)
for d, _, fs in os.walk(PUBLISHED):                                 # a file of an earlier export that this one no longer writes must not stay
    for f_ in fs:
        rel_ = os.path.relpath(os.path.join(d, f_), PUBLISHED).replace(os.sep, "/")
        if rel_ not in staged: os.remove(os.path.join(d, f_)); print("removed", rel_)
shutil.rmtree(OUT)
print("content", h.hexdigest()[:16], "files", len(staged))
print("done:", len(replay["months"]), "replay months,", len(lanes), "lanes; official forecast", OFFICIAL, "; public features:", ", ".join(sorted(FEATURES)),
      "; weekly fuel outlook", "exported" if weekly.get("available") else "not offered", "; air traffic", "exported" if aviation.get("available") else "not available", "; export version", export_info["version"], "engine commit", commit)
