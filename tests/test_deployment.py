"""Free public hosting from one repository (CL-020): the production workflow, the allow-list of the hosted repository,
the checks before an upload, the local stand-ins. No network.

The same file runs in two places. In the research repository it checks the workflow files kept under deploy/public and the
allow-list against everything committed. In the hosted repository (PUBLIC_REPOSITORY.json at its root) it checks the
workflows that are installed and the repository itself."""
import hashlib, importlib.util, json, os, re, shutil, subprocess, sys, threading, urllib.error, urllib.request
import pytest, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
HOSTED = os.path.isfile(os.path.join(ROOT, "PUBLIC_REPOSITORY.json"))
WF_DIR = os.path.join(ROOT, ".github", "workflows") if HOSTED else os.path.join(ROOT, "deploy", "public")
P = lambda *a: os.path.join(ROOT, *a)
research_only = pytest.mark.skipif(HOSTED, reason="checks the research repository, which the hosted repository is built from")
hosted_only = pytest.mark.skipif(not HOSTED, reason="checks the hosted repository itself")


def _script(name):
    spec = importlib.util.spec_from_file_location(name, P("scripts", name + ".py")); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def _wf(name):
    text = open(os.path.join(WF_DIR, name), encoding="utf-8").read(); return text, yaml.safe_load(text)


def _steps(job): return job["steps"], [s.get("name", s.get("uses", "")) for s in job["steps"]]


def test_DPT01_one_workflow_runs_on_three_schedules_and_by_hand_and_never_two_at_once():
    text, wf = _wf("production.yml"); on = wf[True]                                                       # YAML reads the key `on` as True
    crons = [s["cron"] for s in on["schedule"]]; assert set(on) == {"schedule", "workflow_dispatch"} and len(set(crons)) == 3
    assert any(c.endswith("* * *") for c in crons) and any(c.split()[4] != "*" for c in crons) and any(c.split()[2] != "*" for c in crons)      # daily, a weekday, a day of the month
    assert all(re.fullmatch(r"\d{1,2} \d{1,2} (\*|\d{1,2}) \* (\*|\d)", c) for c in crons) and all(c.split()[0] not in ("0", "00") for c in crons)   # not on the hour, when the scheduler is busiest
    assert wf["concurrency"] == {"group": "airpulse-production", "cancel-in-progress": False} and wf["permissions"] == {"contents": "read"}
    assert list(wf["jobs"]) == ["build", "licence", "deploy", "health"] and all(j["runs-on"] == "ubuntu-latest" and j["timeout-minutes"] <= 120 for j in wf["jobs"].values())
    for c in crons: assert f'"{c}"' in text
    weekly, monthly = next(c for c in crons if c.split()[4] != "*"), next(c for c in crons if c.split()[2] != "*")
    run = next(s for s in wf["jobs"]["build"]["steps"] if s.get("id") == "run")["run"]
    assert f'"{weekly}")' in run and f'"{monthly}")' in run and 'FORCE="bls"' in run                         # the cadence is read from the schedule that fired, not from the clock


