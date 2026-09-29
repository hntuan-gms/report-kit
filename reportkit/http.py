"""HTTP calls with the saved login session.

Only call endpoints whose handler you have read and confirmed to be read-only (search / lookup /
export endpoints are often POST - classify by what the handler does, not by the verb).
"""
import datetime as _dt
import os
import pickle
import re

_sessions = {}


def session_paths(profile, system):
    d = os.path.join(profile.work_root, "_sessions"); os.makedirs(d, exist_ok=True)
    return os.path.join(d, "state_%s.json" % system), os.path.join(d, "cookies_%s.pkl" % system)


def session(profile, system):
    import requests
    k = (profile.name, system)
    if k not in _sessions:
        _, jar = session_paths(profile, system)
        if not os.path.exists(jar):
            raise SystemExit("No login session for '%s'. Run: rt login --system %s" % (system, system))
        s = requests.Session()
        with open(jar, "rb") as f:
            s.cookies = pickle.load(f)
        s.headers.update(profile.get("http.headers", {}) or {})
        _sessions[k] = s
    return _sessions[k]


def reset(profile, system):
    _sessions.pop((profile.name, system), None)


def call(profile, system, method, path, params=None, body=None, timeout=120):
    api = profile.system(system)["api"].rstrip("/")
    r = session(profile, system).request(method.upper(), api + path, params=params, json=body, timeout=timeout)
    return r


def json_call(profile, system, method, path, params=None, body=None):
    r = call(profile, system, method, path, params, body)
    ct = r.headers.get("Content-Type", "")
    return r.status_code, (r.json() if "json" in ct else r.text[:2000])


def download(profile, system, method, path, params=None, body=None, out_dir=None, tag=None, timeout=180):
    """Export endpoints: saves the file if the response is a zip/xlsx; else returns the error body."""
    r = call(profile, system, method, path, params, body, timeout)
    cd = r.headers.get("Content-Disposition", "")
    res = {"status": r.status_code, "size": len(r.content),
           "fname": (re.findall(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd) or [None])[0]}
    if r.status_code == 200 and r.content[:2] == b"PK":
        out_dir = out_dir or os.path.join(profile.work_root, "_downloads"); os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, "%s.xlsx" % (tag or _dt.datetime.now().strftime("%H%M%S%f")))
        with open(p, "wb") as f:
            f.write(r.content)
        res["path"] = p
    else:
        res["body"] = r.text[:1000]
    return res


def dig(obj, dotted):
    """'data.data' / 'data.items[0].x' lookup in a JSON response."""
    cur = obj
    if not dotted:
        return cur
    for part in dotted.split("."):
        m = re.match(r"^(\w+)\[(\d+)\]$", part)
        if m:
            cur = (cur or {}).get(m.group(1)); cur = cur[int(m.group(2))] if cur is not None else None
        else:
            cur = (cur or {}).get(part) if isinstance(cur, dict) else None
    return cur
