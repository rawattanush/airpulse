"""The public product (change record CL-019): only what passes the production gate may be published.

Policy, refusals, the evidenced validation events of the anomaly reading, the run record, the documents, and the
anti-hardcoding checks: values regenerate from the files held, a changed source changes what follows from it, and an
observation dated after an issuance date changes no forecast of that date. No network; temporary folders only."""
import csv, hashlib, importlib.util, json, os, re, shutil
import pandas as pd, pytest
from src import config
from src.api import backtest as bt
from src.aviation import config as avcfg
from src.database import store
from src.ingestion.build import build_store
from src.observability import policy, records, registry, sources
from src.ops import adapters, bls, config as opscfg, selection

ROOT = config.ROOT
P = lambda *a: os.path.join(ROOT, *a)


def _script(name):
    spec = importlib.util.spec_from_file_location(name, P("scripts", f"{name}.py")); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def test_PBT01_every_source_has_a_licence_class_with_its_evidence_and_the_policy_is_consistent():
    assert policy.check() == []
    pol = policy.load(); decl = {d["id"] for d in registry.declared()[1]}
    assert set(pol["sources"]) == decl                                                                                   # every declared source is classed, and nothing else
    for i, s in pol["sources"].items():
        assert all(k in s for k in policy.FIELDS), i
        assert s["license_class"] in policy.CLASSES and s["production_status"] in policy.SOURCE_STATUS, i
        assert len(s["evidence"]) > 40 and re.match(r"2026-\d\d-\d\d$", s["evidence_date"]), i                           # a class without the sentence it rests on is not a class
        if s["production_status"] == "PRODUCTION": assert s["attribution"] and s["evidence_url"].startswith("https://"), i
    assert re.match(r"\d{4}-\d\d-\d\d$", pol["audited"])


def test_PBT02_an_unknown_or_restricted_source_is_refused_whatever_else_is_true():
    ok = {"license_class": "COMMERCIAL-SAFE-WITH-ATTRIBUTION", "commercial_allowed": True, "public_display_allowed": True, "derived_data_allowed": True, "enabled": True, "production_status": "PRODUCTION"}
    assert policy.refusal(ok) is None and policy.refusal(None) == "not in the production policy"
    for k in ("UNKNOWN", "NON-COMMERCIAL", "RESEARCH-ONLY", "LICENSE-REQUIRED", "BLOCKED", None, "something else"):
        assert "licence class" in policy.refusal({**ok, "license_class": k})                                             # unknown is a refusal, never a pass
    for k in ("commercial_allowed", "public_display_allowed", "derived_data_allowed", "enabled"):
        assert policy.refusal({**ok, k: False}) and policy.refusal({**ok, k: None}) and policy.refusal({**ok, k: "yes"})   # only an explicit true allows
    for k in ("RESEARCH", "DISABLED", "BLOCKED"): assert "production status" in policy.refusal({**ok, "production_status": k})
    pol = policy.load(); pub = set(policy.publishable_sources(pol))
    assert pub and all(policy.refusal(pol["sources"][i]) is None for i in pub)
    refused = {i: policy.refusal(s) for i, s in pol["sources"].items() if i not in pub}
    assert all(refused.values()) and any("UNKNOWN" in v for v in refused.values()) and any("NON-COMMERCIAL" in v for v in refused.values())


