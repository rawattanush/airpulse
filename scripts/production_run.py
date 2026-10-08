"""The unattended production run: one command that a scheduler starts and nobody watches.

    source health -> what is due -> ingestion -> validation -> forecast -> source registry -> run record

    python scripts/production_run.py                 # fetch what is due, issue what is due, validate, write the registry
    python scripts/production_run.py --offline       # no network: rebuild from the files held, issue anything not yet issued
    python scripts/production_run.py --force bls     # treat a group as due (fuel, bls, news, weekly, aviation; several allowed)
    python scripts/production_run.py --plan          # print what is due and stop

PUBLICATION-AWARE. A scheduler may start this every day. It does not fetch everything every day: a source is asked when
  - it has never been fetched, or
  - its check interval (check_every_days in config/sources.yaml) has passed since the last attempt, or
  - its newest data are older than the interval at which the publisher normally adds data (expect_new_data_after_days)
    and the last attempt is at least 20 hours old: a monthly index is asked daily only from the day its next release is
    expected until it arrives, or
  - its last attempt failed (one bounded retry per run).

IDEMPOTENT. A run on unchanged sources changes no data file and issues no forecast: every fetch records UNCHANGED, the
ledgers are append-only and keyed, and the registry differs only in its clock-derived fields.

EACH LAYER IS A SEPARATE PROCESS with a time limit, so a layer that fails or hangs cannot stop the others or leave them
unrecorded. The aviation layer stays isolated from the validated system: it is only ever started as its own command.

THE GATE. After ingestion the append-only records, the declarations, the selection of the official forecaster and the
aviation quality report are checked. Exit codes:
    0  completed; every production source healthy
    2  completed; a source failed, is degraded or stale. The registry says which; the site shows that state.
    1  the gate failed. Nothing new may be published: the caller must keep the last published data.
Every run appends one record to operations/production_runs.jsonl (append-only, hash-chained)."""
import datetime, json, os, shutil, subprocess, sys, tempfile, time, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True
from src.observability import records, registry                     # noqa: E402
from src.ops import pipeline                                         # noqa: E402

PY = sys.executable
RUNS = os.path.join(ROOT, "operations", "production_runs.jsonl")
GROUP_OF = lambda r: {"core": ("news" if r["id"].startswith("news_") else "fuel" if r["id"].startswith("eia_") else "bls"), "weekly": "weekly", "aviation": "aviation"}.get(r["layer"])
EXPECT_NEW_DATA = {"fuel": 8, "bls": 28, "news": 2, "weekly": 8}     # days after the newest data at which the publisher normally has more; aviation feeds declare a check interval only
RETRY_AFTER_HOURS = 20
LIMITS = {"prepare": 1500, "core": 1500, "news": 2400, "weekly": 900, "aviation": 3000, "verify": 300}      # seconds; a step that exceeds its limit is stopped and recorded as failed


def step(name, args, limit, log):
    """Run one command of a layer. Never raises: the exit code, the time taken and the last lines of output are returned."""
    t0 = time.time()
    try:
        p = subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True, timeout=limit, encoding="utf-8", errors="replace"); code, out = p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as e: code, out = 124, f"stopped after {limit} s (time limit)\n" + str(e.stdout or "")[-400:]
    except Exception as e: code, out = 125, f"{type(e).__name__}: {e}"
    rec = {"step": name, "command": " ".join(args), "exit": code, "seconds": round(time.time() - t0, 1), "tail": out.strip().splitlines()[-6:]}
    log.append(rec); print(f"== {name}: exit {code} in {rec['seconds']} s", flush=True)
    for line in rec["tail"]: print("   ", line[:200], flush=True)
    return code


def due(reg, now, force=()):
    """For every fetched source: is it due, and why. Returns {group: {source id: reason}} with only the sources that are due."""
    out = {}
    for r in reg["sources"]:
        g = GROUP_OF(r) if r.get("layer") else None
        if g is None or r["status"] in ("DISABLED", "RESEARCH_ONLY"): continue
        last = registry.parse_time(r["last_attempt"]); since = None if last is None else (now - last).total_seconds() / 86400
        data = registry.parse_time(r["latest_data"]); age = None if data is None else (now - data).total_seconds() / 86400; expect = EXPECT_NEW_DATA.get(g)
        why = None
        if g in force: why = "forced"
        elif since is None: why = "never fetched"
        elif since >= float(r["check_every_days"]) - 0.1: why = f"check interval of {float(r['check_every_days']):g} days reached"
        elif r["last_result"] and r["status"] in ("FAILED", "DEGRADED") and since * 24 >= 1: why = "the last attempt did not succeed"
        elif expect and age is not None and age >= expect and since * 24 >= RETRY_AFTER_HOURS: why = f"newest data {age:.0f} days old; the publisher normally has more after {expect}"
        if why: out.setdefault(g, {})[r["id"]] = why
    return out


