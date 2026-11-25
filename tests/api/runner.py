"""Sequential API test runner + HTML report. Usage: python runner.py [--only 03] [--fail-fast] [--open]"""
import argparse, datetime, glob, importlib.util, json, os, platform, re, socket, subprocess, sys, time, traceback, urllib.parse

import client
from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = client.ROOT
CASES = []  # filled by @case in file order


class Skip(Exception):
    pass


class T:
    """Handed to each case: record assertions with t.check(label, ok, actual). t.ctx carries state between cases."""
    def __init__(self, ctx):
        self.ctx, self.checks = ctx, []

    def check(self, label, ok, actual=""):
        self.checks.append({"label": label, "ok": bool(ok), "actual": "" if ok else str(actual)[:600]})
        return bool(ok)

    def need(self, *keys):
        missing = [k for k in keys if self.ctx.get(k) is None]
        if missing:
            raise Skip("needs " + ", ".join(missing) + " from an earlier case")


def case(title, slow=False, jobs=()):
    """jobs: names of background jobs this case exercises (see background_jobs() for the discovered names)."""
    def deco(fn):
        CASES.append({"fn": fn, "title": title, "module": fn.__module__, "slow": slow, "jobs": list(jobs)})
        return fn
    return deco


def load_cases(only):
    for f in sorted(glob.glob(os.path.join(HERE, "cases", "[0-9]*.py"))):
        if only and not os.path.basename(f).startswith(only):
            continue
        spec = importlib.util.spec_from_file_location("cases." + os.path.basename(f)[:-3], f)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)


def port_open(url):
    u = urllib.parse.urlparse(url)
    try:
        socket.create_connection((u.hostname, u.port), 2).close()
        return True
    except OSError:
        return False


def preflight():
    # Tests write to the database, so refuse anything but a local target.
    for u in (client.PUBLIC, client.ADMIN):
        if urllib.parse.urlparse(u).hostname not in ("127.0.0.1", "localhost"):
            sys.exit(f"Refusing to run: {u} is not a local address.")
    down = [n for n, u in (("public API :9096", client.PUBLIC), ("admin API :9097", client.ADMIN), ("mock DGePay :18080", client.MOCK)) if not port_open(u)]
    if down:
        sys.exit("Not running: " + ", ".join(down) + ".\nStart the stack: .\\scripts\\dev.ps1 up -MockPayments   (or: .\\scripts\\test.ps1 -Up)")


