"""Collector of operational aviation data (protocol 4.0, section 12). Two sources whose terms allow the use:

  hkia       Hong Kong International Airport flight information (official; data.gov.hk terms: commercial and non-commercial
             use with attribution): every flight of a day, cargo flights apart, with its status.
  positions  community position feed adsb.lol (ODbL): aircraft within a radius of each airport at one moment. A count of
             aircraft seen, with coverage that differs by region. A visualisation, not an activity measure.

Raw answers are archived unmodified and versioned (a day whose content changed gets a new version; nothing is overwritten),
every attempt is written to an append-only log, retries are bounded, and a missing or partial answer is recorded and
never turned into a count."""
import datetime, gzip, hashlib, io, json, os, time, urllib.error, urllib.request
from src.observability import records
from src.ops import pipeline
from src.aviation import aircraft, airports, config as cfg, normalizer, validation

HKIA_URL = "https://www.hongkongairport.com/flightinfo-rest/rest/flights/past?date={day}&lang=en&cargo={cargo}&arrival={arrival}"
POINT_URL = "https://api.adsb.lol/v2/point/{lat:.4f}/{lon:.4f}/{radius}"
PARTS = (("cargo_arr", True, True), ("cargo_dep", True, False), ("pax_arr", False, True), ("pax_dep", False, False))
UA = "AirPulse/1.0 (aviation operations monitor; official open data)"
now_utc = lambda: datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
log_path = lambda out_dir=None: os.path.join(out_dir or cfg.OPS_DIR, "ingestion_log.jsonl")


