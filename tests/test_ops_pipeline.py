"""Operational pipeline tests (OP-T1 to OP-T9): append-only records, adapters (no network: responses are served from the
stored snapshot), idempotency, bounded retries, forecast issue and immutability, outcomes, health derived from the log
and the clock, and the workflow files."""
import csv, datetime, hashlib, io, json, os, shutil, sys, urllib.error
import pandas as pd, pytest, yaml
from src import config
from src.api import backtest as bt
from src.ingestion.build import build_store
from src.observability import health, records, sources
from src.ops import adapters, bls, config as ocfg, pipeline

ROOT = config.ROOT
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
RUN_FIELDS = {"source", "retrieved_at", "latest_observation", "url", "http_status", "record_count", "checksum", "schema_version", "pipeline_version", "result", "error"}
FC_FIELDS = {"forecast_id", "issuance_date", "generated_at", "target_period", "data_cutoff", "feature_version", "model_version", "training_window", "model_parameters", "probabilities", "prediction", "status"}


def test_OPT1_records_are_append_only_and_tampering_is_detected(tmp_path):
    p = str(tmp_path / "log.jsonl")
    for i in range(4): records.append(p, {"n": i})
    assert [r["seq"] for r in records.read(p)] == [1, 2, 3, 4] and records.verify(p) == []
    lines = open(p, encoding="utf-8").read().split("\n")
    open(p, "w", encoding="utf-8").write("\n".join([lines[0], lines[1].replace('"n": 1', '"n": 9')] + lines[2:])); assert any("content" in x for x in records.verify(p))      # an edited record
    open(p, "w", encoding="utf-8").write("\n".join([lines[0]] + lines[2:])); assert records.verify(p)                                                                  # a removed record
    open(p, "w", encoding="utf-8").write("\n".join([lines[1], lines[0]] + lines[2:])); assert records.verify(p)                                                        # a reordered file
    assert records.read(str(tmp_path / "absent.jsonl")) == [] and records.verify(str(tmp_path / "absent.jsonl")) == []


def _held(tmp_path, file_name, body):
    d = str(tmp_path / "current"); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, file_name), "wb").write(body)
    json.dump({"source_id": "SRC-01", "url": "u", "retrieved_at": "2026-10-03T00:00:00Z", "sha256": hashlib.sha256(body).hexdigest(), "http_status": 200}, open(os.path.join(d, file_name + ".meta.json"), "w"))
    return d


XLS = {"eia_jet_fuel": "SRC-01_eia_EER_EPJK_PF4_RGC_DPG.xls", "eia_brent": "SRC-08_eia_RBRTE.xls"}      # the Administration's spreadsheets as retrieved for the benchmark


