"""Test case workbook from the project's template (KBKT layout by default) + companion sheets.

Same API as the original build_workbook.py - Claude writes a short builder script in the workspace:

    from reportkit import profile as P, workbook as W
    prof = P.load(); ws = prof.workspace("1E_117")
    wb = W.Workbook(prof, ws, name="Trang tổng hợp CBTT nội bộ", screen="[# 1E_117] ... - IDS > Trang chủ",
                    ticket="AI-23", ascii_name="TrangTongHopCongBoThongTinNoiBo", version=1)
    wb.chapter("Chức năng 1: ..."); wb.pre("1. Đăng nhập ...")
    wb.cat("Giao diện"); wb.sub("Giao diện chung")
    wb.tc("Kiểm tra ...", "1. ...", "Kết quả mong muốn", basis="Căn cứ: ...", status="P",
          actual="Điều thực tế đã xảy ra, có giá trị cụ thể", bug="BUG-01")
    wb.finish(run_date="28/09/2026", run_note="Thời gian: ...\\nNgười thực hiện: ...\\nBản build: ...")
    wb.sheet_svc(rows, title, note); wb.sheet_bugs(rows, title); wb.sheet_details(rows, title, note)
    wb.sheet_ba(rows, title); wb.sheet_sources(rows, title, headers, widths)
    wb.sheet_coverage([(source, item, requirement, ["Kiểm tra ..."], note), ...], title)   # 'Ma trận bao phủ'
    wb.save()

Profile block (defaults shown are the KBKT template):
  workbook:
    template: "{tools_dir}/Template Testcase/KBKT_Template.xlsx"
    out_dir: "{tools_dir}"
    file_name: "{ticket}_{code_nodash}_{ascii_name}_v{version}.xlsx"
    first_row: 12
    style_rows: {chapter: 12, pre: 13, cat: 14, sub: 15, grp: 24, case: 16}
    header_cells: {screen: D2, code: D3}
    run_header_row: 11            # "Lần N" header row; E=run 1, F=run 2, G=run 3
    font: "Times New Roman"
"""
import copy
import os

import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

GREEN = PatternFill("solid", fgColor="FFC6EFCE"); RED = PatternFill("solid", fgColor="FFFFC7CE")
YELLOW = PatternFill("solid", fgColor="FFFFEB9C"); GREY = PatternFill("solid", fgColor="FFE7E6E6")
BLUE = PatternFill("solid", fgColor="FFDDEBF7"); HEADER = PatternFill("solid", fgColor="FF00CCFF")
STATUS_FILL = {"P": GREEN, "F": RED, "PE": YELLOW}
_thin = Side(style="thin"); BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)

SVC_HEADERS = ["STT", "Hạng mục", "SRS mô tả", "Code thực tế (vị trí file:line)", "Hiện trạng dữ liệu / kết quả chạy DEV", "Loại",
               "Mức độ", "Đề xuất cập nhật SRS", "Đề xuất cho DEV", "Quy chuẩn chung (đã chốt với BA)", "Trạng thái sau Quy chuẩn",
               "BA xác nhận", "DEV xác nhận", "Kết luận"]
BUG_HEADERS = ["Mã lỗi", "Mức độ", "Trạng thái", "Mô tả", "Căn cứ", "Nguyên nhân (code)", "Bằng chứng / tái hiện"]
DETAIL_HEADERS = ["Khoá (công ty / kỳ / dòng)", "Cột", "Chỉ tiêu / trường", "Giá trị trên báo cáo", "Giá trị mong đợi", "Nguồn gây sai", "Mã lỗi"]
BA_HEADERS = ["STT", "Chủ đề", "Câu hỏi", "Mức độ", "Trạng thái", "Trả lời / căn cứ"]
COV_SHEET = "Ma trận bao phủ"
COV_HEADERS = ["STT", "Nguồn", "Mục", "Yêu cầu / quy tắc", "Case", "Kết quả các case (Lần 1)", "Ghi chú"]
COV_REASONS = ("Không áp dụng", "Chưa phủ")          # a row with no case must start its note with one of these
COV_NOTE = ("Mỗi dòng của SRS, Quy chuẩn chung, code, bẫy dữ liệu (rt probe) và checklist trỏ tới case kiểm tra nó. "
            "Case '-' là mục không áp dụng hoặc chưa phủ (lý do ở Ghi chú). Mã case theo cột A của sheet test case.")