def git(*a):
    try:
        return subprocess.check_output(["git", *a], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "?"


def environment():
    subs = {}
    for line in git("submodule", "status").splitlines():
        parts = line.strip("+- U").split()
        if len(parts) >= 2:
            subs[parts[1]] = parts[0][:8]
    dirty = " (uncommitted changes)" if git("status", "--porcelain") else ""
    return {"Workspace commit": git("rev-parse", "--short", "HEAD") + dirty,
            "Submodules": ", ".join(f"{k} {v}" for k, v in subs.items()),
            "Public API": client.PUBLIC, "Admin API": client.ADMIN, "Database": client.DB_CONTAINER,
            "Host": f"{platform.node()} / {platform.system()} {platform.release()}", "Python": platform.python_version()}


def _norm(p):
    return re.sub(r"\{[^}]+\}", "{}", p.strip("/"))


def coverage(hit):
    """Endpoints declared in the API source (read-only scan) vs. endpoints the cases called."""
    declared = set()
    for f in glob.glob(os.path.join(ROOT, "dg-tms-api", "src", "main", "java", "**", "*.java"), recursive=True):
        declared.update(re.findall(r'@Path\("([^"]+)"\)', open(f, encoding="utf-8", errors="ignore").read()))
    declared = {_norm(p) for p in declared if p != "ticket-booking"}
    declared = {p[len("ticket-booking/"):] if p.startswith("ticket-booking/") else p for p in declared}
    # a concrete id in a called path matches a {} template
    def matches(tpl):
        rx = re.compile("^" + re.escape(tpl).replace(re.escape("{}"), "[^/]+") + "$")
        return any(rx.match(h) for h in hit)
    return sorted(p for p in declared if matches(p)), sorted(p for p in declared if not matches(p))


def background_jobs():
    """Background work found in the API source (read-only): every @Scheduled method plus the ticket-batch job type."""
    jobs = [{"name": "ticket_batch", "what": "Bulk ticket generation (background_job table; start, poll, resume)", "trigger": "POST /user-ticket-generator, POST .../resume", "build": "admin"}]
    for f in glob.glob(os.path.join(ROOT, "dg-tms-api", "src", "main", "java", "**", "*.java"), recursive=True):
        src = open(f, encoding="utf-8", errors="ignore").read()
        for m in re.finditer(r'@Scheduled\((.*?)\)\s*(?:public |protected |private )?(?:void )?(\w+)\(', src, re.S):
            cls = os.path.basename(f)[:-5]
            every = re.search(r'every\s*=\s*"([^"]+)"', m.group(1))
            end = src.find("class " + cls)
            start = src.rfind("/**", 0, end)
            doc = src[start + 3:src.find("*/", start)] if start >= 0 and end >= 0 else ""
            what = re.sub(r"\s+", " ", re.sub(r"^\s*\*", "", doc, flags=re.M)).strip().split(". ")[0][:160] or m.group(2)
            jobs.append({"name": cls, "what": what, "trigger": "scheduled, every " + (every.group(1) if every else "?"),
                         "build": "admin" if os.sep + "admin" + os.sep in f else ("public" if "UnlessBuildProperty" in src else "both")})
    return jobs


def run(fail_fast, fast=False):
    ctx, results, hit = {}, [], set()
    started = time.time()
    for i, c in enumerate(CASES, 1):
        t, status, error = T(ctx), "PASS", ""
        client.trace.clear()
        t0 = time.perf_counter()
        try:
            if fast and c["slow"]:
                raise Skip("slow case skipped (--fast)")
            c["fn"](t)
            if not t.checks:
                status, error = "FAIL", "case made no assertions"
            elif not all(x["ok"] for x in t.checks):
                status = "FAIL"
        except Skip as e:
            status, error = "SKIP", str(e)
        except Exception:
            status, error = "FAIL", traceback.format_exc(limit=4)
        for k in client.trace:
            hit.add(urllib.parse.urlparse(k["url"]).path.split("/ticket-booking/", 1)[-1].strip("/"))
        r = {"no": i, "title": c["title"], "module": c["module"].split(".")[-1], "status": status, "error": error,
             "ms": round((time.perf_counter() - t0) * 1000), "checks": t.checks, "calls": list(client.trace), "jobs": c["jobs"]}
        results.append(r)
        print(f"{status:4} {i:02d} {c['title']}  ({r['ms']} ms)" + (f"\n       {error.strip().splitlines()[-1]}" if error else ""))
        for x in t.checks:
            if not x["ok"]:
                print(f"       x {x['label']}  -> {x['actual']}")
        if status == "FAIL" and fail_fast:
            break
    return results, hit, started


def report(results, hit, started):
    covered, missing = coverage(hit)
    jobs = background_jobs()
    for j in jobs:
        cs = [r for r in results if j["name"] in r["jobs"]]
        ran = [r for r in cs if r["status"] != "SKIP"]
        j["cases"] = [r["title"] for r in cs]
        j["status"] = "NOT COVERED" if not cs else ("FAIL" if any(r["status"] == "FAIL" for r in cs) else ("PASS" if ran else "SKIP"))
    n = lambda s: sum(1 for r in results if r["status"] == s)
    checks = [x for r in results for x in r["checks"]]
    ctx = dict(results=results, passed=n("PASS"), failed=n("FAIL"), skipped=n("SKIP"), total=len(results),
               checks_total=len(checks), checks_passed=sum(x["ok"] for x in checks),
               started=datetime.datetime.fromtimestamp(started).strftime("%Y-%m-%d %H:%M:%S"), duration=round(time.time() - started, 1),
               env=environment(), covered=covered, missing=missing, jobs=jobs,
               slowest=sorted((c for r in results for c in r["calls"]), key=lambda c: -c["ms"])[:8])
    html = Environment(loader=FileSystemLoader(os.path.join(HERE, "report")), autoescape=select_autoescape()).get_template("template.html").render(**ctx)
    out = os.path.join(ROOT, "reports")
    os.makedirs(out, exist_ok=True)
    stamp = datetime.datetime.fromtimestamp(started).strftime("%Y%m%d-%H%M%S")
    for name in (f"report-{stamp}.html", "latest.html"):
        open(os.path.join(out, name), "w", encoding="utf-8").write(html)
    json.dump({k: ctx[k] for k in ("results", "passed", "failed", "skipped", "started", "duration", "env")}, open(os.path.join(out, "results.json"), "w"), indent=1)
    return os.path.join(out, "latest.html"), ctx


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="run only case files starting with this prefix, e.g. 04")
    ap.add_argument("--fail-fast", action="store_true")
    ap.add_argument("--fast", action="store_true", help="skip slow cases (the ~2 min background-job wait)")
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()
    sys.modules["runner"] = sys.modules["__main__"]  # cases do `from runner import case`: share this module, not a second copy
    sys.path.insert(0, HERE)
    preflight()
    load_cases(a.only)
    results, hit, started = run(a.fail_fast, a.fast)
    path, c = report(results, hit, started)
    print(f"\n{c['passed']} passed, {c['failed']} failed, {c['skipped']} skipped in {c['duration']}s\nReport: {path}")
    if a.open:
        os.startfile(path)
    sys.exit(1 if c["failed"] else 0)