def test_DPT02_the_build_job_goes_from_the_sources_to_the_upload_in_one_order():
    _, wf = _wf("production.yml"); steps, names = _steps(wf["jobs"]["build"]); at = lambda start: next(i for i, n in enumerate(names) if n.startswith(start))
    order = [at(s) for s in ("Checkout", "Install the engine", "Production run", "Source audit", "Engine tests", "Append-only files intact", "Commit the operational state", "Install the application",
                             "Export the data", "Tests of the application", "Address the site", "Build the application", "Checks before anything is uploaded", "Licence gate", "Upload the site")]
    assert order == sorted(order) and len(set(order)) == len(order)
    run = lambda start: steps[at(start)].get("run", "")
    assert "scripts/production_run.py" in run("Production run") and "pytest tests" in run("Engine tests") and "src.ops.cli verify" in run("Append-only") and "production_report.py" in run("Source audit")
    assert run("Export the data") == "npm run export" and run("Tests of the application") == "npm test" and run("Build the application") == "npm run build"
    assert all(steps[at(s)]["working-directory"] == "airpulse-web" for s in ("Install the application", "Export the data", "Tests of the application", "Build the application"))
    assert "deployment_checks.py all" in run("Checks before") and steps[at("Upload the site")]["uses"].startswith("actions/upload-pages-artifact@") and steps[at("Upload the site")]["with"] == {"path": "airpulse-web/dist"}
    assert steps[at("Build the application")]["env"] == {"VITE_BASE": "${{ steps.pages.outputs.base_path }}/"} and steps[at("Address the site")]["id"] == "pages"   # the base path is read from the Pages settings, not typed
    dep = wf["jobs"]["deploy"]; assert dep["needs"] == "build" and dep["environment"]["name"] == "github-pages" and dep["permissions"] == {"pages": "write", "id-token": "write"}
    assert dep["if"] == "needs.build.outputs.licence_cleared == 'true'" and steps[at("Upload the site")]["if"] == "steps.licence.outputs.cleared == 'true'" and steps[at("Licence gate")]["id"] == "licence"      # nothing is uploaded or deployed while a licence confirmation is open (CL-024)
    assert len(dep["steps"]) == 1 and dep["steps"][0]["uses"].startswith("actions/deploy-pages@")
    health = wf["jobs"]["health"]; assert health["needs"] == ["build", "deploy"] and "exit 1" in health["steps"][0]["run"] and health["steps"][0]["env"] == {"RUN_EXIT": "${{ needs.build.outputs.run_exit }}"}
    assert wf["jobs"]["build"]["outputs"] == {"run_exit": "${{ steps.run.outputs.code }}", "licence_cleared": "${{ steps.licence.outputs.cleared }}"}


def test_DPT03_nothing_is_uploaded_or_deployed_after_a_failed_check():
    text, wf = _wf("production.yml"); steps, names = _steps(wf["jobs"]["build"])
    assert "continue-on-error" not in text
    for s in steps:                                                                                         # only the summary and the log survive a failure; the upload has one condition more, never one less
        if "if" in s: assert (s["if"] == "always()" and s.get("name") in ("Run summary", "Keep the log")) or (s["if"] == "steps.licence.outputs.cleared == 'true'" and s.get("name") == "Upload the site")
        if "|| true" in s.get("run", ""): assert s["name"] == "Run summary"
    assert all("if" not in s for j in ("licence", "deploy", "health") for s in wf["jobs"][j]["steps"]) and [j for j in wf["jobs"] if "if" in wf["jobs"][j]] == ["deploy"]      # the one job condition narrows the deployment
    gate = next(s for s in steps if s.get("id") == "licence")["run"]; assert "scripts/deployment_checks.py licence" in gate and 'echo "cleared=false" >> "$GITHUB_OUTPUT"' in gate and "| tee" not in gate      # the gate's exit code is read directly, not through a pipe
    run = next(s for s in steps if s.get("id") == "run")["run"]
    assert 'if [ "$code" != "0" ] && [ "$code" != "2" ]; then' in run and "exit 1" in run and "pipefail" in run and 'echo "code=$code" >> "$GITHUB_OUTPUT"' in run   # exit 1 of the gate, or anything unexpected, stops the job
    for name in ("Engine tests", "Source audit"): assert "pipefail" in next(s for s in steps if s.get("name", "").startswith(name))["run"]                               # a failure is not hidden by the pipe to the log
    ci_text, ci = _wf("ci.yml"); assert "schedule" not in ci[True] and ci["permissions"] == {"contents": "read"} and "git push" not in ci_text and "deploy-pages" not in ci_text and "upload-pages-artifact" not in ci_text