def http_get(url, timeout=30):
    """(status, body, headers). An HTTP error status is returned, not raised; a network failure raises."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r: return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, b"", dict(e.headers or {})


def fetch(url, get=http_get, retries=3, sleep=time.sleep, backoff=2.0):
    """One resource with bounded retries. Returns {'status': OK | RATE_LIMITED | FAILED, 'http', 'body', 'attempts', 'error'}.
    A 429 waits for Retry-After (at most 60 s) and tries again; a 5xx or a network error tries again; any other status fails at once."""
    last = {"status": "FAILED", "http": None, "body": None, "attempts": 0, "error": ""}
    for k in range(retries):
        last["attempts"] = k + 1
        try: code, body, headers = get(url)
        except Exception as e:
            last.update(status="FAILED", http=None, error=f"{type(e).__name__}: {str(e)[:120]}"); sleep(backoff * (k + 1)); continue
        last["http"] = code
        if code == 200 and body: return {**last, "status": "OK", "body": body, "error": ""}
        if code == 429:
            try: wait = min(float(headers.get("Retry-After", backoff * (k + 1))), 60.0)
            except (TypeError, ValueError): wait = backoff * (k + 1)
            last.update(status="RATE_LIMITED", error="HTTP 429"); sleep(wait); continue
        if code == 200 or 500 <= code < 600:
            last.update(status="FAILED", error="empty body" if code == 200 else f"HTTP {code}"); sleep(backoff * (k + 1)); continue
        return {**last, "status": "FAILED", "error": f"HTTP {code}"}
    return last


def _gz(obj):
    b = io.BytesIO()
    with gzip.GzipFile(fileobj=b, mode="wb", mtime=0) as g: g.write(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return b.getvalue()


def _day_block(body, day):
    """The one block of a flight-information answer, or None when the answer is not what the interface documents."""
    try: j = json.loads(body)
    except ValueError: return None
    blocks = j if isinstance(j, list) else [j]
    hit = [b for b in blocks if isinstance(b, dict) and b.get("date") == day and isinstance(b.get("list"), list)]
    return hit[0] if len(hit) == 1 else None


def collect_hkia(days, get=http_get, now=None, out_dir=None, trigger=None, sleep=time.sleep, pause=0.4):
    """Archive the four lists of each day. A day is stored only when all four answered and parsed; a changed day gets a new version.
    Returns the log records written (one per day)."""
    out_dir = out_dir or cfg.OPS_DIR; trigger = trigger or pipeline.detect_trigger(); log = log_path(out_dir); done = []
    stored = {}
    for r in records.read(log):
        if r.get("source") == "hkia" and r.get("result") in ("NEW", "REVISED"): stored[r["day"]] = r
    for day in days:
        fetched_at = now or now_utc(); parts, info, texts = {}, {}, {}
        for name, cargo, arrival in PARTS:
            r = fetch(HKIA_URL.format(day=day, cargo=str(cargo).lower(), arrival=str(arrival).lower()), get=get, sleep=sleep)
            block = _day_block(r["body"], day) if r["status"] == "OK" else None
            status = "OK" if block is not None else "INVALID" if r["status"] == "OK" else r["status"]
            info[name] = {"status": status, "http": r["http"], "attempts": r["attempts"], "error": r["error"] if status != "INVALID" else "answer is not one block for the day asked",
                          "bytes": len(r["body"] or b""), "sha256": hashlib.sha256(r["body"]).hexdigest() if r["body"] else None, "flights": len(block["list"]) if block else None}
            if block is not None: texts[name] = r["body"].decode("utf-8")
            sleep(pause)
        ok = [n for n in info if info[n]["status"] == "OK"]; rec = {"source": "hkia", "day": day, "fetched_at": fetched_at, "trigger": trigger, "parts": info}
        if len(ok) == len(PARTS):
            key = hashlib.sha256("".join(info[n]["sha256"] for n, _, _ in PARTS).encode()).hexdigest(); prev = stored.get(day)
            if prev and prev["content_key"] == key: rec.update(result="UNCHANGED", version=prev["version"], content_key=key)
            else:
                version = (prev["version"] + 1) if prev else 1; rel = os.path.join("raw", "hkia", f"{day}.v{version}.json.gz"); path = os.path.join(out_dir, rel)
                if os.path.exists(path): raise RuntimeError(f"{rel} exists and the log does not know it: refusing to overwrite")
                os.makedirs(os.path.dirname(path), exist_ok=True); body = _gz({"day": day, "retrieved_at": fetched_at, "parts": texts})
                with open(path, "wb") as f: f.write(body)
                rec.update(result="REVISED" if prev else "NEW", version=version, content_key=key, file=rel.replace(os.sep, "/"), file_sha256=hashlib.sha256(body).hexdigest())
        else:
            kinds = {info[n]["status"] for n in info}
            rec.update(result="PARTIAL" if ok else "RATE_LIMITED" if kinds == {"RATE_LIMITED"} else "FAILED", version=None, content_key=None, failure_reason="; ".join(f"{n}: {info[n]['error']}" for n in info if info[n]["status"] != "OK"))
        r = records.append(log, rec); done.append(r)
        if r["result"] in ("NEW", "REVISED"): stored[day] = r
    return done


def load_hkia(out_dir=None, as_of=None, keep="last"):
    """Canonical records from the archive and the set of days it covers. as_of (ISO time): only versions retrieved by then.
    keep='first' reads each day as first archived, 'last' as last archived. A file that does not match its logged checksum raises."""
    out_dir = out_dir or cfg.OPS_DIR; chosen = {}
    for r in records.read(log_path(out_dir)):
        if r.get("source") != "hkia" or r.get("result") not in ("NEW", "REVISED") or (as_of and r["fetched_at"] > as_of): continue
        if keep == "first" and r["day"] in chosen: continue
        chosen[r["day"]] = r
    recs = []
    for day, r in sorted(chosen.items()):
        with open(os.path.join(out_dir, r["file"]), "rb") as f: body = f.read()
        if hashlib.sha256(body).hexdigest() != r["file_sha256"]: raise RuntimeError(f"{r['file']}: content differs from the checksum in the log")
        doc = json.loads(gzip.decompress(body))
        for name, cargo, arrival in PARTS:
            recs += normalizer.from_hkia(_day_block(doc["parts"][name], day), cargo, arrival, doc["retrieved_at"], r["parts"][name]["sha256"])
    return recs, set(chosen)


def collect_positions(codes=None, get=http_get, now=None, out_dir=None, trigger=None, sleep=time.sleep, pause=1.2, radius=25, budget_seconds=240, clock=time.monotonic):
    """One snapshot of the aircraft within `radius` nautical miles of each airport. Airports that did not answer are listed as such; their count is not zero, it is absent.
    Bounded: the sweep stops asking once `budget_seconds` have passed (a rate-limited interface is not waited on); airports not asked are recorded as not answered."""
    out_dir = out_dir or cfg.OPS_DIR; trigger = trigger or pipeline.detect_trigger(); fetched_at = now or now_utc(); texts, info = {}, {}; t0 = clock()
    for a in (airports.table() if codes is None else [airports.match(c) for c in codes]):
        if clock() - t0 > budget_seconds:
            info[a["airport_iata"]] = {"status": "NOT_ASKED", "http": None, "error": f"time budget of {budget_seconds} s used"}; continue
        r = fetch(POINT_URL.format(lat=a["latitude"], lon=a["longitude"], radius=radius), get=lambda u: get(u, timeout=15) if get is http_get else get(u), sleep=lambda s: sleep(min(s, 5.0)), retries=2); ok = False
        if r["status"] == "OK":
            try: ok = isinstance(json.loads(r["body"]).get("ac"), list)
            except (ValueError, AttributeError): ok = False
        info[a["airport_iata"]] = {"status": "OK" if ok else "INVALID" if r["status"] == "OK" else r["status"], "http": r["http"], "error": r["error"]}
        if ok: texts[a["airport_iata"]] = r["body"].decode("utf-8")
        sleep(pause)
    rec = {"source": "positions", "fetched_at": fetched_at, "trigger": trigger, "airports_asked": len(info), "airports_answered": len(texts), "failed": sorted(k for k, v in info.items() if v["status"] != "OK")}
    if texts:
        rel = os.path.join("raw", "positions", fetched_at.replace(":", "").replace("-", "") + ".json.gz"); path = os.path.join(out_dir, rel); os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path): raise RuntimeError(f"{rel} exists: refusing to overwrite")
        body = _gz({"retrieved_at": fetched_at, "radius_nm": radius, "airports": texts})
        with open(path, "wb") as f: f.write(body)
        rec.update(result="OK" if len(texts) == len(info) else "PARTIAL", file=rel.replace(os.sep, "/"), file_sha256=hashlib.sha256(body).hexdigest())
    else: rec.update(result="FAILED", failure_reason="no airport answered")
    return records.append(log_path(out_dir), rec)


def load_positions(out_dir=None):
    """The newest position snapshot: per airport, aircraft seen, on the ground, airborne, and by aircraft class. None when there is none."""
    out_dir = out_dir or cfg.OPS_DIR; snaps = [r for r in records.read(log_path(out_dir)) if r.get("source") == "positions" and r.get("file")]
    if not snaps: return None
    r = snaps[-1]
    with open(os.path.join(out_dir, r["file"]), "rb") as f: body = f.read()
    if hashlib.sha256(body).hexdigest() != r["file_sha256"]: raise RuntimeError(f"{r['file']}: content differs from the checksum in the log")
    doc = json.loads(gzip.decompress(body)); rows = {}
    for code, text in doc["airports"].items():
        ac = json.loads(text)["ac"]; classes = {}
        for a in ac:
            c = aircraft.classify(a.get("t"), aircraft.operator_of(a.get("flight")))["category"]; classes[c] = classes.get(c, 0) + 1
        ground = sum(1 for a in ac if a.get("alt_baro") == "ground")
        rows[code] = {"aircraft_seen": len(ac), "on_ground": ground, "airborne": len(ac) - ground, "classes": classes, "with_type": sum(1 for a in ac if a.get("t"))}
    return {"retrieved_at": doc["retrieved_at"], "radius_nm": doc["radius_nm"], "airports": rows, "not_answered": r.get("failed", [])}


def status(out_dir=None, now=None):
    """Health of each feed from the log: last attempt, last success, days archived, failures since the last success, and the freshness mode of what is held."""
    out_dir = out_dir or cfg.OPS_DIR; log = records.read(log_path(out_dir)); out = {"log_intact": not records.verify(log_path(out_dir)) if log else True, "feeds": {}}
    for src in ("hkia", "positions"):
        rs = [r for r in log if r.get("source") == src]; good = [r for r in rs if r.get("result") in ("NEW", "REVISED", "UNCHANGED", "OK", "PARTIAL") and (r.get("file") or r.get("result") == "UNCHANGED")]
        last_ok = good[-1]["fetched_at"] if good else None; since = [r for r in rs if not good or r["seq"] > good[-1]["seq"]]
        newest = max((r["day"] for r in rs if r.get("result") in ("NEW", "REVISED", "UNCHANGED")), default=None) if src == "hkia" else last_ok
        newest_time = (f"{newest}T23:59:59+08:00" if src == "hkia" and newest else newest)
        m, age = validation.mode(newest_time, now)
        out["feeds"][src] = {"attempts": len(rs), "last_attempt": rs[-1]["fetched_at"] if rs else None, "last_success": last_ok, "failures_since_last_success": sum(1 for r in since if r.get("result") in ("FAILED", "RATE_LIMITED", "PARTIAL")),
                             "last_result": rs[-1]["result"] if rs else None, "last_failure_reason": next((r.get("failure_reason") for r in reversed(rs) if r.get("failure_reason")), None),
                             "days_archived": len({r["day"] for r in rs if r.get("result") in ("NEW", "REVISED")}) if src == "hkia" else None, "newest_observation": newest_time, "mode": m, "age_hours": age,
                             "triggers": sorted({r.get("trigger") for r in rs if r.get("trigger")}), "scheduled_runs": sum(1 for r in rs if r.get("trigger") == "schedule")}
    return out
