"""Run the observation / comparison steps of one report and write evidence Claude reads and judges.

checks.yaml (in the report workspace):
    system: ids                 # profile system key
    vars: {company: "VVS"}      # extra template variables (see params.py for built-ins)
    data: [ ... ]               # see checks/data.py - independent SQL vs what the app returns
    ui:   [ ... ]               # see checks/ui.py   - steps + observations, no verdicts

Statuses describe the measurement only. Claude decides P / F / PE from the rules of the report and the standard:
    data: MATCH  every compared cell equals the independent expectation
          DIFF   some cells differ (listed, with the alternative rule that explains each one, if any)
    ui:   OBS    observed - read the observations / screenshots
    both: NM     not measurable: a precondition failed (page not ready, wrong element read...) - fix and re-run
          ERR    the step itself failed (selector, HTTP error, SQL error) - fix and re-run

Output: <workspace>/runs/<run id>/<id>.json, summary.json, summary.md (short, for Claude).
Re-run only what broke: `--only D01,U03`, or `--redo` (every NM / ERR of the latest run). The other
entries are carried over from the latest run, so the summary always covers everything.
"""
import datetime as _dt
import time as _time
import json
import os
import shutil

import yaml

from ..params import base_vars, expand_matrix, render
from . import data as data_check
from . import ui as ui_check


def load(ws):
    p = os.path.join(ws.dir, "checks.yaml")
    if not os.path.exists(p):
        raise SystemExit("No checks.yaml in %s. Write it first (see the skill's references/checks-guide.md)." % ws.dir)
    with open(p, encoding="utf-8") as f:
        spec = yaml.safe_load(f) or {}
    ids = [c.get("id") for c in (spec.get("data") or []) + (spec.get("ui") or [])]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if None in ids or dup:
        raise SystemExit("checks.yaml: every entry needs a unique id (missing or duplicated: %s)" % (dup or "missing id"))
    return spec


def _todo(c, budget):
    return {"id": c["id"], "title": c.get("title"), "status": "TODO",
            "reason": "not run: the run reached its %d s budget (kept under the prompt cache's lifetime); "
                      "`rt check <code> --redo` runs it" % budget}


