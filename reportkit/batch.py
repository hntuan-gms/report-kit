"""Several report codes in one request: parse them, group the ones that share a screen, write the plan.

`/report-test 2B_18, 2B_19, 2B_20 note...` runs the same run for every code, but the measuring is done once per
screen group (the "host" workspace), not once per code. Each code still gets its own standalone workbook.
Everything here is pure (no network, no browser) so it can be tested offline.
"""
import json
import os
import re

CODE_RE = re.compile(r"^\[?#?\s*(\d+[A-Za-z]+_?\d+)\]?$")


def parse_codes(tokens):
    """['2B_18,', '2B_19', 'có', 'thể', ...] or '2B_18, 2B_19 note' -> (['2B_18', '2B_19'], 'note').

    Codes come first; the first token that is not a code starts the user's note (the skill reads the note as instructions
    for this run, e.g. "share what can be shared", "no sub-agent may wait more than 5 minutes").
    """
    from .profile import norm_code
    text = " ".join(tokens) if isinstance(tokens, (list, tuple)) else str(tokens or "")
    codes, note = [], []
    for t in re.split(r"[\s,;]+", text):
        if not t:
            continue
        if not note:
            m = CODE_RE.match(t.strip("()."))
            if m:
                c = norm_code(m.group(1))
                if c not in codes:
                    codes.append(c)
                continue
        note.append(t)
    return codes, " ".join(note)


def _top_files(trace, n=3):
    return [x["file"] for x in (trace or {}).get("top", [])[:n]]


def related(ta, tb):
    """Why two traces look like the same screen ([] when they do not)."""
    why = []
    ra, rb = set(ta.get("routes") or []), set(tb.get("routes") or [])
    if ra & rb:
        why.append("same route %s" % ", ".join(sorted(ra & rb)))
    ca, cb = set(ta.get("components") or []), set(tb.get("components") or [])
    if ca & cb:
        why.append("same screen component %s" % os.path.basename(sorted(ca & cb)[0]))
    if len(set(_top_files(ta)) & set(_top_files(tb))) >= 2:
        why.append("2+ of the 3 top code files in common")
    return why


def group_by_screen(traces, joins=()):
    """traces: {code: trace dict or None}. Returns [{codes, host, routes, why, unresolved}] (union of 'related').

    Codes whose trace found nothing (method 'name only') stay alone and are flagged: run `rt start <code> --route /...`
    and `rt batch` again, or force them into a group with joins=[("2B_20", "2B_19")] (CLI: `--join 2B_20:2B_19`) when the
    function is a popup / tab of another code's screen.
    """
    codes = list(traces)
    parent = {c: c for c in codes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    why = {}
    for a, b in joins or ():
        if a in parent and b in parent:
            parent[find(b)] = find(a)
            why.setdefault(a, []).append("joined by hand with %s" % b); why.setdefault(b, []).append("joined by hand with %s" % a)
    for i, a in enumerate(codes):
        for b in codes[i + 1:]:
            w = related(traces[a] or {}, traces[b] or {})
            if w:
                parent[find(b)] = find(a)
                why.setdefault(a, []).extend(w); why.setdefault(b, []).extend(w)
    groups = {}
    for c in codes:
        groups.setdefault(find(c), []).append(c)
    out = []
    for g in groups.values():
        routes = sorted({r for c in g for r in (traces[c] or {}).get("routes") or []})
        unresolved = [c for c in g if len(g) == 1 and not (traces[c] or {}).get("routes") and not (traces[c] or {}).get("components")]
        resolved = [c for c in g if c not in unresolved]
        out.append({"codes": g, "host": (resolved or g)[0], "routes": routes, "unresolved": unresolved,
                    "why": sorted({w for c in g for w in why.get(c, [])})})
    return out


def plan_md(batch_id, note, groups, info):
    """info: {code: {name, group_key, group_file, group_file_exists, ws, method}}."""
    L = ["# Batch %s" % batch_id, "", "Note from the user: %s" % (note or "-"), ""]
    keys = sorted({(info[c].get("group_key") or "-") for g in groups for c in g["codes"]})
    L.append("Function groups (Nhóm): %s" % ", ".join(keys))
    for k in keys:
        files = {(info[c].get("group_file"), info[c].get("group_file_exists")) for g in groups for c in g["codes"] if (info[c].get("group_key") or "-") == k}
        for f, ex in sorted(files, key=str):
            L.append("- %s conventions file: %s (%s)" % (k, f, "exists" if ex else "does not exist yet - create it at the first BA decision"))
    L.append("")
    for n, g in enumerate(groups, 1):
        L.append("## Screen group %d: %s" % (n, ", ".join(g["codes"])))
        L.append("- measuring host (shared checks.yaml, measure scripts, runs): %s  -> %s" % (g["host"], info[g["host"]]["ws"]))
        L.append("- routes: %s" % (", ".join(g["routes"]) or "none found"))
        if g["why"]:
            L.append("- why grouped: %s" % "; ".join(g["why"]))
        if len(g["codes"]) == 1:
            L.append("- single code: measure it in its own workspace")
        for c in g["codes"]:
            L.append("- %s %s [%s]" % (c, info[c].get("name") or "", info[c].get("method") or "?"))
        for c in g["unresolved"]:
            L.append("- !! %s: the trace found no screen. Find its route (menu, routes file, other code's tabs) and run "
                     "`rt start %s --route /...`, then `rt batch` again. If it is a tab or popup of the host's screen, say so in the "
                     "group conventions (decide as BA) and measure it from the host." % (c, c))
        L.append("")
    L += ["## What to do next (SKILL.md 'Batch mode')",
          "1. Trace the code per screen group (sub-agents, read only, 5 minutes max, results as text; you write analysis.md).",
          "2. Ask the user once: account, read-only SELECT OK, other team on the environment. Then `rt login`, `rt probe` every code.",
          "3. Decide the group conventions (Acting as BA) before judging.",
          "4. Measure once per screen group in the host workspace: `rt scaffold`, measure scripts, `rt check --pending` in the background, wait once.",
          "5. One standalone workbook per code (no cross reference to another code), `rt build <code> --check`, then `rt build <code>`.",
          "6. One hand-off for the whole batch."]
    return "\n".join(L)


def save(work_root, batch_id, payload, md):
    d = os.path.join(work_root, "_batch"); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, batch_id + ".json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, default=str)
    p = os.path.join(d, batch_id + ".md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(md)
    return p