def gate(log):
    """Critical checks after ingestion. Returns the list of reasons for which nothing new may be published."""
    bad = []
    if step("gate: production policy consistent (licence classes, rights, features)", ["-m", "src.observability.policy", "--check"], LIMITS["verify"], log) != 0: bad.append("the production policy is inconsistent")
    if step("gate: declarations consistent with the pipeline", ["-m", "src.observability.registry", "--check"], LIMITS["verify"], log) != 0: bad.append("source declarations are inconsistent with the pipeline's source table")
    if step("gate: append-only records intact", ["-m", "src.ops.cli", "verify"], LIMITS["verify"], log) != 0: bad.append("a hash chain of the run log, the forecast ledger or the outcomes is broken")
    if step("gate: official forecaster singled out by the rule", ["-m", "src.ops.cli", "select"], LIMITS["verify"], log) != 0: bad.append("the selection rule does not single out one official forecaster")
    for name, rel in (("weekly", os.path.join("operations", "weekly")), ("production runs", "operations")):
        for f in (("ingestion_log.jsonl", "forecast_ledger.jsonl", "forecast_outcomes.jsonl") if name == "weekly" else ("production_runs.jsonl",)):
            p = os.path.join(ROOT, rel, f)
            if os.path.exists(p) and records.verify(p): bad.append(f"{name}: {f} is not an intact chain")
    return bad