def set_text(cell, value):
    """Text starting with '=' stays text (openpyxl would store a formula and Excel would 'repair' the file)."""
    cell.value = value
    if isinstance(value, str) and value.startswith("="):
        cell.data_type = "s"
    return cell


class Workbook(object):
    def __init__(self, prof, ws, name, screen, ticket="", ascii_name="", version=1, out=None, sheet_title=None):
        cfg = prof.get("workbook", {}) or {}
        self.cfg = cfg
        tpl = prof.expand(cfg.get("template", "{tools_dir}/Template Testcase/KBKT_Template.xlsx"))
        if not os.path.exists(tpl):
            raise SystemExit("Workbook template not found: %s (profile workbook.template)" % tpl)
        fname = cfg.get("file_name", "{ticket}_{code_nodash}_{ascii_name}_v{version}.xlsx").format(
            ticket=ticket, code=ws.code, code_nodash=ws.code.replace("_", ""), ascii_name=ascii_name or ws.code, version=version)
        self.out = out or os.path.join(prof.expand(cfg.get("out_dir", "{tools_dir}")), fname)
        if os.path.exists(self.out):
            raise SystemExit("%s already exists. Never overwrite a delivered version - use version=%d." % (self.out, version + 1))
        f = cfg.get("font", "Times New Roman")
        self.FONT = Font(name=f, size=12); self.FONT_B = Font(name=f, size=12, bold=True)
        self.wb = openpyxl.load_workbook(tpl)
        sh = self.ws = self.wb.worksheets[0]
        sh.title = (sheet_title or ("%s %s" % (ws.code, name)))[:31]
        rows = cfg.get("style_rows", {"chapter": 12, "pre": 13, "cat": 14, "sub": 15, "grp": 24, "case": 16})
        cap = lambda r: [copy.copy(sh.cell(r, c)._style) for c in range(1, 11)]
        self.st = {k: cap(r) for k, r in rows.items()}
        self.first = int(cfg.get("first_row", 12))
        self.cases = []                       # (row, purpose) of every tc(), for sheet_coverage()
        self.pre_h = sh.row_dimensions[rows.get("pre", 13)].height
        for m in [str(m) for m in sh.merged_cells.ranges if m.min_row >= self.first]:
            sh.unmerge_cells(m)
        sh.delete_rows(self.first, sh.max_row)
        sh._images = []                       # the KBKT template carries thousands of stray images
        sh.data_validations.dataValidation = []
        hc = cfg.get("header_cells", {"screen": "D2", "code": "D3"})
        sh[hc["screen"]] = screen; sh[hc["code"]] = ws.code
        self.code_cell = hc["code"]
        self.row = self.first

    def _put(self, kind, b=None, c=None, d=None, j=None, merge=False):
        sh, r = self.ws, self.row
        for col in range(1, 11):
            sh.cell(r, col)._style = copy.copy(self.st[kind][col - 1])
        col_d, row_d = self.code_cell[0], int(self.code_cell[1:])
        hdr = self.first - 1
        sh.cell(r, 1).value = '=IF(AND(D%d="",D%d=""),"",$%s$%d&"_"&ROW()-%d-COUNTBLANK($D$%d:D%d))' % (r, r, col_d, row_d, hdr - 1, hdr, r)
        for col, v in ((2, b), (3, c), (4, d), (10, j)):
            if v is not None:
                set_text(sh.cell(r, col), v)
        if merge:
            sh.merge_cells(start_row=r, start_column=2, end_row=r, end_column=10)
        if kind == "case":
            for col in (2, 3, 4, 8, 9, 10):
                sh.cell(r, col).alignment = Alignment(wrap_text=True, vertical="top")
        self.row += 1
        return r

    def chapter(self, t): self._put("chapter", t, merge=True)
    def cat(self, t): self._put("cat", t, merge=True)
    def sub(self, t): self._put("sub", t, merge=True)
    def grp(self, t): self._put("grp", t, merge=True)

    def pre(self, t):
        r = self._put("pre", t, merge=True); self.ws.row_dimensions[r].height = self.pre_h

    def tc(self, purpose, steps, expected, basis=None, status=None, actual=None, bug=None, run=1):
        if status is None and not actual:
            actual = "Chưa thực hiện"
        if status in ("P", "F", "PE") and actual in (None, "", "P", "F", "PE"):
            raise ValueError("tc(%r): 'actual' must describe what happened, not just the status" % purpose)
        r = self._put("case", purpose, steps, expected, basis)
        set_text(self.ws.cell(r, 8), actual)
        if status:
            c = self.ws.cell(r, 4 + run); c.value = status; c.fill = STATUS_FILL[status]
        if bug:
            self.ws.cell(r, 9).value = bug
        self.cases.append((r, purpose))
        return r

    def case_ids(self):
        """{row: (purpose, case id as column A shows it, status of run 1)} for every tc() so far."""
        return {r: (p, _case_id(self.ws, self.first - 1, self.ws[self.code_cell].value, r), self.ws.cell(r, 5).value)
                for r, p in self.cases}

    def sheet_coverage(self, rows, title, note=None):
        """'Ma trận bao phủ': one row per requirement, pointing at the cases that test it.

        rows: (source, item, requirement, case_keys, note)
          source  'SRS sheet 2' / 'Quy chuẩn chung' / 'Code' / 'Bẫy dữ liệu (rt probe)' / 'Checklist test-areas' / ...
          item    the SRS cell, standard section, file:line, trap id (as probe.md prints it) or checklist item
          case_keys  beginnings of the cases' 'Mục đích' (each must match at least one case, or ValueError)
          note    required when case_keys is empty, and must then start with 'Không áp dụng' or 'Chưa phủ' + the reason
        Case ids and the P/F/PE tally are filled in from the test case sheet.
        """
        import collections
        ids, data = self.case_ids(), []
        for i, (src, item, req, keys, nt) in enumerate(rows, 1):
            keys, nt = list(keys or []), nt or ""
            if not keys and not nt.startswith(COV_REASONS):
                raise ValueError("coverage row %d (%s %s): no case - the note must start with %s" % (i, src, item, " / ".join(COV_REASONS)))
            miss = [k for k in keys if not any(p.startswith(k) for p, _, _ in ids.values())]
            if miss:
                raise ValueError("coverage row %d (%s %s): no case whose 'Mục đích' starts with %r" % (i, src, item, miss))
            hit = [(cid, st) for _, (p, cid, st) in sorted(ids.items()) if any(p.startswith(k) for k in keys)]
            tally = collections.Counter(st or "chưa chạy" for _, st in hit)
            data.append((i, src, item, req, ", ".join(c for c, _ in hit) or "-",
                         ", ".join("%s: %d" % kv for kv in tally.items()) or "-", nt))
        return self.table(COV_SHEET, title, COV_HEADERS, data, [6, 22, 26, 56, 30, 26, 52], note or COV_NOTE)

    def finish(self, run_date, run_note, author="", run=1):
        sh, last, f = self.ws, self.row - 1, self.first
        sh["D4"] = '=COUNTIF($E$%d:$E$%d,"P")' % (f, last)
        sh["D5"] = '=COUNTIF($E$%d:$E$%d,"F")' % (f, last)
        sh["D6"] = '=COUNTIF($E$%d:$E$%d,"PE")' % (f, last)
        sh["D7"] = "=D8-D4-D5-D6"
        sh["D8"] = "=COUNTA($D$%d:$D$%d)" % (f, last)
        hr = int(self.cfg.get("run_header_row", f - 1))
        cell = sh.cell(hr, 4 + run); cell.value = "Lần %d\n%s" % (run, run_date)
        cell.comment = Comment(run_note, author or "reportkit")
        sh.cell(hr - 1, 8).comment = Comment(run_note, author or "reportkit")
        sh.column_dimensions["H"].width = 55; sh.column_dimensions["J"].width = 40
        dv = DataValidation(type="list", formula1='"P,F,PE"', allow_blank=True); dv.add("E%d:G%d" % (f, last))
        sh.add_data_validation(dv)
        return last

    def table(self, name, title, headers, rows, widths, note=None):
        s = self.wb.create_sheet(name[:31])
        s["A1"] = title; s["A1"].font = Font(name=self.FONT.name, size=13, bold=True)
        if note:
            s["A2"] = note; s["A2"].font = Font(name=self.FONT.name, size=11, italic=True)
        for i, h in enumerate(headers, 1):
            c = s.cell(4, i, h); c.font = self.FONT_B; c.fill = HEADER; c.border = BORDER
            c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
            s.column_dimensions[openpyxl.utils.get_column_letter(i)].width = widths[i - 1] if i <= len(widths) else 20
        for r, vals in enumerate(rows, 5):
            for i, v in enumerate(vals, 1):
                c = set_text(s.cell(r, i), v); c.font = self.FONT; c.border = BORDER
                c.alignment = Alignment(wrap_text=True, vertical="top")
        s.freeze_panes = "A5"
        return s

    def sheet_svc(self, rows, title, note):
        """rows: tuples in SVC_HEADERS order without STT and without the 3 review columns (10 values)."""
        data = [(i + 1,) + tuple(r) + ("", "", "") for i, r in enumerate(rows)]
        s = self.table("So sánh SRS - Code", title, SVC_HEADERS, data, [5, 24, 32, 46, 40, 16, 10, 30, 28, 40, 34, 14, 14, 16], note)
        for r in range(5, 5 + len(data)):
            t = s.cell(r, 6).value
            s.cell(r, 6).fill = {"Xung đột SRS-Code": RED, "SRS tự mâu thuẫn": RED, "SRS có - Code thiếu": RED,
                                 "Code có - SRS thiếu": YELLOW, "SRS mơ hồ": BLUE}.get(t, GREY)
            st = str(s.cell(r, 11).value or "")
            s.cell(r, 11).fill = RED if "DEV phải sửa" in st else (GREEN if st.startswith("Đã chốt") else YELLOW)
        dv = DataValidation(type="list", formula1='"Đồng ý,Không đồng ý,Cần trao đổi"', allow_blank=True)
        dv.add("L5:M%d" % (4 + len(data))); s.add_data_validation(dv)
        return s

    def sheet_bugs(self, rows, title):
        s = self.table("Danh sách lỗi", title, BUG_HEADERS, rows, [9, 12, 22, 46, 34, 46, 56])
        for r in range(5, 5 + len(rows)):
            st = str(s.cell(r, 3).value or "")
            s.cell(r, 3).fill = GREY if st.startswith(("Rút", "Đã đóng")) else (RED if st in ("Mở", "Mới") else YELLOW)
        return s

    def sheet_details(self, rows, title, note, headers=None, widths=None):
        return self.table("Chi tiết sai lệch dữ liệu", title, headers or DETAIL_HEADERS, rows, widths or [36, 16, 50, 20, 24, 52, 10], note)

    def sheet_ba(self, rows, title):
        data = [(i + 1,) + tuple(r) for i, r in enumerate(rows)]
        s = self.table("BA làm rõ", title, BA_HEADERS, data, [6, 26, 90, 12, 16, 50])
        for r in range(5, 5 + len(data)):
            s.cell(r, 5).fill = GREEN if s.cell(r, 5).value == "Đã chốt" else YELLOW
        return s

    def sheet_sources(self, rows, title, headers, widths):
        return self.table("Nguồn dữ liệu", title, headers, rows, widths)

    def save(self):
        self.wb.active = 0
        os.makedirs(os.path.dirname(self.out), exist_ok=True)
        self.wb.save(self.out)
        return self.out


