"""Operational side of the aviation layer: unattended refresh of the two official files, the Hong Kong operational
aggregates, and the quality gate that decides whether the layer may be published.

  eurocontrol   daily airport traffic, one file per year (non-commercial reuse). The current year is checked on every run,
                the year before it during the first three months (late additions).
  usdot         monthly nonstop departures between US and foreign airports (public domain), one file for all years.

The research snapshot (research/aviation_data/v4) is the frozen input of the experiments of protocol 4.0 and is never
written here. The operational copies live in operations/aviation/official: seeded from the snapshot once, afterwards
replaced only by an answer that passed validation. A failed, invalid or rate-limited answer leaves the held file in place
and is recorded; nothing is invented and a missing period stays missing.

Publication-aware: the publisher's own change time is read first (HTTP Last-Modified, the portal's rowsUpdatedAt) and the
file is downloaded only when it is newer than the file held."""
import datetime, email.utils, gzip, hashlib, io, json, os, re, shutil, time, urllib.error, urllib.request
import pandas as pd
from src.ingestion import loaders
from src.observability import records
from src.ops import pipeline
from src.aviation import activity, collector, config as cfg, validation

EUR_URL = "https://www.eurocontrol.int/performance/data/download/csv/airport_traffic_{year}.csv"
USD_URL = "https://data.transportation.gov/api/views/innc-gbgc/rows.csv?accessType=DOWNLOAD"
USD_META = "https://data.transportation.gov/api/views/innc-gbgc.json"
EUR_COLUMNS = ("FLT_DATE", "APT_ICAO", "FLT_DEP_1", "FLT_ARR_1", "FLT_TOT_1")
USD_COLUMNS = ("Year", "Month", "usg_apt", "fg_apt", "carrier", "carriergroup", "Scheduled", "Charter", "Total")
EUR_FILE = "airport_traffic_{year}.csv.gz"
USD_FILE = "international_report_departures.csv.gz"
SUCCESS = ("NEW", "REVISED", "UNCHANGED", "SEEDED")
MIN_SHARE_OF_HELD = 0.98        # a new file with fewer than this share of the rows held is refused (a truncated download, not a revision)
HKG_FILE = "hkg_operations.json"
STATUS_FILE = "status.json"


def official_dir(out_dir=None, name=""):
    return os.path.join(out_dir or cfg.OPS_DIR, "official", name)


def _epoch(iso):
    return datetime.datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc).timestamp()


def _gz(raw):
    b = io.BytesIO()
    with gzip.GzipFile(fileobj=b, mode="wb", mtime=0) as g: g.write(raw)             # mtime 0: the same content always gives the same file
    return b.getvalue()


def _held(path):
    """Sidecar of a held file after its checksum was verified; None when there is no file. An altered file raises."""
    return loaders.verify_file(path) if os.path.exists(path) else None


def _put(path, body, meta):
    """Put a validated file and its sidecar in place; the old pair stays until both new files are written."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".new", "wb") as f: f.write(body)
    with open(path + ".meta.json.new", "w", encoding="utf-8", newline="\n") as f: json.dump(meta, f, indent=1, sort_keys=True)
    os.replace(path + ".new", path); os.replace(path + ".meta.json.new", path + ".meta.json")


def http_head(url, timeout=60):
    """(status, headers) of a HEAD request; an HTTP error status is returned, a network failure raises."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": collector.UA}, method="HEAD"), timeout=timeout) as r: return r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {})


def big_get(url):
    return collector.http_get(url, timeout=1200)


# ---------------------------------------------------------------------------------------------------------------- validation

