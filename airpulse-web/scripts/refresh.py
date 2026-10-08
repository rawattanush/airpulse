"""One command from the engine to the site, with a report of what actually changed:

    1 source health -> 2 ingestion of what is due -> 3 validation -> 4 features -> 5 forecast -> 6 registry and reports
    -> 7 export -> 8 web tests

Steps 1 to 6 are the engine's unattended production run (scripts/production_run.py in the engine repository): the same
command its scheduled workflow runs. Step 7 writes to a staging folder and replaces public/data only after its checks.
Running it twice on unchanged sources gives the same content: core.export.content_hash is equal.

    python scripts/refresh.py              # fetch the sources, issue what is due, export, report
    python scripts/refresh.py --offline    # no fetch: export what the engine already holds, report

It runs the engine's own commands in its repository (nothing is computed here), then the export, then prints for every
production source: SOURCE, LATEST DATA, LAST FETCH, EXPECTED UPDATE, STALE?; then FORECAST UPDATED?, EXPORT UPDATED? and
WARNINGS. A source that fails does not stop the report: the export still runs, so the site shows that source as failed or
stale instead of looking fresh. Exit code 0 = exported, nothing to warn about; 2 = exported with warnings (the pages show
the same state); 1 = the export itself failed and the site keeps its previous data.
A run started by a person is recorded by the engine as manual. Only a scheduler makes the data mode AUTOMATED."""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__)); WEB = os.path.dirname(HERE)
def _engine(web):
    """The engine repository: AIRPULSE_ROOT when set; the parent folder when this application lives inside the engine's repository
    (single repository); otherwise the folder AirPlus beside it (two folders side by side)."""
    if os.environ.get("AIRPULSE_ROOT"): return os.environ["AIRPULSE_ROOT"]
    parent = os.path.dirname(web)
    return parent if os.path.isdir(os.path.join(parent, "src", "ops")) else os.path.join(parent, "AirPlus")


ROOT = _engine(WEB)
DATA = os.path.join(WEB, "public", "data")
PY = sys.executable


def run(name, args, cwd):
    print(f"\n== {name}", flush=True)
    return subprocess.run([PY, *args], cwd=cwd).returncode


def load(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p): return None
    with open(p, encoding="utf-8") as f: return json.load(f)


def snapshot():
    """What the site holds: export time, the monthly outlook on record, the weekly outlook on record."""
    core, outlook, weekly = load("core.json"), load("outlook.json"), load("weekly.json")
    op = (outlook or {}).get("operational") or {}; cur = (weekly or {}).get("current") or {}
    return {"export": (core or {}).get("generated_at"), "monthly": (op.get("target_period"), op.get("generated_at")), "weekly": (cur.get("issued_at"), cur.get("generated_at"))}


def report(core, weekly, before, after, failures):
    """The table and the warnings. Returns the list of warnings."""
    rows = [("SOURCE", "LATEST DATA", "LAST FETCH", "EXPECTED UPDATE", "STALE?")]
    for s in core["registry"]["sources"]:                                # the engine's source registry: state from its run records, nothing typed
        if not s.get("production"): continue
        stale = "FAILED" if s["status"] == "FAILED" else "no" if s["status"] == "HEALTHY" else "YES" if s["status"] == "STALE" else s["status"]
        rows.append((s["name"][:58], str(s.get("latest_data") or "-")[:10], str(s.get("last_success") or "never")[:16].replace("T", " "),
                     f"{s['frequency'][:36]}; stale after {float(s['stale_after_days']):g} days", stale))
    w = [max(len(r[i]) for r in rows) for i in range(5)]
    print("\n== sources")
    for r in rows: print("  " + "  ".join(c.ljust(w[i]) for i, c in enumerate(r)))
    upd = lambda a, b: "yes" if a != b and b[0] else "no"
    print("\n== what this run changed")
    print(f"  MONTHLY FORECAST UPDATED?  {upd(before['monthly'], after['monthly'])}   on record: {after['monthly'][0] or 'none'}, generated {str(after['monthly'][1] or '-')[:16].replace('T', ' ')}")
    print(f"  WEEKLY FUEL UPDATED?       {upd(before['weekly'], after['weekly'])}   on record: release {after['weekly'][0] or 'none'}, generated {str(after['weekly'][1] or '-')[:16].replace('T', ' ')}")
    print(f"  EXPORT UPDATED?            {'yes' if after['export'] != before['export'] else 'no'}   {after['export']}; export {core['export']['version']} from engine {core['export']['engine_commit']}")
    print(f"  data runs through: index {core['through']['index']}; fuel {core['through']['fuel']}; weekly fuel release {core['through']['weekly_fuel_release']}")
    warn = [f"step failed: {f}" for f in failures]
    warn += [f"{s['name']}: {s['status']}" + (f" ({s['error']})" if s.get("error") else "") for s in core["registry"]["sources"] if s.get("production") and s["status"] != "HEALTHY"]
    if weekly.get("available") and (weekly.get("state") or {}).get("stale"): warn.append(f"weekly fuel outlook: no release for {weekly['state']['days_since_latest_release']} days; the outlook shown is for a week that has passed")
    if not core["state"]["records_intact"]: warn.append("run records: hash chain check failed")
    notes = []
    if core["state"]["data_mode"] == "SNAPSHOT": notes.append("data mode SNAPSHOT: this run was started by hand; nothing is fetched on a schedule")
    cur = weekly.get("current") or {}
    if cur.get("timing") == "LATE": notes.append(f"the weekly fuel outlook on record was generated {cur['days_after_issuance']} days after its release date")
    print("\n== warnings")
    for x in warn: print("  WARNING", x)
    if not warn: print("  none: every production source is healthy")
    for x in notes: print("  note   ", x)
    return warn


def main(argv):
    offline = "--offline" in argv; before = snapshot(); failures = []
    # 1-6: source health, what is due, ingestion, validation, forecasts, registry and run record: the engine's own production run
    code = run("engine: production run" + (" (no fetch)" if offline else ""), [os.path.join(ROOT, "scripts", "production_run.py")] + (["--offline"] if offline else []), ROOT)
    if code == 1:
        print("\nFAILED: the engine's validation gate did not pass. Nothing is exported; the site keeps its previous data."); return 1
    if code != 0: failures.append("engine run: a source failed, is degraded or stale (the registry names it; the pages show that state)")
    # 7: export, staged and checked before it replaces the published data
    if run("export to the customer application", [os.path.join(HERE, "export_data.py")], WEB) != 0:
        print("\nFAILED: the export did not complete. The site keeps its previous data; nothing fresh-looking was written."); return 1
    # 8: the exported data must satisfy the contract the pages rely on
    if "--no-tests" not in argv:
        print("\n== web tests", flush=True)
        if subprocess.run("npm test", cwd=WEB, shell=True).returncode != 0: failures.append("web tests failed on the exported data")
    warn = report(load("core.json"), load("weekly.json"), before, snapshot(), failures)
    return 2 if warn else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
