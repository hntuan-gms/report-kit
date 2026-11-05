"""`rt` - command line of the kit. Run `rt <command> -h` for options.

  rt init                      create .report-kit/ (profile skeleton) in the current project
  rt doctor [--db]             check Python packages, browser, profile, secrets, web reachability (DB only with --db)
  rt start <code> [--menu M | --route R]  find the function, dump standard / previous workbook, trace the code from the menu -> brief.md
  rt login [--system S]        log in through the real SSO page, save the session
  rt probe <code> [--tables]   run the profile's data traps on the report's tables -> probe.md
  rt check <code> [--only ids] [--redo] [--kind data|ui]    run checks.yaml -> runs/<id>/summary.md
  rt build <code>              run the workspace's build_workbook.py, then the quality gate (results, bug ids, coverage matrix)
  rt status <code>             what is done, what is next
  rt sql "<SELECT ...>"        one read-only query (SELECT only)
  rt api GET /path [--params '{...}']   one call to a read-only endpoint, JSON printed
  rt dump <file>               xlsx / docx -> text (reviewer comments included)
  rt tally <workbook.xlsx> [--probe probe.json]   counts per section + rows failing the quality gate
  rt deployed "<text|regex>"   search the deployed frontend bundle (cached per day): what the build really does
  rt show <code> [ids|all] [--status ERR,NM] [--keys a,b]   print only those entries of the latest run
  rt install-skill [dir]       copy the /report-test skill into <dir>/.claude/skills and add the safety hook (default: current project)
"""
import argparse
import io
import json
import os
import re
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
def _group_info(prof, fn):
    """(group id, conventions file path, exists) of the function's group, or (None, None, False)."""
    m = re.match(r"\s*#?\s*([0-9]+[A-Z](?:\.[IVXLC0-9]+)*)", str(fn.get("group") or ""))
    rel = prof.get("rules.groups")
    if not m or not rel:
        return None, None, False
    path = os.path.normpath(os.path.join(prof.dir, rel, m.group(1) + ".md"))
    return m.group(1), path, os.path.exists(path)


def _group_rules(prof, fn):
    """The group's conventions file (BA decisions already taken for every function of the group), for the brief."""
    gid, path, exists = _group_info(prof, fn)
    if not gid:
        return "none (the profile has no rules.groups, or the row no group)"
    if exists:
        return "%s - read it before step 3: decisions already taken for group %s; apply them and cite them as basis" % (path, gid)
    return ("none yet for group %s. Decisions you take as BA for points the Quy chuẩn leaves open go in %s, "
            "so the group's other functions apply the same ones (several codes: propose them, the main session "
            "writes the file)" % (gid, path))