def validate_eurocontrol(raw, year, today, held_rows=0):
    """(problems, facts) of one year file. Any problem refuses the file."""
    try: df = pd.read_csv(io.BytesIO(raw), usecols=list(EUR_COLUMNS))
    except Exception as e: return [f"cannot be parsed ({type(e).__name__}: {str(e)[:100]})"], {}
    p = []; d = pd.to_datetime(df["FLT_DATE"].astype(str).str[:10], errors="coerce"); num = df[["FLT_DEP_1", "FLT_ARR_1", "FLT_TOT_1"]].apply(pd.to_numeric, errors="coerce")
    if df.empty: return ["no row"], {}
    if d.isna().any(): p.append(f"{int(d.isna().sum())} dates cannot be read")
    if (d.dt.year != year).any(): p.append("dates outside the year of the file")
    if (d > pd.Timestamp(today)).any(): p.append("dates in the future")
    if num.isna().any().any() or (num < 0).any().any(): p.append("counts missing or negative")
    if not df["APT_ICAO"].astype(str).str.match(r"^[A-Z]{4}$").all(): p.append("airport codes that are not four letters")
    if df.duplicated(["FLT_DATE", "APT_ICAO"]).any(): p.append("an airport and day listed twice")
    if (num["FLT_TOT_1"] != num["FLT_DEP_1"] + num["FLT_ARR_1"]).any(): p.append("total differs from departures plus arrivals")
    if len(df) < MIN_SHARE_OF_HELD * held_rows: p.append(f"fewer rows than held ({len(df)} against {held_rows})")
    return p, {"rows": int(len(df)), "latest_observation": None if d.isna().all() else d.max().strftime("%Y-%m-%d"), "airports": int(df["APT_ICAO"].nunique())}


def validate_usdot(raw, today, held_rows=0, held_latest=None):
    try: df = pd.read_csv(io.BytesIO(raw), usecols=list(USD_COLUMNS), dtype={"carrier": str})
    except Exception as e: return [f"cannot be parsed ({type(e).__name__}: {str(e)[:100]})"], {}
    if df.empty: return ["no row"], {}
    p = []; num = df[["Year", "Month", "Scheduled", "Charter", "Total"]].apply(pd.to_numeric, errors="coerce")
    if num.isna().any().any() or (num[["Scheduled", "Charter", "Total"]] < 0).any().any(): p.append("counts missing or negative")
    if not num["Month"].between(1, 12).all(): p.append("month outside 1 to 12")
    month = (num["Year"].astype("Int64").astype(str) + "-" + num["Month"].astype("Int64").astype(str).str.zfill(2)); latest = month.max()
    if latest > str(today)[:7]: p.append("months in the future")
    if (num["Total"] != num["Scheduled"] + num["Charter"]).any(): p.append("total differs from scheduled plus charter")
    for c in ("usg_apt", "fg_apt"):
        if not df[c].astype(str).str.match(r"^[A-Z0-9]{3}$").all(): p.append(f"{c}: codes that are not three characters")
    if len(df) < MIN_SHARE_OF_HELD * held_rows: p.append(f"fewer rows than held ({len(df)} against {held_rows})")
    if held_latest and latest < held_latest: p.append(f"ends earlier than the file held ({latest} against {held_latest})")
    return p, {"rows": int(len(df)), "latest_observation": latest}


def _facts(path, kind, today):
    """Rows and newest period of a held file, from its content."""
    raw = gzip.decompress(open(path, "rb").read())
    if kind == "eurocontrol": return validate_eurocontrol(raw, int(re.search(r"(\d{4})", os.path.basename(path)).group(1)), today)[1]
    return validate_usdot(raw, today)[1]


# ---------------------------------------------------------------------------------------------------------------- seed and refresh

def seed(out_dir=None, now=None, snapshot_dir=None):
    """Copy the snapshot files that are not held yet. One SEEDED record per source, carrying the snapshot's own retrieval time."""
    out_dir = out_dir or cfg.OPS_DIR; snapshot_dir = snapshot_dir or cfg.SNAPSHOT_DIR; now = now or collector.now_utc(); done = []
    for name in ("eurocontrol", "usdot"):
        src, dst = os.path.join(snapshot_dir, name), official_dir(out_dir, name); copied = []
        for f in sorted(os.listdir(src)) if os.path.isdir(src) else []:
            if f.endswith(".meta.json") or os.path.exists(os.path.join(dst, f)): continue
            meta = loaders.verify_file(os.path.join(src, f)); os.makedirs(dst, exist_ok=True)
            for ext in ("", ".meta.json"): shutil.copyfile(os.path.join(src, f + ext), os.path.join(dst, f + ext))
            copied.append((f, meta))
        if not copied: continue
        newest = max(copied, key=lambda c: c[0]); facts = _facts(os.path.join(dst, newest[0]), name, now[:10])
        done.append(records.append(collector.log_path(out_dir), {"source": name, "result": "SEEDED", "trigger": "seed", "fetched_at": max(m["retrieved_at"] for _, m in copied), "recorded_at": now,
                                                                 "files": [f for f, _ in copied], "latest_observation": facts.get("latest_observation"), "rows": facts.get("rows"), "file_sha256": newest[1]["sha256"],
                                                                 "note": "copied from the research snapshot; fetched_at is the time of that fetch"}))
    return done


