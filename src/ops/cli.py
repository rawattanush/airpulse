"""Command line of the operational pipeline. Run from the repository root.

    python -m src.ops.cli init                      # seed operations/current from the benchmark snapshot (no network)
    python -m src.ops.cli run                       # refresh fuel and BLS data, rebuild the operational store, issue forecasts
    python -m src.ops.cli run --sources news        # refresh the headline archive, rebuild and export the event store
    python -m src.ops.cli run --no-fetch            # no network: rebuild from the files held and issue any forecast not yet issued
    python -m src.ops.cli status                    # health and data mode of every source, from the run log and the clock
    python -m src.ops.cli verify                    # check the hash chains of the run log, the forecast ledger and the outcomes
    python -m src.ops.cli select                    # the official forecaster by the selection rule, written to operations/official_forecast.json

Exit code 1 when a source failed or a step raised, so that a scheduler reports the run as failed."""
import argparse, json, sys
from src.observability import health, records, sources
from src.ops import pipeline


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m src.ops.cli", description="AirPulse operational pipeline. Nothing here is live: a run happens when a person or a scheduler starts it.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="seed operations/current from the benchmark snapshot")
    r = sub.add_parser("run", help="one pipeline run")
    r.add_argument("--sources", nargs="*", choices=list(sources.GROUPS), default=["fuel", "bls"]); r.add_argument("--no-fetch", action="store_true")
    r.add_argument("--trigger", choices=["manual", "schedule", "manual-dispatch"], help="default: detected from the environment")
    sub.add_parser("status", help="source health and data mode"); sub.add_parser("verify", help="verify the append-only files")
    sub.add_parser("select", help="the official forecaster by the selection rule; writes operations/official_forecast.json")
    a = ap.parse_args(argv)
    if a.cmd == "init":
        done = pipeline.seed(); print(f"seeded {len(done)} files into operations/current" if done else "operations/current already holds every file"); pipeline.write_status()
    elif a.cmd == "run":
        summary, code = pipeline.run(tuple(a.sources), fetch=not a.no_fetch, trigger=a.trigger)
        print(json.dumps(summary, indent=1)); sys.exit(code)
    elif a.cmd == "status":
        rows = health.all_health()
        print(f"forecast inputs data mode: {health.overall_mode(rows)}")
        for h in rows: print(f"{h['status']:15} {h['data_mode']:9} {h['source']:22} last success {h['last_successful_fetch'] or '-':20} latest observation {h['latest_observation'] or '-':20} {h['failure_reason']}")
    elif a.cmd == "select":
        from src.ops import selection
        try: rec = selection.select()
        except selection.NoSelection as e: print(f"NO OFFICIAL FORECAST: {e}"); sys.exit(1)
        selection.write(rec); print(f"official forecaster: {rec['official']} ({rec['name']}); later decisions consistent: {len(rec['later_decisions'])}")
    elif a.cmd == "verify":
        bad = 0
        for name, path in (("ingestion log", sources.INGESTION_LOG), ("forecast ledger", sources.FORECAST_LEDGER), ("forecast outcomes", sources.FORECAST_OUTCOMES)):
            p = records.verify(path); bad += len(p); print(f"{name}: {len(records.read(path))} records, " + ("intact" if not p else "PROBLEMS: " + "; ".join(p)))
        sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