def cmd_start(a):
    from . import inputs, locate
    prof = P.load(a.profile)
    code = P.norm_code(a.code)
    ws = prof.workspace(code)
    fn = inputs.find_function(prof, code)
    if a.menu:      # the menu path as the screen shows it, when the function list has none (or a wrong one)
        fn["menu"] = a.menu
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
    L.append("- group conventions: %s" % _group_rules(prof, fn))
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
    if a.quiet:     # the main session of several codes needs only this; the agents read brief.md
        gid, _, gexists = _group_info(prof, fn)
        _out("%s: trace %s | siblings %s | previous %d | group %s | %s" % (
            code, t.get("method"), ",".join(s["code"] for s in sibs) or "-", len(prev_out),
            ("%s (%s)" % (gid, "conventions file" if gexists else "no conventions yet")) if gid else "-", ws.p("brief.md")))
    else:
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
    objs = None
    if not tables:
        objs = _trace_objects(ws.dir)
        if objs is None:
            raise SystemExit("Run `rt start %s` first or pass --tables" % a.code)
    # a sibling that probed the same tables (or traced the same SQL objects) today: reuse it, without touching the DB
    src = None if a.fresh else _same_day_probe(ws, tables, objs, a.schema)
    if not tables and not src:
        from . import db
        tables = sorted(set(objs) & set(db.tables(prof, a.schema)))
    if src:                 # a sibling probed exactly these tables today: same examples, no second round of queries
        with open(os.path.join(src, "probe.json"), encoding="utf-8") as f:
            out = json.load(f)
        with open(ws.p("probe.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1, default=str)
        ws.mark("probe", tables=list(out["tables"]), reused_from=os.path.basename(src))
    else:
        out = probe.probe(prof, ws, tables, a.schema)
    md = probe.probe_md(out)
    with open(ws.p("probe.md"), "w", encoding="utf-8") as f:
        f.write(md)
    found = [(t, it["id"]) for t, info in out["tables"].items() for it in info.get("traps", []) if it.get("flagged")]
    errs = [t for t, info in out["tables"].items() if info.get("error")]
    # a summary only: the examples are in probe.md, read with grep when a case needs them
    _out("probe: %d tables%s -> %s\nFOUND (%d): %s%s" % (
        len(out["tables"]), (" (reused from %s, same tables today; --fresh to query again)" % os.path.basename(src)) if src else "",
        ws.p("probe.md"), len(found), ", ".join("%s (%s)" % (i, t) for t, i in found) or "none",
        ("\ntables with an error: %s" % ", ".join(errs)) if errs else ""))


def _trace_objects(ws_dir):
    """The SQL objects the trace found (the probe's candidate tables), or None without a trace."""
    tp = os.path.join(ws_dir, "trace.json")
    if not os.path.exists(tp):
        return None
    with open(tp, encoding="utf-8") as f:
        t = json.load(f)
    return sorted(set(t.get("sql_objects") or []) | {o for x in t.get("top", [])[:8] for o in x.get("sql_objects", [])})


def _same_day_probe(ws, tables, objs, schema):
    """A sibling workspace whose probe.json was written today for the same schema and either covers exactly `tables`,
    or (no --tables) comes from a trace with the same SQL objects."""
    import datetime as _dt
    today = _dt.date.today()
    root = os.path.dirname(ws.dir)
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name, "probe.json")
        if name == os.path.basename(ws.dir) or not os.path.exists(p):
            continue
        if _dt.date.fromtimestamp(os.path.getmtime(p)) != today:
            continue
        try:
            with open(p, encoding="utf-8") as f:
                out = json.load(f)
        except ValueError:
            continue
        if out.get("schema", schema) != schema:
            continue
        if tables is not None and sorted(out.get("tables") or {}) == sorted(tables):
            return os.path.dirname(p)
        if tables is None and objs is not None and _trace_objects(os.path.dirname(p)) == objs:
            return os.path.dirname(p)
    return None


def cmd_check(a):
    from . import auth
    from .checks import engine
    prof = P.load(a.profile); ws = prof.workspace(a.code)
    spec = engine.load(ws)
    auth.ensure(prof, spec.get("system") or next(iter(prof.systems)))
    kinds = (a.kind,) if a.kind else ("data", "ui")
    rd, summary = engine.run(prof, ws, only=a.only.split(",") if a.only else None, redo=a.redo, kinds=kinds, label=a.label,
                             workers=a.workers, budget=a.budget)
    counts = {}
    for c in summary["checks"]:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    _out("run: %s\ncounts: %s" % (rd, counts))
    # what needs a look, from this run only, so the next turn can act without an `rt show` turn first
    fresh = [c for c in summary["checks"] if not c.get("carried_from") and c["status"] in ("ERR", "NM", "DIFF")]
    for c in fresh[:15]:
        _out("  %s %s: %s" % (c["id"], c["status"], (c.get("reason") or c.get("title") or "")[:200]))
    if len(fresh) > 15:
        _out("  … %d more: rt show %s --status ERR,NM,DIFF" % (len(fresh) - 15, a.code))
    if counts.get("TODO"):
        _out("%d entries not run yet (time budget): rt check %s --redo" % (counts["TODO"], a.code))
    _out("details: rt show %s <ids> [--keys a,b]" % a.code)
    if a.print:
        with open(os.path.join(rd, "summary.md"), encoding="utf-8") as f:
            _out(f.read())


def cmd_show(a):
    """Part of a run's summary.md: the entries asked for (ids, `all`, or by status), observations narrowed by --keys."""
    from .checks import engine
    prof = P.load(a.profile); ws = prof.workspace(a.code)
    rd = os.path.join(ws.runs_dir(), a.run) if a.run else ws.latest_run()
    if not rd or not os.path.exists(os.path.join(rd, "summary.json")):
        raise SystemExit("no finished run for %s (rt check writes summary.json at the end)" % a.code)
    with open(os.path.join(rd, "summary.json"), encoding="utf-8") as f:
        summary = json.load(f)
    want = None if a.ids in (None, "all") else {x.strip() for x in a.ids.split(",") if x.strip()}
    status = {x.strip().upper() for x in a.status.split(",")} if a.status else None
    keys = {x.strip() for x in a.keys.split(",")} if a.keys else None
    results = []
    for c in summary["checks"]:
        if (want and c["id"] not in want) or (status and c["status"] not in status):
            continue
        with open(os.path.join(rd, c["id"] + ".json"), encoding="utf-8") as f:
            r = json.load(f)
        r.setdefault("title", c.get("title")); r.setdefault("carried_from", c.get("carried_from"))
        if keys and r.get("observations"):
            r["observations"] = {k: v for k, v in r["observations"].items() if k in keys}
        results.append(r)
    if want and not results:
        raise SystemExit("none of %s in %s" % (sorted(want), rd))
    if keys:
        engine.CLIP = 100000          # the observations asked for by name are printed whole
    md = engine.summary_md(summary, results, max_mismatch=a.limit).split("\n")
    counts = {}
    for c in summary["checks"]:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    md[1] = "Counts (whole run): %s | shown: %d" % (", ".join("%s=%d" % kv for kv in sorted(counts.items())), len(results))
    _out("\n".join(md))


def cmd_build(a):
    from . import workbook
    prof = P.load(a.profile); ws = prof.workspace(a.code)
    script = os.path.join(ws.dir, "build_workbook.py")
    if not os.path.exists(script):
        raise SystemExit("Write %s first (see references/output-format.md)" % script)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", RK_PROFILE=prof.dir)
    r = subprocess.run([sys.executable, script], cwd=ws.dir, env=env, capture_output=True, text=True, encoding="utf-8")
    _out(r.stdout.strip()); _out(r.stderr.strip()) if r.returncode else None
    if r.returncode:
        raise SystemExit(r.returncode)
    out = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    if out.endswith(".xlsx") and os.path.exists(out):
        first = int(prof.get("workbook.first_row", 12))
        counts, bad, f_no_bug = workbook.tally(out, first)
        _out("counts: %s\nrows with empty / status-only 'Kết quả hiện tại': %s\nF rows without bug id: %s" % (counts, bad, f_no_bug))
        cov_ok = _print_coverage(workbook.coverage_gate(out, ws.p("probe.json"), first, (prof.get("workbook.header_cells") or {}).get("code", "D3")))
        hid = workbook.hidden_rows(out, first)
        _out("hidden rows on the test case sheet (invisible in Excel): %s" % (hid or []))
        no_pic = workbook.evidence_gate(out)
        _out("open bugs with no picture in 'Hình ảnh lỗi' and no 'Không có hình: <lý do>': %s" % (no_pic or []))
        ok = not bad and not f_no_bug and cov_ok and not hid and not no_pic
        _out("quality gate: %s" % ("OK" if ok else "FAIL - fix every line above, then `rt build` again (it replaces this run's "
                                               "own draft; bump version only for a file that was delivered)"))
        ws.mark("build", file=out, mtime=os.path.getmtime(out), counts=counts, gate_ok=ok)


def _print_coverage(c):
    if c["missing_sheet"]:
        _out("coverage: sheet '%s' missing - add wb.sheet_coverage(...) (references/output-format.md)" % "Ma trận bao phủ")
        return False
    _out("coverage rows with no case and no 'Không áp dụng' / 'Chưa phủ' reason: %s" % c["rows_without_reason"])
    _out("FOUND traps not mapped to a coverage row: %s" % c["traps_not_mapped"])
    _out("cases no requirement points to (info): %s" % (c["cases_not_referenced"] or "[]"))
    return not c["rows_without_reason"] and not c["traps_not_mapped"]


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
    for n, sql in enumerate(a.sql):     # several lookups in one call: one turn instead of one per query
        if len(a.sql) > 1:
            _out("-- [%d] %s" % (n + 1, " ".join(sql.split())[:100]))
        try:
            rows = db.q(prof, sql, None, a.schema)
        except Exception as e:          # one bad query must not hide the others' answers
            if len(a.sql) == 1:
                raise
            _out("ERROR: %s" % str(e).splitlines()[0][:300]); continue
        for r in rows[: a.limit]:
            _out(json.dumps(r, ensure_ascii=False, default=str))
        if len(rows) > a.limit:
            _out("… %d more rows (--limit)" % (len(rows) - a.limit))


def cmd_api(a):
    from . import http
    prof = P.load(a.profile)
    sc, body = http.json_call(prof, a.system or next(iter(prof.systems)), a.method, a.path,
                              json.loads(a.params) if a.params else None, json.loads(a.body) if a.body else None)
    s = json.dumps(body, ensure_ascii=False, default=str)
    _out("%s %s" % (sc, s if len(s) <= a.max else s[: a.max] + " …(%d chars)" % len(s)))


def cmd_deployed(a):
    from . import deployed
    prof = P.load(a.profile)
    system = a.system or next(iter(prof.systems))
    cache = deployed.cache_dir(prof, system)
    files = deployed.crawl(prof.system(system)["web"], cache)
    hits = deployed.search(files, a.pattern, context=a.context, limit=a.limit)
    _out("deployed %s: %d scripts (cache %s), %d match(es) for %r" % (system, len(files), cache, len(hits), a.pattern))
    for name, pos, snip in hits:
        _out("--- %s @%d\n%s" % (name, pos, snip))


def cmd_dump(a):
    from . import inputs
    text, imgs = inputs.dump_any(a.file, a.out)
    _out(text if not a.out else "written %s (%d chars, %d images)" % (a.out, len(text), len(imgs)))


def cmd_tally(a):
    from . import workbook
    counts, bad, f_no_bug = workbook.tally(a.file)
    _out("counts: %s\nrows with empty / status-only 'Kết quả hiện tại': %s\nF rows without bug id: %s" % (counts, bad, f_no_bug))
    _out("hidden rows on the test case sheet (invisible in Excel): %s" % (workbook.hidden_rows(a.file) or []))
    _out("open bugs with no picture in 'Hình ảnh lỗi' and no 'Không có hình: <lý do>': %s" % (workbook.evidence_gate(a.file) or []))
    _print_coverage(workbook.coverage_gate(a.file, a.probe))


def cmd_install_skill(a):
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-plugin", "skills", "report-test")
    if not os.path.isdir(src):
        raise SystemExit("Skill source not found at %s (install reportkit with `pip install -e <report-kit>`)." % src)
    root = os.path.abspath(a.dir or os.getcwd())
    dst = os.path.join(root, ".claude", "skills", "report-test")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    _out("Installed /report-test into %s" % dst)
    # the per-code agent: a short system prompt and 7 tools, instead of general-purpose's whole tool set on every turn
    agent = os.path.join(os.path.dirname(src), os.pardir, "agents", "report-runner.md")
    if os.path.exists(agent):
        adir = os.path.join(root, ".claude", "agents"); os.makedirs(adir, exist_ok=True)
        shutil.copy(agent, os.path.join(adir, "report-runner.md"))
        _out("Installed the report-runner agent into %s" % adir)
    # the DB / write-request safety net (reportkit/guard.py) as a PreToolUse hook of the project
    sp = os.path.join(root, ".claude", "settings.json")
    try:
        with open(sp, encoding="utf-8") as f:
            settings = json.load(f)
    except FileNotFoundError:
        settings = {}
    pre = settings.setdefault("hooks", {}).setdefault("PreToolUse", [])
    cmd = '"%s" -m reportkit.guard' % sys.executable
    changed = []
    matcher = "Bash|PowerShell|Write|Edit|mcp__.*"      # Write / Edit: injection payloads written into scripts
    mine = [m for m in pre if any("reportkit.guard" in h.get("command", "") for h in m.get("hooks", []))]
    if not mine:
        pre.append({"matcher": matcher, "hooks": [{"type": "command", "command": cmd, "timeout": 10}]})
        changed.append("the safety hook (reportkit.guard)")
    elif any(m.get("matcher") != matcher for m in mine):
        for m in mine:
            m["matcher"] = matcher
        changed.append("the safety hook's matcher (%s)" % matcher)
    env = settings.setdefault("env", {})
    if "PYTHONIOENCODING" not in env:    # agents' own Python scripts print Vietnamese; cp1252 consoles crash on it
        env["PYTHONIOENCODING"] = "utf-8"
        changed.append("env PYTHONIOENCODING=utf-8")
    if changed:
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        _out("Added %s to %s" % (" and ".join(changed), sp))
    _out("Open Claude Code in %s and type: /report-test <code>" % root)


def main(argv=None):
    if hasattr(sys.stdout, "buffer") and (sys.stdout.encoding or "").lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(prog="rt", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", help="profile folder (default: nearest .report-kit/ or RK_PROFILE)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    x = sp.add_parser("init"); x.add_argument("--name"); x.set_defaults(f=cmd_init)
    x = sp.add_parser("doctor"); x.add_argument("--db", action="store_true", help="also connect to the DB (needs the user's OK)"); x.set_defaults(f=cmd_doctor)
    x = sp.add_parser("start"); x.add_argument("code"); x.add_argument("--retrace", action="store_true")
    x.add_argument("--menu", help='the menu path as the screen shows it ("Quản lý hồ sơ >> Tra cứu ... >> <tab>"), '
                                  "when the function list has none; trailing tab names are fine")
    x.add_argument("--route", help="the screen's route (e.g. /statistics/x/y) when the menu path can't be matched")
    x.add_argument("--quiet", action="store_true", help="one summary line instead of the brief (it is in brief.md)"); x.set_defaults(f=cmd_start)
    x = sp.add_parser("login"); x.add_argument("--system", action="append"); x.add_argument("--type"); x.add_argument("--force", action="store_true"); x.set_defaults(f=cmd_login)
    x = sp.add_parser("probe"); x.add_argument("code"); x.add_argument("--tables"); x.add_argument("--schema", default="default")
    x.add_argument("--fresh", action="store_true", help="query again even if a sibling probed the same tables today"); x.set_defaults(f=cmd_probe)
    x = sp.add_parser("check"); x.add_argument("code"); x.add_argument("--only"); x.add_argument("--redo", action="store_true")
    x.add_argument("--kind", choices=["data", "ui"]); x.add_argument("--label"); x.add_argument("--print", action="store_true")
    x.add_argument("--workers", type=int, help="UI entries run in parallel (default: profile ui.workers, 1)")
    x.add_argument("--budget", type=int, help="seconds before the remaining entries are left as TODO (default: ui.run_budget_s, 180; 0 = none)")
    x.set_defaults(f=cmd_check)
    x = sp.add_parser("deployed", help="search the deployed frontend's JS bundle (the build can differ from the repo)")
    x.add_argument("pattern"); x.add_argument("--system"); x.add_argument("--context", type=int, default=300)
    x.add_argument("--limit", type=int, default=12); x.set_defaults(f=cmd_deployed)
    x = sp.add_parser("show", help="print only some entries of a run's summary")
    x.add_argument("code"); x.add_argument("ids", nargs="?", help="U03,D01 or all (default: all)")
    x.add_argument("--status", help="e.g. ERR,NM,DIFF"); x.add_argument("--keys", help="observation names to keep, e.g. rows,heads")
    x.add_argument("--run", help="run id (default: the latest)"); x.add_argument("--limit", type=int, default=12, help="differing cells per part")
    x.set_defaults(f=cmd_show)
    x = sp.add_parser("build"); x.add_argument("code"); x.set_defaults(f=cmd_build)
    x = sp.add_parser("status"); x.add_argument("code"); x.set_defaults(f=cmd_status)
    x = sp.add_parser("sql"); x.add_argument("sql", nargs="+", help="one or more SELECT statements"); x.add_argument("--schema", default="default"); x.add_argument("--limit", type=int, default=50); x.set_defaults(f=cmd_sql)
    x = sp.add_parser("api"); x.add_argument("method"); x.add_argument("path"); x.add_argument("--params"); x.add_argument("--body")
    x.add_argument("--system"); x.add_argument("--max", type=int, default=3000); x.set_defaults(f=cmd_api)
    x = sp.add_parser("dump"); x.add_argument("file"); x.add_argument("--out"); x.set_defaults(f=cmd_dump)
    x = sp.add_parser("tally"); x.add_argument("file"); x.add_argument("--probe", help="probe.json, to check that every FOUND trap is mapped")
    x.set_defaults(f=cmd_tally)
    x = sp.add_parser("install-skill"); x.add_argument("dir", nargs="?"); x.set_defaults(f=cmd_install_skill)
    a = ap.parse_args(argv)
    try:
        return a.f(a) or 0
    except Exception as e:
        # a dropped connection or a timeout is not a bug of the run: one line instead of a 60-line traceback
        import requests
        if type(e).__module__.startswith("playwright"):     # e.g. the SSO page never showed its login button
            from .checks.ui import _err_reason
            raise SystemExit("browser: %s | if the site itself does not answer (`rt doctor`), the environment is down "
                             "or blocked: retry later" % _err_reason(e))
        db_down = type(e).__module__.startswith("oracledb") and re.search(r"DPY-6\d{3}|cannot connect|timed out", str(e))
        if db_down or isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout, TimeoutError,
                                     ConnectionError)):
            raise SystemExit("network: %s (%s). The environment did not answer; wait a minute and run the same command "
                             "again (`rt doctor` checks the network)." % (type(e).__name__, str(e).splitlines()[0][:160]))
        raise


if __name__ == "__main__":
    sys.exit(main())
