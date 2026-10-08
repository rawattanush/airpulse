"""A source that moves, moves the site: checked with a fixture, without the network. It runs in CI, as the last step.

    python scripts/source_to_site_check.py --base /airpulse-ci/

IT CHANGES THE CHECKOUT IT RUNS IN (the flight-list archive, its log, the export, the build), so it runs only where the
checkout is thrown away: with CI=true in the environment, as on a hosted runner, or with --in-place given by hand in a
scratch clone. It never commits and never pushes.

BEFORE   the export and the build of the state held, made by the earlier steps of the job.
FIXTURE  one more day of Hong Kong flight lists: the four lists of the newest archived day, every date in them moved one day on,
         handed to the engine's own collector in place of the airport's answer. Everything after the answer is the real
         code: the check of the answer, the archive, the log, the quality report, the export, the build.
AFTER    the production run without the network, the export, the build.

Confirmed link by link, and the step fails if any link did not move:
  source   the collector recorded the day as NEW and archived its file
  engine   the archive the engine reads covers one more day, and the run passed its gate
  export   aviation.json runs through the new day and carries it in its series; the content hash of the export changed
  build    the built site holds the new export, and it differs from the build before
and nothing else moved: the files of the other features are byte for byte what they were."""
import datetime, gzip, hashlib, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True
PY = sys.executable
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.isfile(p) else None
DATE = re.compile(r"(?<![0-9])20[0-9]{2}-[01][0-9]-[0-3][0-9](?![0-9])")


def sh(args, cwd, env=None):
    p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=(os.name == "nt" and args[0] == "npm"))
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip().splitlines()[-8:]


def files(d):
    return {os.path.relpath(os.path.join(b, f), d).replace(os.sep, "/"): sha(os.path.join(b, f)) for b, _, fs in os.walk(d) for f in fs} if os.path.isdir(d) else {}


def main(argv):
    if os.environ.get("CI") != "true" and "--in-place" not in argv:
        print("this check changes the checkout it runs in. It runs in CI (CI=true); elsewhere give --in-place, in a scratch clone only."); return 1
    base = argv[argv.index("--base") + 1] if "--base" in argv else "/"
    web = os.path.join(ROOT, "airpulse-web"); data, dist = os.path.join(web, "public", "data"), os.path.join(web, "dist")
    from src.aviation import collector
    from src.observability import records
    load = lambda name: json.load(open(os.path.join(data, name), encoding="utf-8"))
    if not os.path.isfile(os.path.join(data, "core.json")) or not os.path.isfile(os.path.join(dist, "data", "aviation.json")): print("the export and the build of the state held are needed first"); return 1
    before = {"core": load("core.json"), "aviation": load("aviation.json"), "data": files(data), "built": files(os.path.join(dist, "data")), "index": sha(os.path.join(dist, "index.html"))}
    _, days0 = collector.load_hkia(); last = max(days0); nxt = (datetime.date.fromisoformat(last) + datetime.timedelta(days=1)).isoformat()
    held = [r for r in records.read(collector.log_path()) if r.get("source") == "hkia" and r.get("day") == last and r.get("result") in ("NEW", "REVISED")][-1]
    with gzip.open(os.path.join(os.path.dirname(collector.log_path()), *held["file"].split("/")), "rt", encoding="utf-8") as f: parts = json.load(f)["parts"]
    def later(m):                                                       # every date of the answer moves one day on, so its blocks stay what they were, a day later
        try: return (datetime.date.fromisoformat(m.group(0)) + datetime.timedelta(days=1)).isoformat()
        except ValueError: return m.group(0)
    answer = {(str(cargo).lower(), str(arrival).lower()): DATE.sub(later, parts[name]).encode("utf-8") for name, cargo, arrival in collector.PARTS}

    def get(url, timeout=30):                                           # the airport's answer for the new day: the lists of the day before, re-dated
        q = dict(kv.split("=") for kv in url.split("?", 1)[1].split("&")); return 200, answer[(q["cargo"], q["arrival"])], {}

    rec = collector.collect_hkia([nxt], get=get, sleep=lambda s: None, pause=0, trigger="fixture")[0]
    _, days1 = collector.load_hkia()
    steps = {"production run without the network": sh([PY, os.path.join("scripts", "production_run.py"), "--offline"], ROOT),
             "export": sh([PY, os.path.join(web, "scripts", "export_data.py")], web, {**os.environ, "AIRPULSE_ROOT": ROOT}),
             "build": sh(["npm", "run", "build"], web, {**os.environ, "VITE_BASE": base, "MSYS_NO_PATHCONV": "1"})}
    after = {"core": load("core.json"), "aviation": load("aviation.json"), "data": files(data), "built": files(os.path.join(dist, "data"))}
    a0, a1 = before["aviation"]["airport"], after["aviation"]["airport"]; moved = sorted(k for k in after["data"] if after["data"][k] != before["data"].get(k))
    checks = {
        "source: the collector recorded the new day and archived its file": rec["result"] == "NEW" and rec["day"] == nxt and os.path.isfile(os.path.join(os.path.dirname(collector.log_path()), *rec["file"].split("/"))),
        "engine: the archive covers one more day": len(days1) == len(days0) + 1 and max(days1) == nxt,
        "engine: the run completed and its gate passed": steps["production run without the network"][0] in (0, 2),
        "export: it was written": steps["export"][0] == 0,
        "export: the airport's counts run through the new day": a0["through"] == last and a1["through"] == nxt and a1["days_archived"] == a0["days_archived"] + 1 and a1["series"][-1]["d"] == nxt and a1["latest"]["day"] == nxt,
        "export: the content hash changed": before["core"]["export"]["content_hash"] != after["core"]["export"]["content_hash"],
        "export: only the files of this source moved": set(moved) == {"aviation.json", "core.json"},
        "build: it was built": steps["build"][0] == 0,
        "build: the site holds the new export": after["built"].get("aviation.json") == after["data"]["aviation.json"] and after["built"] == after["data"],
        "build: the site differs from the build before": after["built"].get("aviation.json") != before["built"].get("aviation.json"),
    }
    print(f"fixture: Hong Kong flight lists of {nxt} (the lists of {last}, every date moved one day on); record {rec['result']}, {sum(p['flights'] or 0 for p in rec['parts'].values())} flights in four lists")
    print(f"export before: through {a0['through']}, {a0['days_archived']} days, content {before['core']['export']['content_hash'][:16]}")
    print(f"export after:  through {a1['through']}, {a1['days_archived']} days, content {after['core']['export']['content_hash'][:16]}; files that moved: {', '.join(moved)}")
    for k, ok in checks.items(): print(f"  {'ok  ' if ok else 'FAIL'} {k}")
    for name, (code, tail) in steps.items():
        if code not in (0, 2) or (name != "production run without the network" and code != 0): print(f"-- {name}: exit {code}"); print("\n".join("   " + l[:200] for l in tail))
    ok = all(checks.values()); print("a source that moves, moves the site: confirmed with a fixture" if ok else "NOT CONFIRMED"); return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
