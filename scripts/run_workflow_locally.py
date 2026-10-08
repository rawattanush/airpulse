"""Run the `run:` steps of a GitHub Actions workflow file locally, in order, the way a GitHub-hosted Linux runner runs them:
each step in `bash -e`, in its working directory, with its environment, stopping a job at the first failure, with steps
marked `if: always()` still executed, and a job that needs a failed job skipped.

This is a stand-in for a hosted run, not a hosted run. It reads the real workflow file, so a wrong path or command in the
file fails here too. It does NOT execute `uses:` steps (checkout, setup-python, setup-node, configure-pages,
upload-pages-artifact, deploy-pages, upload-artifact): they are listed as NOT RUN LOCALLY, and for the upload steps the
paths they would upload are checked for existence. It cannot show how GitHub's scheduler, token, network, permissions or
runner image behave.

Expressions (`${{ ... }}`) in a step's `env` and `with` are evaluated from what a local run can know: outputs written by
earlier steps to $GITHUB_OUTPUT, outputs of needed jobs, `runner.temp`, `github.event_name`, and any value given with
`--set` (for the outputs of a `uses:` step, for example `--set steps.pages.outputs.base_path=/airpulse`, or for an input,
`--set github.event.inputs.force=aviation`). Anything else evaluates to the empty string, as on GitHub; `github.token` is
always empty here.

Usage (from the root of a fresh clone, with the project's interpreter running this script):
    python scripts/run_workflow_locally.py .github/workflows/ci.yml --event workflow_dispatch --temp /tmp/x --out result.json
    python scripts/run_workflow_locally.py .github/workflows/production.yml --temp /tmp/x --out r.json --until "Commit the operational state"
"""
import argparse, datetime, json, os, re, shutil, subprocess, sys
import yaml

now = lambda: datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
UPLOADS = ("upload-artifact", "upload-pages-artifact")


def bash():
    """The shell of the steps. On Windows the name `bash` can resolve to the launcher of another system: the one that ships with git is used."""
    if os.environ.get("AIRPULSE_BASH"): return os.environ["AIRPULSE_BASH"]
    if os.name != "nt": return "bash"
    git = shutil.which("git")
    for cand in ([os.path.join(os.path.dirname(os.path.dirname(git)), "bin", "bash.exe")] if git else []) + [r"C:\Program Files\Git\bin\bash.exe"]:
        if os.path.exists(cand): return cand
    return "bash"


def evaluate(text, ctx, unknown):
    """Replace every ${{ name }} by its value in ctx; a name that a local run cannot know becomes the empty string and is recorded."""
    def one(m):
        key = m.group(1).strip()
        if key not in ctx: unknown.add(key)
        return str(ctx.get(key, ""))
    return re.sub(r"\$\{\{\s*([^}]+?)\s*\}\}", one, str(text))


def condition(text, ctx, unknown):
    """Whether the `if:` of a step or a job holds. Understood: none, `always()`, and one comparison of a context value with a quoted
    text (`steps.x.outputs.y == 'true'`, `needs.a.outputs.b != 'x'`), alone or after `always() &&`. Anything else counts as true and is
    named in the record, so that a condition the runner cannot read is never silently taken as false."""
    t = str(text or "").replace("${{", "").replace("}}", "").strip()
    t = re.sub(r"^always\(\)\s*(&&)?\s*", "", t).strip()
    if not t: return True
    m = re.fullmatch(r"([A-Za-z0-9_.\-]+)\s*(==|!=)\s*'([^']*)'", t)
    if not m: unknown.add("if: " + t); return True
    if m.group(1) not in ctx: unknown.add(m.group(1))
    return (str(ctx.get(m.group(1), "")) == m.group(3)) == (m.group(2) == "==")