def test_OPT2_fuel_adapter_validates_stores_once_and_is_idempotent(tmp_path):
    cfg = sources.SOURCES["eia_jet_fuel"]; full = open(os.path.join(config.SNAPSHOT_DIR, cfg["file"]), "rb").read(); xls = open(os.path.join(config.SNAPSHOT_DIR, XLS["eia_jet_fuel"]), "rb").read()
    old = b"\n".join(full.strip().split(b"\n")[:-5]) + b"\n"; cur = _held(tmp_path, cfg["file"], old); raw = str(tmp_path / "raw"); path = os.path.join(cur, cfg["file"])
    kw = {"current_dir": cur, "raw_dir": raw, "now": lambda: "2026-10-10T06:41:00Z"}
    r = adapters.fetch_eia("eia_jet_fuel", cfg, get=lambda url: (200, xls), **kw)
    assert r["result"] == "UPDATED" and RUN_FIELDS <= set(r) and r["latest_observation"] == "2026-09-29" and r["checksum"] == hashlib.sha256(full).hexdigest() and r["http_status"] == 200
    assert open(path, "rb").read() == full and json.load(open(path + ".meta.json"))["sha256"] == r["checksum"] and r["new_records"] == 5        # the spreadsheet gives the benchmark file, byte for byte
    raws = [f for d, _, fs in os.walk(raw) for f in fs]; assert len(raws) == 1 and raws[0].startswith("20261010T064100Z_")                     # kept under the time of the fetch: a dated archive of what the publisher served
    import gzip
    assert gzip.open(os.path.join(raw, "eia_jet_fuel", raws[0])).read() == xls                             # the spreadsheet is kept exactly as served
    r2 = adapters.fetch_eia("eia_jet_fuel", cfg, get=lambda url: (200, xls), **kw)                         # the same content again
    assert r2["result"] == "UNCHANGED" and r2["raw_snapshot"] is None and [f for d, _, fs in os.walk(raw) for f in fs] == raws and open(path, "rb").read() == full
    other = open(os.path.join(config.SNAPSHOT_DIR, XLS["eia_brent"]), "rb").read()
    for bad, why in ((b"<html>error</html>", "parsed"), (other, "not EER_EPJK_PF4_RGC_DPG")):
        rb = adapters.fetch_eia("eia_jet_fuel", cfg, get=lambda url, b=bad: (200, b), **kw)
        assert rb["result"] == "FAILED" and why in rb["error"] and open(path, "rb").read() == full       # a rejected response leaves the held file untouched
    longer = full + b"2026-09-30,2.5\n2026-10-01,2.5\n"; cur2 = _held(tmp_path / "b", cfg["file"], longer)
    rs = adapters.fetch_eia("eia_jet_fuel", cfg, get=lambda url: (200, xls), current_dir=cur2, raw_dir=raw, now=kw["now"])
    assert rs["result"] == "FAILED" and "fewer observations" in rs["error"] and open(os.path.join(cur2, cfg["file"]), "rb").read() == longer       # a file that lost days is refused
    def down(url): raise adapters.FetchError("HTTP 503 from x", 503)
    rf = adapters.fetch_eia("eia_jet_fuel", cfg, get=down, **kw)
    assert rf["result"] == "FAILED" and rf["http_status"] == 503 and "503" in rf["error"] and open(path, "rb").read() == full


def test_OPT3_http_retries_are_bounded_and_client_errors_are_not_retried():
    calls, sleeps = [], []
    def flaky(req, timeout): calls.append(1); raise urllib.error.URLError("down")
    with pytest.raises(adapters.FetchError): adapters.http_get("https://example.org/x", sleep=sleeps.append, opener=flaky)
    assert len(calls) == ocfg.HTTP_ATTEMPTS == 3 and sleeps == list(ocfg.HTTP_BACKOFF)                     # three requests, two fixed pauses, then it gives up
    calls.clear(); sleeps.clear()
    def missing(req, timeout): calls.append(1); raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, io.BytesIO(b""))
    with pytest.raises(adapters.FetchError) as e: adapters.http_get("https://example.org/x", sleep=sleeps.append, opener=missing)
    assert len(calls) == 1 and sleeps == [] and e.value.status == 404
    calls.clear()
    def limited(req, timeout): calls.append(1); raise urllib.error.HTTPError(req.full_url, 429, "slow", {}, io.BytesIO(b""))
    with pytest.raises(adapters.FetchError): adapters.http_get("https://example.org/x", sleep=sleeps.append, opener=limited)
    assert len(calls) == 3                                                                                  # a rate limit is retried, but no more than the bound


def _drop_vintages(text, k):
    rows = [ln.split(",") for ln in text.strip().split("\n")]; keep = len(rows[0]) - k
    return "\n".join(",".join(r[:keep]) for r in rows if r is rows[0] or any(v != "" for v in r[1:keep])) + "\n"