def test_DPT04_no_secret_is_needed_and_the_write_token_reaches_one_step_only():
    for name in ("production.yml", "ci.yml"):
        text, wf = _wf(name)
        assert "secrets." not in text and "pull_request_target" not in text
        uses = [s["uses"] for j in wf["jobs"].values() for s in j["steps"] if "uses" in s]
        assert uses and all(re.fullmatch(r"actions/[a-z-]+@v\d+", u) for u in uses)                         # the provider's own actions only, each at a named major version
        co = [s for j in wf["jobs"].values() for s in j["steps"] if s.get("uses", "").startswith("actions/checkout@")]
        assert co and all(s["with"]["persist-credentials"] is False for s in co)                           # the checkout keeps no credential
        for j in wf["jobs"].values():
            for s in j["steps"]: assert "${{" not in s.get("run", ""), f"{name}: an expression inside a script ({s.get('name')})"   # values reach a script through its environment only
    text, wf = _wf("production.yml"); steps = wf["jobs"]["build"]["steps"]
    with_token = [s["name"] for s in steps if "github.token" in json.dumps(s)]; assert with_token == ["Commit the operational state (the gate and the tests passed)"] and text.count("github.token") == 1
    assert wf["jobs"]["build"]["permissions"] == {"contents": "write", "pages": "write"} and "id-token" not in wf["jobs"]["build"]["permissions"]   # without the identity token the build job cannot deploy
    assert "contents" not in wf["jobs"]["deploy"]["permissions"] and "permissions" not in wf["jobs"]["health"]   # the job that deploys cannot write to the repository
    ci_text, _ = _wf("ci.yml"); assert "github.token" not in ci_text and "contents: write" not in ci_text


def test_DPT05_only_the_operational_state_is_committed_and_never_by_force():
    text, wf = _wf("production.yml"); commit = next(s for s in wf["jobs"]["build"]["steps"] if s.get("name", "").startswith("Commit the operational state"))["run"]
    assert "git add operations\n" in commit and text.count("git add") == 1 and "git add -A" not in text and "git add ." not in text and "--force" not in text.replace("--force $FORCE", "") and "push -f" not in text
    assert "git diff --cached --quiet" in commit and "git pull --quiet --rebase --autostash" in commit and commit.index("git pull") < commit.index("git push")
    assert 'if [ "${GITHUB_ACTIONS:-}" = "true" ]; then' in commit and "x-access-token:${PUSH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" in commit and "set -x" not in text
    ignore = open(P(".gitignore") if HOSTED else P("deploy", "public", "gitignore"), encoding="utf-8").read()
    for line in ("airpulse-web/public/data/", "airpulse-web/dist/", "airpulse-web/node_modules/", "data/*.sqlite", ".env"): assert line in ignore.splitlines()   # what is generated is never committed


