"""Find and dump the test inputs (function list row, SRS, standard, previous workbook) into text.

Everything is driven by the profile's `inputs:` block, e.g.

inputs:
  function_list:
    glob: "*Danh sách chức năng*.xlsx"      # under tools_dir
    header_contains: "Link UC"              # a cell text that identifies the header row
    columns: {jira: "Link UC", ticket: "Link Jira", name: "UC Name", system: "Phân hệ", srs: "Link SRS", pic: "PIC"}
  srs_globs: ["File SRS/**/*{code}*", "File SRS/**/{srs}"]   # {code} = 1E_117, {srs} = column 'srs'
  standard: {glob: "**/SRS_Quy_chuan_chung*.docx", summary: rules/standard.md}
  previous_workbooks: "*{code_nodash}*.xlsx"
"""
import glob
import os
import re
import zipfile


# ------------------------------------------------------------------ dumpers
def dump_xlsx(path, out=None, max_rows=3000, with_comments=True, images_dir=None):
    import openpyxl
    lines = []
    wb = openpyxl.load_workbook(path, data_only=True)
    for ws in wb.worksheets:
        lines.append("===== SHEET: %s dims=%s" % (ws.title, ws.dimensions))
        n = 0
        for row in ws.iter_rows():
            vals = [(c.coordinate, c.value) for c in row if c.value is not None and str(c.value).strip() != ""]
            if vals:
                lines.append(" | ".join("%s=%s" % (k, str(v).replace("\n", " / ")) for k, v in vals))
                n += 1
                if n >= max_rows:
                    lines.append("...TRUNCATED"); break
    if with_comments:
        wb2 = openpyxl.load_workbook(path)
        for ws in wb2.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if c.comment:
                        lines.append("##### COMMENT %s!%s on [%s]: %s" % (ws.title, c.coordinate, str(c.value)[:200],
                                                                        c.comment.text.replace("\n", " / ")))
    imgs = extract_images(path, images_dir or (os.path.splitext(out)[0] + "_images" if out else None))
    return _emit(lines, out), imgs


def dump_docx(path, out=None, images_dir=None):
    import docx
    from docx.oxml.ns import qn
    lines = []
    for child in docx.Document(path).element.body.iterchildren():
        if child.tag == qn("w:p"):
            t = "".join(x.text or "" for x in child.iter(qn("w:t")))
            if t.strip():
                lines.append(t)
        elif child.tag == qn("w:tbl"):
            for tr in child.iter(qn("w:tr")):
                lines.append(" || ".join(" ".join((x.text or "") for x in tc.iter(qn("w:t"))).strip() for tc in tr.iter(qn("w:tc"))))
            lines.append("--- end table")
    imgs = extract_images(path, images_dir or (os.path.splitext(out)[0] + "_images" if out else None))
    return _emit(lines, out), imgs


def dump_any(path, out=None, images_dir=None):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        return dump_xlsx(path, out, images_dir=images_dir)
    if ext == ".docx":
        return dump_docx(path, out, images_dir=images_dir)
    with open(path, encoding="utf-8", errors="replace") as f:
        return _emit(f.read().splitlines(), out), []


def extract_images(path, out_dir):
    if not out_dir:
        return []
    saved = []
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if re.match(r"^(xl|word)/media/", n):
                os.makedirs(out_dir, exist_ok=True)
                p = os.path.join(out_dir, os.path.basename(n))
                with open(p, "wb") as f:
                    f.write(z.read(n))
                saved.append(p)
    return saved


def _emit(lines, out):
    text = "\n".join(lines)
    if out:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    return text


# ------------------------------------------------------------------ lookups
def _tools(profile, pattern):
    if not profile.tools_dir:
        return []
    return [p for p in glob.glob(os.path.join(profile.tools_dir, pattern), recursive=True) if not os.path.basename(p).startswith("~$")]


def _function_rows(profile):
    """(source file, [raw row dict]) of the function list."""
    import openpyxl
    fl = profile.get("inputs.function_list", {}) or {}
    hits = _tools(profile, fl.get("glob", "*.xlsx"))
    if not hits:
        raise SystemExit("Function list '%s' not found in %s" % (fl.get("glob"), profile.tools_dir))
    ws = openpyxl.load_workbook(hits[0], data_only=True).active
    marker = fl.get("header_contains", "")
    hdr_row = next((r for r in range(1, 30) if any(marker in str(ws.cell(r, c).value or "") for c in range(1, 30))), None)
    if not hdr_row:
        raise SystemExit("Header row containing '%s' not found in %s" % (marker, hits[0]))
    hdr = {c: str(ws.cell(hdr_row, c).value).strip() for c in range(1, ws.max_column + 1) if ws.cell(hdr_row, c).value}
    return hits[0], [{hdr[c]: ws.cell(r, c).value for c in hdr} for r in range(hdr_row + 1, ws.max_row + 1)]