def layer_notes():
    """Problems that withhold one layer without stopping the others (the export leaves that layer out and says why)."""
    notes = {}; p = os.path.join(ROOT, "operations", "aviation", "status.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f: q = json.load(f).get("quality") or {}
        if q.get("critical"): notes["aviation"] = q["critical"]
    return notes


NEW_DATA = ("UPDATED", "NEW", "REVISED", "OK")          # results of a fetch that brought data not held before


def ledgers():
    """How many forecasts are on the two ledgers."""
    return sum(len(records.read(os.path.join(ROOT, "operations", *p))) for p in (("forecast_ledger.jsonl",), ("weekly", "forecast_ledger.jsonl")))


def attempts(since):
    """What the layers recorded since `since` (the start of this run), from their own run logs: sources asked, answered, failed, and whether new data arrived."""
    layers, decl = registry.declared(); known = {d["id"] for d in decl}; asked, good, bad, new = set(), set(), set(), False
    for layer in layers.values():
        for r in records.read(os.path.join(ROOT, layer["log"].replace("/", os.sep))):
            t = registry.parse_time(r.get(layer["time"]) or ""); recorded = registry.parse_time(r.get("recorded_at") or "")
            if r.get("source") not in known or t is None or (recorded or t) < since or r.get("result") == "SEEDED": continue
            asked.add(r["source"]); ok = r.get("result") in layer["success"]
            (good if ok else bad).add(r["source"]); new = new or (ok and r.get("result") in NEW_DATA)
    return sorted(asked), sorted(good - bad), sorted(bad), new


def main(argv):
    offline = "--offline" in argv; force = tuple(a for a in argv[argv.index("--force") + 1:] if not a.startswith("--")) if "--force" in argv else ()
    now = registry.now_utc(); started = now.strftime("%Y-%m-%dT%H:%M:%SZ"); log = []; trigger = pipeline.detect_trigger()
    run_id = now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]; before = ledgers() if os.path.isdir(os.path.join(ROOT, "operations")) else 0
    problems = registry.check_declarations()
    if problems:
        for p in problems: print("DECLARATION PROBLEM:", p)
        return 1
    reg0 = registry.build(now); plan = {} if offline else due(reg0, now, force)
    news_on = any(r["id"].startswith("news_") and r["status"] != "DISABLED" for r in reg0["sources"])
    print(f"production run {started}, started by: {trigger}" + ("; offline" if offline else ""))
    for g, why in sorted(plan.items()): print(f"  due: {g}: " + "; ".join(f"{k} ({v})" for k, v in sorted(why.items())))
    if not plan: print("  nothing is due to be fetched" if not offline else "  no fetch (offline)")
    if "--plan" in argv: return 0

    # 1. the benchmark store (the evaluation the official forecast rests on) is derived; build it when it is absent
    if not os.path.exists(os.path.join(ROOT, "data", "airpulse.sqlite")):
        step("prepare: benchmark store and walk-forward evaluation from the frozen snapshot", ["-c", "from src.dashboard import data as d; print('built' if d.ensure_store() else 'present')"], LIMITS["prepare"], log)
    step("prepare: operational files present", ["-m", "src.ops.cli", "init"], LIMITS["verify"], log)

    # 2. ingestion, validation, forecast: one process per layer
    core = [g for g in ("fuel", "bls") if g in plan]
    step("monthly outlook: " + ("refresh " + ", ".join(core) if core else "no fetch due") + "; rebuild, issue what is due, record outcomes", ["-m", "src.ops.cli", "run"] + (["--sources", *core] if core else ["--no-fetch"]), LIMITS["core"], log)
    if "news" in plan:
        snap = tempfile.mkdtemp(prefix="airpulse_archive_before_")       # outside the repository: the guard needs it only for this run
        step("event layer: snapshot of the archive", [os.path.join("scripts", "news_archive_guard.py"), "snapshot", snap], LIMITS["verify"], log)
        step("event layer: fetch new headlines, rebuild and export the event store", ["-m", "src.ops.cli", "run", "--sources", "news"], LIMITS["news"], log)
        step("event layer: nothing removed, nothing altered, no duplicate", [os.path.join("scripts", "news_archive_guard.py"), "check", snap], LIMITS["verify"], log)
        shutil.rmtree(snap, ignore_errors=True)
    elif news_on and not os.path.exists(os.path.join(ROOT, "data", "news.sqlite")):          # only where the headline sources are switched on and their archive is held
        step("event layer: rebuild the event store from the archive held", ["-m", "src.news.cli", "build"], LIMITS["news"], log)
    if any(r.get("layer") == "weekly" and r["status"] not in ("DISABLED", "RESEARCH_ONLY") for r in reg0["sources"]):      # the weekly fuel outlook is out of the product (CL-024): no weekly source is declared
        step("weekly fuel outlook: " + ("refresh, " if "weekly" in plan else "no fetch due; ") + "record outcomes, issue the newest once", ["-m", "src.v2.cli", "weekly-run"] + ([] if "weekly" in plan else ["--offline"]), LIMITS["weekly"], log)
    av = sorted(plan.get("aviation", {}))
    step("air traffic: " + ("refresh " + ", ".join(av) if av else "no fetch due") + "; aggregates, quality report", ["-m", "src.aviation.cli", "refresh"] + (["--sources", *av] if av else ["--offline"]), LIMITS["aviation"], log)

    # 3. the gate, the registry, the record
    critical = gate(log); notes = layer_notes(); reg = registry.build(); registry.write(reg)
    s = reg["summary"]; unhealthy = [r for r in reg["sources"] if r["production"] and r["status"] != "HEALTHY"]; failed_steps = [x["step"] for x in log if x["exit"] not in (0, 2) and not x["step"].startswith("gate")]
    code = 1 if critical else 2 if (unhealthy or failed_steps or notes) else 0
    asked, good, bad, new_data = attempts(now.replace(microsecond=0)); issued = ledgers() - before
    errors = [f"gate: {c}" for c in critical] + [f"step failed: {x}" for x in failed_steps] + [f"{r['id']}: {r['status']}: {r['error']}" for r in unhealthy] + [f"{k} withheld" for k in notes]
    rec = records.append(RUNS, {"run_id": run_id, "status": "FAILED" if critical else "DEGRADED" if code == 2 else "OK", "sources_attempted": asked, "sources_succeeded": good, "sources_failed": bad,
                                "data_changed": bool(new_data or issued), "forecast_issued": issued, "errors": errors,
                                # publication is another job's record: the publish workflow of the customer application exports, tests, builds and deploys, and writes what started it into the export
                                "export_published": None, "build_status": None, "deployment_status": None, "publication_recorded_in": "core.publish of the exported data (customer application)",
                                "started_at": started, "finished_at": registry.now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"), "trigger": trigger, "workflow_run": pipeline.workflow_run(), "offline": offline, "forced": list(force),
                                "due": plan, "steps": [{k: x[k] for k in ("step", "exit", "seconds")} for x in log], "gate": {"passed": not critical, "critical": critical}, "layers_withheld": notes,
                                "registry": {k: s[k] for k in ("sources", *registry.STATUSES, "production", "production_healthy", "scheduled_runs")},
                                "not_healthy": [{"id": r["id"], "status": r["status"], "error": r["error"]} for r in reg["sources"] if r["status"] in ("STALE", "DEGRADED", "FAILED")], "exit": code})
    print(f"== run {run_id}: sources asked {len(asked)}, answered {len(good)}, failed {len(bad)}; new data: {bool(new_data or issued)}; forecasts issued: {issued}")
    print(f"\n== result: exit {code}; production sources healthy {s['production_healthy']} of {s['production']}; gate {'PASSED' if not critical else 'FAILED: ' + '; '.join(critical)}; run record {rec['seq']}")
    for r in rec["not_healthy"]: print(f"   {r['status']:9} {r['id']}: {r['error'][:140]}")
    for k, v in notes.items(): print(f"   WITHHELD  {k}: {'; '.join(str(x) for x in v)[:160]}")
    for x in failed_steps: print(f"   STEP FAILED  {x}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