@research_only
def test_DPT06_the_allow_list_leaves_out_everything_that_may_not_be_redistributed():
    b = _script("build_public_repo"); man = yaml.safe_load(open(P("deploy", "public", "manifest.yaml"), encoding="utf-8"))
    tracked = [f for f in subprocess.run(["git", "-c", "core.quotepath=off", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.splitlines() if f]
    files = {f: b"" for f in tracked}; took = b.chosen(files, man["engine"]["include"], man["engine"]["exclude"]); checks = _script("deployment_checks")
    assert len(took) > 200 and len(took) < len(tracked) / 2                                                 # a production subset, not the repository
    for rel in took:
        assert not any(re.search(rx, rel) for rx in checks.FORBIDDEN_PATHS), rel
        assert not any(__import__("fnmatch").fnmatchcase(rel, p) for p in man["never"]), rel
    for gone in ("research/news_archive/", "research/news_labels/", "research/aviation_data/", "reference/", "operations/news/", "operations/aviation/official/eurocontrol/", "execution/", "requirements/", "claude/"):
        assert any(f.startswith(gone) for f in tracked) and not any(f.startswith(gone) for f in took), gone
    left = {f for f in tracked if f.startswith("src/")} - set(took)                                         # the engine as it runs in production; the modules of the research passes stay in the research repository (CL-024)
    assert left and all(f.startswith(("src/v2/", "src/v3/")) or f in ("src/aviation/experiment.py", "src/aviation/report.py") for f in left)
    assert {"src/ops/bls.py", "src/ops/eia.py", "src/ops/adapters.py", "src/api/backtest.py", "src/aviation/cli.py", "src/preprocessing/labels.py"} <= set(took)
    snap = sorted(f for f in took if f.startswith("research/data_samples/")); assert len(snap) == 24 and all(f.startswith(("research/data_samples/SRC-09_bls_", "research/data_samples/SRC-01_eia_EER_", "research/data_samples/SRC-08_eia_RBRTE")) for f in snap)   # ten series read at their publishers, the two spreadsheets, each with its checksum file
    rest = sorted(f for f in took if f.startswith("research/") and f not in snap); assert rest == ["research/bls_releases/final_values.csv", "research/bls_releases/final_values.csv.meta.json", "research/bls_releases/reconstruction_log.csv", "research/bls_releases/releases_manifest.csv", "research/bls_releases/transport_tables.jsonl.gz", "research/data_pipeline_sources.csv", "research/event_taxonomy_v1.yaml", "research/source_reliability.yaml"]   # the last two: the rule files of the press parser (CL-028); AirPulse's own, no data
    assert set(man["switched_off"]) == {"news_aircargoweek", "news_splash247", "eurocontrol", "flight_lists_2019_2022"} and man["max_file_mib"] <= 50
    for path in ("deploy/public/production.yml", "deploy/public/ci.yml", "deploy/public/README.md", "deploy/public/NOTICE.md", "deploy/public/gitignore"): assert path in b.TEMPLATES and os.path.isfile(P(*path.split("/")))


@research_only
def test_DPT07_the_public_profile_switches_off_exactly_the_sources_that_may_not_be_published():
    b = _script("build_public_repo"); man = yaml.safe_load(open(P("deploy", "public", "manifest.yaml"), encoding="utf-8")); off = man["switched_off"]
    from src.observability import policy
    pol = policy.load(); refused = {i for i, e in pol["sources"].items() if policy.refusal(e)}; assert set(off) <= refused                 # nothing publishable is switched off
    for path, key, rows in (("sources.yaml", "active", "sources"), ("production_sources.yaml", "enabled", "sources")):
        before = open(P("config", path), encoding="utf-8").read(); after = b.switch_off(before, off, key)
        a, z = {s["id"]: s for s in yaml.safe_load(before)[rows]}, {s["id"]: s for s in yaml.safe_load(after)[rows]}
        assert set(a) == set(z) and all(z[i][key] is False for i in off) and all(a[i][key] is True for i in off)
        assert all(a[i] == z[i] for i in a if i not in off) and all({k: v for k, v in a[i].items() if k != key} == {k: v for k, v in z[i].items() if k != key} for i in off)   # one word changes per source, nothing else
        assert len(before.splitlines()) == len(after.splitlines())
    with pytest.raises(SystemExit): b.switch_off(open(P("config", "sources.yaml"), encoding="utf-8").read(), ["no_such_source"], "active")
    held = {i for i, e in pol["sources"].items() if not policy.refusal(e)}                                 # what stays on: every publishable source is declared active
    decl = {s["id"]: s for s in yaml.safe_load(open(P("config", "sources.yaml"), encoding="utf-8"))["sources"]}; assert all(decl[i]["active"] is True for i in held)


def _site(tmp, base="/x/", secret=None, dev=None, root_address=False, no_fallback=False, foreign=False):
    """A minimal built site and its exported data."""
    web = tmp / "airpulse-web"; dist = web / "dist"; data = web / "public" / "data"; (dist / "assets").mkdir(parents=True); (dist / "data").mkdir(); data.mkdir(parents=True)
    core = {"registry": {"sources": [{"id": "hkia", "status": "HEALTHY"}]}, "export": {"content_hash": "abc"}, "generated_at": "2026-10-06T00:00:00Z"}
    for d in (data, dist / "data"): (d / "core.json").write_text(json.dumps(core), encoding="utf-8")
    js = "const a=1;" + (f"const k='{secret}';" if secret else "") + (f"fetch('{dev}')" if dev else "") + ("fetch('/data/core.json')" if root_address else "")
    (dist / "assets" / "index-1.js").write_text(js, encoding="utf-8")
    html = f'<html><head><link rel="icon" href="{base}brand/icon.png"><script type="module" src="{"https://cdn.example.org/" if foreign else base}assets/index-1.js"></script></head></html>'
    (dist / "brand").mkdir(); (dist / "brand" / "icon.png").write_bytes(b"\x89PNG")
    (dist / "index.html").write_text(html, encoding="utf-8")
    if not no_fallback: (dist / "404.html").write_text(html, encoding="utf-8")
    return str(dist), str(data)


def test_DPT08_the_checks_before_an_upload_find_what_they_are_there_to_find(tmp_path):
    c = _script("deployment_checks"); key = "AKIA" + "ABCDEFGHIJKLMNOP"; token = "gh" + "p_" + "a" * 36
    dist, data = _site(tmp_path / "clean"); assert c.check_bundle(dist, "/x/", data)[0] == [] and c.check_data(data, ["hkia"])[0] == []
    found = lambda bad, word: any(word in b for b in bad)
    d, dd = _site(tmp_path / "s2", secret=key); assert found(c.check_bundle(d, "/x/", dd)[0], "cloud access key")
    d, dd = _site(tmp_path / "s3", secret=token); assert found(c.check_bundle(d, "/x/", dd)[0], "GitHub token")
    d, dd = _site(tmp_path / "s4", dev="http://localhost:5183/data/core.json"); assert found(c.check_bundle(d, "/x/", dd)[0], "development server")
    d, dd = _site(tmp_path / "s5", dev="C:\\\\Users\\\\someone\\\\file.json"); assert found(c.check_bundle(d, "/x/", dd)[0], "development machine")
    d, dd = _site(tmp_path / "s6", root_address=True); assert found(c.check_bundle(d, "/x/", dd)[0], "fixed at the root")
    d, dd = _site(tmp_path / "s7", no_fallback=True); assert found(c.check_bundle(d, "/x/", dd)[0], "404.html")
    d, dd = _site(tmp_path / "s8", foreign=True); assert found(c.check_bundle(d, "/x/", dd)[0], "another host")
    d, dd = _site(tmp_path / "s9"); assert found(c.check_bundle(d, "/other/", dd)[0], "outside the base path")           # built for one path, checked for another
    d, dd = _site(tmp_path / "s10"); open(os.path.join(dd, "core.json"), "w").write("{}"); bad = c.check_bundle(d, "/x/", dd)[0]; assert found(bad, "does not hold the exported file")
    assert found(c.check_bundle(str(tmp_path / "nothing"), "/x/")[0], "not built")
    # the exported data
    def data_with(obj, name="aviation.json"):
        d_, dd_ = _site(tmp_path / hashlib.sha256(json.dumps(obj).encode()).hexdigest()[:10]); open(os.path.join(dd_, name), "w", encoding="utf-8").write(json.dumps(obj)); return c.check_data(dd_, ["hkia"])[0]
    for obj, word in (({"airport": {"expected": 3}}, '"expected"'), ({"x": [{"z": 1.2}]}, '"z"'), ({"events": []}, '"events"'), ({"label": "EXPERIMENTAL"}, "EXPERIMENTAL"), ({"source": "eurocontrol"}, "eurocontrol"),
                      ({"anomaly_reading": 1}, "anomal"), ({"headline": "x"}, "headline"), ({"capacity_proxy": 1}, "capacity_proxy")):
        assert found(data_with(obj), word), word
    assert found(data_with({"url": "https://example.org/x?api_key=" + "a1b2c3d4" * 4}), "key in an address") and found(data_with({"contact": "someone" + "@" + "example.org"}), "e-mail")
    assert found(data_with({"path": "/home/runner/work/x"}), "development machine")
    d, dd = _site(tmp_path / "p1"); assert found(c.check_data(dd, ["usdot"])[0], "refuses")                               # a source the policy does not allow is listed
    assert found(c.check_data(str(tmp_path / "none"))[0], "missing")
    # the repository
    repo = tmp_path / "repo"; (repo / "src").mkdir(parents=True); (repo / "src" / "a.py").write_text("x = 1\n"); assert c.check_repo(str(repo))[0] == []
    (repo / "src" / "b.py").write_text(f'TOKEN = "{token}"\n'); (repo / "research" / "news_archive").mkdir(parents=True); (repo / "research" / "news_archive" / "2026.jsonl").write_text("{}\n")
    (repo / "data").mkdir(); (repo / "data" / "x.sqlite").write_bytes(b"0"); (repo / ".env").write_text("A=1\n"); bad = c.check_repo(str(repo))[0]
    assert found(bad, "GitHub token") and found(bad, "research/news_archive/2026.jsonl") and found(bad, "x.sqlite") and found(bad, ".env") and len(bad) >= 4
    (repo / "big.bin").write_bytes(b"0" * (2 * 1024 * 1024)); assert found(c.check_repo(str(repo), max_file_mib=1)[0], "above the limit")
    assert c.main(["nonsense"]) == 1


def test_DPT09_a_static_server_like_pages_answers_a_deep_link_with_the_application(tmp_path):
    s = _script("serve_like_pages"); dist, _ = _site(tmp_path / "site"); import http.server
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), s.handler(dist, "/x/")); port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()
    direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))                                   # this machine itself: never through a proxy of the environment
    def get(path):
        try:
            with direct.open(f"http://127.0.0.1:{port}{path}", timeout=10) as r: return r.status, r.read()
        except urllib.error.HTTPError as e: return e.code, e.read()
    try:
        index = open(os.path.join(dist, "index.html"), "rb").read()
        assert get("/x/") == (200, index) and get("/x/assets/index-1.js")[0] == 200 and get("/x/data/core.json")[0] == 200
        assert get("/x/market/forecast") == (404, index) and get("/x/data/nothing.json") == (404, index)       # no file: the site's 404.html, which is the application
        assert get("/")[0] == 404 and get("/data/core.json")[0] == 404 and get("/x/../x/index.html")[0] in (200, 404)   # nothing is served outside the path of the site
    finally: srv.shutdown()
    assert s.main([str(tmp_path / "nothing")]) == 1