def _years(now):
    y, m = int(now[:4]), int(now[5:7])
    return [y - 1, y] if m <= 3 else [y]


def refresh_eurocontrol(get=None, head=http_head, now=None, out_dir=None, trigger=None, sleep=time.sleep, years=None):
    """One run record. Each year file is checked against the publisher's change time and replaced only by a valid, different answer."""
    out_dir = out_dir or cfg.OPS_DIR; now = now or collector.now_utc(); trigger = trigger or pipeline.detect_trigger(); get = get or big_get; files, latest, rows, sha = {}, None, None, None
    for year in years or _years(now):
        path = os.path.join(official_dir(out_dir, "eurocontrol"), EUR_FILE.format(year=year)); url = EUR_URL.format(year=year); info = {"result": "FAILED", "http": None, "error": ""}; files[str(year)] = info
        try: held = _held(path)
        except loaders.IngestionError as e: info.update(result="INVALID", error=f"held file: {e}"); continue
        try:
            code, headers = head(url); info["http"] = code; modified = headers.get("Last-Modified")
            if code == 200 and held and modified and email.utils.parsedate_to_datetime(modified).timestamp() <= _epoch(held["retrieved_at"]):
                facts = _facts(path, "eurocontrol", now[:10]); info.update(result="UNCHANGED", source_last_modified=modified, **facts); continue
        except Exception as e: info["error"] = f"change time not readable ({type(e).__name__})"                # not fatal: the file itself is asked for
        r = collector.fetch(url, get=get, sleep=sleep); info.update(http=r["http"], attempts=r["attempts"])
        if r["status"] != "OK": info.update(result=r["status"], error=r["error"]); continue
        held_rows = _facts(path, "eurocontrol", now[:10]).get("rows", 0) if held else 0
        problems, facts = validate_eurocontrol(r["body"], year, now[:10], held_rows)
        if problems: info.update(result="INVALID", error="validation failed: " + "; ".join(problems)); continue
        raw_sha = hashlib.sha256(r["body"]).hexdigest()
        if held and held.get("raw_sha256") == raw_sha: info.update(result="UNCHANGED", error="", **facts); continue
        body = _gz(r["body"])
        _put(path, body, {"source_id": "AV-11", "url": url, "retrieved_at": now, "sha256": hashlib.sha256(body).hexdigest(), "http_status": 200, "bytes": len(body), "raw_sha256": raw_sha, "raw_bytes": len(r["body"]),
                          "licence": "non-commercial reuse with attribution (EUROCONTROL disclaimer)", "note": f"operational refresh; previous file {held['sha256'][:16] if held else 'none'}"})
        info.update(result="REVISED" if held else "NEW", error="", file_sha256=hashlib.sha256(body).hexdigest(), **facts)
    for y in sorted(files):
        if files[y].get("latest_observation"): latest, rows, sha = files[y]["latest_observation"], files[y]["rows"], files[y].get("file_sha256", sha)
    kinds = {v["result"] for v in files.values()}; bad = sorted(kinds - set(SUCCESS))
    result = ("REVISED" if kinds & {"REVISED", "NEW"} else "UNCHANGED") if not bad else ("RATE_LIMITED" if bad == ["RATE_LIMITED"] else "INVALID" if "INVALID" in bad else "FAILED")
    rec = {"source": "eurocontrol", "fetched_at": now, "trigger": trigger, "result": result, "files": files, "latest_observation": latest, "rows": rows, "file_sha256": sha, "workflow_run": pipeline.workflow_run()}
    if bad: rec["failure_reason"] = "; ".join(f"{y}: {v['error'] or v['result']}" for y, v in sorted(files.items()) if v["result"] not in SUCCESS)
    return records.append(collector.log_path(out_dir), rec)