def _bureau(series):
    """Serves what the Bureau serves: the list of archived releases, each release page, and the database (as it stood after the newest release kept)."""
    import csv, gzip
    d = os.path.join(ROOT, "research", "bls_releases")
    with gzip.open(os.path.join(d, "transport_tables.jsonl.gz"), "rt", encoding="utf-8") as fh: tabs = {t["release_date"]: t for t in map(json.loads, fh)}
    with open(os.path.join(d, "final_values.csv"), newline="", encoding="utf-8") as fh: base = {r["month"]: r["value"] for r in csv.DictReader(fh) if r["series"] == series}
    by_url = {bls.RELEASE_URL.format(mm=k[5:7], dd=k[8:], yyyy=k[:4]): t["table"] for k, t in tabs.items()}
    def get(url):
        if url == bls.ARCHIVE_LIST: return 200, "".join(f'<a href="/news.release/archives/ximpim_{k[5:7]}{k[8:]}{k[:4]}.htm">x</a>' for k in tabs).encode()
        return 200, ("<html><body>" + by_url[url] + "</body></html>").encode("utf-8")
    def post(url, body):
        q = json.loads(body); assert url == bls.API and q["seriesid"] == [bls.bls_id(series)]
        data = [{"year": m[:4], "period": "M" + m[5:7], "value": v, "footnotes": [{}]} for m, v in sorted(base.items(), reverse=True) if q["startyear"] <= m[:4] <= q["endyear"]]
        return 200, json.dumps({"status": "REQUEST_SUCCEEDED", "message": [], "Results": {"series": [{"seriesID": bls.bls_id(series), "data": data}]}}).encode()
    return get, post, {m: float(v) for m, v in base.items()}


def test_OPT4_vintage_adapter_fetches_only_new_releases_and_never_touches_stored_ones(tmp_path):
    cfg = sources.SOURCES["bls_IC1312"]; full = open(os.path.join(config.SNAPSHOT_DIR, cfg["file"]), encoding="utf-8").read()
    held = _drop_vintages(full, 3); cur = _held(tmp_path, cfg["file"], held.encode()); path = os.path.join(cur, cfg["file"]); asked = []
    serve, post, base = _bureau("IC1312")
    def get(url): asked.append(url); return serve(url)
    kw = {"current_dir": cur, "raw_dir": str(tmp_path / "raw"), "now": lambda: "2026-10-16T14:23:00Z", "sleep": lambda s: None}
    r = adapters.fetch_bls("bls_IC1312", cfg, get=get, post=post, **kw)
    assert r["result"] == "UPDATED" and r["new_records"] == 3 and r["record_count"] == 198 and r["latest_observation"] == "2026-09-16" and RUN_FIELDS <= set(r)
    assert len(asked) == 4 and asked[0] == bls.ARCHIVE_LIST and [u[-12:-4] for u in asked[1:]] == ["07172026", "08182026", "09162026"]      # the list once, then exactly the three new releases
    got = open(path, encoding="utf-8").read(); a, b = adapters._columns(got), adapters._columns(full)
    assert a[1] == b[1] and a[2][:195] == adapters._columns(held)[2] == b[2][:195]                           # the stored columns are untouched
    assert a[2][195] == b[2][195] and a[2][196] == b[2][196]                                                # releases read later than the next one: rebuilt by the rule, as in the benchmark
    newest = dict(a[2][197]); second = newest.pop("2026-06-01"); want = dict(b[2][197]); want.pop("2026-06-01")
    assert newest == want and second == base["2026-06-01"]                                                  # the newest release: the month the table does not print is the database value read then
    assert "e database value read while the release was the newest" in json.load(open(path + ".meta.json"))["note"]
    r2 = adapters.fetch_bls("bls_IC1312", cfg, get=get, post=post, **kw)
    assert r2["result"] == "UNCHANGED" and len(asked) == 5 and open(path, encoding="utf-8").read() == got   # idempotent: only the list is asked again
    def early(url): return serve(url)
    re_ = adapters.fetch_bls("bls_IC1312", cfg, get=early, post=post, current_dir=_held(tmp_path / "c", cfg["file"], held.encode()), raw_dir=str(tmp_path / "raw"), now=lambda: "2026-08-01T00:00:00Z", sleep=lambda s: None)
    assert re_["result"] == "FAILED" and "after the fetch" in re_["error"]                                  # a release dated after the clock is refused
    def broken(url): return (200, serve(url)[1]) if url == bls.ARCHIVE_LIST else (200, b"<html><table>selected transportation services Inbound Air Freight</table></html>")
    rb = adapters.fetch_bls("bls_IC1312", cfg, get=broken, post=post, current_dir=_held(tmp_path / "d", cfg["file"], held.encode()), raw_dir=str(tmp_path / "raw"), now=kw["now"], sleep=lambda s: None)
    assert rb["result"] == "FAILED" and open(os.path.join(str(tmp_path / "d" / "current"), cfg["file"]), encoding="utf-8").read() == held      # a page that cannot be read leaves the held file untouched