def test_DPT10_the_local_stand_in_runs_steps_as_the_workflow_file_says(tmp_path):
    r = _script("run_workflow_locally"); sh = r.bash()
    if shutil.which(sh) is None and not os.path.exists(sh): pytest.skip("no bash on this machine")
    wf = {"name": "t", True: {"workflow_dispatch": {}}, "jobs": {
        "a": {"runs-on": "ubuntu-latest", "outputs": {"v": "${{ steps.one.outputs.v }}"}, "steps": [
            {"uses": "actions/checkout@v7"},
            {"name": "one", "id": "one", "env": {"X": "${{ github.event.inputs.force }}", "T": "${{ github.token }}"}, "run": 'echo "v=${X:-none}-${T:-notoken}" >> "$GITHUB_OUTPUT"'},
            {"name": "in a folder", "working-directory": "sub", "run": "test -f here.txt"},
            {"name": "pages", "id": "pages", "uses": "actions/configure-pages@v6"},
            {"name": "base", "env": {"B": "${{ steps.pages.outputs.base_path }}/"}, "run": 'test "$B" = "/site/"'}]},
        "b": {"runs-on": "ubuntu-latest", "needs": "a", "steps": [{"name": "fails", "env": {"V": "${{ needs.a.outputs.v }}"}, "run": 'test "$V" = "aviation-notoken" && exit 3'}, {"name": "skipped", "run": "true"}, {"name": "always", "if": "always()", "run": "true"}]},
        "c": {"runs-on": "ubuntu-latest", "needs": ["a", "b"], "steps": [{"name": "never", "run": "true"}]}}}
    work = tmp_path / "w"; (work / "sub").mkdir(parents=True); (work / "sub" / "here.txt").write_text("x"); (work / "wf.yml").write_text(yaml.safe_dump(wf), encoding="utf-8")
    p = subprocess.run([sys.executable, P("scripts", "run_workflow_locally.py"), "wf.yml", "--temp", str(tmp_path / "t"), "--out", str(tmp_path / "r.json"), "--set", "github.event.inputs.force=aviation", "--set", "steps.pages.outputs.base_path=/site"],
                       cwd=str(work), capture_output=True, text=True)
    res = json.load(open(tmp_path / "r.json", encoding="utf-8")); st = lambda j: [s["status"] for s in res["jobs"][j]["steps"]]
    assert p.returncode == 1 and res["result"] == "FAILED" and st("a") == ["NOT RUN LOCALLY", "PASSED", "PASSED", "NOT RUN LOCALLY", "PASSED"] and res["jobs"]["a"]["outputs"] == {"v": "aviation-notoken"}
    assert st("b") == ["FAILED", "SKIPPED (an earlier step failed)", "PASSED"] and res["jobs"]["b"]["steps"][0]["exit_code"] == 3 and res["jobs"]["c"]["status"] == "SKIPPED (a needed job failed)" and res["jobs"]["c"]["steps"] == []
    assert res["jobs"]["a"]["steps"][3]["outputs_given"] == {"steps.pages.outputs.base_path": "/site"}
    p = subprocess.run([sys.executable, P("scripts", "run_workflow_locally.py"), "wf.yml", "--temp", str(tmp_path / "t2"), "--out", str(tmp_path / "r2.json"), "--until", "in a folder"], cwd=str(work), capture_output=True, text=True)
    res = json.load(open(tmp_path / "r2.json", encoding="utf-8")); assert p.returncode == 0 and res["stopped_after"] == "in a folder" and res["jobs"]["a"]["steps"][4]["status"].startswith("NOT RUN (outside") and res["jobs"]["b"]["status"].startswith("NOT RUN")
    assert res["jobs"]["a"]["outputs"] == {"v": "none-notoken"} and "github.event.inputs.force" in res["expressions_empty_locally"]   # what a local run cannot know is empty, and listed


