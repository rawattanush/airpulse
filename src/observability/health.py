"""Health and data mode of every source, derived from the ingestion run log and the clock. Nothing is hard-coded:
the same log with a later clock gives a staler answer.

Health of a pipeline source
  NOT CONFIGURED   no run of this source is recorded
  FAILED           the most recent attempt failed
  STALE            the last successful run is older than check_days x grace
  HEALTHY          the last successful run is recent enough
Research-only and unconnected sources (from research/data_pipeline_sources.csv) are reported as RESEARCH ONLY or
NOT CONNECTED; they have no runs.

Data mode of a pipeline source
  SNAPSHOT    its data come from the seeded snapshot or from runs started by hand
  AUTOMATED   the most recent successful run was started by a scheduler and is not stale
  LIVE        AUTOMATED, and the source is checked at least hourly, and the last success is under an hour old.
              No AirPulse source is scheduled more often than daily, so this state cannot be reached today.
Other labels used by the dashboard (set by what a thing is, not by a clock): HISTORICAL for the validated backtest,
EXPERIMENTAL for the event layer, RESEARCH for sources outside the pipeline."""
import csv, datetime, os
from src.observability import records, sources

SUCCESS = ("UPDATED", "UNCHANGED", "SEEDED")
SCHEDULED = ("schedule",)


def _ts(s):
    return datetime.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def source_health(runs, source_id, now=None):
    """One row of the data-health table for a pipeline source. `runs`: records of the ingestion log (any order)."""
    now = now or now_utc(); cfg = sources.SOURCES[source_id]
    mine = sorted((r for r in runs if r.get("source") == source_id), key=lambda r: r["retrieved_at"])
    ok = [r for r in mine if r["result"] in SUCCESS]; last, last_ok = (mine[-1] if mine else None), (ok[-1] if ok else None)
    fetched = [r for r in ok if r["result"] != "SEEDED"]                     # a seed is a copy of the frozen snapshot, not a fetch
    limit = cfg["check_days"] * cfg["grace"]
    age = (now - _ts(last_ok["retrieved_at"])).total_seconds() / 86400 if last_ok else None
    if not mine: status, reason = "NOT CONFIGURED", "no run recorded for this source"
    elif last["result"] not in SUCCESS: status, reason = "FAILED", last.get("error") or "the last attempt failed"
    elif age > limit: status, reason = "STALE", f"last successful run {age:.1f} days ago; expected at least every {cfg['check_days']} days (limit {limit:.0f})"
    else: status, reason = "HEALTHY", ""
    sched = [r for r in fetched if r.get("trigger") in SCHEDULED]
    if status == "HEALTHY" and fetched and fetched[-1].get("trigger") in SCHEDULED:
        mode = "LIVE" if (cfg["check_days"] * 24 <= 1 and age * 24 < 1) else "AUTOMATED"
    else: mode = "SNAPSHOT"
    obs = last_ok.get("latest_observation") if last_ok else None
    return {"source": source_id, "name": cfg["name"], "group": cfg["group"], "status": status, "data_mode": mode, "failure_reason": reason,
            "last_successful_fetch": last_ok["retrieved_at"] if last_ok else None, "last_attempted_fetch": last["retrieved_at"] if last else None,
            "last_result": last["result"] if last else None, "last_trigger": last.get("trigger") if last else None,
            "expected_cadence_days": cfg["cadence_days"], "check_every_days": cfg["check_days"], "age_days": None if age is None else round(age, 2),
            "latest_observation": obs, "record_count": last_ok.get("record_count") if last_ok else None, "checksum": last_ok.get("checksum") if last_ok else None,
            "validation": last_ok.get("validation") if last_ok else None, "http_status": last.get("http_status") if last else None,
            "last_workflow_run": (last.get("workflow_run") or {}).get("url") if last else None,
            "scheduled_runs": len(sched), "manual_runs": len([r for r in mine if r.get("trigger") not in SCHEDULED and r["result"] != "SEEDED"]),
            "production": cfg["production"]}


def all_health(log_path=None, now=None):
    runs = records.read(log_path or sources.INGESTION_LOG)
    return [source_health(runs, s, now) for s in sources.SOURCES]


def research_sources(path=None):
    """Sources outside the pipeline, from the audit registry: RESEARCH ONLY or NOT CONNECTED, with the registry's own evidence."""
    path = path or sources.RESEARCH_REGISTRY; out = []
    if not os.path.exists(path): return out
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            ps = r["production_status"].lower()
            if ps.startswith("production") or ps.startswith("experimental layer"): continue          # pipeline sources and the dashboard row are not research sources
            status = "NOT CONNECTED" if "not connected" in ps else "RESEARCH ONLY"
            out.append({"source": r["source"], "status": status, "data_mode": "RESEARCH", "data_type": r["data_type"], "last_evidence": r["last_observed_update"], "notes": r["notes"], "evidence_file": r["evidence_file"]})
    return out


def overall_mode(health_rows, groups=("fuel", "bls")):
    """Data mode of the forecast inputs as a whole: the weakest mode among the production sources."""
    order = {"SNAPSHOT": 0, "AUTOMATED": 1, "LIVE": 2}
    modes = [h["data_mode"] for h in health_rows if h["group"] in groups]
    return min(modes, key=lambda m: order[m]) if modes else "SNAPSHOT"
