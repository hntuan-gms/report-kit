"""What the deployed frontend really does: search its JS bundle (the build can differ from the repo).

`rt deployed "<text or regex>" [--system ids]` downloads index.html, the entry scripts and every chunk they import
(static files, GET only, cached per day under <work_root>/_deployed/<system>/<date>/), then prints each match with
the code around it. One call instead of fetching and grepping chunks by hand.
"""
import datetime as _dt
import os
import re
from concurrent.futures import ThreadPoolExecutor

_SCRIPT = re.compile(r"""(?:src|href)=["']([^"']+\.js)["']""")
_CHUNK = re.compile(r"\b((?:chunk|main|polyfills|runtime|scripts)(?:-[\w]+)?\.js)\b")


def _get(url, timeout=30):
    import requests
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text


def crawl(web, cache_dir, fetch=None, limit=600):
    """{file name: text} of the deployed bundle reachable from index.html (main / chunk / runtime scripts only)."""
    fetch = fetch or _get
    os.makedirs(cache_dir, exist_ok=True)
    web = web.rstrip("/")

    def load(name):
        p = os.path.join(cache_dir, name.replace("/", "_"))
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="ignore") as f:
                return f.read()
        text = fetch(web + "/" + name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return text

    index = load("index.html")
    todo = [os.path.basename(m) for m in _SCRIPT.findall(index) if _CHUNK.fullmatch(os.path.basename(m))]
    seen, files = set(), {}
    with ThreadPoolExecutor(8) as pool:
        while todo and len(seen) < limit:
            batch = [n for n in dict.fromkeys(todo) if n not in seen][: limit - len(seen)]
            todo = []
            seen.update(batch)
            for name, text in zip(batch, pool.map(lambda n: _safe(load, n), batch)):
                if text is None:
                    continue
                files[name] = text
                todo += [m for m in _CHUNK.findall(text) if m not in seen]
    return files


def _safe(load, name):
    try:
        return load(name)
    except Exception:
        return None


def search(files, pattern, context=300, limit=12):
    """[(file, offset, snippet)] of the matches of `pattern` (regex, case-insensitive; plain text works too)."""
    rx = re.compile(pattern, re.I)
    out = []
    for name in sorted(files):
        text = files[name]
        for m in rx.finditer(text):
            a, b = max(0, m.start() - context), min(len(text), m.end() + context)
            out.append((name, m.start(), " ".join(text[a:b].split())))
            if len(out) >= limit:
                return out
    return out


def cache_dir(profile, system):
    return os.path.join(profile.work_root, "_deployed", system, _dt.date.today().isoformat())
