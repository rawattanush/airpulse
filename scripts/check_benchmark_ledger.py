"""Compare a regenerated benchmark ledger (evaluation/forecast_ledger.csv in the working tree, as `python -m src.cli backtest`
has just written it) with the ledger of record (the committed file, whose SHA-256 is pinned in evaluation/benchmark_ledger.sha256).

Three outcomes, printed and returned as the exit code:
  BYTE-IDENTICAL            the regenerated file has the pinned hash                                              exit 0
  NUMERICALLY EQUIVALENT    not the same bytes, and ALL of the following hold                                     exit 0
                              1. same rows and columns, in the same order
                              2. every field other than the three probabilities is identical: forecast identifier, dates,
                                 predicted and actual direction, hit or miss, training size, status
                              3. the three rule baselines have identical probabilities (they are counts and one division,
                                 which every IEEE-754 machine computes to the same bits)
                              4. every probability of a fitted model is within that model's tolerance (TOLERANCES:
                                 logistic model 1e-10, boosted trees 1e-14), AND the mean absolute difference over all
                                 probabilities of that model is within its mean tolerance (MEAN_TOLERANCES: 1e-12 and
                                 1e-16): rounding is small in every row and small on average, so many rows each moved by
                                 less than the row tolerance are refused
                              5. every reported metric, recomputed for both ledgers by the benchmark's own scoring code
                                 (every series, forecaster, label kind and period): the metrics that depend on classes only
                                 (hit rate, balanced hit rate, macro F-score, confusion matrix, count) are identical, Brier
                                 score and log loss are within METRIC_TOLERANCE, and every value is the same at the three
                                 decimals that are reported
  DIFFERENT                 anything else, or the committed ledger itself no longer has the pinned hash           exit 1

Why the second outcome exists. The ledger of record was produced on Windows. On Linux, with the same package versions, the
probabilities of the logistic and boosted-tree models differ in the last digits of a 64-bit float, so the bytes differ although
no forecast, hit or reported score does. The check reports every statistic of the difference and says which outcome it found;
it never reports byte-identity that it did not observe.

What the tolerances are for, and what they are not. They separate rounding differences between builds of the numerical
libraries from a change of the method. Each is set by one rule from a measurement (evaluation/ledger_tolerance_study.md,
scripts/ledger_tolerance_study.py): the smallest power of ten that is at least 100 times the largest platform difference measured
for that model. The logistic model's coefficients come from an iterative solver and differ between platforms by up to 8.8e-13;
the boosted trees differ by half a unit in the last place (5.6e-17). Measured again on the benchmark of record after the licence
repair (CL-024), where the rule gives 1e-10 and 1e-14: one power of ten tighter than on the ledger before it (1.2e-12 and 1.1e-16
then). A single tolerance of 1e-9 for both, as first written, would
have hidden a real change of the boosted trees (a learning rate altered by one part in a billion moves their probabilities by
6e-10), so the tolerance is per model. A forecaster without an entry in TOLERANCES must be identical.
The mean tolerances follow the same rule from the measured mean differences (7.7e-15 and 1.3e-19).
The rules were attacked with deliberate alterations of the Linux ledger (below, at and above each tolerance; class, hit and
baseline changes; a probability near zero; many rows moved together); the results are section D of the study and are repeated
by test T-22 and audit check O11.
A tolerance cannot detect a change whose effect on every probability is smaller than the tolerance; what such a change could
alter is bounded (no predicted class, no hit; Brier score by at most 6 x the tolerance; every metric by at most
METRIC_TOLERANCE) and the bound is reported. On the machine that produced the record no tolerance applies at all: there the
audit and the tests require the pinned hash (--strict).

    python scripts/check_benchmark_ledger.py [--regenerated FILE] [--out result.json] [--keep FILE] [--restore] [--strict]
--regenerated  compare this file instead of the working-tree ledger (for a ledger brought from another machine)
--keep         copy the regenerated ledger to FILE (before --restore), so that it can be examined later
--restore      put the ledger of record (and evaluation/experiments.csv) back in the working tree after a passing result,
               so that every later check runs against the record
--strict       pass only on BYTE-IDENTICAL"""
import argparse, csv, hashlib, io, json, os, platform, shutil, subprocess, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.api import backtest as bt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = "evaluation/forecast_ledger.csv"; PIN = "evaluation/benchmark_ledger.sha256"
TOLERANCES = {"ML-LOGIT": 1e-10, "ML-GBT": 1e-14}   # largest accepted difference in a probability, per fitted model; rule and measurement: evaluation/ledger_tolerance_study.md
MEAN_TOLERANCES = {"ML-LOGIT": 1e-12, "ML-GBT": 1e-16}   # largest accepted mean absolute difference over all probabilities of the model; same rule, from the measured means
TOLERANCE = max(TOLERANCES.values())               # the largest of them: no probability of any forecaster may differ by more than this
HEADROOM = 100                                     # each tolerance is the smallest power of ten that is at least this many times the measured platform difference
EQUALITY_PASSES = True                             # comparator semantics, documented here and observed in the study (section D): a difference is refused only when it is
                                                   # GREATER than its tolerance; a difference exactly equal to the tolerance is accepted. The same holds for the mean and metric tolerances.