@hosted_only
def test_DPT11_the_hosted_repository_holds_what_its_record_says_and_nothing_that_may_not_be_redistributed():
    rec = json.load(open(P("PUBLIC_REPOSITORY.json"), encoding="utf-8")); c = _script("deployment_checks")
    assert sorted(os.listdir(P(".github", "workflows"))) == ["ci.yml", "production.yml"] and not rec.get("trial")
    bad, info = c.check_repo(ROOT); assert bad == [] and info["files"] > 250
    h = hashlib.sha256()
    for rel in sorted(f for f in c.repo_files(ROOT) if f.startswith("src/")):
        h.update(rel.encode()); h.update(hashlib.sha256(open(P(*rel.split("/")), "rb").read()).digest())
    assert h.hexdigest() == rec["src_tree_sha256"]                                                          # the engine is the engine of the research commit named in the record
    decl = {s["id"]: s for s in yaml.safe_load(open(P("config", "sources.yaml"), encoding="utf-8"))["sources"]}; pol = {s["id"]: s for s in yaml.safe_load(open(P("config", "production_sources.yaml"), encoding="utf-8"))["sources"]}
    for i in rec["sources_switched_off"]: assert decl[i]["active"] is False and pol[i]["enabled"] is False
    from src.observability import policy
    assert policy.check() == [] and all(decl[i]["active"] is True for i in policy.publishable_sources())
    for gone in ("research/news_archive", "research/news_labels", "reference", "execution", "operations/news"): assert not os.path.exists(P(*gone.split("/"))), gone
    assert not os.path.isdir(P("airpulse-web", ".github")) and os.path.isfile(P("airpulse-web", "package-lock.json")) and os.path.isfile(P("NOTICE.md"))