@pytest.fixture(scope="module")
def ops_area(tmp_path_factory):
    """An operational area seeded from the benchmark snapshot, with its own store, log and ledger."""
    d = tmp_path_factory.mktemp("ops"); a = {"current": str(d / "current"), "db": str(d / "ops.sqlite"), "log": str(d / "log.jsonl"), "ledger": str(d / "ledger.jsonl"), "outcomes": str(d / "outcomes.jsonl")}
    a["seeded"] = pipeline.seed(a["log"], a["current"]); build_store(a["db"], a["current"])
    return a


def test_OPT5_forecasts_are_issued_once_with_full_provenance_and_equal_the_backtest(ops_area):
    a = ops_area; now = lambda: "2026-09-17T14:23:00Z"
    assert len(a["seeded"]) == 10 and all(r["result"] == "SEEDED" and r["trigger"] == "seed" for r in records.read(a["log"])) and pipeline.seed(a["log"], a["current"]) == []
    issued = pipeline.issue_forecasts(a["db"], a["current"], a["ledger"], trigger="schedule", now=now)
    assert len(issued) == 40 and {r["target_period"] for r in issued} == {"2026-09"} and all(FC_FIELDS <= set(r) for r in issued)
    assert all(r["data_cutoff"] <= r["issuance_date"] < r["generated_at"][:10] and r["timing"] == "ON_TIME" and r["status"] == "ISSUED" for r in issued)   # nothing later than the issuance date was used
    assert all(abs(sum(r["probabilities"].values()) - 1) < 1e-9 and r["training_window"]["latest_label_date"] <= r["issuance_date"] and r["training_window"]["n"] > 0 for r in issued)
    before = open(a["ledger"], "rb").read()
    assert pipeline.issue_forecasts(a["db"], a["current"], a["ledger"], now=lambda: "2026-10-30T00:00:00Z") == [] and open(a["ledger"], "rb").read() == before   # a second run issues nothing and changes nothing
    assert records.verify(a["ledger"]) == []
    led = {r["FORECAST-ID"]: r for r in csv.DictReader(open(os.path.join(config.EVAL_DIR, "forecast_ledger.csv"), encoding="utf-8"))}     # the validated backtest ledger
    for r in issued:
        b = led[r["forecast_id"]]
        assert b["ISSUED-AT"] == r["issuance_date"] and b["PREDICTION"] == r["prediction"] and b["MAX_FEATURE_INFO_TIME"] == r["data_cutoff"]
        assert [float(b[k]) for k in ("P_DOWN", "P_FLAT", "P_UP")] == pytest.approx([r["probabilities"][k] for k in ("down", "flat", "up")], abs=1e-9)   # 0.0 on the platform that made the ledger; about 1e-12 on another one (the tolerance of scripts/check_benchmark_ledger.py)
    late = pipeline.issue_forecasts(a["db"], a["current"], str(os.path.dirname(a["ledger"])) + "/late.jsonl", now=lambda: "2026-10-04T05:00:00Z")
    assert {r["timing"] for r in late} == {"LATE"} and {r["days_after_issuance"] for r in late} == {18}      # a forecast generated long after its issuance date says so