def details_from_run(run_dir, causes=None, labels=None):
    """Rows for the 'Chi tiết sai lệch dữ liệu' sheet straight from the data comparison results.

    causes: {variant name: (cause text, bug id)} - the first variant that explains a cell gives its cause / bug.
    labels: {check id: text for the 'Chỉ tiêu / trường' column} (default: the entry's title).
    """
    import json
    causes, labels, rows = causes or {}, labels or {}, []
    for fn in sorted(os.listdir(run_dir)):
        if not fn.endswith(".json") or fn == "summary.json":
            continue
        with open(os.path.join(run_dir, fn), encoding="utf-8") as f:
            r = json.load(f)
        if r.get("kind") != "data":
            continue
        for p in r.get("parts", []):
            period = ", ".join("%s=%s" % kv for kv in (p.get("vars") or {}).items())
            for m in p.get("mismatches", []):
                expl = m.get("explained_by") or []
                cause, bug = next((causes[v] for v in expl if v in causes), (", ".join(expl) or "chưa quy được nguyên nhân", ""))
                key = "/".join(str(k) for k in m["key"] if k != "*")
                rows.append(("%s %s%s" % (r["id"], period + " / " if period else "", key or "-"), m["field"],
                             labels.get(r["id"], r.get("title")), str(m["actual"]), str(m["expected"]), cause, bug))
    return rows


