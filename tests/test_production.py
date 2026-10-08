"""Production pipeline (change record CL-018): source registry, unattended run, failure behaviour, selection of the official forecaster.

Every test works on temporary folders or reads the repository; none writes a run record of the repository and none uses the network.
A source failure is simulated by the function the adapter is given in place of its HTTP call."""
import datetime, gzip, hashlib, importlib.util, io, json, os, shutil, sys
import pytest, yaml
from src import config
from src.aviation import collector, operations
from src.observability import records, registry, sources
from src.ops import adapters, config as opscfg, pipeline, selection

ROOT = config.ROOT
UTC = datetime.timezone.utc
T = lambda s: datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _script(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", f"{name}.py")); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def _world(tmp_path, runs, **decl):
    """A registry world of one source 's' in one layer, with the given run records."""
    d = {"id": "s", "layer": "L", "name": "S", "url": "u", "type": "series", "frequency": "weekly", "check_every_days": 7, "stale_after_days": 14, "active": True, "production": True, "license": "x", "coverage": "x", "notes": "x", **decl}
    doc = {"version": 1, "layers": {"L": {"log": "operations/log.jsonl", "time": "at", "latest": ["latest"], "success": ["OK", "SEEDED"], "partial": ["PARTIAL"]}}, "sources": [d]}
    p = tmp_path / "sources.yaml"; p.write_text(yaml.safe_dump(doc), encoding="utf-8")
    log = tmp_path / "operations" / "log.jsonl"
    if log.exists(): log.unlink()
    for r in runs: records.append(str(log), {"source": "s", **r})
    return lambda now: registry.build(T(now), str(p), str(tmp_path))["sources"][0]


# ---------------------------------------------------------------------------------------------------------------- registry

def test_PRT01_declarations_hold_no_state_and_agree_with_the_pipeline():
    assert registry.check_declarations() == []
    layers, decl = registry.declared()
    assert {d["id"] for d in decl} >= set(sources.SOURCES) and len({d["id"] for d in decl}) == len(decl)
    for d in decl:
        assert not {"status", "last_success", "last_attempt", "latest_data", "error"} & set(d), d["id"]          # state is never declared: it is computed
        assert all(k in d for k in registry.REQUIRED), d["id"]
        if d.get("layer"): assert d["layer"] in layers and os.path.exists(os.path.join(ROOT, layers[d["layer"]]["log"]))
    assert any(not d["active"] for d in decl) and any(d["type"] == "research" for d in decl)


def test_PRT02_status_follows_the_records_and_the_clock(tmp_path):
    ok = {"at": "2026-10-01T06:00:00Z", "result": "OK", "latest": "2026-09-29", "trigger": "manual"}
    at = _world(tmp_path, [ok])
    assert at("2026-10-02T00:00:00Z")["status"] == "HEALTHY" and at("2026-10-02T00:00:00Z")["error"] == ""
    late = at("2026-10-20T00:00:00Z"); assert late["status"] == "STALE" and "not checked for" in late["error"]           # the same records, a later clock
    assert late["last_success"] == "2026-10-01T06:00:00Z" and late["latest_data"] == "2026-09-29"                        # what is held is still stated, with its age
    at = _world(tmp_path, [ok, {"at": "2026-10-03T06:00:00Z", "result": "FAILED", "error": "HTTP 503", "trigger": "manual"}])
    d = at("2026-10-04T00:00:00Z"); assert d["status"] == "DEGRADED" and "HTTP 503" in d["error"] and d["last_success"] == "2026-10-01T06:00:00Z" and d["last_attempt"] == "2026-10-03T06:00:00Z"
    f = at("2026-10-30T00:00:00Z"); assert f["status"] == "FAILED" and "last success" in f["error"]
    at = _world(tmp_path, [{"at": "2026-10-03T06:00:00Z", "result": "FAILED", "error": "timed out", "trigger": "manual"}])
    assert at("2026-10-03T07:00:00Z")["status"] == "FAILED" and at("2026-10-03T07:00:00Z")["latest_data"] is None       # never fetched: nothing is shown as held
    at = _world(tmp_path, [])
    assert at("2026-10-03T07:00:00Z")["status"] == "FAILED" and "no run is recorded" in at("2026-10-03T07:00:00Z")["error"]
    at = _world(tmp_path, [ok, {"at": "2026-10-03T06:00:00Z", "result": "PARTIAL", "latest": "2026-10-02", "trigger": "manual"}])
    assert at("2026-10-03T07:00:00Z")["status"] == "DEGRADED" and "partial" in at("2026-10-03T07:00:00Z")["error"]
    at = _world(tmp_path, [{**ok, "at": "2026-10-04T06:00:00Z", "latest": "2026-06"}], data_stale_after_days=60)
    s = at("2026-10-05T00:00:00Z"); assert s["status"] == "STALE" and "newest data" in s["error"]                        # reached, but the publisher has nothing newer
    assert _world(tmp_path, [ok], active=False)("2026-10-02T00:00:00Z")["status"] == "DISABLED"
    assert _world(tmp_path, [ok], type="research")("2026-10-02T00:00:00Z")["status"] == "RESEARCH_ONLY"


def test_PRT03_nothing_is_called_automated_without_a_scheduled_run(tmp_path):
    at = _world(tmp_path, [{"at": "2026-10-01T06:00:00Z", "result": "OK", "latest": "2026-09-29", "trigger": "manual"}])
    r = at("2026-10-02T00:00:00Z"); assert r["data_mode"] == "SNAPSHOT" and r["scheduled_runs"] == 0 and r["manual_runs"] == 1
    at = _world(tmp_path, [{"at": "2026-10-01T06:00:00Z", "result": "SEEDED", "latest": "2026-09-29", "trigger": "seed"}])
    r = at("2026-10-02T00:00:00Z"); assert r["data_mode"] == "SNAPSHOT" and r["scheduled_runs"] == 0 and r["manual_runs"] == 0      # a copy of a snapshot is not a fetch
    at = _world(tmp_path, [{"at": "2026-10-01T06:00:00Z", "result": "OK", "latest": "2026-09-29", "trigger": "schedule"}])
    assert at("2026-10-02T00:00:00Z")["data_mode"] == "AUTOMATED" and at("2026-10-30T00:00:00Z")["data_mode"] == "SNAPSHOT"            # a scheduled fetch that has gone stale is not automated any more
    real = registry.build()
    if real["summary"]["scheduled_runs"] == 0: assert all(r["data_mode"] in (None, "SNAPSHOT") for r in real["sources"])
    assert all(r["status"] in registry.STATUSES for r in real["sources"]) and sum(real["summary"][s] for s in registry.STATUSES) == len(real["sources"])
    assert all(real["logs_intact"].values())


def test_PRT04_the_registry_file_is_generated_and_reproducible(tmp_path):
    now = T("2026-10-05T12:00:00Z"); a, b = registry.build(now), registry.build(now)
    assert a == b                                                                                                         # the same records and the same clock: the same registry
    p = registry.write(a, str(tmp_path / "sources.yaml")); text = open(p, encoding="utf-8").read()
    assert text.startswith("# GENERATED") and "Do not edit" in text and registry.read(p) == a
    for k in ("id", "name", "url", "type", "frequency", "active", "license", "last_success", "last_attempt", "latest_data", "stale_after", "status", "error", "coverage", "notes"): assert k in a["sources"][0]
    assert registry.parse_time("2026-06") == datetime.datetime(2026, 6, 30, 23, 59, 59, tzinfo=UTC) and registry.parse_time("2026-10-04T23:59:59+08:00") == T("2026-10-04T15:59:59Z") and registry.parse_time("nonsense") is None


# ---------------------------------------------------------------------------------------------------------------- failure behaviour of the forecast inputs

def _held(tmp_path, sid="eia_jet_fuel"):
    """A held file of one source, taken from the benchmark snapshot (so the test does not depend on what later runs have fetched)."""
    cfg = sources.SOURCES[sid]; cur = tmp_path / "current"; cur.mkdir(exist_ok=True)
    for ext in ("", ".meta.json"): shutil.copyfile(os.path.join(config.SNAPSHOT_DIR, cfg["file"] + ext), cur / (cfg["file"] + ext))
    return cfg, str(cur), (cur / cfg["file"]).read_bytes()


def _spreadsheet(sid):
    """The publisher's spreadsheet the benchmark file of a fuel source was written from."""
    return open(os.path.join(config.SNAPSHOT_DIR, sources.SOURCES[sid]["file"][:-4] + ".xls"), "rb").read()


@pytest.mark.parametrize("answer, expect", [
    (adapters.FetchError("HTTP 503 from https://www.eia.gov/dnav/pet/hist_xls/x.xls", 503), "HTTP 503"),                  # source unavailable
    (adapters.FetchError("TimeoutError: timed out"), "timed out"),                                                         # timeout
    (adapters.FetchError("HTTP 429 from https://www.eia.gov/dnav/pet/hist_xls/x.xls", 429), "HTTP 429"),                  # rate limit, after the bounded attempts
    (b"<html><body>Service temporarily unavailable</body></html>", "cannot be parsed|validation failed"),                 # corrupted response
    ("OTHER SERIES", "cannot be parsed"),                                                                                  # a spreadsheet of another series under this address
    ("TRUNCATED", "fewer observations than held"),                                                                         # a response that lost days the file held
    (b"", "cannot be parsed|validation failed"),                                                                           # empty response
    ("FUTURE", "observation dated after the fetch"),                                                                       # a value dated after the clock of the fetch
])
def test_PRT05_a_failed_or_corrupt_answer_changes_nothing_and_invents_nothing(tmp_path, answer, expect):
    import re
    cfg, cur, before = _held(tmp_path); when = "2026-10-06T06:00:00Z"
    if answer == "TRUNCATED":                                                                                              # the file held has two days the publisher no longer serves
        before = before + b"2026-09-30,2.5\n2026-10-01,2.5\n"; open(os.path.join(cur, cfg["file"]), "wb").write(before)
        meta = json.load(open(os.path.join(cur, cfg["file"] + ".meta.json"))); meta["sha256"] = hashlib.sha256(before).hexdigest(); json.dump(meta, open(os.path.join(cur, cfg["file"] + ".meta.json"), "w"))
    if answer == "FUTURE": when = "2026-09-01T06:00:00Z"                                                                   # the spreadsheet runs to 2026-09-29: seen from 1 September its last days lie in the future
    def get(url):
        if isinstance(answer, Exception): raise answer
        return 200, _spreadsheet("eia_brent") if answer == "OTHER SERIES" else _spreadsheet("eia_jet_fuel") if answer in ("TRUNCATED", "FUTURE") else answer
    r = adapters.fetch_eia("eia_jet_fuel", cfg, current_dir=cur, raw_dir=str(tmp_path / "raw"), get=get, now=lambda: when)
    assert r["result"] == "FAILED" and re.search(expect, r["error"]) and r["latest_observation"] is None and r["new_records"] == 0     # no observation is reported for a failed fetch
    assert open(os.path.join(cur, cfg["file"]), "rb").read() == before and not os.path.exists(str(tmp_path / "raw"))                    # the file held is untouched and nothing was stored
    log = str(tmp_path / "operations" / "log.jsonl"); records.append(log, {**r, "trigger": "schedule"})
    doc = {"version": 1, "layers": {"core": {"log": "operations/log.jsonl", "time": "retrieved_at", "latest": ["latest_observation"], "success": ["UPDATED", "UNCHANGED", "SEEDED"], "partial": []}},
           "sources": [next(d for d in registry.declared()[1] if d["id"] == "eia_jet_fuel")]}
    (tmp_path / "s.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    e = registry.build(T("2026-10-06T07:00:00Z"), str(tmp_path / "s.yaml"), str(tmp_path))["sources"][0]
    assert e["status"] == "FAILED" and e["error"] and e["latest_data"] is None and e["data_mode"] == "SNAPSHOT"                         # the registry says failed; it does not say fresh


def test_PRT06_one_failed_source_does_not_stop_or_alter_the_others(tmp_path):
    log = str(tmp_path / "log.jsonl"); cur = tmp_path / "current"; cur.mkdir()
    for cfg in sources.SOURCES.values():
        if cfg["file"]:
            for ext in ("", ".meta.json"): shutil.copyfile(os.path.join(config.SNAPSHOT_DIR, cfg["file"] + ext), cur / (cfg["file"] + ext))
    good = _spreadsheet("eia_brent")
    def get(url):
        if "EER_EPJK_PF4_RGC_DPG" in url: raise adapters.FetchError("HTTP 500 from source", 500)
        return 200, good
    out = pipeline.refresh(("fuel",), trigger="schedule", log_path=log, eia_series={"current_dir": str(cur), "raw_dir": str(tmp_path / "raw"), "get": get})
    by = {r["source"]: r for r in out}
    assert by["eia_jet_fuel"]["result"] == "FAILED" and by["eia_brent"]["result"] == "UNCHANGED" and len(out) == 2 and not records.verify(log)                   # one record per source, whatever happened
    def boom(sid, cfg, **kw): raise RuntimeError("adapter bug")
    out = pipeline.refresh(("fuel",), trigger="schedule", log_path=log, adapters_map={"eia_series": boom})
    assert [r["result"] for r in out] == ["FAILED", "FAILED"] and all("adapter error" in r["error"] for r in out)                                                # even a bug in an adapter leaves a record
    cfg = sources.SOURCES["bls_IC1312"]; matrix = (cur / cfg["file"]).read_bytes()
    page = b'<a href="/news.release/archives/ximpim_01152031.htm">x</a>'                                                                                          # the source lists a release dated in the future
    r = adapters.fetch_bls("bls_IC1312", cfg, current_dir=str(cur), raw_dir=str(tmp_path / "raw"), get=lambda url: (200, page), post=lambda u, b: (200, b"{}"), now=lambda: "2026-10-06T06:00:00Z", sleep=lambda s: None)
    assert r["result"] == "FAILED" and "release dated after the fetch" in r["error"] and (cur / cfg["file"]).read_bytes() == matrix


# ---------------------------------------------------------------------------------------------------------------- air-traffic official files

EUR_HEAD = "FLT_DATE,APT_ICAO,FLT_DEP_1,FLT_ARR_1,FLT_TOT_1\n"


def _eur(days, year=2026, airports=("EDDF", "EGLL")):
    rows = [f"{year}-01-{d:02d}T00:00:00Z,{a},{100 + d},{90 + d},{190 + 2 * d}" for d in range(1, days + 1) for a in airports]
    return (EUR_HEAD + "\n".join(rows) + "\n").encode()


def _seed_eur(tmp_path, raw):
    d = tmp_path / "official" / "eurocontrol"; d.mkdir(parents=True); body = operations._gz(raw); p = d / "airport_traffic_2026.csv.gz"; p.write_bytes(body)
    (d / "airport_traffic_2026.csv.gz.meta.json").write_text(json.dumps({"sha256": hashlib.sha256(body).hexdigest(), "raw_sha256": hashlib.sha256(raw).hexdigest(), "retrieved_at": "2026-02-01T00:00:00Z"}), encoding="utf-8")
    return p


def test_PRT07_official_file_is_downloaded_only_when_the_publisher_changed_it(tmp_path):
    p = _seed_eur(tmp_path, _eur(10)); before = p.read_bytes(); asked = []
    def get(url): asked.append(url); return 200, _eur(20), {}
    old = lambda url: (200, {"Last-Modified": "Mon, 12 Jan 2026 06:00:00 GMT"})
    r = operations.refresh_eurocontrol(get=get, head=old, now="2026-02-10T06:00:00Z", out_dir=str(tmp_path), trigger="schedule", sleep=lambda s: None, years=[2026])
    assert r["result"] == "UNCHANGED" and asked == [] and p.read_bytes() == before and r["latest_observation"] == "2026-01-10"                 # not downloaded: the publisher's file is older than the one held
    new = lambda url: (200, {"Last-Modified": "Mon, 09 Feb 2026 06:00:00 GMT"})
    r = operations.refresh_eurocontrol(get=get, head=new, now="2026-02-10T06:00:00Z", out_dir=str(tmp_path), trigger="schedule", sleep=lambda s: None, years=[2026])
    assert r["result"] == "REVISED" and len(asked) == 1 and r["latest_observation"] == "2026-01-20" and r["rows"] == 40 and p.read_bytes() != before
    assert operations.loaders.verify_file(str(p))["retrieved_at"] == "2026-02-10T06:00:00Z" and len(operations.european_daily(str(tmp_path))) == 40
    r = operations.refresh_eurocontrol(get=get, head=lambda url: (200, {}), now="2026-02-11T06:00:00Z", out_dir=str(tmp_path), trigger="schedule", sleep=lambda s: None, years=[2026])
    assert r["result"] == "UNCHANGED" and len(asked) == 2                                                                                      # downloaded (no change time given) and found identical: no new file
    assert not records.verify(collector.log_path(str(tmp_path)))


@pytest.mark.parametrize("answer, result, why", [
    ((503, b"", {}), "FAILED", "HTTP 503"),                                                                               # unavailable
    ((429, b"", {"Retry-After": "1"}), "RATE_LIMITED", "429"),                                                            # rate limited
    ((200, b"<html>maintenance</html>", {}), "INVALID", "cannot be parsed"),                                              # corrupted
    ((200, _eur(3), {}), "INVALID", "fewer rows than held"),                                                              # truncated
    ((200, _eur(10).replace(b"2026-01-05", b"2031-01-05"), {}), "INVALID", "outside the year|future"),                    # impossible dates
    ((200, _eur(10) + b"2026-01-01T00:00:00Z,EDDF,5,5,10\n", {}), "INVALID", "listed twice"),                             # duplicate
    ((200, _eur(10).replace(b",EDDF,101,91,192", b",EDDF,101,91,999"), {}), "INVALID", "total differs"),                  # inconsistent counts
    (TimeoutError("timed out"), "FAILED", "TimeoutError"),                                                                # timeout
])
def test_PRT08_a_bad_official_file_is_refused_and_the_held_file_stays(tmp_path, answer, result, why):
    import re
    p = _seed_eur(tmp_path, _eur(10)); before = p.read_bytes()
    def get(url):
        if isinstance(answer, Exception): raise answer
        return answer
    r = operations.refresh_eurocontrol(get=get, head=lambda url: (200, {}), now="2026-02-10T06:00:00Z", out_dir=str(tmp_path), trigger="schedule", sleep=lambda s: None, years=[2026])
    assert r["result"] == result and re.search(why, r["failure_reason"]) and p.read_bytes() == before                    # refused, recorded with its reason; nothing replaced
    assert r["latest_observation"] is None                                                                                # and no observation date is claimed for the refused answer
    assert len(operations.european_daily(str(tmp_path))) == 20                                                            # the data held are still readable and unchanged


def test_PRT09_route_file_checks_and_change_time(tmp_path):
    head = "Year,Month,usg_apt,fg_apt,carrier,carriergroup,Scheduled,Charter,Total\n"; row = lambda y, m, t=30: f"{y},{m},JFK,HKG,CX,0,{t},0,{t}\n"
    raw = (head + row(2025, 11) + row(2025, 12)).encode(); d = tmp_path / "official" / "usdot"; d.mkdir(parents=True); body = operations._gz(raw); p = d / operations.USD_FILE; p.write_bytes(body)
    (d / (operations.USD_FILE + ".meta.json")).write_text(json.dumps({"sha256": hashlib.sha256(body).hexdigest(), "raw_sha256": hashlib.sha256(raw).hexdigest(), "retrieved_at": "2026-10-05T10:00:00Z"}), encoding="utf-8")
    asked = []
    def get(url): asked.append(url); return 200, (head + row(2025, 11) + row(2025, 12) + row(2026, 1)).encode(), {}
    meta = lambda t: (lambda url: (200, json.dumps({"rowsUpdatedAt": t}).encode(), {}))
    kw = dict(out_dir=str(tmp_path), trigger="schedule", sleep=lambda s: None)
    r = operations.refresh_usdot(get=get, meta_get=meta(int(operations._epoch("2026-08-07T00:00:00Z"))), now="2026-10-06T06:00:00Z", **kw)
    assert r["result"] == "UNCHANGED" and asked == [] and r["latest_observation"] == "2025-12"                            # rows last changed before the file held was fetched: no download
    r = operations.refresh_usdot(get=get, meta_get=meta(int(operations._epoch("2026-10-20T00:00:00Z"))), now="2026-10-21T06:00:00Z", **kw)
    assert r["result"] == "REVISED" and len(asked) == 1 and r["latest_observation"] == "2026-01" and len(operations.us_international(str(tmp_path))) == 3
    r = operations.refresh_usdot(get=get, meta_get=meta(int(operations._epoch("2026-10-20T00:00:00Z"))), now="2026-10-22T06:00:00Z", **kw)
    assert r["result"] == "UNCHANGED" and len(asked) == 1                                                                 # the change time already recorded: not downloaded again
    assert "months in the future" in " ".join(operations.validate_usdot((head + row(2031, 1)).encode(), "2026-10-06")[0])
    assert "total differs" in " ".join(operations.validate_usdot((head + "2025,12,JFK,HKG,CX,0,30,0,31\n").encode(), "2026-10-06")[0])
    assert "ends earlier" in " ".join(operations.validate_usdot((head + row(2025, 11)).encode(), "2026-10-06", 0, "2025-12")[0])
    assert "month outside" in " ".join(operations.validate_usdot((head + row(2025, 13)).encode(), "2026-10-06")[0])


def test_PRT10_the_quality_gate_withholds_a_feed_whose_files_do_not_verify(tmp_path):
    p = _seed_eur(tmp_path, _eur(10)); q = operations.quality(str(tmp_path))
    assert "eurocontrol" not in q["critical"] and q["critical"].get("usdot") == ["no file held"]                          # a feed without a file is named, not passed
    p.write_bytes(p.read_bytes() + b"x"); q = operations.quality(str(tmp_path))
    if {d["id"]: d for d in registry.declared()[1]}["eurocontrol"]["active"]: assert "SHA-256 does not match" in q["critical"]["eurocontrol"][0]       # an altered file is critical
    else: assert q["checked"]["eurocontrol"] == {"switched_off": True} and "eurocontrol" not in q["critical"]            # a source that is switched off is not read at all
    log = collector.log_path(str(tmp_path)); records.append(log, {"source": "x", "result": "OK"}); records.append(log, {"source": "x", "result": "OK"})
    lines = open(log, encoding="utf-8").read().splitlines(); open(log, "w", encoding="utf-8", newline="\n").write(lines[1] + "\n" + lines[0] + "\n")
    assert "log" in operations.quality(str(tmp_path))["critical"]                                                         # a reordered run log is critical for the whole layer
    real = operations.quality(); assert real["critical"] == {} and real["checked"]["hkia"]["days"] > 0                    # the repository's own files pass


def test_PRT11_the_position_sweep_is_bounded_and_a_missing_answer_is_never_a_count(tmp_path):
    t = {"now": 0.0}
    def clock(): t["now"] += 100.0; return t["now"]
    def get(url): return 200, json.dumps({"ac": [{"t": "B77W", "flight": "CPA123", "alt_baro": "ground"}]}).encode(), {}
    r = collector.collect_positions(codes=["HKG", "FRA", "DEL", "LHR", "JFK"], get=get, now="2026-10-06T06:00:00Z", out_dir=str(tmp_path), trigger="schedule", sleep=lambda s: None, budget_seconds=250, clock=clock)
    assert r["result"] == "PARTIAL" and r["airports_answered"] == 2 and len(r["failed"]) == 3                             # the sweep stopped when its time was used
    snap = collector.load_positions(str(tmp_path)); assert set(snap["airports"]) == {"HKG", "FRA"} and sorted(snap["not_answered"]) == ["DEL", "JFK", "LHR"]
    assert all(v["aircraft_seen"] == 1 for v in snap["airports"].values()) and "DEL" not in snap["airports"]            # an airport that was not asked has no count: it is absent, not zero
    r = collector.collect_positions(codes=["HKG"], get=lambda url: (429, b"", {"Retry-After": "600"}), now="2026-10-06T07:00:00Z", out_dir=str(tmp_path), trigger="schedule", sleep=lambda s: None)
    assert r["result"] == "FAILED" and "file" not in r


# ---------------------------------------------------------------------------------------------------------------- selection, ledger, orchestrator

def test_PRT12_the_official_forecaster_is_selected_by_rule_and_recorded(tmp_path, monkeypatch):
    rec = selection.select(); cand = [c for c in rec["candidates"] if c["status"] == "VALIDATED"]
    assert rec["official"] == min(cand, key=lambda c: c["brier"])["id"] == max(cand, key=lambda c: c["hit_rate"])["id"]   # the rule, recomputed from the scores in the record
    assert rec["benchmark_ledger_sha256"] == open(os.path.join(config.EVAL_DIR, "benchmark_ledger.sha256")).read().split()[0]
    held = [rel.replace(os.sep, "/") for _, rel in selection.DECISIONS if os.path.exists(os.path.join(ROOT, rel))]; hosted = os.path.isfile(os.path.join(ROOT, "PUBLIC_REPOSITORY.json"))
    assert [d["file"] for d in rec["later_decisions"]] == held and len(held) == (0 if hosted else 2)    # one decision on record for every result file the repository holds: both in the research repository; none in a hosted
                                                                                                         # one, where the results of the research passes, made on the retired inputs, are not published (CL-024)
    assert all(d["official"] == rec["official"] and not d["changed"] for d in rec["later_decisions"])
    p = str(tmp_path / "official.json"); h1 = selection.write(rec, p); m1 = os.path.getmtime(p); h2 = selection.write(rec, p)
    assert h1 == h2 and os.path.getmtime(p) == m1 and selection.read(p) == rec and "generated" not in json.dumps(rec)     # no clock in the record: unchanged inputs leave the file untouched
    stored = selection.read()
    if stored is not None: assert stored == rec                                                                           # the record in the repository is the one the evaluation gives now
    from src.dashboard import data as dd
    monkeypatch.setattr(dd, "best_by", lambda table, column, lower: table.index[0] if lower else table.index[-1])
    with pytest.raises(selection.NoSelection, match="criteria disagree"): selection.select()
    monkeypatch.undo()
    root = tmp_path / "root"; (root / "evaluation" / "monthly").mkdir(parents=True); shutil.copyfile(os.path.join(config.EVAL_DIR, "benchmark_ledger.sha256"), root / "evaluation" / "benchmark_ledger.sha256")
    (root / "evaluation" / "monthly" / "results_v2.json").write_text(json.dumps({"generated": "2026-10-05", "decision": {"official": "GBT[ALL]", "changed": True, "passed": ["GBT[ALL]"]}}), encoding="utf-8")
    with pytest.raises(selection.NoSelection, match="promotion is completed in the repository"): selection.select(root=str(root))
    src = open(os.path.join(ROOT, "src", "ops", "selection.py"), encoding="utf-8").read()
    assert 'official = "BL-' not in src and "return \"BL-" not in src                                                     # nothing in the module names the official forecaster
    missing = str(tmp_path / "no_store.sqlite"); monkeypatch.setattr(config, "DB_PATH", missing)                          # a fresh clone has no benchmark store (found by the clean-clone run)
    with pytest.raises(selection.NoSelection, match="benchmark store is absent"): selection.select()
    assert not os.path.exists(missing)                                                                                    # and looking for it must not create an empty one
    monkeypatch.undo()
    run_src = open(os.path.join(ROOT, "src", "ops", "pipeline.py"), encoding="utf-8").read()
    assert run_src.count("dd.ensure_store()") == 2 and run_src.index('if "news" in groups:') > run_src.index("dd.ensure_store(); rec = selection.select()")   # the pipeline builds the derived store itself; a headlines-only run does not select


def test_PRT13_every_new_forecast_record_names_its_data_file_by_file():
    v = pipeline.source_versions(); files = [s for s, c in sources.SOURCES.items() if c["file"]]
    assert set(v) == set(files) and all(len(x["sha256"]) == 64 and x["retrieved_at"] for x in v.values())
    for sid in files:
        with open(os.path.join(opscfg.CURRENT_DIR, sources.SOURCES[sid]["file"]), "rb") as f: assert hashlib.sha256(f.read()).hexdigest() == v[sid]["sha256"]
    assert opscfg.FORECAST_SCHEMA_VERSION == "FC-2" and str(config.FLAT_BAND_PCT) in opscfg.CONFIGURATION_VERSION and config.FEATURE_VERSION in opscfg.CONFIGURATION_VERSION
    code = open(os.path.join(ROOT, "src", "ops", "pipeline.py"), encoding="utf-8").read()
    for k in ('"source_versions": versions', '"configuration_version"', '"official_forecaster": official', '"is_official"'): assert k in code
    led = records.read(sources.FORECAST_LEDGER); assert led and not records.verify(sources.FORECAST_LEDGER)
    for r in led:                                                                                                         # the permanent record of every forecast issued
        for k in ("forecast_id", "issuance_date", "generated_at", "target_period", "data_cutoff", "forecaster_id", "probabilities", "feature_version", "model_version", "input_data_version", "code_hash", "pipeline_version", "status", "trigger"): assert k in r
        if r["schema_version"] != "FC-1": assert r["source_versions"] and r["configuration_version"]


def test_PRT14_only_what_is_due_is_fetched():
    pr = _script("production_run"); now = T("2026-10-10T08:00:00Z")
    row = lambda i, layer="core", **kw: {"id": i, "layer": layer, "status": "HEALTHY", "check_every_days": 7, "last_attempt": "2026-10-09T08:00:00Z", "latest_data": "2026-10-07", "last_result": "UNCHANGED", **kw}
    reg = {"sources": [
        row("eia_A"),                                                                                                    # checked yesterday, weekly: not due
        row("eia_B", last_attempt="2026-10-02T08:00:00Z"),                                                               # check interval reached
        row("bls_X", check_every_days=19, latest_data="2026-09-16", last_attempt="2026-10-09T08:00:00Z"),              # monthly index, released 24 days ago: not asked daily
        row("news_n", check_every_days=1, last_attempt="2026-10-09T07:00:00Z"),                                           # daily
        row("hkia", "aviation", check_every_days=1, last_attempt="2026-10-10T07:30:00Z"),                                 # asked half an hour ago: not due
        row("positions", "aviation", check_every_days=1, last_attempt="2026-10-10T06:00:00Z", status="DEGRADED", last_result="PARTIAL"),   # the last attempt did not succeed: one retry
        row("never", "weekly", last_attempt=None, latest_data=None, last_result=None, status="FAILED"),
        row("off", status="DISABLED"), row("study", None, status="RESEARCH_ONLY")]}
    d = pr.due(reg, now)
    assert set(d) == {"fuel", "news", "aviation", "weekly"} and set(d["fuel"]) == {"eia_B"} and set(d["aviation"]) == {"positions"} and "bls" not in d
    assert "never fetched" in d["weekly"]["never"] and "check interval" in d["fuel"]["eia_B"] and "did not succeed" in d["aviation"]["positions"]
    late = pr.due({"sources": [row("bls_X", check_every_days=19, latest_data="2026-09-16", last_attempt="2026-10-14T08:00:00Z")]}, T("2026-10-15T08:00:00Z"))
    assert "publisher normally has more" in late["bls"]["bls_X"]                                                       # from the day the next release is expected, the index is asked daily until it arrives
    soon = pr.due({"sources": [row("bls_X", check_every_days=19, latest_data="2026-09-16", last_attempt="2026-10-15T02:00:00Z")]}, T("2026-10-15T08:00:00Z"))
    assert soon == {}                                                                                                     # but not twice within a day
    assert set(pr.due(reg, now, force=("bls",))["bls"]) == {"bls_X"}


def test_PRT15_a_step_that_fails_or_hangs_is_recorded_and_does_not_stop_the_run():
    pr = _script("production_run"); log = []
    assert pr.step("ok", ["-c", "print('fine')"], 30, log) == 0 and pr.step("fails", ["-c", "import sys; print('bad'); sys.exit(3)"], 30, log) == 3
    assert pr.step("hangs", ["-c", "import time; time.sleep(30)"], 2, log) == 124 and pr.step("crash", ["-c", "raise SystemError('x')"], 30, log) != 0
    assert [x["step"] for x in log] == ["ok", "fails", "hangs", "crash"] and "time limit" in " ".join(log[2]["tail"]) and all("seconds" in x for x in log)
    text = open(os.path.join(ROOT, "scripts", "production_run.py"), encoding="utf-8").read()
    assert "code = 1 if critical else 2 if" in text and "records.append(RUNS" in text and '"-m", "src.aviation.cli", "refresh"' in text      # gate failure is exit 1; every run is recorded; the air-traffic layer is its own process
    runs = records.read(pr.RUNS); assert not records.verify(pr.RUNS)
    for r in runs:
        assert r["trigger"] in ("manual", "schedule", "manual-dispatch") and isinstance(r["gate"]["passed"], bool) and r["exit"] in (0, 1, 2)
        if r["trigger"] == "schedule": assert r["workflow_run"] and r["workflow_run"]["run_id"]                           # a scheduled run is only one that a hosted runner identified


@pytest.mark.research_record
def test_PRT16_workflows_define_daily_weekly_and_monthly_runs_that_commit_only_after_the_gate():
    d = os.path.join(ROOT, ".github", "workflows"); wf = {n: yaml.safe_load(open(os.path.join(d, n), encoding="utf-8")) for n in ("production.yml", "data_refresh.yml", "news_ingest.yml")}
    text = open(os.path.join(d, "production.yml"), encoding="utf-8").read(); crons = [s["cron"] for s in wf["production.yml"][True]["schedule"]]
    assert len(crons) == 3 and any(c.endswith("* * *") for c in crons) and any(c.split()[4] != "*" for c in crons) and any(c.split()[2] != "*" for c in crons)       # daily, weekly (a weekday), monthly (a day of the month)
    assert len({wf[n]["concurrency"]["group"] for n in wf}) == 1 and wf["production.yml"]["permissions"] == {"contents": "write"}                                    # never two jobs committing at once
    steps = wf["production.yml"]["jobs"]["run"]["steps"]; names = [s.get("name", "") for s in steps]
    run_i = next(i for i, n in enumerate(names) if n.startswith("Production run")); commit_i = next(i for i, n in enumerate(names) if n.startswith("Commit")); report_i = next(i for i, n in enumerate(names) if n.startswith("Report a source"))
    assert run_i < commit_i < report_i and "scripts/production_run.py" in steps[run_i]["run"] and 'if [ "$code" = "1" ]' in steps[run_i]["run"] and "exit 1" in steps[report_i]["run"]
    assert "git add operations research/news_archive" in steps[commit_i]["run"] and "secrets." not in text and wf["production.yml"]["jobs"]["run"]["timeout-minutes"] <= 180
    assert "tests/test_production.py" in text and "python -m src.ops.cli verify" in text
    all_crons = [s["cron"] for n in wf for s in wf[n][True]["schedule"]]; assert len(set(all_crons)) == len(all_crons)


def test_PRT17_the_operations_report_is_written_from_the_records():
    rp = _script("production_report"); text, m, reg = rp.build("daily", T("2026-10-06T00:00:00Z"))
    for r in reg["sources"]: assert f"| {r['name']} | {r['status']} |" in text
    runs = records.read(os.path.join(sources.OPS_DIR, "production_runs.jsonl")); sched = sum(1 for r in runs if r.get("trigger") == "schedule")
    assert f"Runs on record: {len(runs)}; started by a scheduler: {sched}" in text and "Do not edit" in text
    assert m["official"] == selection.select()["official"] and (m["month_due"] is None or m["on_record"] == (m["month_due"] in m["months_on_record"]))
    later, _, reg2 = rp.build("daily", T("2027-10-06T00:00:00Z")); assert reg2["summary"]["HEALTHY"] == 0 and "| HEALTHY |" not in later                              # the same records a year later: nothing is healthy


@pytest.mark.research_record
def test_PRT18_documents_of_the_production_pass_say_what_the_records_support():
    P = lambda *a: os.path.join(ROOT, *a)
    contract = open(P("docs", "PRODUCTION_DATA_CONTRACT.md"), encoding="utf-8").read(); audit = open(P("evaluation", "AUTOMATION_AUDIT.md"), encoding="utf-8").read()
    report = open(P("execution", "FINAL_PRODUCTION_READINESS_REPORT.md"), encoding="utf-8").read()
    for col in ("Field", "Source", "Ingestion", "Raw artifact", "Calculation", "Update frequency", "Stale after", "Fallback", "Kind", "Customer-safe"): assert col in contract
    audited = audit.split("## Values", 1)[1].split("## Kept by hand", 1)[0]                                              # the two audit tables: the values, and what starts the code
    rows = [l for l in audited.splitlines() if l.startswith("| ") and not l.startswith("| UI value") and not l.startswith("|---")]
    assert len(rows) >= 30 and all(("| AUTOMATED |" in l) != ("| MANUAL / BLOCKER |" in l) for l in rows)                 # every row is one or the other
    for n in range(1, 18): assert f"## {n}. " in report
    import re
    status = re.findall(r"^PRODUCTION STATUS: (PRODUCTION READY WITH EXPLICIT NON-PRODUCTION FEATURES REMOVED|PRODUCTION READY|NOT READY)$", report, re.M); assert len(status) == 1
    real = registry.build(); runs = records.read(os.path.join(sources.OPS_DIR, "production_runs.jsonl"))
    if real["summary"]["scheduled_runs"] == 0 and not any(r.get("trigger") == "schedule" for r in runs):
        assert status[0] == "NOT READY" and "fully automated" not in report.lower().replace("not fully automated", "").replace("not be called fully automated", "")   # without a scheduled run on record nothing is called ready or fully automated
    for doc in (contract, audit, report): assert "actual cargo capacity" not in doc.lower() and "real-time" not in doc.lower().replace("not real-time", "").replace("no real-time", "")


@pytest.mark.research_record
def test_PRT19_from_zero_again_and_with_every_source_down_is_on_record():
    path = os.path.join(config.EVAL_DIR, "zero_to_site_verification.json"); z = json.load(open(path, encoding="utf-8")); ph = z["phases"]
    assert z["passed"] and set(ph) == {"A_from_zero", "B_again", "C_sources_down"} and len(z["engine_commit"]) == 40 and len(z["web_commit"]) == 40
    a, b, c = ph["A_from_zero"], ph["B_again"], ph["C_sources_down"]
    assert not z["derived_stores_in_the_clone_before_the_run"] and "web: public/data" in z["deleted_before_the_run"] and "operations/forecast_ledger.jsonl" in z["deleted_before_the_run"]      # it started from nothing generated
    assert all(a["state"]["stores"].values()) and a["state"]["monthly_forecasts_on_ledger"] > 0 and a["state"]["last_production_run"]["gate"]["passed"] and a["site_built"] and all(s["exit"] == 0 for s in a["steps"][1:])
    assert all(b["unchanged"].values()) and a["state"]["export"]["content_hash"] == b["state"]["export"]["content_hash"]                                                                     # a second run on unchanged data changes nothing
    assert all(c["checks"].values()) and c["steps"][0]["exit"] == 2                                                                                                                         # sources down: completed, reported, nothing invented
    fetched = [k for k, v in c["state"]["registry"]["status"].items() if v not in ("DISABLED", "RESEARCH_ONLY")]
    assert fetched and all(c["state"]["registry"]["status"][k] != "HEALTHY" for k in fetched) and c["state"]["monthly_forecasts_on_ledger"] == b["state"]["monthly_forecasts_on_ledger"]
    assert all(r["trigger"] == "manual" for r in (a["state"]["last_production_run"], c["state"]["last_production_run"]))                                                                    # and none of it is called a scheduled run
