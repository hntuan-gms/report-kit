"""Data traps: run the profile's catalogue of known data pitfalls on the tables a report reads,
and keep real examples. This is step "profile the data" of the method, done by a script instead
of hand-written queries each time.

rules/traps.yaml (in the profile):
  traps:
    - id: lang_twins
      title: Bản ghi VI và EN song song cho cùng một nghiệp vụ
      needs: [LANGUAGE_CD, COMPANY_PROFILE_ID, FORM_ID]     # every column must exist in the table
      period_any: [PERIOD_YEAR, REPORT_YEAR]                  # optional: first existing column -> {period}
      sql: >
        SELECT COUNT(*) N FROM (SELECT COMPANY_PROFILE_ID, FORM_ID, {period} FROM {table}
        GROUP BY COMPANY_PROFILE_ID, FORM_ID, {period} HAVING COUNT(DISTINCT LANGUAGE_CD) > 1)
      flag: {col: N, gt: 0}                                   # or {rows_gt: 1}
      example: "SELECT ID, LANGUAGE_CD FROM {table} WHERE ... AND ROWNUM <= 3"
      lesson: "Đếm không lọc LANGUAGE_CD sẽ gần gấp đôi (1E_117)"
Placeholders: {table}, {period}, and {<col>} for any column listed in `pick:` ({name: [candidates]}).
"""
import os

import yaml

from . import db


def load_traps(profile):
    p = profile.path(profile.get("rules.traps", "rules/traps.yaml"))
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("traps", [])


def _flagged(rule, rows):
    if not rule:
        return bool(rows)
    if "rows_gt" in rule:
        return len(rows) > rule["rows_gt"]
    if "col" in rule:
        return any((r.get(rule["col"]) or 0) > rule.get("gt", 0) for r in rows)
    return bool(rows)


def probe(profile, ws, tables, schema="default", limit_rows=12):
    traps = load_traps(profile)
    out = {"tables": {}, "schema": schema}
    known = set(db.tables(profile, schema))
    for t in tables:
        t = t.upper()
        if t not in known:
            out["tables"][t] = {"error": "not a table / view in schema %s" % schema}; continue
        cols = set(db.columns(profile, t, schema))
        res = []
        for tr in traps:
            if not set(c.upper() for c in tr.get("needs", [])) <= cols:
                continue
            subs = {"table": t}
            if tr.get("period_any"):
                per = next((c for c in tr["period_any"] if c.upper() in cols), None)
                if not per:
                    continue
                subs["period"] = per
            ok = True
            for name, cands in (tr.get("pick") or {}).items():
                c = next((x for x in cands if x.upper() in cols), None)
                if not c:
                    ok = False; break
                subs[name] = c
            if not ok:
                continue
            item = {"id": tr["id"], "title": tr.get("title"), "lesson": tr.get("lesson")}
            try:
                rows = db.q(profile, tr["sql"].format(**subs), None, schema)
                item["rows"] = rows[:limit_rows]
                item["flagged"] = _flagged(tr.get("flag"), rows)
                if item["flagged"] and tr.get("example"):
                    item["examples"] = db.q(profile, tr["example"].format(**subs), None, schema)[:5]
            except Exception as e:
                item["error"] = str(e).splitlines()[0][:200]
            res.append(item)
        out["tables"][t] = {"columns": len(cols), "traps": res}
    import json
    with open(os.path.join(ws.dir, "probe.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    ws.mark("probe", tables=list(out["tables"]))
    return out


def probe_md(out):
    L = ["# Data traps (schema %s)" % out["schema"]]
    for t, info in out["tables"].items():
        L.append("## %s" % t)
        if info.get("error"):
            L.append("- " + info["error"]); continue
        for it in info["traps"]:
            mark = "ERROR" if it.get("error") else ("FOUND" if it.get("flagged") else "none")
            L.append("- [%s] %s: %s" % (mark, it["id"], it.get("title") or ""))
            if it.get("error"):
                L.append("    " + it["error"])
            elif it.get("flagged"):
                L.append("    rows: " + str(it.get("rows"))[:400])
                if it.get("examples"):
                    L.append("    examples: " + str(it["examples"])[:400])
                if it.get("lesson"):
                    L.append("    why it matters: " + it["lesson"])
    return "\n".join(L)
