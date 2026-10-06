"""Find the code behind a report from the function list's menu path and name, without the model grepping around.

The chain is followed the way a reader would:
  1. menu path ('Thống kê >> Thống kê CTĐC >> BC tổng hợp quản trị công ty') -> the i18n keys whose label matches
     each level (profile `codemap.i18n`, the UI language);
  2. the menu definition entry with that title key, and its nested parents -> its link (route);
     (no menu path, or no match: the screen name is matched against i18n titles and the component that uses that key)
  3. the route definition -> the screen component (.ts + .html);
  4. the services the component calls -> the API URLs;
  5. backend: the component's distinctive identifiers (report-code constants such as R017_..., URL segments) are the
     fingerprints. Every file under `codemap.include` is scored by the distinct fingerprints it contains, weighted by
     rarity (a token found in 3 files counts far more than one found in 300);
  6. the SQL objects of the top files, the view definitions behind them, and the Excel templates they name.

`rt start <code> --route /path` skips steps 1-2 when the menu can't be matched.
The result is a starting point Claude verifies by reading those files, not a conclusion.
Cached per git commit + seeds in <workspace>/trace.json.

profile:
  codemap:
    include: ["*-service/src/main/**/*.java", "*-frontend/src/app/**/*.ts", "*-frontend/src/assets/i18n/**/*.json", ...]
    exclude: ["**/*.spec.ts", "**/test/**"]
    i18n: "**/i18n/vi/**/*.json"            # label files of the UI language the menu path is written in
    frontend: {ids: ids-frontend, audit: audit-frontend}   # system key -> folder of its frontend (narrows steps 1-4)
    stop_tokens: [ID, NAME, CODE]           # too common to mean anything
"""
import fnmatch
import hashlib
import json
import math
import os
import re
import subprocess
import unicodedata

IDENT = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b|\bR\d{3}[A-Z0-9_]*\b")
QUOTED = re.compile(r"['\"‘’“”]([A-Za-z][A-Za-z0-9_]{3,})['\"‘’“”]")
UPPER_PHRASE = re.compile(r"(?:[A-ZÀ-Ỹ&][A-ZÀ-Ỹ0-9&]*[ \t]+){2,}[A-ZÀ-Ỹ0-9&]+")
CELL_REF = re.compile(r"(?:^|(?<=\s))[A-Z]{1,3}\d{1,6}=")
ENDPOINT_BE = re.compile(r"@(Get|Post|Put|Delete|Patch|Request)Mapping\(\s*(?:value\s*=\s*|path\s*=\s*)?\"([^\"]*)\"")
URL_FE = re.compile(r"['\"`](/?[a-z][\w-]*(?:/[\w${}.-]+){1,})['\"`]")
SQL_OBJ = re.compile(r"\b(?:FROM|JOIN)\s+([A-Z][A-Z0-9_]{3,})\b", re.I)
TABLE_ANN = re.compile(r"@(?:Table|View)\(\s*name\s*=\s*\"(?:\w+\.)?([A-Za-z][A-Za-z0-9_]{3,})\"")
TEMPLATE = re.compile(r"[\"']([\w/.-]+\.xlsx?)[\"']")
DEFAULT_STOP = {"ID", "NAME", "CODE", "TYPE", "DATE", "STATUS", "DELETE_FLG", "CREATED_BY", "CREATED_DATE", "UPDATED_BY",
                "UPDATED_DATE", "LANGUAGE_CD", "UTF_8", "YYYY_MM_DD"}
GENERIC_SEGMENTS = {"api", "v1", "v2", "search", "export", "list", "detail", "details", "report", "reports", "get", "all",
                    "page", "paging", "create", "update", "delete", "save", "lookup", "common", "master", "data"}
SKIP_DIRS = {"node_modules", "target", "dist", ".git", ".angular", "build", ".idea"}


# ------------------------------------------------------------------ small helpers
def fingerprints(text, extra_phrases=(), stop=()):
    """Identifiers and upper-case phrases of a free text (e.g. a name, a dumped document)."""
    stop = DEFAULT_STOP | {s.upper() for s in stop}
    text = CELL_REF.sub("\n", text).replace(" | ", "\n").replace(" / ", "\n")   # dumped xlsx: 'B40=x | C40=y'
    ids = {t for t in IDENT.findall(text) if t not in stop and len(t) >= 4}
    ids |= {t for t in QUOTED.findall(text) if t.upper() == t and t not in stop}
    phrases = {" ".join(p.split()) for p in UPPER_PHRASE.findall(text) if len(p) >= 12}
    phrases |= {" ".join(p.split()) for p in extra_phrases if p and len(p) >= 8}
    return sorted(ids), sorted(phrases)