def test_PBT03_a_feature_is_public_only_when_it_is_production_ready_and_every_source_of_it_may_be_published():
    pol = policy.load(); pub = policy.public_features(pol); ok = set(policy.publishable_sources(pol))
    assert pub and all(pol["features"][i]["status"] == "PRODUCTION READY" and set(pol["features"][i].get("sources") or []) <= ok for i in pub)
    for i, f in pol["features"].items():
        assert f["status"] in policy.FEATURE_STATUS, i                                                                    # five classes; none of them is 'experimental but shown'
        if i in pub: assert f["validation"] and f["wording"] and f["pages"], i
        else: assert f["reason"] and policy.feature_refusal(i, pol), i
    bad = dict(pol["features"][pub[0]]); src = (bad.get("sources") or [None])[0]
    if src:
        broken = {"audited": pol["audited"], "sources": {**pol["sources"], src: {**pol["sources"][src], "license_class": "UNKNOWN"}}, "features": pol["features"]}
        assert pub[0] not in policy.public_features(broken) and "UNKNOWN" in policy.feature_refusal(pub[0], broken)          # a feature falls out of the product when the terms of its source are no longer known
    assert policy.public_status({"status": "DISABLED"}) == "UNAVAILABLE" and policy.public_status({"status": "FAILED", "last_success": None}) == "UNAVAILABLE"
    assert policy.public_status({"status": "FAILED", "last_success": "2026-10-01T00:00:00Z"}) == "FAILED" and policy.public_status({"status": "HEALTHY", "last_success": "x"}) == "HEALTHY"
    assert set(policy.PUBLIC_STATUS) == {"HEALTHY", "DEGRADED", "STALE", "FAILED", "UNAVAILABLE"}
    src_text = open(P("src", "observability", "policy.py"), encoding="utf-8").read()
    assert not re.search(r"from src\.(ops|aviation|v2|v3|news)|eia_|bls_|hkia|usdot", src_text)                         # the policy module names no source and imports no layer


@pytest.mark.research_record
def test_PBT04_the_validation_events_of_the_anomaly_reading_are_evidenced_and_the_unchanged_rule_decides():
    with open(P("data", "reference", "disruption_events.csv"), newline="", encoding="utf-8") as f: ev = list(csv.DictReader(f))
    listed = [(n, k, tuple(c), a, b) for n, k, c, a, b in avcfg.KNOWN_DISRUPTIONS]
    assert [(e["event"], e["class"], tuple(e["airports"].split(";")), e["start"], e["end"]) for e in ev] == listed          # the list of protocol 4.0, in its order: no event added, replaced or reclassified
    for e in ev:
        assert e["status"] in ("VERIFIED", "REMOVED") and e["verified_on"]
        if e["status"] == "VERIFIED": assert e["url"].startswith("https://") and e["second_source_url"].startswith("https://") and len(e["evidence"]) > 60 and e["source"], e["event"]
    assert avcfg.STATUS_RULE["min_recall_closure"] == 0.8 and avcfg.STATUS_RULE["max_false_alarm_share"] == 0.05           # the rule was not moved
    assert [n for n, _ in avcfg.BANDS] == ["NORMAL", "ELEVATED", "UNUSUAL", "EXTREME"] and avcfg.BASELINE["same_weekday_weeks"] == 8 and avcfg.BASELINE["min_history"] == 6
    av = json.load(open(P("evaluation", "aviation", "anomaly_validation.json"), encoding="utf-8"))
    met = av["closure"]["detected"] / av["closure"]["testable"] >= av["rule"]["min_recall_closure"] and av["quiet_days"]["false_alarm_share_low"] <= av["rule"]["max_false_alarm_share"]
    pol = policy.load(); f = pol["features"]["airport_anomaly_reading"]
    assert (f["status"] == "PRODUCTION READY") == met or f["status"] != "PRODUCTION READY"                                 # it is never in the product without meeting its rule
    if not met: assert "airport_anomaly_reading" not in policy.public_features(pol) and av["status"] != "VALIDATED"