METRIC_TOLERANCE = 1e-6      # largest accepted difference in a reported metric at full precision (metrics are reported at three decimals)
PROBS = ("P_DOWN", "P_FLAT", "P_UP"); CLASSES = ("DOWN", "FLAT", "UP")
EXACT = sorted(bt.BASELINES)                                     # forecasters whose probabilities must be identical on every platform
LEVELS = (0.0, 1e-15, 1e-14, 1e-13, 1e-12, 1e-10, 1e-9)           # rows are counted above each of these; every tolerance is one of them
CLASS_METRICS = ("hit_rate", "balanced_hit_rate", "macro_f1"); PROB_METRICS = ("brier", "log_loss")


_RECORD_METRICS = {}                                # metrics of a ledger of record, by its checksum: computed once when many candidates are compared with it


def read_ledger(b):
    return list(csv.DictReader(io.StringIO(b.decode("utf-8"), newline="")))


def write_ledger(rows):
    """Ledger rows back to bytes, in the format the backtest exports (the inverse of read_ledger)."""
    buf = io.StringIO(newline=""); w = csv.DictWriter(buf, list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _number(text):
    try: return float(text)
    except ValueError: return np.nan


def proba(rows):
    """(n, 3) array of the probabilities; NaN where the ledger holds none (a skipped forecast) or holds something that is not a number."""
    return np.array([[_number(r[c]) if r[c] != "" else np.nan for c in PROBS] for r in rows])


def reported_metrics(rows):
    """Every metric the benchmark reports, recomputed from ledger rows by the benchmark's own scoring function:
    {(series, forecaster, label kind, period): metrics}. Months are those common to all forecasters, as in the backtest."""
    df = pd.DataFrame({"series": [r["SERIES"] for r in rows], "forecaster_id": [r["FORECASTER"] for r in rows], "target_month": [r["TARGET_MONTH"] + "-01" for r in rows],
                       "predicted": [r["PREDICTION"] or None for r in rows], "actual": [r["ACTUAL"] or None for r in rows], "actual_realtime": [r["ACTUAL_REALTIME"] or None for r in rows]})
    P = proba(rows); df["p_down"], df["p_flat"], df["p_up"] = P[:, 0], P[:, 1], P[:, 2]; df["proba_ok"] = df["p_up"].notna()
    out = {}
    for sid, g in df.groupby("series"):
        for kind, col in (("FINAL", "actual"), ("REALTIME", "actual_realtime")):
            for (fid, period), m in bt._score_rows(g, col).items(): out[(sid, fid, kind, period)] = m
    return out


def difference_statistics(old, new):
    """Statistics of the probability differences, by forecaster and for the fitted models together. A row's difference is the
    largest absolute difference among its three probabilities."""
    Po, Pn = proba(old), proba(new); d = np.abs(Pn - Po); both = np.isfinite(d).all(axis=1)          # a row with a missing or non-numeric probability is reported by its own rule, not measured here
    row = np.where(both, np.max(np.where(np.isfinite(d), d, 0.0), axis=1), 0.0); signed = (Pn - Po)
    fid = np.array([r["FORECASTER"] for r in old])

    def stats(mask):
        r = row[mask & both]; v = d[mask & both].ravel(); s = signed[mask & both].ravel()
        if len(r) == 0: return {"rows": 0}
        return {"rows": int(len(r)), "probabilities": int(len(v)), "rows_different": int((r > 0).sum()), "max_abs": float(r.max()), "mean_abs_all_probabilities": float(v.mean()),
                "mean_abs_changed_probabilities": float(v[v > 0].mean()) if (v > 0).any() else 0.0, "mean_signed": float(s.mean()),
                "percentiles_of_row_difference": {f"p{q:g}": float(np.percentile(r, q, method="higher")) for q in (50, 90, 95, 99, 99.9, 100)},   # "higher": always a value that occurs
                "rows_above": {f"{lv:g}": int((r > lv).sum()) for lv in LEVELS}}
    fitted = ~np.isin(fid, EXACT)
    return {"by_forecaster": {str(f): stats(fid == f) for f in sorted(set(fid))}, "fitted_models": stats(fitted), "all": stats(np.ones(len(fid), bool))}


def record_margins(old):
    """How far the record is from a change of class or of a clipped log loss: the smallest gap between the two highest
    probabilities of a fitted-model forecast, and the smallest probability any forecaster gave to the class that occurred."""
    P = proba(old); ok = ~np.isnan(P).any(axis=1); fitted = np.array([r["FORECASTER"] not in EXACT for r in old])
    top = np.sort(P[ok & fitted], axis=1); gap = top[:, 2] - top[:, 1]
    pa = [P[i, CLASSES.index(a)] for i, r in enumerate(old) for a in (r["ACTUAL"], r["ACTUAL_REALTIME"]) if ok[i] and a in CLASSES]
    return {"smallest_gap_between_the_two_highest_probabilities_fitted_models": float(gap.min()), "smallest_probability_given_to_an_actual_class": float(min(pa))}


def compare(record_bytes, new_bytes, pin):
    res = {"pinned_sha256": pin, "record_sha256": hashlib.sha256(record_bytes).hexdigest(), "regenerated_sha256": hashlib.sha256(new_bytes).hexdigest(), "tolerance": TOLERANCE, "tolerances": dict(TOLERANCES),
           "metric_tolerance": METRIC_TOLERANCE, "platform": platform.platform(), "python": platform.python_version()}
    if res["record_sha256"] != pin: return {**res, "outcome": "DIFFERENT", "reasons": ["the committed ledger does not have the pinned hash"]}
    if res["regenerated_sha256"] == pin: return {**res, "outcome": "BYTE-IDENTICAL"}
    old = read_ledger(record_bytes); new = read_ledger(new_bytes)
    if len(old) != len(new) or not new or list(old[0]) != list(new[0]) or [r["FORECAST-ID"] for r in old] != [r["FORECAST-ID"] for r in new]:
        return {**res, "outcome": "DIFFERENT", "reasons": [f"rows {len(new)} against {len(old)}, or different columns, or different forecast identifiers"]}
    other = [c for c in old[0] if c not in PROBS]; reasons = []; rules = []                     # rules: the same findings as short codes, for tests and the audit
    changed = {c: sum(a[c] != b[c] for a, b in zip(new, old)) for c in other}; changed = {c: n for c, n in changed.items() if n}
    Po, Pn = proba(old), proba(new); ok = np.isfinite(Po).all(axis=1) & np.isfinite(Pn).all(axis=1)
    empties = int((np.isfinite(Po) != np.isfinite(Pn)).sum())                             # a probability that is missing, infinite or not a number in one ledger only: such a row would otherwise drop out of every statistic
    argmax = int((np.argmax(Po[ok], axis=1) != np.argmax(Pn[ok], axis=1)).sum())
    st = difference_statistics(old, new)
    base_diff = sum(any(a[c] != b[c] for c in PROBS) for a, b in zip(new, old) if a["FORECASTER"] not in TOLERANCES)      # baselines, and any forecaster without a tolerance
    for f, x in st["by_forecaster"].items():
        if x.get("rows"): x["tolerance"] = TOLERANCES.get(f, 0.0); x["mean_tolerance"] = MEAN_TOLERANCES.get(f, 0.0); x["rows_above_its_tolerance"] = x["rows_above"][f"{TOLERANCES[f]:g}"] if f in TOLERANCES else x["rows_different"]
    res.update({"rows": len(new), "predicted_class_changes": changed.get("PREDICTION", 0), "largest_probability_changes_position": argmax,
                "hit_or_miss_changes": changed.get("CORRECT", 0) + changed.get("CORRECT_REALTIME", 0), "other_fields_changed": {c: n for c, n in changed.items() if c not in ("PREDICTION", "CORRECT", "CORRECT_REALTIME")},
                "baseline_rows_with_a_different_probability": base_diff, "probability_differences": st, "record_margins": record_margins(old)})
    if changed:
        reasons.append(f"fields other than probabilities differ: {changed}")
        rules += [code for code, cols in (("class", ("PREDICTION",)), ("hit", ("CORRECT", "CORRECT_REALTIME"))) if any(c in changed for c in cols)]
        if any(c not in ("PREDICTION", "CORRECT", "CORRECT_REALTIME") for c in changed): rules.append("field")
    if empties: reasons.append(f"{empties} probabilities are a finite number in one ledger and missing or not a number in the other"); rules.append("missing_probability")
    if argmax: reasons.append(f"the largest probability moves to another class in {argmax} rows"); rules.append("largest_probability")
    if base_diff: reasons.append(f"{base_diff} baseline rows differ in a probability; baselines must be identical"); rules.append("baseline")
    for f, tol in TOLERANCES.items():
        x = st["by_forecaster"].get(f, {})
        if x.get("max_abs", 0.0) > tol: reasons.append(f"{f}: largest probability difference {x['max_abs']:.3e} exceeds the tolerance {tol:g} ({x['rows_above_its_tolerance']} rows)"); rules.append(f"row_tolerance:{f}")
        if x.get("mean_abs_all_probabilities", 0.0) > MEAN_TOLERANCES[f]:
            reasons.append(f"{f}: mean absolute probability difference {x['mean_abs_all_probabilities']:.3e} exceeds the mean tolerance {MEAN_TOLERANCES[f]:g}: the differences are too widespread to be rounding"); rules.append(f"mean_tolerance:{f}")
    if not empties:                                                                      # metrics need every probability; a changed class is scored like any other ledger
        if res["record_sha256"] not in _RECORD_METRICS: _RECORD_METRICS.clear(); _RECORD_METRICS[res["record_sha256"]] = reported_metrics(old)
        mo, mn = _RECORD_METRICS[res["record_sha256"]], reported_metrics(new); cells = 0; big = {m: 0.0 for m in PROB_METRICS}; cls_bad = 0; dec_bad = 0; any_metric = 0.0
        for k in mo:
            a, b = mo[k], mn.get(k, {"n": -1})
            if a["n"] != b["n"] or a.get("confusion") != b.get("confusion"): cls_bad += 1
            for m in CLASS_METRICS + PROB_METRICS:
                if m not in a or m not in b: continue
                cells += 1; dec_bad += f"{a[m]:.3f}" != f"{b[m]:.3f}"; any_metric = max(any_metric, abs(a[m] - b[m]))
                if m in CLASS_METRICS: cls_bad += a[m] != b[m]
                else: big[m] = max(big[m], abs(a[m] - b[m]))
        pmin = res["record_margins"]["smallest_probability_given_to_an_actual_class"]
        res["metrics"] = {"metric_values_compared": cells, "groups": len(mo), "class_based_metrics_identical": cls_bad == 0, "largest_change": big, "largest_change_of_any_metric": any_metric, "values_identical_at_three_decimals": dec_bad == 0,
                          "bound_at_the_tolerance": {"brier": 6 * TOLERANCE, "log_loss": TOLERANCE / max(pmin - TOLERANCE, 1e-12)}}
        if cls_bad: reasons.append(f"{cls_bad} class-based metrics, counts or confusion matrices differ"); rules.append("class_metric")
        if dec_bad: reasons.append(f"{dec_bad} metric values differ at the three reported decimals"); rules.append("metric_decimals")
        if max(big.values()) > METRIC_TOLERANCE: reasons.append(f"a metric changes by {max(big.values()):.3e}, more than {METRIC_TOLERANCE:g}"); rules.append("metric_tolerance")
    return {**res, "outcome": "DIFFERENT" if reasons else "NUMERICALLY EQUIVALENT", "reasons": reasons, "rules_violated": rules}


def report(res):
    """The printed summary: one line per question a reader would ask."""
    out = [f"benchmark ledger: {res['outcome']}"]
    for r in res.get("reasons", []): out.append(f"  reason: {r}")
    if "probability_differences" in res:
        f = res["probability_differences"]["fitted_models"]; b = res["probability_differences"]["by_forecaster"]
        by = ", ".join(f"{k} {v['rows_different']}" for k, v in b.items())
        out.append(f"  rows: {res['rows']}; rows with a different probability: {res['probability_differences']['all']['rows_different']} ({by})")
        out.append(f"  fitted models, probability difference: largest {f['max_abs']:.3e}; mean over all {f['probabilities']} probabilities {f['mean_abs_all_probabilities']:.3e}; mean over changed ones {f['mean_abs_changed_probabilities']:.3e}")
        out.append("  fitted models, percentiles of the row difference: " + ", ".join(f"{k} {v:.3e}" for k, v in f["percentiles_of_row_difference"].items()))
        out.append("  fitted models, rows above: " + ", ".join(f"{k}: {v}" for k, v in f["rows_above"].items() if k != "0"))
        out.append("  by forecaster, largest difference against its tolerance: " + "; ".join(f"{k} {v['max_abs']:.3e} / {('identical required' if not v.get('tolerance') else format(v['tolerance'], 'g'))}" for k, v in b.items()))
        out.append("  fitted models, mean difference against the mean tolerance: " + "; ".join(f"{k} {v['mean_abs_all_probabilities']:.3e} / {v['mean_tolerance']:g}" for k, v in b.items() if v.get("mean_tolerance")))
        out.append(f"  predicted class changes: {res['predicted_class_changes']}; hit or miss changes: {res['hit_or_miss_changes']}; other fields changed: {res['other_fields_changed'] or 'none'}; baseline rows different: {res['baseline_rows_with_a_different_probability']}")
    if "metrics" in res:
        m = res["metrics"]
        out.append(f"  reported metrics ({m['metric_values_compared']} values in {m['groups']} groups): class-based identical {m['class_based_metrics_identical']}; largest change Brier {m['largest_change']['brier']:.3e}, log loss {m['largest_change']['log_loss']:.3e} "
                   f"(tolerance {res['metric_tolerance']:g}); identical at three decimals {m['values_identical_at_three_decimals']}")
    out.append(f"  platform: {res['platform']}, Python {res['python']}; record {res['record_sha256'][:16]}, regenerated {res['regenerated_sha256'][:16]}")
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--regenerated"); ap.add_argument("--out"); ap.add_argument("--keep"); ap.add_argument("--restore", action="store_true"); ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    pin = open(os.path.join(ROOT, PIN), encoding="utf-8").read()[:64]
    record = subprocess.run(["git", "show", f"HEAD:{LEDGER}"], cwd=ROOT, capture_output=True, check=True).stdout
    src = a.regenerated or os.path.join(ROOT, LEDGER); res = compare(record, open(src, "rb").read(), pin)
    if a.out: json.dump(res, open(a.out, "w", encoding="utf-8"), indent=1)
    if a.keep and os.path.abspath(a.keep) != os.path.abspath(src): shutil.copyfile(src, a.keep)
    print("\n".join(report(res)))
    if res["outcome"] == "DIFFERENT" or (a.strict and res["outcome"] != "BYTE-IDENTICAL"):
        if a.strict and res["outcome"] != "DIFFERENT": print("  --strict: only BYTE-IDENTICAL passes")
        sys.exit(1)
    if a.restore: subprocess.run(["git", "checkout", "--", LEDGER, "evaluation/experiments.csv"], cwd=ROOT, check=True); print("  ledger of record and experiment register restored in the working tree")


if __name__ == "__main__":
    main()