def _logical(profile, raw):
    row = {}
    for logical, head in ((profile.get("inputs.function_list", {}) or {}).get("columns") or {}).items():
        col = next((h for h in raw if head.lower() in h.lower()), None)
        row[logical] = raw.get(col) if col else None
    return row


def _has_code(raw, code):
    variants = {code, code.replace("_", "")}
    return any(any(v and re.search(r"(?<![\w])%s(?![\d])" % re.escape(x), str(v)) for x in variants) for v in raw.values())


def find_function(profile, code):
    """Row of the function list for `code` as {logical column: value}, plus 'system_key' resolved to a profile key."""
    src, rows = _function_rows(profile)
    for raw in rows:
        if _has_code(raw, code):
            row = {"_raw": {k: v for k, v in raw.items() if v is not None}, "code": code, "source": src}
            row.update(_logical(profile, raw))
            row["system_key"] = profile.system_for_label(row.get("system"))
            return row
    raise SystemExit("Code %s not found in %s" % (code, src))


_CODE_IN_NAME = re.compile(r"(?<![\w])(\d+[A-Za-z]+_\d+)(?![\d])")


def find_siblings(profile, code, fn, trace=None, workspaces_root=None):
    """Other functions that share this one's SRS file or its main code files.

    Two function-list rows with the same SRS usually mean one screen seen by two kinds of user (e.g. 1E_117 internal /
    1E_118 public company): a workbook that copies the sibling's cases then tests nothing new.
    Returns [{code, name, why: [...], workspace, delivered: [...]}].
    """
    out = {}
    srs = str(fn.get("srs") or "").strip().lower()
    if srs and srs != str(fn.get("name") or "").strip().lower():
        _, rows = _function_rows(profile)
        for raw in rows:
            lg = _logical(profile, raw)
            if str(lg.get("srs") or "").strip().lower() != srs or _has_code(raw, code):
                continue
            m = _CODE_IN_NAME.search(str(lg.get("name") or ""))
            if m:
                out.setdefault(m.group(1), {"code": m.group(1), "name": lg.get("name"), "why": []})["why"].append("cùng SRS '%s'" % fn.get("srs"))
    top = [x["file"] for x in (trace or {}).get("top", [])[:3]]
    if top and workspaces_root and os.path.isdir(workspaces_root):
        for d in os.listdir(workspaces_root):
            tp = os.path.join(workspaces_root, d, "trace.json")
            if d == code or not os.path.exists(tp):
                continue
            import json
            with open(tp, encoding="utf-8") as f:
                other = [x["file"] for x in json.load(f).get("top", [])[:3]]
            same = len(set(top) & set(other))
            if same >= 2:
                out.setdefault(d, {"code": d, "name": None, "why": []})["why"].append("trùng %d/3 file code đứng đầu trace" % same)
    for s in out.values():
        ws = os.path.join(workspaces_root or "", s["code"])
        s["workspace"] = ws if workspaces_root and os.path.isdir(ws) else None
        s["delivered"] = [os.path.basename(p) for p in find_previous(profile, s["code"])]
    return sorted(out.values(), key=lambda s: s["code"])


def find_srs(profile, code, srs_name=None):
    out = []
    for pat in profile.get("inputs.srs_globs", ["**/*{code}*"]) or []:
        if "{srs}" in pat and not srs_name:
            continue
        pat = pat.replace("{code}", code).replace("{srs}", glob.escape(str(srs_name or "")))
        for p in _tools(profile, pat):
            if p not in out and os.path.splitext(p)[1].lower() in (".xlsx", ".docx", ".md", ".txt"):
                out.append(p)
    return out


def find_standard(profile):
    """(path of the standard document or None, path of the profile's summary or None)."""
    st = profile.get("inputs.standard", {}) or {}
    docs = _tools(profile, st["glob"]) if st.get("glob") else []
    summ = profile.path(st["summary"]) if st.get("summary") else None
    return (docs[0] if docs else None), (summ if summ and os.path.exists(summ) else None)


def find_previous(profile, code):
    pat = profile.get("inputs.previous_workbooks")
    if not pat:
        return []
    pat = pat.replace("{code_nodash}", code.replace("_", "")).replace("{code}", code)
    return sorted(_tools(profile, pat), key=os.path.getmtime)