def test_OPT6_an_earlier_forecast_is_never_changed_and_its_outcome_is_added_later(tmp_path, ops_area):
    """Issue on data cut four releases earlier, then let the store catch up: the forecast stays, the outcome is appended."""
    cur = str(tmp_path / "current"); shutil.copytree(ops_area["current"], cur)
    for s in config.BLS_SERIES:
        p = os.path.join(cur, config.BLS_SERIES[s][1]); body = _drop_vintages(open(p, encoding="utf-8").read(), 4).encode(); open(p, "wb").write(body)
        m = json.load(open(p + ".meta.json")); m["sha256"] = hashlib.sha256(body).hexdigest(); json.dump(m, open(p + ".meta.json", "w"))
    db_then = str(tmp_path / "then.sqlite"); build_store(db_then, cur); ledger, outs = str(tmp_path / "ledger.jsonl"), str(tmp_path / "outcomes.jsonl")
    issued = pipeline.issue_forecasts(db_then, cur, ledger, now=lambda: "2026-05-15T14:23:00Z")
    assert {r["target_period"] for r in issued} == {"2026-05"} and all(r["data_cutoff"] <= "2026-05-14" for r in issued)
    led = {r["FORECAST-ID"]: r for r in csv.DictReader(open(os.path.join(config.EVAL_DIR, "forecast_ledger.csv"), encoding="utf-8"))}
    for r in issued:                                                                                          # what was issued then is what the backtest says was knowable then
        assert [float(led[r["forecast_id"]][k]) for k in ("P_DOWN", "P_FLAT", "P_UP")] == pytest.approx([r["probabilities"][k] for k in ("down", "flat", "up")], abs=1e-9)
    assert pipeline.record_outcomes(db_then, ledger, outs) == []                                             # the target month was not published yet: no outcome
    frozen = open(ledger, "rb").read()
    got = pipeline.record_outcomes(ops_area["db"], ledger, outs, now=lambda: "2026-09-16T15:00:00Z")          # four releases later
    kinds = {(o["forecast_id"], o["kind"]) for o in got}
    assert len(got) == 80 and {k for _, k in kinds} == {"REALTIME", "FINAL"} and open(ledger, "rb").read() == frozen                # 40 forecasts x 2 labels; the ledger is untouched
    ic = next(o for o in got if o["forecast_id"] == "IC1312|BL-SEA|2026-05" and o["kind"] == "FINAL")
    assert ic["actual"] == led["IC1312|BL-SEA|2026-05"]["ACTUAL"] and ic["correct"] == int(led["IC1312|BL-SEA|2026-05"]["CORRECT"]) and ic["label_date"] > "2026-05-15"
    assert pipeline.record_outcomes(ops_area["db"], ledger, outs) == [] and records.verify(outs) == []          # each outcome is recorded once


def test_OPT7_health_and_data_mode_come_from_the_log_and_the_clock():
    t = lambda s: datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    run = lambda src, when, result="UPDATED", trigger="manual", **k: {"source": src, "retrieved_at": when, "result": result, "trigger": trigger, "latest_observation": "2026-10-06", "record_count": 10, "checksum": "c", "validation": "passed", "http_status": 200, **k}
    s = "eia_jet_fuel"
    assert health.source_health([], s, t("2026-10-10T00:00:00Z"))["status"] == "NOT CONFIGURED"
    seeded = [run(s, "2026-10-03T14:37:02Z", "SEEDED", "seed")]
    h = health.source_health(seeded, s, t("2026-10-05T00:00:00Z")); assert (h["status"], h["data_mode"]) == ("HEALTHY", "SNAPSHOT")
    assert health.source_health(seeded, s, t("2026-10-25T00:00:00Z"))["status"] == "STALE"                  # the same log, a later clock
    manual = seeded + [run(s, "2026-10-08T06:41:00Z")]
    assert health.source_health(manual, s, t("2026-10-09T00:00:00Z"))["data_mode"] == "SNAPSHOT"            # a run started by hand does not make a source automated
    sched = manual + [run(s, "2026-10-15T06:41:00Z", "UNCHANGED", "schedule")]
    h = health.source_health(sched, s, t("2026-10-16T00:00:00Z")); assert (h["status"], h["data_mode"], h["scheduled_runs"]) == ("HEALTHY", "AUTOMATED", 1)
    h = health.source_health(sched, s, t("2026-11-20T00:00:00Z")); assert (h["status"], h["data_mode"]) == ("STALE", "SNAPSHOT")       # a scheduler that stopped is no longer automated
    failed = sched + [run(s, "2026-10-22T06:41:00Z", "FAILED", "schedule", error="HTTP 503 from x")]
    h = health.source_health(failed, s, t("2026-10-22T07:00:00Z"))
    assert h["status"] == "FAILED" and "503" in h["failure_reason"] and h["last_successful_fetch"] == "2026-10-15T06:41:00Z" and h["last_attempted_fetch"] == "2026-10-22T06:41:00Z"
    hourly = [run(s, "2026-10-22T06:41:00Z", "UPDATED", "schedule")]
    assert health.source_health(hourly, s, t("2026-10-22T06:50:00Z"))["data_mode"] == "AUTOMATED"            # LIVE needs an hourly schedule, which no source has
    assert all(c["check_days"] >= 1 for c in sources.SOURCES.values())
    rows = [health.source_health(sched, x, t("2026-10-16T00:00:00Z")) for x in sources.SOURCES]
    assert health.overall_mode(rows) == "SNAPSHOT"                                                            # one automated source does not make the forecast inputs automated
    research = health.research_sources()
    assert {r["status"] for r in research} <= {"RESEARCH ONLY", "NOT CONNECTED"} and any("GDELT" in r["source"] for r in research) and any(r["source"] in ("Reddit", "X") and r["status"] == "NOT CONNECTED" for r in research)