def refresh_usdot(get=None, meta_get=collector.http_get, now=None, out_dir=None, trigger=None, sleep=time.sleep):
    """One run record. The portal's change time is read first; the file (about 85 MB) is downloaded only when its rows changed after the file held was fetched."""
    out_dir = out_dir or cfg.OPS_DIR; now = now or collector.now_utc(); trigger = trigger or pipeline.detect_trigger(); get = get or big_get
    path = os.path.join(official_dir(out_dir, "usdot"), USD_FILE); rec = {"source": "usdot", "fetched_at": now, "trigger": trigger, "result": "FAILED", "latest_observation": None, "rows": None, "file_sha256": None, "workflow_run": pipeline.workflow_run()}
    try: held = _held(path)
    except loaders.IngestionError as e: return records.append(collector.log_path(out_dir), {**rec, "result": "INVALID", "failure_reason": f"held file: {e}"})
    facts = _facts(path, "usdot", now[:10]) if held else {}; updated = None
    m = collector.fetch(USD_META, get=meta_get, sleep=sleep)
    if m["status"] == "OK":
        try: updated = int(json.loads(m["body"])["rowsUpdatedAt"])
        except (ValueError, KeyError, TypeError): updated = None
    elif m["status"] == "RATE_LIMITED": return records.append(collector.log_path(out_dir), {**rec, **facts, "result": "RATE_LIMITED", "failure_reason": m["error"], "file_sha256": held["sha256"] if held else None})
    known = held.get("rows_updated_at") if held else None                                                    # the portal's change time of the file held, when it was recorded
    if held and updated is not None and (updated == known if known is not None else updated <= _epoch(held["retrieved_at"])):
        return records.append(collector.log_path(out_dir), {**rec, **facts, "result": "UNCHANGED", "file_sha256": held["sha256"], "source_rows_updated_at": updated})
    r = collector.fetch(USD_URL, get=get, sleep=sleep)
    if r["status"] != "OK": return records.append(collector.log_path(out_dir), {**rec, **facts, "result": r["status"], "failure_reason": r["error"] or "no answer", "file_sha256": held["sha256"] if held else None})
    problems, new = validate_usdot(r["body"], now[:10], facts.get("rows", 0), facts.get("latest_observation"))
    if problems: return records.append(collector.log_path(out_dir), {**rec, **facts, "result": "INVALID", "failure_reason": "validation failed: " + "; ".join(problems), "file_sha256": held["sha256"] if held else None})
    raw_sha = hashlib.sha256(r["body"]).hexdigest()
    if held and held.get("raw_sha256") == raw_sha: return records.append(collector.log_path(out_dir), {**rec, **new, "result": "UNCHANGED", "file_sha256": held["sha256"], "source_rows_updated_at": updated})
    body = _gz(r["body"]); sha = hashlib.sha256(body).hexdigest()
    _put(path, body, {"source_id": "AV-15", "url": USD_URL, "retrieved_at": now, "sha256": sha, "http_status": 200, "bytes": len(body), "raw_sha256": raw_sha, "raw_bytes": len(r["body"]), "rows_updated_at": updated,
                      "licence": "Public Domain U.S. Government", "note": f"operational refresh; previous file {held['sha256'][:16] if held else 'none'}"})
    return records.append(collector.log_path(out_dir), {**rec, **new, "result": "REVISED" if held else "NEW", "file_sha256": sha, "source_rows_updated_at": updated})


# ---------------------------------------------------------------------------------------------------------------- readers, gate, status

def european_daily(out_dir=None):
    return activity.european_daily(official_dir(out_dir, "eurocontrol"))


def us_international(out_dir=None):
    return activity.us_international(official_dir(out_dir, "usdot"))


CRITICAL = ("duplicate", "bad_timestamp", "bad_event_type", "bad_category", "missing_schema_field", "bad_coordinates", "event_after_ingestion")