def test_DPT12_the_hosting_audit_names_one_provider_and_no_service_that_asks_for_a_card():
    audit = open(P("docs", "FREE_HOSTING_AUDIT.md"), encoding="utf-8").read(); guide = open(P("docs", "HOSTING_STEP_BY_STEP.md"), encoding="utf-8").read()
    assert "| Component | Service | Cost | Credit Card | Limit | Suitable? |" in audit
    rows = [l for l in audit.split("| Component | Service | Cost | Credit Card | Limit | Suitable? |", 1)[1].split("\n\n", 1)[0].splitlines() if l.startswith("| ") and not l.startswith("|---")]
    assert len(rows) >= 8
    for l in rows:
        cells = [x.strip() for x in l.strip("|").split("|")]; assert len(cells) == 6 and re.match(r"(YES|NO)\b", cells[5]) and re.match(r"(NO|YES|NOT READ)\b", cells[3])
        if cells[5].startswith("YES"): assert cells[2].startswith("$0") and cells[3].startswith("NO"), l     # what is used costs nothing and asks for no card
    used = {[x.strip() for x in l.strip("|").split("|")][1].split(" (")[0] for l in rows if [x.strip() for x in l.strip("|").split("|")][5].startswith("YES")}
    assert used and all(u.startswith("GitHub") or u.startswith("git") for u in used)                         # one provider
    assert "CLAUDE DOES" in guide and "USER DOES" in guide and "AIRPULSE_ENGINE_REPOSITORY" not in guide
    for word in ("Create a GitHub account", "Create the repository", "Push", "Actions", "Pages", "Run workflow", "address of the site"): assert word in guide, word
    for doc in (audit, guide): assert "localhost" not in doc and not re.search(r"[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com)[A-Za-z0-9.-]+\.(com|org|net)\b", doc)