def read_outputs(path):
    out = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8", errors="replace"):
            if "=" in line: k, v = line.rstrip("\r\n").split("=", 1); out[k.strip()] = v
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("workflow"); ap.add_argument("--event", default="workflow_dispatch", choices=["workflow_dispatch", "schedule", "push"])
    ap.add_argument("--temp", required=True); ap.add_argument("--out", required=True); ap.add_argument("--set", action="append", default=[], metavar="NAME=VALUE", help="value of an expression a local run cannot know")
    ap.add_argument("--until", default=None, metavar="STEP NAME", help="run steps up to and including the first whose name starts with this text; later steps and jobs are not run")
    a = ap.parse_args()
    wf = yaml.safe_load(open(a.workflow, encoding="utf-8")); os.makedirs(a.temp, exist_ok=True); temp = os.path.abspath(a.temp).replace(os.sep, "/"); repo = os.getcwd()
    env = {**os.environ, "RUNNER_TEMP": temp, "GITHUB_STEP_SUMMARY": temp + "/step_summary.md", "GITHUB_EVENT_NAME": a.event, "CI": "true"}
    env["PATH"] = os.path.dirname(os.path.abspath(sys.executable)) + os.pathsep + env.get("PATH", "")          # `python` in a step is the interpreter running this script
    if os.name == "nt": env["MSYS_NO_PATHCONV"] = "1"; env["MSYS2_ARG_CONV_EXCL"] = "*"; env["MSYS2_ENV_CONV_EXCL"] = "*"     # a value such as /airpulse/ is an address, not a path of this machine
    for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_REPOSITORY", "GITHUB_ACTIONS", "GITHUB_WORKFLOW", "GITHUB_SHA", "GITHUB_REF_NAME", "GITHUB_TOKEN", "GH_TOKEN"): env.pop(k, None)     # a local run has no hosted run identity and must not record one
    ctx = {"runner.temp": temp, "github.event_name": a.event, "github.token": ""}; given = {}
    for s in a.set:
        k, v = s.split("=", 1); ctx[k.strip()] = v; given[k.strip()] = v
    res = {"workflow": wf.get("name"), "file": a.workflow, "event": a.event, "temp": temp, "started": now(), "permissions": wf.get("permissions"), "concurrency": wf.get("concurrency"),
           "schedules": [s["cron"] for s in (wf.get(True) or {}).get("schedule", [])] if isinstance(wf.get(True), dict) else [], "given": given, "jobs": {}}
    failed = False; stopped = False; job_failed = {}; job_skipped = {}; unknown = set(); sh = bash()
    for job_name, job in wf["jobs"].items():
        steps = []; needs = job.get("needs") or []; needs = [needs] if isinstance(needs, str) else list(needs)
        res["jobs"][job_name] = {"runs_on": job.get("runs-on"), "needs": needs, "permissions": job.get("permissions"), "environment": job.get("environment"), "steps": steps}
        if stopped: res["jobs"][job_name]["status"] = "NOT RUN (outside the part of the workflow asked for)"; continue
        if any(job_failed.get(n) for n in needs): res["jobs"][job_name]["status"] = "SKIPPED (a needed job failed)"; job_failed[job_name] = True; continue
        if any(job_skipped.get(n) for n in needs): res["jobs"][job_name]["status"] = "SKIPPED (a needed job was skipped)"; job_skipped[job_name] = True; continue
        if "if" in job and not condition(job["if"], ctx, unknown): res["jobs"][job_name]["status"] = "SKIPPED (its condition is false)"; res["jobs"][job_name]["if"] = str(job["if"]); job_skipped[job_name] = True; continue
        this_failed = False
        for i, st in enumerate(job["steps"], start=1):
            name = st.get("name") or st.get("uses") or f"step {i}"; always = "always()" in str(st.get("if", ""))
            if stopped: steps.append({"n": i, "name": name, "kind": "uses" if "uses" in st else "run", "status": "NOT RUN (outside the part of the workflow asked for)"}); continue
            if "if" in st and not condition(st["if"], ctx, unknown): steps.append({"n": i, "name": name, "kind": "uses" if "uses" in st else "run", "status": "SKIPPED (its condition is false)", "if": str(st["if"])}); continue
            if "uses" in st:
                rec = {"n": i, "name": name, "kind": "uses", "uses": st["uses"], "status": "NOT RUN LOCALLY"}
                if any(u in st["uses"] for u in UPLOADS):
                    paths = [evaluate(p.strip(), ctx, unknown) for p in str(st.get("with", {}).get("path", "")).splitlines() if p.strip()]
                    rec["artifact_name"] = st.get("with", {}).get("name")
                    rec["artifact_paths"] = [{"path": p.replace(temp, "$RUNNER_TEMP"), "exists": os.path.exists(p), "bytes": os.path.getsize(p) if os.path.isfile(p) else sum(os.path.getsize(os.path.join(b, f)) for b, _, fs in os.walk(p) for f in fs) if os.path.isdir(p) else 0} for p in paths]
                if st.get("id"): rec["outputs_given"] = {k: v for k, v in given.items() if k.startswith(f"steps.{st['id']}.outputs.")}
                steps.append(rec)
            elif this_failed and not always:
                steps.append({"n": i, "name": name, "kind": "run", "status": "SKIPPED (an earlier step failed)"})
            else:
                out_file = os.path.join(a.temp, f"output_{job_name}_{i}.txt"); open(out_file, "w").close()
                step_env = {**env, "GITHUB_OUTPUT": os.path.abspath(out_file).replace(os.sep, "/"), **{k: evaluate(v, ctx, unknown) for k, v in (st.get("env") or {}).items()}}
                cwd = os.path.join(repo, st["working-directory"]) if st.get("working-directory") else repo
                t0 = now(); p = subprocess.run([sh, "-e", "-c", st["run"]], env=step_env, cwd=cwd, capture_output=True, text=True, errors="replace"); out = (p.stdout + p.stderr).strip().splitlines()
                rec = {"n": i, "name": name, "kind": "run", "started": t0, "finished": now(), "exit_code": p.returncode, "status": "PASSED" if p.returncode == 0 else "FAILED", "output_tail": out[-25:]}
                if st.get("working-directory"): rec["working_directory"] = st["working-directory"]
                if st.get("id"):
                    rec["outputs"] = read_outputs(out_file)
                    for k, v in rec["outputs"].items(): ctx[f"steps.{st['id']}.outputs.{k}"] = v
                steps.append(rec); print(f"[{'ok' if p.returncode == 0 else 'FAIL'}] {wf.get('name')} / {job_name} / {name}", flush=True)
                if p.returncode != 0: this_failed = True; print("\n".join(out[-40:]), flush=True)
            if a.until and name.startswith(a.until): stopped = True
        outputs = {k: evaluate(v, ctx, unknown) for k, v in (job.get("outputs") or {}).items()}
        for k, v in outputs.items(): ctx[f"needs.{job_name}.outputs.{k}"] = v
        res["jobs"][job_name]["outputs"] = outputs; res["jobs"][job_name]["status"] = "FAILED" if this_failed else "PASSED"
        job_failed[job_name] = this_failed; failed = failed or this_failed
    res["finished"] = now(); res["result"] = "FAILED" if failed else "PASSED"; res["expressions_empty_locally"] = sorted(unknown); res["stopped_after"] = a.until if stopped else None
    json.dump(res, open(a.out, "w", encoding="utf-8"), indent=1)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