def run(profile, ws, only=None, redo=False, kinds=("data", "ui"), label=None, workers=None, budget=None):
    budget = int(profile.get("ui.run_budget_s", 180) if budget is None else budget)
    deadline = _time.time() + budget if budget > 0 else None
    spec = load(ws)
    system = spec.get("system") or next(iter(profile.systems))
    prev = ws.latest_run()
    prev_sum = _read(os.path.join(prev, "summary.json")) if prev and os.path.exists(os.path.join(prev, "summary.json")) else None
    selected = set(only or [])
    if redo and prev_sum:
        selected |= {c["id"] for c in prev_sum["checks"] if c["status"] in ("NM", "ERR", "TODO")}
    if redo and not selected:
        print("Nothing to redo: the latest run has no NM / ERR / TODO entries."); return prev, prev_sum
    run_id = _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ("-" + label if label else "")
    rd = os.path.join(ws.runs_dir(), run_id); os.makedirs(rd, exist_ok=True)
    bv = dict(base_vars(), login_user=profile.secrets().get("login_user"))
    vars_ = dict(bv, **render(spec.get("vars") or {}, bv))
    results = []

    def wanted(c):
        return not selected or c["id"] in selected

    if "data" in kinds:
        for c in spec.get("data") or []:
            if not wanted(c):
                continue
            if deadline and _time.time() > deadline:
                results.append(_write(rd, dict(_todo(c, budget), kind="data"))); print("%s TODO" % c["id"]); continue
            parts = []
            for combo in expand_matrix(c.get("matrix"), vars_) or [{}]:
                try:
                    parts.append(data_check.run(profile, system, c, dict(vars_, **combo), rd))
                except Exception as e:
                    parts.append({"vars": combo, "status": "ERR", "reason": str(e).splitlines()[0][:300]})
            results.append(_write(rd, _merge_data(c, parts)))
            print("%s %s" % (c["id"], results[-1]["status"]))
    if "ui" in kinds and any(wanted(c) for c in spec.get("ui") or []):
        entries = [render(c, vars_) for c in spec.get("ui") or [] if wanted(c)]
        n = max(1, min(int(workers or profile.get("ui.workers", 1)), len(entries)))
        results += _run_ui(profile, system, entries, rd, n, deadline, budget)
    done = {r["id"] for r in results}
    if selected and prev:
        for c in (spec.get("data") or []) + (spec.get("ui") or []):
            src = os.path.join(prev, c["id"] + ".json")
            if c["id"] not in done and os.path.exists(src):
                r = _read(src); r["carried_from"] = r.get("carried_from") or os.path.basename(prev)
                _copy_shots(prev, rd, c["id"])
                results.append(_write(rd, r))
    order = [c["id"] for c in (spec.get("data") or []) + (spec.get("ui") or [])]
    results.sort(key=lambda r: order.index(r["id"]) if r["id"] in order else 999)
    summary = {"run": run_id, "report": ws.code, "system": system, "at": _dt.datetime.now().isoformat(timespec="seconds"),
               "checks": [{k: r.get(k) for k in ("id", "kind", "title", "status", "reason", "carried_from")} for r in results]}
    with open(os.path.join(rd, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1, default=str)
    with open(os.path.join(rd, "summary.md"), "w", encoding="utf-8") as f:
        f.write(summary_md(summary, results))
    ws.mark("check", run=run_id, counts=_counts(results))
    return rd, summary


def _run_ui(profile, system, entries, rd, workers, deadline=None, budget=0):
    """UI entries, each in its own browser context. With workers > 1 they run on that many threads, each with its own
    Playwright and browser (the sync API is per thread), so a long run stays within the prompt cache's lifetime."""
    import queue
    import threading
    from playwright.sync_api import sync_playwright
    todo, out, lock = queue.Queue(), [], threading.Lock()
    for c in entries:
        todo.put(c)

    def worker():
        with sync_playwright() as p:
            b = p.chromium.launch()
            try:
                while True:
                    if deadline and _time.time() > deadline:
                        return                  # the rest is reported as TODO below
                    try:
                        rc = todo.get_nowait()
                    except queue.Empty:
                        return
                    try:
                        r = ui_check.run(profile, system, rc, b, rd)
                    except Exception as e:      # ui_check.run reports its own errors; this guards the thread
                        r = {"id": rc["id"], "status": "ERR", "reason": str(e).splitlines()[0][:300]}
                    r.update(kind="ui", title=rc.get("title"))
                    with lock:
                        out.append(_write(rd, r))
                        print("%s %s" % (rc["id"], r["status"]), flush=True)
            finally:
                b.close()

    if workers == 1:
        worker()
    else:
        threads = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    while not todo.empty():
        rc = todo.get_nowait()
        out.append(_write(rd, dict(_todo(rc, budget), kind="ui"))); print("%s TODO" % rc["id"], flush=True)
    return out


def _copy_shots(prev, rd, cid):
    src = os.path.join(prev, "shots")
    if os.path.isdir(src):
        dst = os.path.join(rd, "shots"); os.makedirs(dst, exist_ok=True)
        for f in os.listdir(src):
            if f.startswith(cid + "_"):
                shutil.copy(os.path.join(src, f), dst)


def _merge_data(c, parts):
    st = [p["status"] for p in parts]
    status = "ERR" if "ERR" in st else "NM" if "NM" in st else "DIFF" if "DIFF" in st else "MATCH"
    cells = sum(p.get("cells", 0) for p in parts); mism = sum(len(p.get("mismatches", [])) for p in parts)
    return {"id": c["id"], "kind": "data", "title": c.get("title"), "status": status,
            "reason": "; ".join(p["reason"] for p in parts if p.get("reason")) or None,
            "cells": cells, "mismatch_count": mism, "parts": parts}


def _write(rd, r):
    with open(os.path.join(rd, r["id"] + ".json"), "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1, default=str)
    return r


def _read(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _counts(results):
    out = {}
    for r in results:
        out[r["status"]] = out.get(r["status"], 0) + 1
    return out


CLIP = 400      # summary.md shortens each observation; `rt show --keys` prints them whole


def _clip(v, n=None):
    n = n or CLIP
    s = json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + " …(%d chars, full text in the .json)" % len(s)


def summary_md(summary, results, max_mismatch=12):
    """Short text for Claude: one block per entry; full detail stays in <id>.json and shots/."""
    L = ["# Run %s - %s (%s)" % (summary["run"], summary["report"], summary["system"]),
         "Counts: " + ", ".join("%s=%d" % kv for kv in sorted(_counts(results).items())), ""]
    for r in results:
        head = "## %s [%s] %s" % (r["id"], r["status"], r.get("title") or "")
        if r.get("carried_from"):
            head += "  (carried from %s)" % r["carried_from"]
        L.append(head)
        if r.get("reason"):
            L.append("reason: " + r["reason"])
        if r.get("kind") == "data":
            L.append("cells compared: %d, differing: %d" % (r.get("cells", 0), r.get("mismatch_count", 0)))
            for p in r.get("parts", []):
                ms = p.get("mismatches", [])
                expl = {}
                for m in ms:
                    for e in m.get("explained_by") or ["(unexplained)"]:
                        expl[e] = expl.get(e, 0) + 1
                L.append("- %s: %s, %s cells, %d diff%s%s%s" % (
                    p.get("vars") or "-", p.get("status"), p.get("cells", "?"), len(ms),
                    (", explained by " + ", ".join("%s=%d" % kv for kv in expl.items())) if ms else "",
                    (", extra rows %d" % len(p["extra_in_actual"])) if p.get("extra_in_actual") else "",
                    (", missing rows %d" % len(p["missing_in_actual"])) if p.get("missing_in_actual") else ""))
                if p.get("reason"):
                    L.append("    reason: " + p["reason"])
                for m in ms[:max_mismatch]:
                    L.append("    %s.%s: app=%s expected=%s %s" % (m["key"], m["field"], m["actual"], m["expected"],
                                                                 ("[" + ",".join(m["explained_by"]) + "]") if m.get("explained_by") else ""))
                if len(ms) > max_mismatch:
                    L.append("    … %d more in %s.json" % (len(ms) - max_mismatch, r["id"]))
        else:
            for k, v in (r.get("observations") or {}).items():
                if k == "screenshots":
                    L.append("- screenshots: " + ", ".join(os.path.basename(x) for x in v)); continue
                L.append("- %s: %s" % (k, _clip(v)))
            if r.get("screenshot"):
                L.append("- screenshot: " + os.path.basename(r["screenshot"]))
        L.append("")
    return "\n".join(L)