@research_only
def test_DPT13_the_deployment_report_says_what_the_records_support():
    from src.observability import records
    report = open(P("execution", "FREE_PUBLIC_DEPLOYMENT_REPORT.md"), encoding="utf-8").read(); head = report.split("\n## ", 1)[0]
    line = lambda k: re.search(rf"^{re.escape(k)}: (.+)$", head, re.M).group(1).strip()
    status = line("HOSTING STATUS"); assert status in ("READY", "READY WITH LICENSING CONFIRMATION REQUIRED", "READY WITH LIMITATIONS", "BLOCKED")
    pending = _script("build_hosting_docs").licence_pending()                                             # CL-024: a production source that awaits a licence confirmation decides the status
    assert (status == "READY WITH LICENSING CONFIRMATION REQUIRED") == (bool(pending) and status != "BLOCKED")
    assert line("MONTHLY COST") in ("$0", "NOT $0") and line("CREDIT CARD") in ("NOT REQUIRED", "REQUIRED") and line("PC REQUIRED AFTER DEPLOYMENT") in ("NO", "YES") and line("AUTOMATED REFRESH") in ("YES", "NO") and line("AUTOMATED DEPLOYMENT") in ("YES", "NO")
    runs = records.read(P("operations", "production_runs.jsonl")); hosted = [r for r in runs if r.get("trigger") == "schedule" and r.get("workflow_run")]
    if not hosted: assert status != "READY" and "has not been run on GitHub" in report                    # nothing is called deployed that was not deployed
    evp = P("evaluation", "public_deployment_verification.json"); ev = json.load(open(evp, encoding="utf-8")) if os.path.exists(evp) else None
    if status != "BLOCKED": assert ev is not None and ev["passed"] is True and not ev["trial"]                # no status but BLOCKED without passing evidence of the clean path
    if ev is None or not ev["passed"]: assert status == "BLOCKED" and line("AUTOMATED REFRESH") == "NO" and line("AUTOMATED DEPLOYMENT") == "NO"
    assert len(re.findall(r"^## \d+\. ", report, re.M)) == 19 and "CLAUDE DOES" in report and "USER DOES" in report


def test_DPT14_a_source_that_is_switched_off_demands_no_file_and_is_not_rebuilt(tmp_path, monkeypatch):
    from src.aviation import operations
    from src.observability import registry
    layers, decl = registry.declared(); with_eur = lambda active: (layers, [{**d, "active": active} if d["id"] == "eurocontrol" else d for d in decl])
    monkeypatch.setattr(registry, "declared", lambda *a, **k: with_eur(False)); q = operations.quality(str(tmp_path))
    assert q["checked"]["eurocontrol"] == {"switched_off": True} and "eurocontrol" not in q["critical"] and q["critical"].get("usdot") == ["no file held"]    # switched off: no file is demanded; a source that is on is still named
    monkeypatch.setattr(registry, "declared", lambda *a, **k: with_eur(True)); q = operations.quality(str(tmp_path))
    assert q["critical"].get("eurocontrol") == ["no file held"] and q["critical"].get("usdot") == ["no file held"]                                        # switched on: its file is demanded as before
    text = open(P("scripts", "production_run.py"), encoding="utf-8").read()
    assert 'news_on = any(r["id"].startswith("news_") and r["status"] != "DISABLED" for r in reg0["sources"])' in text and 'elif news_on and not os.path.exists(os.path.join(ROOT, "data", "news.sqlite")):' in text   # the event store is rebuilt only where the headline sources are on
    run = open(P("src", "aviation", "operations.py"), encoding="utf-8").read().split("\ndef run(", 1)[1]
    assert "hkg(" not in run and "load_hkia(out_dir)" in run                                              # the unattended refresh reads the archive and computes no anomaly reading