def _case_id(sh, hdr, code, r):
    """Value of the column-A formula of row r: code_N, N = non-blank 'Kết quả mong muốn' cells from the header row to r."""
    return "%s_%d" % (code, sum(1 for rr in range(hdr, r + 1) if sh.cell(rr, 4).value not in (None, "")))


def coverage_gate(path, probe_json=None, first_row=12, code_cell="D3"):
    """Quality gate on the 'Ma trận bao phủ' sheet.

    Returns {missing_sheet, rows_without_reason, traps_not_mapped, cases_not_referenced}. The first three block the build:
      - rows_without_reason: STT of rows with no case and no 'Không áp dụng' / 'Chưa phủ' note
      - traps_not_mapped: 'TABLE.trap_id' flagged FOUND in probe.json that no row names (trap id in 'Mục'; when the
        same trap is FOUND on several tables, the row must also name the table, or name none of them)
    cases_not_referenced is informative: cases that no requirement points to.
    """
    import json
    wb = openpyxl.load_workbook(path)
    res = {"missing_sheet": COV_SHEET not in wb.sheetnames, "rows_without_reason": [], "traps_not_mapped": [], "cases_not_referenced": []}
    if res["missing_sheet"]:
        return res
    s = wb[COV_SHEET]
    rows = [[s.cell(r, c).value for c in range(1, 8)] for r in range(5, s.max_row + 1) if s.cell(r, 1).value is not None]
    res["rows_without_reason"] = [r[0] for r in rows if str(r[4] or "-").strip() in ("", "-") and not str(r[6] or "").startswith(COV_REASONS)]
    if probe_json and os.path.exists(probe_json):
        with open(probe_json, encoding="utf-8") as f:
            tables = json.load(f).get("tables", {})
        found = {}
        for tb, t in tables.items():
            for it in t.get("traps", []):
                if it.get("flagged"):
                    found.setdefault(it["id"], []).append(tb)
        for tid, tbs in found.items():
            for tb in tbs:
                ok = False
                for r in rows:
                    if tid not in str(r[2] or ""):
                        continue
                    text = " ".join(str(v or "") for v in r[1:])
                    if tb in text or not any(x in text for x in tbs):
                        ok = True; break
                if not ok:
                    res["traps_not_mapped"].append("%s.%s" % (tb, tid))
    sh = wb.worksheets[0]
    code, hdr = sh[code_cell].value, first_row - 1
    referenced = {x.strip() for r in rows for x in str(r[4] or "").split(",")}
    res["cases_not_referenced"] = [cid for cid in (_case_id(sh, hdr, code, r) for r in range(first_row, sh.max_row + 1)
                                                   if sh.cell(r, 4).value not in (None, "") and sh.cell(r, 2).value)
                                   if cid not in referenced]
    return res


def tally(path, first_row=12):
    """Counts per section + rows whose 'Kết quả hiện tại' is empty or only a status (quality gate)."""
    import collections
    sh = openpyxl.load_workbook(path).worksheets[0]
    sec, per, bad, f_no_bug = None, collections.defaultdict(collections.Counter), [], []
    for r in range(first_row, sh.max_row + 1):
        b = sh.cell(r, 2).value
        if sh.cell(r, 4).value is None and b in ("Giao diện", "Chức năng", "An toàn thông tin"):
            sec = b
        if sh.cell(r, 4).value:
            st = sh.cell(r, 5).value or "Chưa thực hiện"
            per[sec][st] += 1
            if not sh.cell(r, 8).value or sh.cell(r, 8).value in ("P", "F", "PE"):
                bad.append(r)
            if st == "F" and not sh.cell(r, 9).value:
                f_no_bug.append(r)
    return {k: dict(v) for k, v in per.items()}, bad, f_no_bug
