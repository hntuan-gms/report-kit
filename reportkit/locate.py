"""Find the code behind a report from the SRS text, without the model grepping around.

Fingerprints are taken from the SRS (and the function name):
  - identifiers: TABLE / COLUMN / lookup codes (COMPANY_DATA, NEWS_TYPE_CD, BAT_THUONG, R018 ...)
  - quoted literals: 'DINH_KY', "SUBMITTED_LATE"
  - phrases: upper-case titles and the function name ("XU HƯỚNG VI PHẠM CÔNG BỐ THÔNG TIN")
Every file under the profile's `codemap.include` globs is scored by the distinct fingerprints it
contains, weighted by rarity (a token found in 3 files counts far more than one found in 300).
For the top files the endpoints (Spring @*Mapping, FE URL strings) and SQL objects are listed.

The result is a short ranked list with file:line - a starting point Claude verifies by reading
those files, not a conclusion. Cached per git commit + fingerprint set in <workspace>/trace.json.

profile:
  codemap:
    include: ["**/src/**/*.java", "**/src/**/*.ts", "**/src/**/*.html", "**/src/**/*.sql", "**/src/**/*.json"]
    exclude: ["**/node_modules/**", "**/target/**", "**/dist/**", "**/test/**"]
    stop_tokens: [ID, NAME, CODE]           # too common to mean anything
"""
import fnmatch
import hashlib
import json
import math
import os
import re
import subprocess

IDENT = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b|\bR\d{3}[A-Z0-9_]*\b")
QUOTED = re.compile(r"['\"‘’“”]([A-Za-z][A-Za-z0-9_]{3,})['\"‘’“”]")
UPPER_PHRASE = re.compile(r"(?:[A-ZÀ-Ỹ&][A-ZÀ-Ỹ0-9&]*[ \t]+){2,}[A-ZÀ-Ỹ0-9&]+")
CELL_REF = re.compile(r"(?:^|(?<=\s))[A-Z]{1,3}\d{1,6}=")
ENDPOINT_BE = re.compile(r"@(Get|Post|Put|Delete|Patch|Request)Mapping\(\s*(?:value\s*=\s*|path\s*=\s*)?\"([^\"]*)\"")
URL_FE = re.compile(r"['\"`](/?[a-z][\w-]*(?:/[\w${}.-]+){1,})['\"`]")
SQL_OBJ = re.compile(r"\b(?:FROM|JOIN)\s+([A-Z][A-Z0-9_]{3,})\b", re.I)
DEFAULT_STOP = {"ID", "NAME", "CODE", "TYPE", "DATE", "STATUS", "DELETE_FLG", "CREATED_BY", "CREATED_DATE", "UPDATED_BY",
                "UPDATED_DATE", "LANGUAGE_CD", "UTF_8", "YYYY_MM_DD"}


def fingerprints(text, extra_phrases=(), stop=()):
    stop = DEFAULT_STOP | {s.upper() for s in stop}
    text = CELL_REF.sub("\n", text).replace(" | ", "\n").replace(" / ", "\n")   # dumped xlsx: 'B40=x | C40=y'
    ids = {t for t in IDENT.findall(text) if t not in stop and len(t) >= 4}
    ids |= {t for t in QUOTED.findall(text) if t.upper() == t and t not in stop}
    phrases = {" ".join(p.split()) for p in UPPER_PHRASE.findall(text) if len(p) >= 12}
    phrases |= {" ".join(p.split()) for p in extra_phrases if p and len(p) >= 8}
    return sorted(ids), sorted(phrases)