def test_PBT05_every_run_leaves_a_record_with_what_was_asked_what_answered_and_what_changed():
    pr = _script("production_run"); runs = records.read(pr.RUNS); assert runs and not records.verify(pr.RUNS)
    new = [r for r in runs if "run_id" in r]; assert new, "no run with the record of CL-019 is on file"
    decl = {d["id"] for d in registry.declared()[1]}
    for r in new:
        assert re.match(r"\d{8}T\d{6}Z-[0-9a-f]{8}$", r["run_id"]) and r["status"] in ("OK", "DEGRADED", "FAILED") and (r["status"] == "FAILED") == (not r["gate"]["passed"])
        assert set(r["sources_attempted"]) <= decl and set(r["sources_succeeded"]) | set(r["sources_failed"]) == set(r["sources_attempted"]) and not set(r["sources_succeeded"]) & set(r["sources_failed"])
        assert isinstance(r["data_changed"], bool) and isinstance(r["forecast_issued"], int) and isinstance(r["errors"], list) and r["started_at"] <= r["finished_at"]
        assert r["export_published"] is None and r["deployment_status"] is None and r["publication_recorded_in"]              # this job does not claim a publication it did not make
        if r["status"] == "OK": assert r["errors"] == [] and r["sources_failed"] == []
    assert len({r["run_id"] for r in new}) == len(new)
    asked, good, bad, changed = pr.attempts(registry.parse_time("2999-01-01"))
    assert (asked, good, bad, changed) == ([], [], [], False)                                                              # nothing is reported for a run in which nothing was asked


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """A copy of the operational input files and the store built from it; then the same after a source published more."""
    d = tmp_path_factory.mktemp("world"); cur = str(d / "current"); shutil.copytree(opscfg.CURRENT_DIR, cur)
    def built(name):
        db = str(d / name); build_store(db, cur); conn = store.connect(db); hist = bt.load_histories(conn); frame = bt.prepare(conn, config.PRIMARY_SERIES, hist)
        fuel = pd.read_sql_query("SELECT obs_date, value FROM observations WHERE series_id = '" + config.JET_FUEL + "' AND value IS NOT NULL ORDER BY obs_date", conn); conn.close()
        return frame, fuel
    before = built("before.sqlite")
    def rewrite(file, body):
        with open(os.path.join(cur, file), "wb") as f: f.write(body)
        m = json.load(open(os.path.join(cur, file + ".meta.json"), encoding="utf-8")); m["sha256"] = hashlib.sha256(body).hexdigest(); m["retrieved_at"] = "2026-11-20T06:00:00Z"
        json.dump(m, open(os.path.join(cur, file + ".meta.json"), "w", encoding="utf-8"))
    fuel_file = sources.SOURCES["eia_jet_fuel"]["file"]; raw = open(os.path.join(cur, fuel_file), "rb").read()
    last = adapters._fuel_frame(raw).dropna(subset=["v"]).iloc[-1]; new_day = (last["d"] + pd.Timedelta(days=1)).strftime("%Y-%m-%d"); new_price = round(float(last["v"]) * 1.5, 3)
    rewrite(fuel_file, raw.rstrip(b"\r\n") + f"\n{new_day},{new_price}\n".encode())                                         # the fuel source published one more day
    cfg = sources.SOURCES[f"bls_{config.PRIMARY_SERIES}"]; text = open(os.path.join(cur, cfg["file"]), encoding="utf-8").read(); lines = text.strip().splitlines()
    rows = {ln.split(",", 1)[0]: [v for v in ln.split(",")[1:] if v != ""] for ln in lines[1:]}; newest = max(rows); nxt = (pd.Timestamp(newest) + pd.offsets.MonthBegin(1)).strftime("%Y-%m-%d")
    held = lines[0].split(",")[-1].rsplit("_", 1)[1]; vintage = (pd.Timestamp(held) + pd.Timedelta(days=30)).strftime("%Y-%m-%d"); value = round(float(rows[newest][-1]) * 1.2, 1)
    series_, dates_, cols_ = adapters._columns(text); added = dict(cols_[-1]); added[nxt] = value
    rewrite(cfg["file"], bls.matrix_text(series_, dates_ + [vintage], cols_ + [added]).encode())                                    # the index source published a release with one more month
    after = built("after.sqlite")
    return {"before": before, "after": after, "new_day": new_day, "new_price": new_price, "vintage": vintage, "new_month": nxt, "new_value": value}


def test_PBT06_values_regenerate_from_the_files_held_and_a_changed_source_changes_what_follows_from_it(world):
    (f0, fuel0), (f1, fuel1) = world["before"], world["after"]
    assert len(f0) > 150 and len(fuel0) > 8000                                                                              # built from nothing but the files: the values are there
    assert len(fuel1) == len(fuel0) + 1 and fuel1.iloc[-1]["obs_date"][:10] == world["new_day"] and abs(fuel1.iloc[-1]["value"] - world["new_price"]) < 1e-9   # the new price is in the store: nothing is typed in between
    assert f1["target_month"].max() > f0["target_month"].max() and len(f1) == len(f0) + 1                                    # a new release makes a new month due
    official = next(F for F in bt.FORECASTERS if F.forecaster_id == selection.select()["official"])
    o = bt.forecast_origin(f1, len(f1) - 1, official)
    assert o["status"] == "OK" and abs(sum(o["proba"]) - 1) < 1e-9 and o["predicted"] in config.CLASSES and f1.iloc[-1]["issued_at"] == world["vintage"]   # and the outlook for it is generated, with its issuance date, from the data
    known0 = f0.set_index("target_month")["rt_label"].dropna(); known1 = f1.set_index("target_month")["rt_label"].dropna()
    assert len(known1) == len(known0) + 1                                                                                   # the month just published has its outcome; no page needs to be told


