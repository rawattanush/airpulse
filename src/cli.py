"""MOD-00 Orchestrator: one command-line entry point (REQ-FN-004).

    python -m src.cli build-db
    python -m src.cli backtest [--series IC1312 ...]
    python -m src.cli replay --series IC1312 --forecaster ML-LOGIT --month 2021-09
    python -m src.cli report-metrics [--series IC1312] [--label FINAL|REALTIME] [--period ALL]
"""
import argparse, os, sys, time
from src import config
from src.database import store


def _conn():
    if not os.path.exists(config.DB_PATH): sys.exit("Store not found. Run: python -m src.cli build-db")
    return store.connect(config.DB_PATH)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m src.cli", description="AirPulse: backtest of a monthly air freight price-index direction forecast (US-lane proxy).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build-db", help="verify the snapshot and rebuild the canonical store (existing forecasts are discarded)")
    b = sub.add_parser("backtest", help="walk-forward backtest; writes the ledger and registers")
    b.add_argument("--series", nargs="*", choices=list(config.BLS_SERIES), help="default: all eight series")
    r = sub.add_parser("replay", help="recompute one stored forecast and compare")
    r.add_argument("--series", required=True, choices=list(config.BLS_SERIES)); r.add_argument("--forecaster", required=True); r.add_argument("--month", required=True, help="YYYY-MM")
    m = sub.add_parser("report-metrics", help="print the metric table of a series")
    m.add_argument("--series", default=config.PRIMARY_SERIES, choices=list(config.BLS_SERIES))
    m.add_argument("--label", default="FINAL", choices=["FINAL", "REALTIME"]); m.add_argument("--period", default="ALL")
    a = ap.parse_args(argv)

    if a.cmd == "build-db":
        from src.ingestion.build import build_store
        t0 = time.time(); counts = build_store()
        print(f"store built at {config.DB_PATH} in {time.time() - t0:.1f}s"); [print(f"  {k}: {v} revision-log rows") for k, v in counts.items()]
    elif a.cmd == "backtest":
        from src.api.backtest import run_backtest
        conn = _conn(); t0 = time.time(); run_id, n = run_backtest(conn, a.series or None)
        print(f"run {run_id}: {n} forecasts written in {time.time() - t0:.1f}s; ledger exported to evaluation/forecast_ledger.csv")
    elif a.cmd == "replay":
        from src.api.backtest import replay
        s, o, diff = replay(_conn(), a.series, a.forecaster, a.month)
        print(f"stored:     {s['predicted']}  p(down, flat, up) = ({s['p_down']}, {s['p_flat']}, {s['p_up']})  issued {s['issued_at']}  status {s['status']}")
        print(f"recomputed: {o['predicted']}  p = {None if o['proba'] is None else tuple(float(x) for x in o['proba'])}  n_train {o['n_train']}")
        print(f"max abs probability difference: {diff}")
        if diff is not None and diff > 1e-9: sys.exit(1)
    elif a.cmd == "report-metrics":
        from src.api.backtest import metric_table
        t = metric_table(_conn(), a.series, a.label, a.period)
        print(f"BACKTEST  series {a.series}  label {a.label}  period {a.period}")
        print("(no results)" if t.empty else t[["n", "hit_rate", "balanced_hit_rate", "macro_f1", "brier", "log_loss"]].round(3).to_string())


if __name__ == "__main__":
    main()
