"""`rt` - command line of the kit. Run `rt <command> -h` for options.

  rt init                      create .report-kit/ (profile skeleton) in the current project
  rt doctor [--db]             check Python packages, browser, profile, secrets, web reachability (DB only with --db)
  rt start <code> [--route R]  find the function, dump standard / previous workbook, trace the code from the menu -> brief.md
  rt login [--system S]        log in through the real SSO page, save the session
  rt probe <code> [--tables]   run the profile's data traps on the report's tables -> probe.md
  rt check <code> [--only ids] [--redo] [--kind data|ui]    run checks.yaml -> runs/<id>/summary.md
  rt build <code> [--check]    run the workspace's build_workbook.py, then the quality gate (coverage, results, hidden rows,
                               wording); --check builds <workspace>/_check.xlsx only, so a failing gate costs no version
  rt status <code>             what is done, what is next
  rt sql "<SELECT ...>"        one read-only query (SELECT only)
  rt api GET /path [--params '{...}']   one call to a read-only endpoint, JSON printed
  rt dump <file>               xlsx / docx -> text (reviewer comments included)
  rt tally <workbook.xlsx>     counts per section + rows failing the quality gate
  rt install-skill [dir]       copy the /report-test skill into <dir>/.claude/skills (default: current project)
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys

from . import profile as P


def _out(s):
    print(s); sys.stdout.flush()


# ------------------------------------------------------------------ init / doctor
def cmd_init(a):
    dst = os.path.join(os.getcwd(), ".report-kit")
    if os.path.exists(os.path.join(dst, "project.yaml")):
        raise SystemExit("%s already has project.yaml" % dst)
    src = os.path.join(os.path.dirname(__file__), "assets", "profile-template")
    shutil.copytree(src, dst, dirs_exist_ok=True)
    _out("Created %s\nEdit project.yaml (systems, auth, db, codemap, inputs, workbook), then put credentials in %s:\n"
         "  %s:\n    login_user: ...\n    login_password: ...\n    db_password: ...\nThen run: rt doctor" % (dst, P.SECRETS_FILE, a.name or "<name in project.yaml>"))


def cmd_doctor(a):
    ok = True

    def line(good, what, hint=""):
        nonlocal ok
        ok = ok and good
        _out("[%s] %s%s" % ("OK " if good else "FAIL", what, ("  -> " + hint) if (hint and not good) else ""))

    line(sys.version_info >= (3, 10), "Python %s" % sys.version.split()[0], "need 3.10+")
    for mod in ("yaml", "openpyxl", "docx", "oracledb", "playwright", "requests"):
        try:
            __import__(mod); line(True, "package %s" % mod)
        except ImportError:
            line(False, "package %s" % mod, "pip install -e <report-kit>")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            line(os.path.exists(p.chromium.executable_path), "chromium browser", "python -m playwright install chromium")
    except Exception as e:
        line(False, "chromium browser (%s)" % str(e).splitlines()[0][:80], "python -m playwright install chromium")
    try:
        prof = P.load(a.profile)
        line(True, "profile '%s' (%s)" % (prof.name, prof.dir))
    except SystemExit as e:
        line(False, "profile", str(e)); return 1
    line(bool(prof.tools_dir) and os.path.isdir(prof.tools_dir), "tools_dir %s" % prof.tools_dir, "set paths.tools_dir in project.local.yaml")
    line(os.path.isdir(prof.code_root), "code_root %s" % prof.code_root)
    tpl = prof.expand((prof.get("workbook", {}) or {}).get("template", ""))
    line(bool(tpl) and os.path.exists(tpl), "workbook template %s" % tpl)
    sec = prof.secrets()
    for k in ("login_user", "login_password", "db_password"):
        line(bool(sec.get(k)), "secret %s %s" % (k, "set" if sec.get(k) else "missing"), "add under '%s:' in %s" % (prof.name, P.SECRETS_FILE))
    import requests
    for key, s in prof.systems.items():
        try:
            r = requests.head(s["web"], timeout=10, allow_redirects=True)
            line(r.status_code < 500, "web %s %s -> %s" % (key, s["web"], r.status_code), "VPN / company network?")
        except Exception as e:
            line(False, "web %s %s (%s)" % (key, s["web"], str(e)[:60]), "VPN / company network?")
    if a.db:
        from . import db
        for schema in (prof.get("db.users") or {}):
            try:
                db.q(prof, "SELECT 1 X FROM DUAL", None, schema); line(True, "db %s" % schema)
            except Exception as e:
                line(False, "db %s (%s)" % (schema, str(e).splitlines()[0][:80]))
    _out("doctor: %s" % ("all good" if ok else "fix the FAIL lines"))
    return 0 if ok else 1


# ------------------------------------------------------------------ start
def cmd_start(a):
    from . import inputs, locate
    prof = P.load(a.profile)
    code = P.norm_code(a.code)
    ws = prof.workspace(code)
    fn = inputs.find_function(prof, code)
    with open(ws.p("inputs", "function.json"), "w", encoding="utf-8") as f:
        json.dump(fn, f, ensure_ascii=False, indent=1, default=str)
    std_doc, std_sum = inputs.find_standard(prof)
    std_out = None
    if std_doc:
        std_out = ws.p("inputs", "standard.txt"); inputs.dump_any(std_doc, std_out)
    prev = inputs.find_previous(prof, code)
    prev_out = []
    for p in prev[-2:]:
        out = ws.p("inputs", "prev_" + os.path.splitext(os.path.basename(p))[0] + ".txt")
        text, _ = inputs.dump_any(p, out)
        prev_out.append((p, out, text.count("##### COMMENT")))
    t = locate.locate(prof, ws, fn, route=a.route, force=a.retrace or bool(a.route))
    L = ["# Brief %s - %s" % (code, fn.get("name") or ""),
         "- system: %s (%s) | jira: %s | ticket: %s | PIC: %s | status: %s" % (
             fn.get("system_key"), fn.get("system"), fn.get("jira"), fn.get("ticket") or "UNKNOWN - ask the user",
             fn.get("pic"), fn.get("status")),
         "- menu: %s" % (" >> ".join(inputs.menu_path(fn)) or "not given in the function list - find it in the code"),
         "- workspace: %s" % ws.dir]
    notes = [(k, fn.get(k)) for k in ("description", "note_tester", "note_ba", "replace") if fn.get(k)]
    if notes:
        L += ["", "## Function list notes"] + ["- %s: %s" % (k, " ".join(str(v).split())) for k, v in notes]
    L += ["", "## Inputs"]
    L.append("- standard: %s" % (("%s -> %s" % (std_doc, std_out)) if std_doc else "document not found; profile summary %s" % std_sum))
    L += ["- previous workbook: %s -> %s (%d reviewer comments)" % x for x in prev_out] or ["- previous workbook: none"]
    sibs = inputs.find_siblings(prof, code, fn, trace=t, workspaces_root=os.path.dirname(ws.dir))
    if sibs:
        L += ["", "## Sibling reports - SAME SCREEN OR SAME CODE: test the difference, don't copy",
              "These functions share this one's screen or its main code files, so they are probably the same screen for another",
              "kind of user or another filter. Before writing a case, find out what differs (account type, data scope, filter) and",
              "ask for the account / data that shows it. Shared behaviour: cite the sibling's case instead of copying it, unless",
              "it is re-run with what makes this report different.", ""]
        for s in sibs:
            L.append("- **%s** %s - %s%s%s" % (s["code"], s["name"] or "", "; ".join(s["why"]),
                                               ("; workspace %s" % s["workspace"]) if s["workspace"] else "",
                                               ("; delivered: %s" % ", ".join(s["delivered"])) if s["delivered"] else ""))
    L += ["", locate.trace_md(t)]
    brief = "\n".join(L)
    with open(ws.p("brief.md"), "w", encoding="utf-8") as f:
        f.write(brief)
    ws.mark("start", std=std_doc, prev=[x[0] for x in prev_out], siblings=[s["code"] for s in sibs], trace=t.get("method"))
    _out(brief)


# ------------------------------------------------------------------ login / probe / check / build
def cmd_login(a):
    from . import auth
    prof = P.load(a.profile)
    for s in (a.system or list(prof.systems)):
        w = auth.login(prof, s, a.type) if a.force else auth.ensure(prof, s, a.type)
        _out("%s: login=%s name=%s super_admin=%s" % (s, w.get("login"), w.get("name"), w.get("super_admin")))


def cmd_probe(a):
    from . import probe
    prof = P.load(a.profile); ws = prof.workspace(a.code)
    tables = a.tables.split(",") if a.tables else None
    if not tables:
        tp = os.path.join(ws.dir, "trace.json")
        if not os.path.exists(tp):
            raise SystemExit("Run `rt start %s` first or pass --tables" % a.code)
        with open(tp, encoding="utf-8") as f:
            t = json.load(f)
        objs = set(t.get("sql_objects") or []) | {o for x in t["top"][:8] for o in x.get("sql_objects", [])}
        from . import db
        known = set(db.tables(prof, a.schema))
        tables = sorted(objs & known)
    out = probe.probe(prof, ws, tables, a.schema)
    md = probe.probe_md(out)
    with open(ws.p("probe.md"), "w", encoding="utf-8") as f:
        f.write(md)
    _out(md)


def cmd_check(a):
    from . import auth
    from .checks import engine
    prof = P.load(a.profile); ws = prof.workspace(a.code)
    spec = engine.load(ws)
    auth.ensure(prof, spec.get("system") or next(iter(prof.systems)))
    kinds = (a.kind,) if a.kind else ("data", "ui")
    rd, summary = engine.run(prof, ws, only=a.only.split(",") if a.only else None, redo=a.redo, kinds=kinds, label=a.label)
    counts = {}
    for c in summary["checks"]:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    _out("run: %s\ncounts: %s\nread: %s" % (rd, counts, os.path.join(rd, "summary.md")))
    if a.print:
        with open(os.path.join(rd, "summary.md"), encoding="utf-8") as f:
            _out(f.read())


def cmd_build(a):
    from . import workbook
    prof = P.load(a.profile); ws = prof.workspace(a.code)
    script = os.path.join(ws.dir, "build_workbook.py")
    if not os.path.exists(script):
        raise SystemExit("Write %s first (see references/output-format.md)" % script)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", RK_PROFILE=prof.dir)
    env.pop("RK_WB_OUT", None)
    if getattr(a, "check", False):
        env["RK_WB_OUT"] = os.path.join(ws.dir, "_check.xlsx")
    r = subprocess.run([sys.executable, script], cwd=ws.dir, env=env, capture_output=True, text=True, encoding="utf-8")
    _out(r.stdout.strip()); _out(r.stderr.strip()) if r.returncode else None
    if r.returncode:
        raise SystemExit(r.returncode)
    out = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    cov = os.path.join(ws.dir, "coverage.md")
    if os.path.exists(cov):
        with open(cov, encoding="utf-8") as f:
            _out("coverage: %s (%s)" % (f.readline().strip().lstrip("# "), cov))
    if out.endswith(".xlsx") and os.path.exists(out):
        first = int(prof.get("workbook.first_row", 12))
        ok = _gate(out, first, (prof.get("workbook.header_cells") or {}).get("code", "D3"))
        if getattr(a, "check", False):
            _out("quality gate (check only, nothing delivered): %s" % ("OK - run rt build without --check" if ok else "FAIL - fix the lines above"))
            return
        _out("quality gate: %s" % ("OK" if ok else "FAIL - fix the lines above, then bump version and rebuild"))
        ws.mark("build", file=out, gate_ok=ok)


def _gate(path, first=12, code_cell="D3"):
    """Print the checks of the test case sheet; True when nothing blocks."""
    from . import workbook
    counts, bad = workbook.tally(path, first)
    _out("counts: %s\nrows with empty / status-only 'Kết quả hiện tại': %s" % (counts, bad))
    hid = workbook.hidden_rows(path, first)
    _out("hidden rows on the test case sheet (invisible in Excel): %s" % (hid or []))
    rd = workbook.readability(path, first, code_cell)
    _out("wording for a Tester / BA reader: %s" % ("OK" if not rd else "%d problems" % len(rd)))
    for cid, col, why in rd:
        _out("  %s %s: %s" % (cid, col, why))
    return not bad and not hid and not rd


def cmd_status(a):
    prof = P.load(a.profile); ws = prof.workspace(a.code)
    st = ws.state()["steps"]
    order = [("start", "rt start"), ("probe", "rt probe (after the user OKs SELECT)"), ("checks.yaml", "write checks.yaml"),
             ("check", "rt check"), ("build_workbook.py", "write build_workbook.py"), ("build", "rt build")]
    for step, what in order:
        done = step in st or os.path.exists(os.path.join(ws.dir, step))
        _out("[%s] %-18s %s" % ("x" if done else " ", step, st.get(step, {}).get("at", "") if step in st else what))
    _out("workspace: %s" % ws.dir)


# ------------------------------------------------------------------ small tools
def cmd_sql(a):
    from . import db
    prof = P.load(a.profile)
    for r in db.q(prof, a.sql, None, a.schema)[: a.limit]:
        _out(json.dumps(r, ensure_ascii=False, default=str))


def cmd_api(a):
    from . import http
    prof = P.load(a.profile)
    sc, body = http.json_call(prof, a.system or next(iter(prof.systems)), a.method, a.path,
                              json.loads(a.params) if a.params else None, json.loads(a.body) if a.body else None)
    s = json.dumps(body, ensure_ascii=False, default=str)
    _out("%s %s" % (sc, s if len(s) <= a.max else s[: a.max] + " …(%d chars)" % len(s)))


def cmd_dump(a):
    from . import inputs
    text, imgs = inputs.dump_any(a.file, a.out)
    _out(text if not a.out else "written %s (%d chars, %d images)" % (a.out, len(text), len(imgs)))


def cmd_tally(a):
    _gate(a.file)


def cmd_install_skill(a):
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-plugin", "skills", "report-test")
    if not os.path.isdir(src):
        raise SystemExit("Skill source not found at %s (install reportkit with `pip install -e <report-kit>`)." % src)
    root = os.path.abspath(a.dir or os.getcwd())
    dst = os.path.join(root, ".claude", "skills", "report-test")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    _out("Installed /report-test into %s\nOpen Claude Code in %s and type: /report-test <code>" % (dst, root))


def main(argv=None):
    if hasattr(sys.stdout, "buffer") and (sys.stdout.encoding or "").lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(prog="rt", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", help="profile folder (default: nearest .report-kit/ or RK_PROFILE)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    x = sp.add_parser("init"); x.add_argument("--name"); x.set_defaults(f=cmd_init)
    x = sp.add_parser("doctor"); x.add_argument("--db", action="store_true", help="also connect to the DB (needs the user's OK)"); x.set_defaults(f=cmd_doctor)
    x = sp.add_parser("start"); x.add_argument("code"); x.add_argument("--retrace", action="store_true")
    x.add_argument("--route", help="the screen's route (e.g. /statistics/x/y) when the menu path can't be matched"); x.set_defaults(f=cmd_start)
    x = sp.add_parser("login"); x.add_argument("--system", action="append"); x.add_argument("--type"); x.add_argument("--force", action="store_true"); x.set_defaults(f=cmd_login)
    x = sp.add_parser("probe"); x.add_argument("code"); x.add_argument("--tables"); x.add_argument("--schema", default="default"); x.set_defaults(f=cmd_probe)
    x = sp.add_parser("check"); x.add_argument("code"); x.add_argument("--only"); x.add_argument("--redo", action="store_true")
    x.add_argument("--kind", choices=["data", "ui"]); x.add_argument("--label"); x.add_argument("--print", action="store_true"); x.set_defaults(f=cmd_check)
    x = sp.add_parser("build"); x.add_argument("code")
    x.add_argument("--check", action="store_true", help="build <workspace>/_check.xlsx and run the gates; no version used up"); x.set_defaults(f=cmd_build)
    x = sp.add_parser("status"); x.add_argument("code"); x.set_defaults(f=cmd_status)
    x = sp.add_parser("sql"); x.add_argument("sql"); x.add_argument("--schema", default="default"); x.add_argument("--limit", type=int, default=50); x.set_defaults(f=cmd_sql)
    x = sp.add_parser("api"); x.add_argument("method"); x.add_argument("path"); x.add_argument("--params"); x.add_argument("--body")
    x.add_argument("--system"); x.add_argument("--max", type=int, default=3000); x.set_defaults(f=cmd_api)
    x = sp.add_parser("dump"); x.add_argument("file"); x.add_argument("--out"); x.set_defaults(f=cmd_dump)
    x = sp.add_parser("tally"); x.add_argument("file"); x.set_defaults(f=cmd_tally)
    x = sp.add_parser("install-skill"); x.add_argument("dir", nargs="?"); x.set_defaults(f=cmd_install_skill)
    a = ap.parse_args(argv)
    return a.f(a) or 0


if __name__ == "__main__":
    sys.exit(main())
