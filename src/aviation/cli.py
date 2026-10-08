"""Aviation operations layer: command line (protocol evaluation/validation_protocol_v4.md).

    python -m src.aviation.cli collect [days]   # archive the Hong Kong flight lists of the last `days` days (default 3) and one position snapshot (network)
    python -m src.aviation.cli refresh [--offline] [--days N] [--sources ...]
                                                # unattended operational run: Hong Kong flight lists, position picture, the two official files
                                                # (downloaded only when the publisher changed them), check of the Hong Kong archive, quality gate, status
    python -m src.aviation.cli status           # health and freshness of the feeds, from the log
    python -m src.aviation.cli analyse          # anomaly validation, capacity proxy, corridors, South Asia to Europe, Hong Kong operations, lead-lag
    python -m src.aviation.cli ablation         # screening ablation on the monthly target (about 6 min)
    python -m src.aviation.cli reports          # research/*.md and execution/PHASE_4_REPORT.md from the stored results
    python -m src.aviation.cli all              # analyse, ablation, reports

Reads the stored snapshots, the operational archive and the benchmark store. Writes evaluation/aviation, operations/aviation
and the aviation reports. Never writes the benchmark ledger or the official forecast."""
import datetime, json, os, sys
import pandas as pd
from src import config as base
from src.api import backtest as bt
from src.aviation import activity, collector, config as cfg, features

P = lambda name: os.path.join(cfg.EVAL_DIR, name)
today = lambda: datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def collect(days=3):
    t = datetime.datetime.now(datetime.timezone.utc).date()
    out = collector.collect_hkia([(t - datetime.timedelta(days=k)).isoformat() for k in range(days, 0, -1)]); p = collector.collect_positions()
    res = {}
    for r in out: res[r["result"]] = res.get(r["result"], 0) + 1
    print(f"hong kong flight lists: {res}; positions: {p['result']} ({p['airports_answered']} of {p['airports_asked']} airports answered)")
    return 0 if all(r["result"] in ("NEW", "REVISED", "UNCHANGED") for r in out) else 2


def status():
    from src.aviation import operations
    s = operations.write_status(); print(json.dumps(s, indent=1)); return 0


def refresh(argv):
    from src.aviation import operations
    names = ("hkia", "positions", "eurocontrol", "usdot"); days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 3
    chosen = [a for a in argv[argv.index("--sources") + 1:] if a in names] if "--sources" in argv else list(names)
    summary, code = operations.run(tuple(chosen), days, fetch="--offline" not in argv); print(json.dumps(summary, indent=1)); return code


def _research():
    """The research commands (analyse, ablation, reports) use the modules of the research passes; the operational commands do not load them."""
    from src.v2 import cli as c2cli, monthly as mo
    from src.aviation import experiment
    return c2cli._write, c2cli._csv, mo, experiment


def analyse():
    _write, _csv, mo, experiment = _research()
    eur, usd = activity.european_daily(), activity.us_international(); meta = {"generated": today(), "protocol": cfg.PROTOCOL_VERSION, "processing": cfg.PROCESSING_VERSION, "code_hash": bt.code_hash()}
    av = experiment.anomaly_validation(eur); _write(P("anomaly_validation.json"), {**meta, **av})
    print(f"anomaly signal: closure events {av['closure']['detected']} of {av['closure']['testable']} detected; false alarms {100 * av['quiet_days']['false_alarm_share_low']:.1f}% of quiet days; status {av['status']}")
    cor = experiment.corridors(usd); _write(P("corridors.json"), {**meta, **cor})
    hk = experiment.hkg_operations(); _write(P("hkg_operations.json"), {**meta, **hk})
    print(f"hong kong: {hk['days']} days, {hk['first_day']} to {hk['last_day']}; {len(hk['events'])} events, {hk['events_added_to_store']} new in the store")
    src = features.monthly_sources(eur, usd); ll = experiment.lead_lag(src); _write(P("lead_lag.json"), {**meta, **ll})
    print(f"lead-lag: {ll['tests']} correlations, {len(ll['significant_after_holm'])} significant after Holm")
    for name in (features.EUR, features.USD): _csv(P(f"monthly_{name}.csv"), src[name].reset_index(names="month"))
    if os.path.exists(os.path.join(cfg.SNAPSHOT_DIR, "flightlists", "flightlist_airport_daily.csv.gz")):
        px = experiment.proxy_evaluation(eur); _write(P("proxy_evaluation.json"), {**meta, **px}); sae = experiment.south_asia_europe(meta["generated"]); _write(P("south_asia_europe.json"), {**meta, **sae})
        print(f"capacity proxy: schemes that track cargo: {px['schemes_that_track_cargo'] or 'none'}; airports with stable coverage: {px['airports_stable_enough'] or 'none'}; South Asia to Europe monitorable: {sae['monitorable']}")
    else: print("flight-list aggregates not present: capacity proxy and South Asia to Europe not evaluated")
    return 0


def ablation(n_jobs=-2):
    _write, _csv, mo, experiment = _research()
    src = features.monthly_sources(); out = experiment.ablation(src, n_jobs); res, frame, lad = out["result"], out["frame"], out["lad"]
    res = {"generated": today(), "code_hash": bt.code_hash(), "european_hubs": src["meta"], **res}; _write(P("ablation_results.json"), res)
    info = frame[["max_info_v2", "av_eur_available", "av_usd_available"]].fillna("").max(axis=1)
    _csv(P("forecasts_v4.csv"), mo.ledger_frame(frame.assign(max_info_v2=info), lad))
    _csv(P("features_v4.csv"), frame[["target_month", "issued_at"] + [c for c in frame.columns if c.startswith("av_")]])
    print(f"ablation: {res['tests']} tests on {res['scored_months']} months; baselines against the ledger: {[v['largest_difference'] for v in res['baseline_check'].values()]}; conclusion: {res['conclusion']}; official forecast can change: {res['official_forecast_can_change']}")
    return 0


def main(argv):
    what = argv[0] if argv else "all"
    if what == "collect": return collect(int(argv[1]) if len(argv) > 1 else 3)
    if what == "status": return status()
    if what == "refresh": return refresh(argv[1:])
    if what in ("analyse", "all"): analyse()
    if what in ("ablation", "all"): ablation()
    if what in ("reports", "all"):
        from src.aviation import report; report.write_all()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