def norm(s):
    """Label comparison form: NFC, lower case, single spaces, no surrounding punctuation."""
    s = unicodedata.normalize("NFC", str(s or "")).lower()
    return " ".join(s.split()).strip(" .:;,-*")


def label_variants(label):
    """'CTĐC đăng ký/ Danh sách (mới)' -> the label, without the parenthesis, and each '/' alternative."""
    out = []
    for v in (label, re.sub(r"\([^)]*\)", "", label)):
        for x in [v] + v.split("/"):
            x = norm(x)
            if len(x) >= 3 and x not in out:
                out.append(x)
    return out


_GLOBS = {}


def _match(rel, pat):
    """Glob match ('*' crosses folders, like fnmatch) where '**/' may also stand for no folder at all."""
    rx = _GLOBS.get(pat)
    if rx is None:
        alts = {pat, pat.replace("/**/", "/")} | ({pat[3:]} if pat.startswith("**/") else set())
        rx = _GLOBS[pat] = re.compile("|".join("(?:%s)" % fnmatch.translate(a) for a in sorted(alts)))
    return rx.match(rel) is not None


def _git_head(root):
    try:
        return subprocess.check_output(["git", "-C", root, "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "nogit"


def _files(profile):
    cm = profile.get("codemap", {}) or {}
    inc = cm.get("include") or ["**/*.java", "**/*.ts", "**/*.html", "**/*.sql", "**/i18n/**/*.json"]
    exc = cm.get("exclude") or ["**/node_modules/**", "**/target/**", "**/dist/**", "**/.git/**"]
    root = profile.code_root
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            rel = os.path.relpath(os.path.join(d, f), root).replace("\\", "/")
            if any(_match(rel, p) for p in inc) and not any(_match(rel, p) for p in exc):
                yield rel


class _Code(object):
    """The code base as relative paths, with cached reads."""

    def __init__(self, profile):
        self.root = profile.code_root
        self.files = list(_files(profile))
        self._text = {}

    def text(self, rel):
        if rel not in self._text:
            try:
                with open(os.path.join(self.root, rel), encoding="utf-8", errors="ignore") as f:
                    self._text[rel] = f.read()
            except OSError:
                self._text[rel] = ""
        return self._text[rel]

    def exists(self, rel):
        return os.path.isfile(os.path.join(self.root, rel))

    @staticmethod
    def line(text, pos):
        return text.count("\n", 0, pos) + 1


# ------------------------------------------------------------------ 1. labels -> i18n keys
def _flatten(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten(v, "%s.%s" % (prefix, k) if prefix else str(k))
    elif isinstance(obj, str):
        yield prefix, obj


def i18n_index(code, glob_pat, fe=None):
    """[(file, dotted key, label)] of the UI-language label files."""
    out = []
    for rel in code.files:
        if not rel.endswith(".json") or not _match(rel, glob_pat) or (fe and not rel.startswith(fe.rstrip("/") + "/")):
            continue
        try:
            data = json.loads(code.text(rel))
        except ValueError:
            continue
        out += [(rel, k, v) for k, v in _flatten(data)]
    return out


def keys_for(index, label, fuzzy=0.0):
    """i18n keys whose label equals one of the label's variants (or, with `fuzzy`, shares that share of words)."""
    vs = set(label_variants(label))
    out = {k for _, k, v in index if norm(v) in vs}
    if out or not fuzzy:
        return out
    a = set(norm(label).split())
    best, keys = 0.0, set()
    for _, k, v in index:
        b = set(norm(v).split())
        if len(b) < 3:
            continue
        sim = 2.0 * len(a & b) / (len(a) + len(b))
        if sim >= fuzzy and sim >= best:
            keys = keys | {k} if sim == best else {k}
            best = sim
    return keys


# ------------------------------------------------------------------ 2. menu definitions
_TITLE = re.compile(r"\b(?:title|label|name|text)\s*:\s*['\"]([^'\"]+)['\"]")
_LINK = re.compile(r"\b(?:routerLink|link|url|route)\s*:\s*['\"](/[^'\"]*)['\"]")


def menu_entries(text):
    """Entries of a TS menu definition: [{title, link, parents: [titles], pos}], by tracking object nesting."""
    entries, stack, i, n = [], [], 0, len(text)
    while i < n:
        c = text[i]
        if c in "'\"`":                                     # skip string literals
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if c == "/" and text[i:i + 2] == "//":
            i = text.find("\n", i)
            i = n if i < 0 else i
            continue
        if c == "{":
            stack.append({"start": i, "title": None, "link": None})
        elif c == "}" and stack:
            obj = stack.pop()
            body = text[obj["start"]:i + 1]
            depth, own = 0, []
            for k, ch in enumerate(body[1:-1]):              # keep the object's own keys, not its children's
                if ch in "{[":
                    depth += 1
                elif ch in "}]":
                    depth -= 1
                elif depth == 0:
                    own.append(ch)
                else:
                    own.append(" ")
            own = "".join(own)
            t, l = _TITLE.search(own), _LINK.search(own)
            obj["title"] = t.group(1) if t else None
            obj["link"] = l.group(1) if l else None
            if obj["title"]:                                 # parents' titles are not known yet: resolved below
                entries.append({"title": obj["title"], "link": obj["link"], "pos": obj["start"], "_parents": list(stack)})
        i += 1
    by_start = {}
    for e in entries:
        by_start[e["pos"]] = e["title"]
    for e in entries:
        e["parents"] = [by_start.get(p["start"]) for p in e.pop("_parents") if by_start.get(p["start"])]
    return entries


def resolve_menu(code, index, path, fe=None):
    """Menu entries for the deepest level of the path that is a menu item (trailing tabs / buttons are dropped)."""
    for k in range(len(path), 0, -1):
        found = _menu_level(code, index, path[:k], fe)
        if found:
            for f in found:
                f["unmatched_tail"] = path[k:]
            return found
    return []


def _menu_level(code, index, path, fe):
    """Menu entries whose title matches the last level of the path, ranked by how many parent levels also match."""
    want = [keys_for(index, lv) for lv in path]
    if not want[-1]:
        return []
    found = []
    for rel in code.files:
        if not rel.endswith(".ts") or (fe and not rel.startswith(fe.rstrip("/") + "/")):
            continue
        text = code.text(rel)
        if not any(k in text for k in want[-1]):
            continue
        for e in menu_entries(text):
            if e["title"] in want[-1] and e["link"]:
                score = 1 + sum(1 for keys in want[:-1] if keys & set(e["parents"]))
                found.append({"file": rel, "line": code.line(text, e["pos"]), "title": e["title"], "parents": e["parents"],
                              "link": e["link"], "score": score})
    if not found:
        return []
    best = max(f["score"] for f in found)
    return [f for f in found if f["score"] == best]


# ------------------------------------------------------------------ 3. route -> component
_LOAD = re.compile(r"(?:loadComponent|loadChildren)\s*:\s*\(\)\s*=>\s*import\(\s*['\"]([^'\"]+)['\"]")
_COMP = re.compile(r"\bcomponent\s*:\s*(\w+)")


def _resolve_import(code, from_rel, spec):
    base = os.path.normpath(os.path.join(os.path.dirname(from_rel), spec)).replace("\\", "/")
    for cand in (base + ".ts", base, base + "/index.ts"):
        if code.exists(cand):
            return cand
    return None


def resolve_route(code, route, fe=None):
    """(routes file, line, component .ts) for a route like '/statistics/a/b', trying the longest matching suffix first."""
    segs = [s for s in route.strip("/").split("/") if s]
    for k in range(len(segs)):
        suffix = "/".join(segs[k:])
        pat = re.compile(r"\bpath\s*:\s*['\"]%s['\"]" % re.escape(suffix))
        for rel in code.files:
            if not rel.endswith(".ts") or (fe and not rel.startswith(fe.rstrip("/") + "/")):
                continue
            text = code.text(rel)
            m = pat.search(text)
            if not m:
                continue
            window = text[m.end():m.end() + 600]
            nxt = re.search(r"\bpath\s*:", window)
            window = window[:nxt.start()] if nxt else window
            imp = _LOAD.search(window)
            comp = None
            if imp:
                comp = _resolve_import(code, rel, imp.group(1))
            else:
                cm = _COMP.search(window)
                if cm:
                    im = re.search(r"import\s*\{[^}]*\b%s\b[^}]*\}\s*from\s*['\"]([^'\"]+)['\"]" % cm.group(1), text)
                    comp = _resolve_import(code, rel, im.group(1)) if im else None
            if comp:
                return rel, code.line(text, m.start()), comp
    return None


def components_for_titles(code, index, names, fe=None):
    """Screen components that use an i18n key whose label is one of the screen names (fallback without a menu path)."""
    keys = set()
    for nm in names:
        keys |= keys_for(index, nm, fuzzy=0.75)
    hits = {}
    for rel in code.files:
        if not rel.endswith((".html", ".ts")) or (fe and not rel.startswith(fe.rstrip("/") + "/")) or "i18n" in rel:
            continue
        text = code.text(rel)
        for k in keys:
            if "." in k and ("'%s'" % k in text or ".%s'" % k in text or '"%s"' % k in text or '.%s"' % k in text):
                ts = rel[:-5] + ".ts" if rel.endswith(".html") else rel
                if ts.endswith(".component.ts") and code.exists(ts):
                    hits.setdefault(ts, set()).add(k)
    return sorted(hits, key=lambda r: -len(hits[r]))


# ------------------------------------------------------------------ 4. component -> services -> URLs
_IMPORT = re.compile(r"import\s*\{([^}]*)\}\s*from\s*['\"](\.[^'\"]+)['\"]")
_INJECT = re.compile(r"(\w+)\s*=\s*inject\(\s*(\w+)\s*\)")
_CTOR = re.compile(r"(?:private|public|protected)\s+(?:readonly\s+)?(\w+)\s*:\s*(\w+)")
_CALL = re.compile(r"this\.(\w+)\.(\w+)\s*\(")
_FIELD_STR = re.compile(r"(\w+)\s*=\s*['\"]([^'\"]+)['\"]")
_URL_TPL = re.compile(r"`([^`]*\$\{[^`]*)`|['\"](/[^'\"\s]+)['\"]")
_METHOD_DEF = re.compile(r"^[ \t]{1,16}(?:public |private |protected |async |static |override )*(\w+)\s*(?:<[^>]*>)?\s*\(", re.M)


def services_of(code, comp):
    """{service class: (file, [called methods])} for the services the component imports and calls."""
    text = code.text(comp)
    classes = {}
    for names, spec in _IMPORT.findall(text):
        for nm in (x.strip() for x in names.split(",")):
            if nm.endswith("Service"):
                f = _resolve_import(code, comp, spec)
                if f:
                    classes[nm] = f
    fields = {f: c for f, c in _INJECT.findall(text) + _CTOR.findall(text) if c in classes}
    out = {c: (f, []) for c, f in classes.items()}
    for fld, meth in _CALL.findall(text):
        if fld in fields and meth not in out[fields[fld]][1]:
            out[fields[fld]][1].append(meth)
    return out


def endpoints_of(code, svc_file, methods):
    """['METHOD url'] for the given methods of a service: the URL templates in each method's body."""
    text = code.text(svc_file)
    consts = dict(_FIELD_STR.findall(text))
    defs = [(m.group(1), m.start()) for m in _METHOD_DEF.finditer(text)]
    out = []
    for i, (name, pos) in enumerate(defs):
        if name not in methods:
            continue
        body = text[pos:defs[i + 1][1] if i + 1 < len(defs) else len(text)]
        verb = re.search(r"\.(get|post|put|delete|patch)\s*[<(]", body)
        for a, b in _URL_TPL.findall(body):
            u = a or b
            if "/" not in u:
                continue
            u = re.sub(r"\$\{\s*this\.(\w+)\s*\}", lambda m: consts.get(m.group(1), "{%s}" % m.group(1)), u)
            u = re.sub(r"\$\{[^}]*\}", "{}", u)
            u = re.sub(r"^\{(?:baseUrl|apiBase|base)\}", "", u)
            out.append("%s %s (%s.%s)" % ((verb.group(1).upper() if verb else "?"), u, os.path.basename(svc_file), name))
    return out


def seeds_from_component(code, comp, extra_files=(), stop=()):
    """Distinctive identifiers of the screen: constants / enum members in the component and its template."""
    stop = DEFAULT_STOP | {s.upper() for s in stop}
    ids = set()
    for rel in [comp] + list(extra_files):
        t = code.text(rel)
        ids |= {x for x in IDENT.findall(t) if x not in stop and len(x) >= 4}
        ids |= {x for x in re.findall(r"\b[A-Z]\w*\.([A-Z][A-Z0-9_]{3,})\b", t) if x not in stop}
    return sorted(ids)


def url_seeds(endpoints):
    """The most specific literal segment of each URL ('/masterdata/categories/all-parents' -> 'all-parents')."""
    segs = set()
    for e in endpoints:
        url = e.split(" ")[1]
        lits = [s for s in url.strip("/").split("/") if "{" not in s and len(s) >= 6 and s.lower() not in GENERIC_SEGMENTS]
        if lits:
            segs.add(lits[-1])
    return sorted(segs)


# ------------------------------------------------------------------ 5-6. backend scoring, SQL, views, templates
def score_files(code, ids, phrases, skip=(), weights=None, skip_ext=(), registry_rx=None):
    """Files ranked by the distinct fingerprints they contain, each weighted by rarity (and by `weights`, default 1).

    A file naming more than 8 different report codes (`registry_rx`: an enum, a template list) is a registry, not the
    report's code: its score counts for 0.2.
    """
    df, hits, registry = {}, {}, set()
    weights = weights or {}
    phr_norm = {p: p.lower() for p in phrases}
    for rel in code.files:
        if rel in skip or "/i18n/" in rel or rel.endswith(tuple(skip_ext)):
            continue
        text = code.text(rel)
        low = text.lower()
        found = {}
        for t in ids:
            i = text.find(t)
            if i >= 0:
                found[t] = code.line(text, i)
        for p, pl in phr_norm.items():
            i = low.find(pl)
            if i >= 0:
                found[p] = code.line(text, i)
        if found:
            hits[rel] = found
            for t in found:
                df[t] = df.get(t, 0) + 1
            if registry_rx is not None and len(set(registry_rx.findall(text))) > 8:
                registry.add(rel)
    n = max(1, len(hits))
    scored = [(round(sum(math.log(1 + n / df[t]) * weights.get(t, 2.0 if t in phr_norm else 1.0) for t in found)
                     * (0.2 if rel in registry else 1.0), 2), rel, found)
              for rel, found in hits.items()]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored, df


def role(rel):
    if rel.endswith(".component.ts"):
        return "component"
    if rel.endswith(".html"):
        return "template"
    if rel.endswith("service.ts"):
        return "FE service"
    if rel.endswith("Controller.java"):
        return "controller"
    if rel.endswith(".sql"):
        return "sql"
    if rel.endswith(".java"):
        return "java"
    return os.path.splitext(rel)[1].lstrip(".") or "file"


def file_info(code, rel):
    text = code.text(rel)
    eps = ["%s %s" % (m[0].upper(), m[1]) for m in ENDPOINT_BE.findall(text)][:12]
    sql = sorted(set(x.upper() for x in SQL_OBJ.findall(text)))[:15] if re.search(r"\b(SELECT|FROM)\b", text) else []
    sql = sorted(set(sql) | {x.upper() for x in TABLE_ANN.findall(text)})
    return eps, sql


def find_views(code, objects):
    """{object: (file, line)} for the .sql files that define a view / table named in `objects`."""
    out = {}
    want = {o.upper() for o in objects}
    for rel in code.files:
        if not rel.endswith(".sql"):
            continue
        text = code.text(rel)
        for m in re.finditer(r"\b(?:VIEW|TABLE)\s+(?:\w+\.)?\"?([A-Za-z][A-Za-z0-9_]{3,})\"?", text, re.I):
            name = m.group(1).upper()
            if name in want and name not in out:
                out[name] = (rel, code.line(text, m.start()))
    return out


def find_templates(code, files):
    """Excel templates named near a matched fingerprint of the top files ('templates/excel/R017_x.xlsx')."""
    names = []
    for x in files:
        lines = code.text(x["file"]).splitlines()
        for ln in set((x.get("matches") or {}).values()):
            for nm in TEMPLATE.findall("\n".join(lines[max(0, ln - 3):ln + 15])):
                if nm not in names:
                    names.append(nm)
    if not names:
        return []
    found = {}
    for d, dirs, fs in os.walk(code.root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in fs:
            if f.lower().endswith((".xlsx", ".xls")):
                found.setdefault(f, []).append(os.path.relpath(os.path.join(d, f), code.root).replace("\\", "/"))
    out = []
    for nm in names:
        base = nm.replace("\\", "/").lstrip("/")
        out += [p for p in found.get(os.path.basename(base), []) if p.endswith(base) and p not in out]
    return out


# ------------------------------------------------------------------ main entry
def locate(profile, ws, fn, route=None, top=15, force=False):
    """Trace a report's code from its function-list row (`fn`: menu, name, description, system_key)."""
    from .inputs import menu_path, screen_names
    cm = profile.get("codemap", {}) or {}
    fe = (cm.get("frontend") or {}).get(fn.get("system_key")) if fn.get("system_key") else None
    path, names = menu_path(fn), screen_names(fn)
    seed_key = {"menu": path, "names": names, "route": route, "fe": fe}
    head = _git_head(profile.code_root)
    key = hashlib.sha1(json.dumps([head, seed_key], ensure_ascii=False).encode()).hexdigest()[:16]
    cache = os.path.join(ws.dir, "trace.json")
    if not force and os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            old = json.load(f)
        if old.get("key") == key:
            old["cached"] = True
            return old

    code = _Code(profile)
    index = i18n_index(code, cm.get("i18n", "**/i18n/vi/**/*.json"), fe)
    out = {"key": key, "code_root": profile.code_root, "commit": head, "seeds": seed_key, "method": None,
           "menu": [], "routes": [], "route_def": None, "components": [], "services": [], "endpoints": [],
           "fingerprints": {"identifiers": [], "phrases": []}, "top": [], "sql_objects": [], "views": [], "templates": [],
           "not_found": []}

    # 1-3: screen component
    routes, comps = [], []
    if route:
        out["method"] = "route given"
        routes = [route]
    else:
        out["menu"] = resolve_menu(code, index, path, fe)
        routes = sorted({m["link"] for m in out["menu"]})
        if routes:
            out["method"] = "menu path"
        elif path:
            out["not_found"].append("menu path '%s' (no menu entry whose title matches '%s')" % (" >> ".join(path), path[-1]))
    for r in routes:
        rd = resolve_route(code, r, fe)
        if rd:
            out["route_def"] = {"file": rd[0], "line": rd[1], "route": r}
            comps.append(rd[2])
        else:
            out["not_found"].append("route definition of %s" % r)
    if not comps:
        comps = components_for_titles(code, index, names + path[-1:], fe)[:2]
        if comps:
            out["method"] = out["method"] or "screen title"
    out["routes"] = routes
    out["components"] = comps

    # 4: services and URLs
    fe_files, endpoints = [], []
    for comp in comps:
        html = comp[:-3] + ".html"
        fe_files += [comp] + ([html] if code.exists(html) else [])
        for cls, (f, meths) in services_of(code, comp).items():
            eps = endpoints_of(code, f, meths)
            out["services"].append({"class": cls, "file": f, "methods": meths})
            endpoints += [e for e in eps if e not in endpoints]
    out["endpoints"] = endpoints

    # 5: backend by fingerprints from the screen (fallback: the names, as before)
    stop = cm.get("stop_tokens", [])
    weights, skip_ext = {}, ()
    rc_rx = re.compile(r"(?<![A-Za-z0-9])(%s)(?![0-9])" % cm.get("report_code", r"R\d{3}"), re.I)
    if comps:
        consts = seeds_from_component(code, comps[0], [f for f in fe_files if f != comps[0]], stop)
        urls = url_seeds(endpoints)
        # the report code (R017...) of the component, its services' files and URLs: the strongest fingerprint
        where = "\n".join([code.text(f) for f in fe_files] + [s["file"] for s in out["services"]] + endpoints)
        rcodes = sorted({m.upper() for m in rc_rx.findall(where)})
        weights = {t: 1.0 for t in consts}
        weights.update({t: 0.5 for t in urls})
        weights.update({t: 10.0 for t in rcodes})
        ids = sorted(set(consts) | set(urls) | set(rcodes))
        out["report_codes"] = rcodes
        phrases = []
        skip_ext = (".ts", ".html", ".json")                 # the screen side is known: rank the backend only
        out["method"] = out["method"] or "component"
    else:
        ids, phrases = fingerprints("\n".join(names + path), names, stop)
        out["method"] = "name only (weak - check the files, or pass --route)"
        out["not_found"].append("screen component")
    out["fingerprints"] = {"identifiers": ids, "phrases": phrases}
    menu_files = {m["file"] for m in out["menu"]} | ({out["route_def"]["file"]} if out["route_def"] else set())
    scored, df = score_files(code, ids, phrases, skip=set(fe_files) | menu_files, weights=weights, skip_ext=skip_ext,
                             registry_rx=rc_rx)
    out["not_found"] += [t for t in ids + phrases if t not in df]

    # 6: ranked list = the screen files, then the scored ones; SQL objects, views, templates
    files = [{"file": f, "score": None, "role": role(f), "matches": {}} for f in fe_files]
    for score, rel, found in scored[:top]:
        files.append({"file": rel, "score": score, "role": role(rel),
                      "matches": {t: found[t] for t in sorted(found, key=lambda t: df[t])[:12]}})
    objs = set()
    for x in files:
        x["endpoints"], x["sql_objects"] = file_info(code, x["file"])
        if x["score"] is not None:
            objs |= set(x["sql_objects"])
    views = find_views(code, objs)
    for name, (rel, line) in sorted(views.items()):
        out["views"].append({"name": name, "file": rel, "line": line})
        if rel not in [x["file"] for x in files]:
            eps, sql = file_info(code, rel)
            files.append({"file": rel, "score": None, "role": "view", "matches": {name: line}, "endpoints": eps, "sql_objects": sql})
        objs |= set(file_info(code, rel)[1])
    out["top"] = files
    out["sql_objects"] = sorted(objs)
    out["templates"] = find_templates(code, [x for x in files[:len(fe_files) + 6] if x["file"].endswith(".java")])
    out["files_scanned"] = len(code.files)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    ws.mark("locate", method=out["method"], top=[x["file"] for x in files[:5]])
    return out


def trace_md(t, n=14):
    L = ["# Code trace (commit %s%s) - found by: %s" % (t["commit"][:9], ", cached" if t.get("cached") else "", t.get("method"))]
    for m in t.get("menu") or []:
        L.append("- menu: %s:%d  %s > %s -> %s%s" % (m["file"], m["line"], " > ".join(m["parents"]), m["title"], m["link"],
                                                     ("  (not menu items, look inside the screen: %s)" % " > ".join(m["unmatched_tail"]))
                                                     if m.get("unmatched_tail") else ""))
    if t.get("report_codes"):
        L.append("- report code(s): %s" % ", ".join(t["report_codes"]))
    if t.get("route_def"):
        r = t["route_def"]
        L.append("- route: %s  (%s:%d)" % (r["route"], r["file"], r["line"]))
    for c in t.get("components") or []:
        L.append("- screen component: %s" % c)
    for s in t.get("services") or []:
        L.append("- service %s (%s): %s" % (s["class"], s["file"], ", ".join(s["methods"]) or "-"))
    for e in t.get("endpoints") or []:
        L.append("- calls: %s" % e)
    fp = t.get("fingerprints") or {}
    L += ["", "Fingerprints from the screen: %s" % (", ".join((fp.get("identifiers") or []) + (fp.get("phrases") or []))[:400] or "-"),
          "Not found: %s" % ("; ".join(t.get("not_found") or [])[:400] or "-"), ""]
    for x in (t.get("top") or [])[:n]:
        L.append("- **%s** (%s%s)" % (x["file"], x["role"], ", score %s" % x["score"] if x["score"] is not None else ""))
        if x.get("matches"):
            L.append("  matches: " + ", ".join("%s@%d" % kv for kv in x["matches"].items()))
        if x.get("endpoints"):
            L.append("  endpoints: " + ", ".join(x["endpoints"]))
        if x.get("sql_objects"):
            L.append("  sql objects: " + ", ".join(x["sql_objects"]))
    if t.get("views"):
        L.append("")
        L += ["- view %s: %s:%d" % (v["name"], v["file"], v["line"]) for v in t["views"]]
    if t.get("templates"):
        L.append("- Excel templates: " + ", ".join(t["templates"]))
    return "\n".join(L)
