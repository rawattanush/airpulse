"""Checks on what is about to be published. They run in the workflow after the build and before the upload: a finding
stops the job, so nothing is uploaded and the site published before stays.

    python scripts/deployment_checks.py repo                 # the files of the repository: secrets, files that may not be redistributed, sizes
    python scripts/deployment_checks.py data                 # the exported data: fields of removed features, sources the policy refuses, secrets, local paths
    python scripts/deployment_checks.py bundle --base /x/    # the built site: every address under the base path, deep links answered, no secret, no development address
    python scripts/deployment_checks.py all --base /x/       # the three together
    python scripts/deployment_checks.py size                 # what the repository holds, in files and MiB (printed on every run; never fails)

Exit 0 when nothing was found, 1 otherwise; every finding is printed with the file it was found in. The checks read files
only. They do not replace the export's own refusal (airpulse-web/scripts/export_data.py) or the tests: they are a second,
independent look at the files themselves, including the bundle, which no other check opens."""
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIB = 1024 * 1024

# Shapes of credentials. A match in any published or committed file is a finding, whatever the surrounding text says.
SECRETS = (("private key", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY"),
           ("cloud access key", r"\bAKIA[0-9A-Z]{16}\b"),
           ("GitHub token", r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})"),
           ("Google API key", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
           ("Slack token", r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
           ("key in an address", r"[?&](?:api_key|apikey|access_token|token|key)=[A-Za-z0-9_\-]{16,}"),
           ("bearer token", r"\bBearer\s+[A-Za-z0-9_\-\.=]{24,}"),
           ("assigned secret", r"(?i)\b(?:api[_-]?key|secret|password|passwd|access[_-]?token|auth[_-]?token)\b\s*[:=]\s*[\"'][A-Za-z0-9_\-/+=]{16,}[\"']"))
# Addresses of a development machine. React Router carries the bare origin http://localhost as a parsing base; that string alone is not an address the site calls.
DEV = (("address of a development server", r"(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]):\d{2,5}"), ("loopback address", r"\b127\.0\.0\.1\b"),
       ("path of a development machine", r"(?:[A-Za-z]:\\\\?Users\\|/mnt/[a-z]/|/home/[a-z][a-z0-9_-]*/|/Users/[A-Za-z][A-Za-z0-9_-]*/|file://)"))
# Paths that may not be in a hosted repository: material whose redistribution is not established, stores, environments, keys.
FORBIDDEN_PATHS = (r"^research/news_archive/", r"^research/news_labels/", r"^research/aviation_data/", r"^research/data_samples_v[0-9]+/", r"^research/vintage_archive/", r"^reference/", r"^operations/news/",
                   r"(^|/)official/eurocontrol/", r"airport_traffic_\d{4}", r"(^|/)raw/positions/", r"\.sqlite$", r"\.db$", r"(^|/)\.env(\.|$)", r"\.pem$", r"(^|/)id_(rsa|ed25519)", r"(^|/)node_modules/", r"\.pyc$")
# Fields and labels of features that are not in the public product (CL-019). The same list as the export's refusal, kept apart from it on purpose.
REMOVED = (r"EXPERIMENTAL", r"RESEARCH[-_ ]ONLY", r"DATA[-_ ]LIMITED", r"UNVERIFIED", r"NOT PREDICTIVE", r'"band"\s*:', r'"expected"\s*:', r'"z"\s*:', r"capacity_proxy", r"eurocontrol",
           r'"events"\s*:', r'"positions"\s*:', r'"anomal[a-z_]*"\s*:', r'"headline[a-z_]*"\s*:', r'"title_raw"\s*:')
# The retired access path (CL-024): nothing that came through the relay services of the Federal Reserve Bank of St. Louis may be in a
# hosted repository, in the exported data or in the built site. Written in pieces so that this file does not match itself.
_F, _A, _HOST = "fr" + "ed", "alfr" + "ed", "stlouis" + "fed"
RETIRED = (("address of the retired relay service", _HOST + r"|" + _F + r"graph|" + _A + r"graph"), ("identifier of a source read through the retired service", r"\b(?:" + _A + "|" + _F + r")_[A-Za-z0-9]"),
           ("file that came through the retired service", r"(?:SRC-\d+|V\d)_(?:" + _A + "|" + _F + r")_"), ("series identifier of the retired service", r"\b(?:DJFUEL" + "USGULF|DCOIL" + "BRENTEU|WJFUEL" + "USGULF|MJFUEL" + "USGULF|DCOIL" + "WTICO|OVX" + r"CLS)\b"))
RETIRED_NAME = ("name of the retired relay service", r"\b(?:" + _F.upper() + "|" + _A.upper() + r")\b")
RETIRED_PATHS = (r"(?i)(^|[/_])(?:" + _A + "|" + _F + r")[_.]", r"^src/v[0-9]+/", r"^evaluation/weekly/", r"^operations/weekly/", r"^evaluation/benchmark_earlier_inputs/", r"^evaluation/licence_repair/",
                 r"^research/operations_archive", r"^evaluation/monthly/results_v2", r"^evaluation/global_features/", r"^evaluation/calibration/")
NAMED_IN = ("NOTICE.md", "README.md", "docs/FREE_HOSTING_AUDIT.md", "docs/HOSTING_STEP_BY_STEP.md", "docs/PRODUCTION_DATA_CONTRACT.md",
            "docs/SRS.md", "docs/SYSTEM_DESIGN.md", "docs/REQUIREMENTS_TRACEABILITY.md", "docs/VERIFICATION_AND_VALIDATION.md", "docs/DATA_AND_LICENSING.md", "docs/USER_GUIDE.md", "docs/OPERATIONS.md")      # documents that say, in words, which path was retired and why; no address, no identifier
TEXT = (".py", ".js", ".mjs", ".jsx", ".json", ".jsonl", ".yml", ".yaml", ".md", ".txt", ".csv", ".html", ".css", ".toml", ".ini", ".cfg", ".sh", ".map", ".svg", ".xml", ".lock", "")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", ".pytest_cache"}
THIS = "scripts/deployment_checks.py"


def _text(path, limit=40 * MIB):
    if os.path.getsize(path) > limit: return None
    with open(path, "rb") as f: raw = f.read()
    if b"\x00" in raw[:4096]: return None
    return raw.decode("utf-8", errors="replace")


def scan_text(text, patterns):
    """[(what, the matching text shortened)] for every pattern found."""
    out = []
    for what, rx in patterns:
        m = re.search(rx, text)
        if m: out.append((what, m.group(0)[:12] + "…"))
    return out


def repo_files(root):
    """Paths the repository holds: what git tracks when this is a git repository, otherwise every file outside the folders nothing is committed from."""
    try:
        p = subprocess.run(["git", "-c", "core.quotepath=off", "ls-files", "-z"], cwd=root, capture_output=True, timeout=120)
        if p.returncode == 0 and p.stdout: return sorted(x for x in p.stdout.decode("utf-8", errors="replace").split("\x00") if x and os.path.isfile(os.path.join(root, x)))
    except (OSError, subprocess.SubprocessError): pass
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        out += [os.path.relpath(os.path.join(base, f), root).replace(os.sep, "/") for f in files]
    return sorted(out)


def is_hosted(root=ROOT):
    """A hosted (production-only) repository carries the record of its build. The research repository holds the retired files as research and is not scanned for them."""
    return os.path.isfile(os.path.join(root, "PUBLIC_REPOSITORY.json"))


def check_repo(root=ROOT, max_file_mib=50, hosted=None):
    """Secrets, paths that may not be redistributed and oversized files among the files of the repository; in a hosted
    repository also: no file, address, identifier or name of the retired access path (CL-024)."""
    bad = []; files = repo_files(root); hosted = is_hosted(root) if hosted is None else hosted
    for rel in files:
        p = os.path.join(root, rel)
        for rx in FORBIDDEN_PATHS:
            if re.search(rx, rel): bad.append(f"{rel}: a path that may not be in a hosted repository ({rx})")
        if hosted:
            for rx in RETIRED_PATHS:
                if re.search(rx, rel): bad.append(f"{rel}: a file of the retired access path or of research built on it ({rx})")
        if os.path.islink(p): bad.append(f"{rel}: a symbolic link"); continue
        size = os.path.getsize(p)
        if size > max_file_mib * MIB: bad.append(f"{rel}: {size / MIB:.0f} MiB, above the limit of {max_file_mib} MiB for one file")
        if rel == THIS or os.path.splitext(rel)[1].lower() not in TEXT: continue
        t = _text(p)
        if t is None: continue
        bad += [f"{rel}: {what} ({shown})" for what, shown in scan_text(t, SECRETS)]
        if hosted: bad += [f"{rel}: {what} ({shown})" for what, shown in scan_text(t, RETIRED + (() if rel in NAMED_IN else (RETIRED_NAME,)))]
    return bad, {"files": len(files), "bytes": sum(os.path.getsize(os.path.join(root, f)) for f in files), "hosted": hosted}


def check_data(data_dir, policy_ids=None):
    """The exported data: nothing of a removed feature, only sources the policy allows, no secret, no path of a machine."""
    bad = []
    if not os.path.isdir(data_dir): return [f"{data_dir}: the exported data are missing"], {"files": 0}
    files = sorted(os.path.relpath(os.path.join(b, f), data_dir).replace(os.sep, "/") for b, _, fs in os.walk(data_dir) for f in fs)
    if "core.json" not in files: bad.append("core.json is missing from the exported data")
    for rel in files:
        p = os.path.join(data_dir, rel); t = _text(p)
        if not rel.endswith(".json"): bad.append(f"{rel}: not a JSON file"); continue
        try: obj = json.loads(t)
        except (ValueError, TypeError): bad.append(f"{rel}: not valid JSON"); continue
        flat = json.dumps(obj, ensure_ascii=False)
        bad += [f"{rel}: holds {rx}, a field or label of a feature that is not in the product" for rx in REMOVED if re.search(rx, flat)]
        bad += [f"{rel}: {what} ({shown})" for what, shown in scan_text(flat, SECRETS + DEV + RETIRED + (RETIRED_NAME,))]
        if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}", flat): bad.append(f"{rel}: an e-mail address")
        if rel == "core.json":
            listed = {r["id"] for r in (obj.get("registry") or {}).get("sources", [])}
            if not listed: bad.append("core.json lists no source")
            if policy_ids is not None and listed - set(policy_ids): bad.append(f"core.json lists sources the production policy refuses: {sorted(listed - set(policy_ids))}")
            if not (obj.get("export") or {}).get("content_hash"): bad.append("core.json carries no content hash")
    return bad, {"files": len(files)}


def check_bundle(dist, base="/", data_dir=None):
    """The built site: complete, addressed under the base path, deep links answered with the application, nothing of a development machine, no secret."""
    bad = []; base = "/" + base.strip("/") + "/" if base.strip("/") else "/"
    index = os.path.join(dist, "index.html")
    if not os.path.isfile(index): return [f"{dist}: index.html is missing: the site was not built"], {"files": 0}
    html = open(index, encoding="utf-8").read(); fallback = os.path.join(dist, "404.html")
    if not os.path.isfile(fallback) or open(fallback, encoding="utf-8").read() != html: bad.append("404.html is missing or differs from index.html: a reload of a route would not load the application")
    refs = re.findall(r"""(?:src|href)=["']([^"']+)["']""", html)
    if not any(r.endswith(".js") for r in refs): bad.append("index.html loads no script")
    for r in refs:
        if re.match(r"^(?:[a-z]+:)?//", r) or r.startswith("data:"): bad.append(f"index.html loads from another host: {r[:60]}"); continue
        if not r.startswith(base): bad.append(f"index.html addresses {r[:60]} outside the base path {base}"); continue
        if not os.path.isfile(os.path.join(dist, r[len(base):].split("?")[0].split("#")[0])): bad.append(f"index.html addresses a file that is not in the build: {r[:60]}")
    total = 0; n = 0
    for b, _, fs in os.walk(dist):
        for f in fs:
            p = os.path.join(b, f); rel = os.path.relpath(p, dist).replace(os.sep, "/"); n += 1
            if os.path.islink(p): bad.append(f"{rel}: a symbolic link (GitHub Pages refuses an artifact that holds one)"); continue
            size = os.path.getsize(p); total += size
            if size > 100 * MIB: bad.append(f"{rel}: {size / MIB:.0f} MiB")
            if rel.endswith(".map"): bad.append(f"{rel}: a source map is published")
            if os.path.splitext(rel)[1].lower() not in TEXT: continue
            t = _text(p)
            if t is None: continue
            bad += [f"{rel}: {what} ({shown})" for what, shown in scan_text(t, SECRETS + DEV)]
            if rel.endswith((".js", ".html", ".css")) and re.search(r"""["'`(]/(?:data|brand|img|assets)/""", t) and base != "/": bad.append(f"{rel}: an address fixed at the root of the host; under {base} it would not be found")
    if total > 1024 * MIB: bad.append(f"the built site is {total / MIB:.0f} MiB; GitHub Pages allows 1 GB")
    built = os.path.join(dist, "data")
    if not os.path.isfile(os.path.join(built, "core.json")): bad.append("the build holds no data: data/core.json is missing")
    elif data_dir and os.path.isdir(data_dir):
        for b, _, fs in os.walk(data_dir):
            for f in fs:
                rel = os.path.relpath(os.path.join(b, f), data_dir); q = os.path.join(built, rel)
                if not os.path.isfile(q) or open(q, "rb").read() != open(os.path.join(b, f), "rb").read(): bad.append(f"data/{rel.replace(os.sep, '/')}: the build does not hold the exported file")
    return bad, {"files": n, "bytes": total, "base": base}


def policy_ids(root=ROOT):
    """Sources the production policy allows in the public product, read from the policy file alone (no engine code is imported)."""
    import yaml
    with open(os.path.join(root, "config", "production_sources.yaml"), encoding="utf-8") as f: pol = yaml.safe_load(f)
    safe = ("COMMERCIAL-SAFE", "COMMERCIAL-SAFE-WITH-ATTRIBUTION", "COMMERCIAL-SAFE-WITH-LIMITS")
    owner = lambda s: s["license_class"] == "OWNER-ACCEPTED" and bool(str(s.get("owner_decision") or "").strip())      # terms not established: only with the owner's decision written beside it (CL-028)
    return sorted(s["id"] for s in pol["sources"] if (s["license_class"] in safe or owner(s)) and s["commercial_allowed"] is True and s["public_display_allowed"] is True and s["derived_data_allowed"] is True
                  and s["enabled"] is True and s["production_status"] == "PRODUCTION")


def licence_gate(root=ROOT):
    """Production sources whose licence status is not CLEARED: [(id, open question)]. While the list is not empty nothing is deployed.
    Read from the policy file alone."""
    import yaml
    with open(os.path.join(root, "config", "production_sources.yaml"), encoding="utf-8") as f: pol = yaml.safe_load(f)
    return [(s["id"], str(s.get("pending") or f"licence status {s.get('licence_status')}")) for s in pol["sources"] if s.get("production_status") == "PRODUCTION" and s.get("enabled") is True and s.get("licence_status") != "CLEARED"]


def main(argv):
    what = argv[0] if argv else "all"; base = argv[argv.index("--base") + 1] if "--base" in argv else "/"; root = os.path.abspath(argv[argv.index("--root") + 1]) if "--root" in argv else ROOT
    web = os.path.join(root, "airpulse-web") if os.path.isdir(os.path.join(root, "airpulse-web")) else os.path.join(os.path.dirname(root), "airpulse-web")
    web = os.path.abspath(argv[argv.index("--web") + 1]) if "--web" in argv else web
    if what == "size":                                               # the files a clone checks out; history adds to it each time a binary file is replaced (docs/FREE_HOSTING_AUDIT.md)
        files = repo_files(root); size = {f: os.path.getsize(os.path.join(root, f)) for f in files}; big = max(size, key=size.get) if size else None
        print(f"this repository holds {len(files)} files, {sum(size.values()) / MIB:.1f} MiB" + (f"; the largest is {big} ({size[big] / MIB:.1f} MiB)" if big else "")); return 0
    if what == "licence":                                            # the last check before the site is handed to the host
        open_ = licence_gate(root)
        for i, why in open_: print(f"  NOT CLEARED: {i}: {why}")
        print("every production source is CLEARED: the site may be deployed" if not open_ else f"{len(open_)} production source(s) await a licence confirmation: the site is built and checked, and it is NOT deployed")
        return 1 if open_ else 0
    if what not in ("repo", "data", "bundle", "all"): print(__doc__); return 1
    findings = {}
    if what in ("repo", "all"):
        bad, info = check_repo(root, hosted=True if "--hosted" in argv else None); findings["repository"] = bad      # --hosted: the folder is a hosted repository being assembled, its record not written yet
        print(f"repository{' (hosted: the retired access path is searched for)' if info['hosted'] else ''}: {info['files']} files, {info['bytes'] / MIB:.1f} MiB; findings: {len(bad)}")
    if what in ("data", "all"):
        bad, info = check_data(os.path.join(web, "public", "data"), policy_ids(root)); findings["exported data"] = bad; print(f"exported data: {info['files']} files; findings: {len(bad)}")
    if what in ("bundle", "all"):
        bad, info = check_bundle(os.path.join(web, "dist"), base, os.path.join(web, "public", "data")); findings["built site"] = bad
        print(f"built site: {info['files']} files, {info.get('bytes', 0) / MIB:.1f} MiB, base path {info.get('base', base)}; findings: {len(bad)}")
    for k, bad in findings.items():
        for b in bad: print(f"  FINDING ({k}): {b}")
    total = sum(len(b) for b in findings.values())
    print("nothing found: the files may be published" if not total else f"{total} findings: nothing may be published")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
