"""Which forecaster the product shows, decided by rule and written down.

The rule is the one the evaluation has always applied (README, final report): the official forecaster is the one that
the walk-forward evaluation on the validated target supports among the forecasters whose registry status is VALIDATED,
by probability score and by hit rate. The two criteria must name the same forecaster; if they do not, nothing is
selected. A later experiment changes the official forecaster only through its own pre-registered promotion rule, and
its stored decision must name the same forecaster; if it does not, nothing is selected.

Nothing here names a forecaster. The record is recomputed from the evaluation store and the stored decisions on every
run and written to operations/official_forecast.json, so the choice a customer sees is traceable to the scores it rests on."""
import hashlib, json, os
from src import config as base
from src.database import store
from src.observability import sources

RECORD = os.path.join(sources.OPS_DIR, "official_forecast.json")
DECISIONS = (("expansion pass (protocol 2.0)", os.path.join("evaluation", "monthly", "results_v2.json")),
             ("global pass (protocol 3.0)", os.path.join("evaluation", "global_features", "results_v3.json")))
SHORT = {"SEA": "BL-SEA", "MAJ": "BL-MAJ", "PER": "BL-PER"}        # how the later experiments abbreviate the three baselines
RULE = ("Among the forecasters with registry status VALIDATED, the one with the lowest Brier score and the highest hit rate on the final labels "
        "of the validated target over all scored months; both criteria must agree. Every later pre-registered experiment must name the same forecaster.")


class NoSelection(Exception):
    """The evaluation does not single out one forecaster. Nothing may be shown as the official forecast."""


def select(conn=None, root=None):
    """The selection record. Raises NoSelection with the reason when the rule does not single out one forecaster."""
    from src.dashboard import data as dd
    root = root or base.ROOT; own = conn is None
    if own and not os.path.exists(base.DB_PATH):                         # never create an empty store by looking for one
        raise NoSelection("the benchmark store is absent; it is derived from the frozen snapshot (src.dashboard.data.ensure_store, or python -m src.cli build-db and backtest)")
    conn = conn or store.connect(base.DB_PATH)
    try: table = dd.model_table(conn, base.PRIMARY_SERIES)
    finally:
        if own: conn.close()
    if table is None or table.empty: raise NoSelection("the store holds no evaluation of the validated target; run the backtest first")
    cand = table[table["status"] == "VALIDATED"]
    if cand.empty: raise NoSelection("no forecaster has registry status VALIDATED")
    by_score, by_hit = dd.best_by(cand, "Brier score", True), dd.best_by(cand, "hit rate", False)
    if by_score != by_hit: raise NoSelection(f"the criteria disagree (best probability score: {by_score}; best hit rate: {by_hit})")
    decisions = []
    for name, rel in DECISIONS:
        p = os.path.join(root, rel)
        if not os.path.exists(p): continue
        with open(p, encoding="utf-8") as f: r = json.load(f)
        d = r["decision"]; named = SHORT.get(d["official"], d["official"])
        decisions.append({"experiment": name, "file": rel.replace(os.sep, "/"), "date": r.get("generated"), "official": named, "changed": bool(d["changed"]), "candidates_that_passed": list(d["passed"])})
        if named != by_score: raise NoSelection(f"the {name} names {named} and the evaluation names {by_score}; a promotion is completed in the repository, not at run time")
    with open(os.path.join(root, "evaluation", "benchmark_ledger.sha256"), encoding="utf-8") as f: ledger = f.read().split()[0]
    rows = [{"id": i, "name": r["forecaster"], "role": r["role"], "status": r["status"], "brier": float(r["Brier score"]), "hit_rate": float(r["hit rate"]), "months": int(r["months scored"])} for i, r in table.iterrows()]
    return {"official": by_score, "name": table.at[by_score, "forecaster"], "series": base.PRIMARY_SERIES, "rule": RULE, "evaluation_period": table.at[by_score, "evaluation period"],
            "candidates": rows, "later_decisions": decisions, "benchmark_ledger_sha256": ledger}


def write(record, path=None):
    """Write the record; the file changes only when the selection or what it rests on changes (it carries no clock)."""
    path = path or RECORD; os.makedirs(os.path.dirname(path), exist_ok=True); text = json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    if not os.path.exists(path) or open(path, encoding="utf-8").read() != text:
        with open(path, "w", encoding="utf-8", newline="\n") as f: f.write(text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read(path=None):
    path = path or RECORD
    if not os.path.exists(path): return None
    with open(path, encoding="utf-8") as f: return json.load(f)
