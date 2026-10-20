"""Read the results of `rt check` compactly (`rt show`).

A workspace's runs/ folder holds one folder per run and later runs carry earlier entries over, but a run that was
stopped half way (or `--only`) does not hold everything. `latest(ws, id)` therefore looks from the newest run back.
"""
import json
import os

DEFAULT_NOISE = ("/profile", "session-info", "notifications")


def _runs(ws):
    d = ws.runs_dir()
    return [os.path.join(d, x) for x in sorted(os.listdir(d)) if os.path.isdir(os.path.join(d, x))]


def latest(ws, check_id):
    for r in reversed(_runs(ws)):
        f = os.path.join(r, check_id + ".json")
        if os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            d["_run"] = os.path.basename(r)
            return d
    return None


def all_ids(ws):
    ids, seen = [], set()
    for r in reversed(_runs(ws)):
        for x in sorted(os.listdir(r)):
            if x.endswith(".json") and x not in ("summary.json",) and x[:-5] not in seen:
                seen.add(x[:-5]); ids.append(x[:-5])
    return ids


def statuses(ws):
    """{id: status} of the newest result of every entry that ever ran."""
    return {i: (latest(ws, i) or {}).get("status") for i in all_ids(ws)}


def clip(v, n):
    s = json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + " …(%d chars)" % len(s)


def show(ws, ids, limit=700, noise=None, keys=None):
    """Text block per entry: status, reason, observations (requests without the noise paths, screenshots as file names)."""
    noise = tuple(noise or DEFAULT_NOISE)
    out = []
    for i in ids:
        d = latest(ws, i)
        if not d:
            out.append("## %s MISSING (never ran)" % i); continue
        out.append("## %s %s%s | %s  [run %s]" % (i, d.get("status"), (" - " + d["reason"]) if d.get("reason") else "",
                                                  (d.get("title") or "")[:80], d["_run"]))
        if d.get("kind") == "data":
            out.append("   cells %s, differing %s" % (d.get("cells"), d.get("mismatch_count")))
            continue
        for k, v in (d.get("observations") or {}).items():
            if keys and k not in keys:
                continue
            if k == "screenshots":
                v = [os.path.basename(x) for x in v]
            elif k == "calls" or (isinstance(v, list) and v and isinstance(v[0], list) and len(v[0]) == 3 and isinstance(v[0][2], int)):
                v = [c for c in v if not any(n in c[1] for n in noise)]
            out.append("   %s: %s" % (k, clip(v, limit)))
    return "\n".join(out)