def test_OPT8_refresh_records_one_run_per_source_and_survives_a_failing_adapter(tmp_path):
    log = str(tmp_path / "log.jsonl")
    def ok(sid, cfg, **kw): return adapters._record(sid, cfg, "2026-10-08T06:41:00Z", result="UNCHANGED", http_status=200, record_count=1, checksum="c")
    def boom(sid, cfg, **kw): raise RuntimeError("bug")
    out = pipeline.refresh(("fuel", "bls"), trigger="schedule", log_path=log, adapters_map={"eia_series": ok, "bls_releases": boom})
    assert len(out) == 10 and [r["result"] for r in out].count("FAILED") == 8 and all(r["trigger"] == "schedule" and RUN_FIELDS <= set(r) for r in out)
    assert "RuntimeError" in out[-1]["error"] and records.verify(log) == [] and len(records.read(log)) == 10
    st = pipeline.write_status(now=datetime.datetime(2026, 10, 8, 7, tzinfo=datetime.timezone.utc), status_path=str(tmp_path / "status.json"), log_path=log, ledger_path=str(tmp_path / "l.jsonl"), outcomes_path=str(tmp_path / "o.jsonl"))
    by = {s["source"]: s for s in st["sources"]}
    assert by["bls_IC1312"]["status"] == "FAILED" and by["eia_brent"]["status"] == "HEALTHY" and by["news_splash247"]["status"] == "NOT CONFIGURED" and st["forecast_inputs_data_mode"] == "SNAPSHOT"
    assert pipeline.detect_trigger() in ("manual", "schedule", "manual-dispatch")