def test_PBT07_an_observation_published_later_changes_no_forecast_issued_before_it(world):
    (f0, _), (f1, _) = world["before"], world["after"]; official = next(F for F in bt.FORECASTERS if F.forecaster_id == selection.select()["official"])
    a, b = f0.set_index("target_month"), f1.set_index("target_month"); cols = ["issued_at", "max_info"] + list(bt.FEATURES)
    for t in list(a.index[-24:]):                                                                                           # every month that was already due: same issuance, same information date, same inputs
        for c in cols:
            x, y = a.at[t, c], b.at[t, c]
            assert (pd.isna(x) and pd.isna(y)) or x == y, (t, c)
    for k in (len(f0) - 1, len(f0) - 6, len(f0) - 18):
        o0, o1 = bt.forecast_origin(f0, k, official), bt.forecast_origin(f1, k, official)
        assert o0["predicted"] == o1["predicted"] and list(o0["proba"]) == list(o1["proba"]) and o0["n_train"] == o1["n_train"]   # the forecast of a past date is the same, whatever was published afterwards
    assert all(d > f0["issued_at"].max() for d in (world["vintage"],))                                                      # the injected release is later than every issuance date it could have leaked into


@pytest.mark.research_record
def test_PBT08_the_documents_of_the_final_audit_follow_the_policy_and_the_records():
    pol = policy.load(); gap = open(P("evaluation", "FINAL_PRODUCTION_GAP_AUDIT.md"), encoding="utf-8").read(); audit = open(P("evaluation", "FINAL_PRODUCTION_AUDIT.md"), encoding="utf-8").read()
    report = open(P("execution", "FINAL_PRODUCTION_READINESS_REPORT.md"), encoding="utf-8").read()
    for f in pol["features"].values(): assert f"| {f['name']} | {f['kind']} | {f['status']} |" in gap, f["name"]            # every feature, with one of the five classes
    for letter in "ABCDEFGHIJKLMNOPQR": assert re.search(rf"^## {letter}\. ", audit, re.M), letter
    for name in (pol["features"][i]["name"] for i in policy.public_features(pol)): assert f"| {name} |" in audit and "| PRODUCTION READY |" in audit
    for head in ("PRODUCTION STATUS:", "PUBLIC FEATURES:", "REMOVED FEATURES:", "BLOCKED FEATURES:", "LICENSE BLOCKERS:", "AUTOMATION STATUS:", "HARD-CODE STATUS:", "DATA LINEAGE STATUS:", "SCHEDULER STATUS:", "DEPLOYMENT STATUS:"):
        assert len(re.findall(rf"^{head}", report, re.M)) == 1, head
    assert report.index("PRODUCTION STATUS:") < report.index("## 1. Architecture") and "### CLAUDE MUST DO" in report and "### I MUST DO" in report
    runs = records.read(P("operations", "production_runs.jsonl"))
    if not any(r.get("trigger") == "schedule" for r in runs): assert "PRODUCTION STATUS: NOT READY\n" in report               # tests passing never make it ready
    with open(P("evaluation", "UI_DATA_LINEAGE.csv"), newline="", encoding="utf-8") as f: lin = list(csv.DictReader(f))
    need = {"ui_value", "page", "public_artifact", "exported_field", "generator", "feature_or_model", "source_id", "source_timestamp", "ingestion_timestamp", "source_version_sha256", "software_version_code_hash"}
    assert lin and need <= set(lin[0]) and all(r["exported_field"] and r["generator"] for r in lin)
    ok = set(policy.publishable_sources(pol)); used = {r["source_id"] for r in lin if not r["source_id"].startswith("none")}
    assert used and used <= ok                                                                                              # no customer-facing value rests on a source that may not be published
    assert all(r["ingestion_timestamp"] and r["source_version_sha256"] for r in lin if r["source_id"] in ok)
    for doc in (gap, audit, report): assert "Do not edit by hand" in doc