def _git_head(root):
    try:
        return subprocess.check_output(["git", "-C", root, "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "nogit"


def _files(profile):
    cm = profile.get("codemap", {}) or {}
    inc = cm.get("include") or ["**/*.java", "**/*.ts", "**/*.html", "**/*.sql"]
    exc = cm.get("exclude") or ["**/node_modules/**", "**/target/**", "**/dist/**", "**/.git/**"]
    root = profile.code_root
    skip_dirs = {"node_modules", "target", "dist", ".git", ".angular", "build", ".idea"}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in skip_dirs]
        for f in files:
            rel = os.path.relpath(os.path.join(d, f), root).replace("\\", "/")
            if any(fnmatch.fnmatch(rel, p) for p in inc) and not any(fnmatch.fnmatch(rel, p) for p in exc):
                yield rel


def locate(profile, ws, srs_text, name=None, top=15, force=False):
    cm = profile.get("codemap", {}) or {}
    ids, phrases = fingerprints(srs_text + "\n" + (name or ""), [name] if name else [], cm.get("stop_tokens", []))
    key = hashlib.sha1(json.dumps([_git_head(profile.code_root), ids, phrases]).encode()).hexdigest()[:16]
    cache = os.path.join(ws.dir, "trace.json")
    if not force and os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            old = json.load(f)
        if old.get("key") == key:
            old["cached"] = True
            return old
    df, hits = {}, {}
    phr_norm = {p: p.lower() for p in phrases}
    for rel in _files(profile):
        try:
            with open(os.path.join(profile.code_root, rel), encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        low = text.lower()
        found = {}
        for t in ids:
            if t in text:
                found[t] = text.count("\n", 0, text.index(t)) + 1
        for p, pl in phr_norm.items():
            i = low.find(pl)
            if i >= 0:
                found[p] = text.count("\n", 0, i) + 1
        if found:
            hits[rel] = found
            for t in found:
                df[t] = df.get(t, 0) + 1
    n = max(1, len(hits))
    scored = []
    for rel, found in hits.items():
        score = sum(math.log(1 + n / df[t]) * (2.0 if t in phr_norm else 1.0) for t in found)
        scored.append((round(score, 2), rel, found))
    scored.sort(reverse=True)
    files = []
    for score, rel, found in scored[:top]:
        with open(os.path.join(profile.code_root, rel), encoding="utf-8", errors="ignore") as f:
            text = f.read()
        eps = ["%s %s" % (m[0].upper(), m[1]) for m in ENDPOINT_BE.findall(text)][:12]
        if rel.endswith(".ts"):
            eps += sorted(set(u for u in URL_FE.findall(text) if not u.startswith(("assets/", "./", "../"))))[:12]
        sql = sorted(set(x.upper() for x in SQL_OBJ.findall(text)))[:15] if re.search(r"\b(SELECT|FROM)\b", text) else []
        files.append({"file": rel, "score": score,
                      "matches": {t: found[t] for t in sorted(found, key=lambda t: df[t])[:12]},
                      "endpoints": eps, "sql_objects": sql})
    unmatched = [t for t in ids + phrases if t not in df]
    out = {"key": key, "code_root": profile.code_root, "commit": _git_head(profile.code_root), "fingerprints": {"identifiers": ids, "phrases": phrases},
           "files_scanned_with_hits": len(hits), "top": files, "not_found_in_code": unmatched}
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    ws.mark("locate", top=[x["file"] for x in files[:5]])
    return out


def trace_md(t, n=12):
    L = ["# Code trace (commit %s%s)" % (t["commit"][:9], ", cached" if t.get("cached") else ""),
         "Fingerprints: %d identifiers, %d phrases; not found in code: %s" % (
             len(t["fingerprints"]["identifiers"]), len(t["fingerprints"]["phrases"]), ", ".join(t["not_found_in_code"][:25]) or "-"), ""]
    for x in t["top"][:n]:
        L.append("- **%s** (score %s)" % (x["file"], x["score"]))
        L.append("  matches: " + ", ".join("%s@%d" % kv for kv in x["matches"].items()))
        if x["endpoints"]:
            L.append("  endpoints: " + ", ".join(x["endpoints"]))
        if x["sql_objects"]:
            L.append("  sql objects: " + ", ".join(x["sql_objects"]))
    return "\n".join(L)