def quality(out_dir=None, now=None):
    """The gate of the layer. critical: reasons for which nothing of a feed may be published (a broken record chain, a file that
    differs from its checksum, records that break the schema). warnings: reported, never repaired."""
    out_dir = out_dir or cfg.OPS_DIR; out = {"critical": {}, "warnings": {}, "checked": {}}
    bad = records.verify(collector.log_path(out_dir))
    if bad: out["critical"]["log"] = bad[:3]
    try:
        recs, days = collector.load_hkia(out_dir); qa = validation.check(recs); out["checked"]["hkia"] = {"records": qa["records"], "days": len(days)}
        hit = {k: qa["problems"][k]["count"] for k in CRITICAL if qa["problems"][k]["count"]}
        if hit: out["critical"]["hkia"] = [f"{k}: {n} records" for k, n in sorted(hit.items())]
        soft = {k: v["count"] for k, v in qa["problems"].items() if v["count"] and k not in CRITICAL}
        if soft: out["warnings"]["hkia"] = [f"{k}: {n} records" for k, n in sorted(soft.items())]
    except Exception as e: out["critical"]["hkia"] = [f"archive cannot be read ({type(e).__name__}: {str(e)[:120]})"]
    from src.observability import registry
    active = {d_["id"]: bool(d_["active"]) for d_ in registry.declared()[1]}
    for name, pattern in (("eurocontrol", "airport_traffic_"), ("usdot", "international_report_departures")):
        if not active.get(name, True): out["checked"][name] = {"switched_off": True}; continue          # a source that is switched off holds no file and needs none
        d = official_dir(out_dir, name); files = sorted(f for f in os.listdir(d) if f.startswith(pattern) and f.endswith(".csv.gz")) if os.path.isdir(d) else []
        if not files: out["critical"][name] = ["no file held"]; continue
        try:
            for f in files: loaders.verify_file(os.path.join(d, f))
            out["checked"][name] = {"files": len(files)}
        except loaders.IngestionError as e: out["critical"][name] = [str(e)]
    return out


def hkg(out_dir=None, now=None):
    """Research use (not part of the unattended run since CL-020): recompute the Hong Kong aggregates with their anomaly reading from the archive,
    append newly detected events to the store, and keep the result with the operational files."""
    from src.aviation import experiment
    out = experiment.hkg_operations(now, True, out_dir); out["generated"] = now or collector.now_utc()
    path = os.path.join(out_dir or cfg.OPS_DIR, HKG_FILE)
    with open(path, "w", encoding="utf-8", newline="\n") as f: json.dump(out, f, indent=1, sort_keys=True, default=str)
    return out


def write_status(out_dir=None, now=None):
    """operations/aviation/status.json: feed health from the log, the quality gate, and when it was written."""
    out_dir = out_dir or cfg.OPS_DIR; now = now or collector.now_utc()
    st = {"generated": now, **collector.status(out_dir, now), "quality": quality(out_dir, now)}
    with open(os.path.join(out_dir, STATUS_FILE), "w", encoding="utf-8", newline="\n") as f: json.dump(st, f, indent=1, sort_keys=True)
    return st


def run(sources=("hkia", "positions", "eurocontrol", "usdot"), days=3, fetch=True, now=None, out_dir=None):
    """One operational run. Returns (summary, exit code). A source that fails does not stop the others; the exit code is 2 when any failed."""
    now = now or collector.now_utc(); summary = {"seeded": [r["source"] for r in seed(out_dir, now)], "runs": {}, "errors": []}
    if fetch:
        t = datetime.date.fromisoformat(now[:10])
        steps = {"hkia": lambda: [r["result"] for r in collector.collect_hkia([(t - datetime.timedelta(days=k)).isoformat() for k in range(days, 0, -1)], out_dir=out_dir)],
                 "positions": lambda: [collector.collect_positions(out_dir=out_dir)["result"]], "eurocontrol": lambda: [refresh_eurocontrol(now=now, out_dir=out_dir)["result"]],
                 "usdot": lambda: [refresh_usdot(now=now, out_dir=out_dir)["result"]]}
        for s in sources:
            try: summary["runs"][s] = steps[s]()
            except Exception as e: summary["errors"].append(f"{s}: {type(e).__name__}: {str(e)[:160]}")
    try:                                                                  # the archive must be readable; the counts the product shows are computed from it at export
        recs, days = collector.load_hkia(out_dir); summary["hong_kong"] = {"days": len(days), "last_day": max(days) if days else None, "records": len(recs)}
    except Exception as e: summary["errors"].append(f"hong kong archive: {type(e).__name__}: {str(e)[:160]}")
    st = write_status(out_dir); summary["critical"] = st["quality"]["critical"]
    failed = [s for s, rs in summary["runs"].items() if s != "positions" and any(r not in SUCCESS for r in rs)]      # the position picture is a visualisation: its gaps are recorded, they do not fail the run
    summary["failed_sources"] = failed
    return summary, (2 if failed or summary["errors"] or summary["critical"] else 0)