@pytest.mark.research_record
def test_OPT9_workflows_match_the_declared_schedules_and_keep_their_results():
    wf = {n: yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", n), encoding="utf-8")) for n in ("news_ingest.yml", "data_refresh.yml", "ci.yml")}
    text = {n: open(os.path.join(ROOT, ".github", "workflows", n), encoding="utf-8").read() for n in wf}
    crons = lambda n: sorted(c["cron"] for c in wf[n][True]["schedule"])                                     # YAML reads the key `on` as True
    assert crons("news_ingest.yml") == [sources.GROUP_SCHEDULE["news"]["cron"]] and crons("data_refresh.yml") == sorted([sources.GROUP_SCHEDULE["fuel"]["cron"], sources.GROUP_SCHEDULE["bls"]["cron"]])
    assert wf["news_ingest.yml"]["concurrency"]["group"] == wf["data_refresh.yml"]["concurrency"]["group"] and "schedule" not in wf["ci.yml"][True]
    for n in ("news_ingest.yml", "data_refresh.yml"):
        runs = [s.get("run", "") for s in next(iter(wf[n]["jobs"].values()))["steps"]]; i = lambda needle: next(k for k, r in enumerate(runs) if needle in r)
        assert i("src.ops.cli run") < i("pytest") < i("src.ops.cli verify") < i("git push") and "git add" in runs[i("git push")] and "operations" in runs[i("git push")]
        assert "--force" not in text[n] and "secrets." not in text[n] and "NOT YET EXECUTED ON GITHUB" in text[n] and "pipefail" in runs[i("src.ops.cli run")] and "|| true" not in runs[i("src.ops.cli run")]
    assert "operations/news" in text["news_ingest.yml"] and "data/news.sqlite" in text["news_ingest.yml"]   # the event store is exported and uploaded, not discarded
    assert "check_benchmark_ledger.py" in text["ci.yml"] and "benchmark_ledger.sha256" in text["ci.yml"]


def test_OPT10_operations_never_write_to_the_benchmark(ops_area):
    """The operational pipeline has its own files; the benchmark snapshot, store and ledger are read-only for it."""
    want = open(os.path.join(config.EVAL_DIR, "benchmark_ledger.sha256"), encoding="utf-8").read().split()[0]
    snap = {f: sha(os.path.join(config.SNAPSHOT_DIR, f)) for f in sorted(os.listdir(config.SNAPSHOT_DIR)) if f.startswith(("SRC-01_eia_E", "SRC-08_eia_R", "SRC-09_bls"))}
    pipeline.issue_forecasts(ops_area["db"], ops_area["current"], str(os.path.dirname(ops_area["ledger"])) + "/again.jsonl", now=lambda: "2026-09-17T00:00:00Z")
    assert sha(os.path.join(config.EVAL_DIR, "forecast_ledger.csv")) == want                              # the validated ledger is byte-identical
    assert {f: sha(os.path.join(config.SNAPSHOT_DIR, f)) for f in snap} == snap
    code = "".join(open(os.path.join(ROOT, "src", "ops", f), encoding="utf-8").read() for f in ("adapters.py", "pipeline.py", "cli.py", "config.py"))
    assert "EVAL_DIR" not in code and "export_ledger" not in code and "run_backtest" not in code and "base.DB_PATH" not in code and "config.DB_PATH" not in code
    assert code.count('"evaluation"') == 1 and 'open(ledger_path, newline=""' in code                    # the one evaluation file it touches (the ablation ledger) is opened for reading
    assert code.count("SNAPSHOT_DIR") == 1 and "shutil.copyfile(os.path.join(snapshot_dir" in code     # the snapshot is only ever read, to seed
    assert ocfg.OPS_DB_PATH != config.DB_PATH and ocfg.CURRENT_DIR.startswith(sources.OPS_DIR) and not ocfg.CURRENT_DIR.startswith(config.SNAPSHOT_DIR)


def test_OPT11_a_hosted_run_identity_is_recorded_only_when_the_runner_provides_one(tmp_path, monkeypatch):
    def ok(sid, cfg, **kw): return adapters._record(sid, cfg, "2026-10-09T14:23:00Z", result="UNCHANGED", http_status=200, record_count=1, checksum="c")
    amap = {"eia_series": ok, "bls_releases": ok}
    for k in ("GITHUB_RUN_ID", "GITHUB_ACTIONS", "GITHUB_REPOSITORY", "GITHUB_EVENT_NAME"): monkeypatch.delenv(k, raising=False)
    local = pipeline.refresh(("fuel",), log_path=str(tmp_path / "a.jsonl"), adapters_map=amap)
    assert all(r["workflow_run"] is None and r["trigger"] == "manual" for r in local)                       # a run on any other machine carries no run identifier
    monkeypatch.setenv("GITHUB_RUN_ID", "123456789")                                                        # a run id alone is not enough: the runner must say it is GitHub Actions
    assert pipeline.workflow_run() is None
    for k, v in (("GITHUB_ACTIONS", "true"), ("GITHUB_REPOSITORY", "owner/airpulse"), ("GITHUB_RUN_ATTEMPT", "1"), ("GITHUB_WORKFLOW", "data-refresh"), ("GITHUB_SHA", "abc"), ("GITHUB_EVENT_NAME", "schedule")): monkeypatch.setenv(k, v)
    hosted = pipeline.refresh(("fuel",), log_path=str(tmp_path / "b.jsonl"), adapters_map=amap)
    w = hosted[0]["workflow_run"]
    assert hosted[0]["trigger"] == "schedule" and w["run_id"] == "123456789" and w["workflow"] == "data-refresh" and w["url"] == "https://github.com/owner/airpulse/actions/runs/123456789"
    h = health.source_health(hosted, "eia_jet_fuel", datetime.datetime(2026, 10, 9, 15, tzinfo=datetime.timezone.utc))
    assert h["data_mode"] == "AUTOMATED" and h["last_workflow_run"].endswith("/actions/runs/123456789")
    drv = open(os.path.join(ROOT, "scripts", "run_workflow_locally.py"), encoding="utf-8").read()
    assert 'env.pop(k, None)' in drv and '"GITHUB_RUN_ID"' in drv                                            # the local stand-in removes any run identity instead of inventing one


@pytest.mark.research_record
def test_OPT12_the_operational_classification_follows_the_records_and_nothing_else():
    """A to D are derived from the run records: only records that carry a hosted run identity can raise the class."""
    sys.path.insert(0, os.path.join(ROOT, "scripts")); import operational_evidence as oe
    now = datetime.datetime(2026, 10, 12, 15, tzinfo=datetime.timezone.utc); stamp = "2026-10-12T14:23:00Z"
    wr = lambda n, wf: {"run_id": str(n), "run_attempt": "1", "workflow": wf, "repository": "owner/airpulse", "commit": "abc", "url": f"https://github.com/owner/airpulse/actions/runs/{n}"}

    def recs(trigger, hosted, groups=("fuel", "bls", "news"), at=stamp, result="UNCHANGED"):
        return [{"source": s, "group": c["group"], "retrieved_at": at, "result": result, "trigger": trigger, "duration_seconds": 1.0, "new_records": 0, "validation": "passed: x", "error": "",
                 "workflow_run": (wr(7 if c["group"] == "news" else 8, "news-ingest" if c["group"] == "news" else "data-refresh") if hosted else None)} for s, c in sources.SOURCES.items() if c["group"] in groups]
    by_hand = recs("manual", False)
    assert oe.classify(by_hand, now, clean_ok=False)[0] == "D. MANUAL/SNAPSHOT" and oe.classify(by_hand, now, clean_ok=True)[0] == "C. BUILT BUT HOSTING-BLOCKED"
    assert oe.classify(recs("schedule", False), now, clean_ok=True)[0] == "C. BUILT BUT HOSTING-BLOCKED"       # the word "schedule" without a hosted run identity proves nothing
    assert oe.classify(recs("manual-dispatch", True), now, clean_ok=True)[0] == "B. DEPLOYED BUT NOT YET SCHEDULE-VERIFIED"
    part = recs("manual-dispatch", True, groups=("fuel", "bls")) + recs("manual", False, groups=("news",))
    letter, why = oe.classify(part, now, clean_ok=True); assert letter.startswith("B.") and "news" in why
    mixed = recs("schedule", True, groups=("fuel", "bls")) + recs("manual-dispatch", True, groups=("news",))
    letter, why = oe.classify(mixed, now, clean_ok=True); assert letter.startswith("B.") and why.endswith("news")   # one group still waits for its first scheduled run
    assert oe.classify(recs("schedule", True), now, clean_ok=False)[0] == "A. OPERATIONAL"
    later = now + datetime.timedelta(days=30)
    assert oe.classify(recs("schedule", True), later, clean_ok=True)[0].startswith("B.")                       # scheduled runs that stopped are no longer operational
    failed = recs("schedule", True) + recs("schedule", True, groups=("fuel",), at="2026-10-12T14:40:00Z", result="FAILED")
    assert oe.classify(failed, now, clean_ok=True)[0].startswith("B.")
    runs = oe.hosted_runs(recs("schedule", True), [{"workflow_run": wr(8, "data-refresh"), "target_period": "2026-09"}] * 40)
    assert [x["run_id"] for x in runs] == ["7", "8"] or [x["run_id"] for x in runs] == ["8", "7"]
    dr = next(x for x in runs if x["run_id"] == "8")
    assert dr["trigger"] == "schedule" and dr["forecasts_issued"] == 40 and len(dr["sources_fetched"]) == 10 and dr["validation"] == "passed" and dr["url"].endswith("/actions/runs/8") and dr["last_fetch_completed"] == "2026-10-12T14:23:01Z"
    assert oe.hosted_runs(by_hand, []) == []
    real = records.read(sources.INGESTION_LOG)
    assert oe.classify(real, clean_ok=True)[0][0] in "BC" or any(r.get("trigger") == "schedule" and r.get("workflow_run") for r in real)   # the repository's own records: never A without scheduled hosted runs
