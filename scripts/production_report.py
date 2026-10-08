"""The operations report: what the records say now. Generated, never edited.

    python scripts/production_report.py                      # operations/reports/latest.md
    python scripts/production_report.py --cadence weekly     # the same; the cadence is named in the report
    python scripts/production_report.py --cadence monthly    # also kept as operations/reports/<YYYY-MM>.md, and exit 1 unless
                                                             # the official outlook of the newest month due is on the ledger

Everything in it is read from the source registry (run logs and the clock), the forecast ledgers, the outcomes and the
production run records. Nothing is typed: the same records at a later time give a later report."""
import datetime, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True
from src import config                                               # noqa: E402
from src.api import backtest as bt                                   # noqa: E402
from src.database import store                                       # noqa: E402
from src.observability import records, registry, sources             # noqa: E402
from src.ops import config as opscfg, selection                      # noqa: E402

OUT = os.path.join(sources.OPS_DIR, "reports")


def monthly_state():
    """The newest month for which an issuance date exists in the operational data, and whether the official outlook for it is on the ledger."""
    sel = selection.read() or {}; official = sel.get("official"); led = records.read(sources.FORECAST_LEDGER); outs = records.read(sources.FORECAST_OUTCOMES)
    due = None
    if os.path.exists(opscfg.OPS_DB_PATH):
        conn = store.connect(opscfg.OPS_DB_PATH)
        try:
            frame = bt.prepare(conn, config.PRIMARY_SERIES, bt.load_histories(conn)); due = frame["target_month"].max()[:7] if len(frame) else None
        finally: conn.close()
    mine = [r for r in led if r["series"] == config.PRIMARY_SERIES and r["forecaster_id"] == official]
    on_record = sorted({r["target_period"] for r in mine}); last = max(mine, key=lambda r: (r["target_period"], r["seq"])) if mine else None
    return {"official": official, "month_due": due, "on_record": bool(due) and due in on_record, "months_on_record": on_record, "last": last, "forecasts_issued": len(led), "outcomes_recorded": len(outs),
            "official_outcomes": [o for o in outs if any(o["forecast_id"] == r["forecast_id"] for r in mine)]}


def weekly_state():
    d = os.path.join(sources.OPS_DIR, "weekly"); led = records.read(os.path.join(d, "forecast_ledger.jsonl")); outs = records.read(os.path.join(d, "forecast_outcomes.jsonl"))
    return {"issued": len(led), "outcomes": len(outs), "last": led[-1] if led else None}


def build(cadence, now=None):
    now = now or registry.now_utc(); reg = registry.build(now); m = monthly_state(); w = weekly_state(); runs = records.read(os.path.join(sources.OPS_DIR, "production_runs.jsonl")); s = reg["summary"]
    sched = sum(1 for r in runs if r.get("trigger") == "schedule"); last = runs[-1] if runs else None
    L = [f"# AirPulse operations report ({cadence})", "", f"Generated {reg['generated_at']} from the run records, the ledgers and the clock. Do not edit: the next run overwrites it.", "",
         "## Pipeline runs", "",
         f"- Runs on record: {len(runs)}; started by a scheduler: {sched}; started by hand: {len(runs) - sched}.",
         f"- Last run: {last['started_at']}, started by {last['trigger']}, exit {last['exit']}, gate {'passed' if last['gate']['passed'] else 'FAILED: ' + '; '.join(last['gate']['critical'])}." if last else "- No production run is on record.",
         f"- Source fetches on record: {s['scheduled_runs']} by a scheduler, {s['manual_runs']} by hand.", "",
         "## Sources", "", "| Source | Status | Last success | Newest data | Stale after | Note |", "|---|---|---|---|---|---|"]
    for r in reg["sources"]:
        L.append(f"| {r['name']} | {r['status']} | {r['last_success'] or '-'} | {r['latest_data'] or '-'} | {r['stale_after'] or '-'} | {r['error'] or ''} |")
    L += ["", "## Monthly outlook", "",
          f"- Official forecaster by the selection rule: {m['official'] or 'none selected'}.",
          f"- Newest month due: {m['month_due'] or 'unknown (no operational store)'}; official outlook on the ledger for it: {'yes' if m['on_record'] else 'NO'}.",
          f"- Last official outlook issued: {m['last']['target_period']} ({m['last']['prediction']}), generated {m['last']['generated_at']}, {m['last']['timing']}, started by {m['last']['trigger']}." if m["last"] else "- No official outlook is on the ledger.",
          f"- Forecasts on the ledger (all series and forecasters): {m['forecasts_issued']}; outcomes recorded: {m['outcomes_recorded']}; outcomes of the official outlook: {len(m['official_outcomes'])}.", "",
          "## Weekly fuel-cost outlook", "",
          (f"- Outlooks issued: {w['issued']}; outcomes recorded: {w['outcomes']}. Last: release {w['last']['issued_at']} ({w['last']['predicted']}), generated {w['last']['generated_at']}, {w['last']['timing']}." if w["last"]
           else "- Not issued: the weekly fuel-cost outlook is not in the product (see `config/production_sources.yaml`, feature weekly_fuel_outlook)."), ""]
    return "\n".join(L) + "\n", m, reg


def main(argv):
    cadence = argv[argv.index("--cadence") + 1] if "--cadence" in argv else "daily"
    text, m, reg = build(cadence); os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "latest.md"), "w", encoding="utf-8", newline="\n") as f: f.write(text)
    print(f"operations report: {reg['summary']['production_healthy']} of {reg['summary']['production']} production sources healthy; month due {m['month_due']}; official outlook on record: {m['on_record']}")
    if cadence == "monthly":
        with open(os.path.join(OUT, f"{reg['generated_at'][:7]}.md"), "w", encoding="utf-8", newline="\n") as f: f.write(text)
        if not m["on_record"]: print(f"MONTHLY CHECK FAILED: no official outlook for {m['month_due']} is on the ledger"); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
