import datetime as dt
import os

import openpyxl
import pytest
import yaml

from reportkit import excel, locate, params, profile as P, safety
from reportkit.checks import assertions, data


# ---------------------------------------------------------------- params
def test_params_dates_and_arithmetic():
    v = params.base_vars(dt.date(2026, 1, 15))
    assert v["prev_month"] == 12 and v["prev_month_year"] == 2025
    assert params.render("{current_year-4} - {current_year}", v) == "2022 - 2026"
    assert params.render("{today:%Y-%m-%d}", v) == "2026-01-15"
    assert params.render("{current_year}", v) == 2026                 # lone numeric token -> int
    assert params.render("keep {unknown} and {fn(x)}", v) == "keep {unknown} and {fn(x)}"


def test_matrix_expands_cartesian():
    v = params.base_vars(dt.date(2026, 9, 28))
    combos = params.expand_matrix({"year": ["{current_year}", "{current_year-1}"], "lang": ["vi", "en"]}, v)
    assert len(combos) == 4 and {"year": 2025, "lang": "en"} in combos


def test_matrix_ranges_cover_every_value():
    v = params.base_vars(dt.date(2026, 9, 28))
    assert [c["year"] for c in params.expand_matrix({"year": "{current_year}..2022"}, v)] == [2026, 2025, 2024, 2023, 2022]
    assert [c["year"] for c in params.expand_matrix({"year": "2024..{current_year}"}, v)] == [2024, 2025, 2026]
    assert [c["y"] for c in params.expand_matrix({"y": ["2016..2017", "{current_year}"]}, v)] == [2016, 2017, 2026]
    assert params.expand_matrix({"rank": ["A", "B"]}, v) == [{"rank": "A"}, {"rank": "B"}]


# ---------------------------------------------------------------- safety
@pytest.mark.parametrize("sql", ["SELECT 1 FROM DUAL", "with x as (select 1 a from dual) select * from x",
                                 "SELECT 'DELETE me' TXT FROM DUAL", "SELECT DELETE_FLG, BEGIN_DATE FROM T"])
def test_sql_allowed(sql):
    safety.check_sql(sql)


@pytest.mark.parametrize("sql", ["DELETE FROM T", "UPDATE T SET A=1", "SELECT 1 FROM DUAL; DROP TABLE T",
                                 "BEGIN NULL; END;", "select * from t for update; commit",
                                 "/* SELECT */ INSERT INTO T VALUES (1)"])
def test_sql_refused(sql):
    with pytest.raises(safety.Refused):
        safety.check_sql(sql)


# ---------------------------------------------------------------- excel display
def test_shown_applies_formats():
    wb = openpyxl.Workbook(); ws = wb.active
    ws["A1"] = 2.0; ws["A1"].number_format = "#,##0"
    ws["A2"] = 1234.5; ws["A2"].number_format = "#,##0.00"
    ws["A3"] = dt.datetime(2026, 9, 28); ws["A3"].number_format = "dd/mm/yyyy"
    ws["A4"] = 0.1234; ws["A4"].number_format = "0.00%"
    assert [excel.shown(ws[c]) for c in ("A1", "A2", "A3", "A4")] == ["2", "1,234.50", "28/09/2026", "12.34%"]
    assert excel.std_number(25604) == "25,604" and excel.std_number(61.42) == "61.42"


# ---------------------------------------------------------------- preconditions
def test_preconditions():
    assert assertions.check("Hạng A: 57/2325", {"regex": "^Hạng A"}) == []
    assert assertions.check("Hạng B: 335/2325", {"regex": "^Hạng A"})
    assert assertions.check(4, {"min": 4}) == [] and assertions.check([], {"not_empty": True})
    assert assertions.check_all({"n": 3}, {"n": {"min": 4}, "missing": {"min": 1}}).keys() == {"n", "missing"}


# ---------------------------------------------------------------- data comparison helpers
def test_compare_numeric_and_text():
    assert data._same("2,433", 2433, {}) and data._same(61.42, "61.42", {})
    assert not data._same(2433, 2436, {}) and data._same(2433, 2436, {"tolerance": 5})
    assert data._same(" Hạng  A ", "Hạng A", {"numeric": False})
    k = data._keyed([{"thang": 1, "a": 5}, {"thang": 2, "a": 7}], ["thang"], {"DK": "a"})
    assert k == {("1",): {"DK": 5}, ("2",): {"DK": 7}}


# ---------------------------------------------------------------- locate
def test_fingerprints_from_free_text():
    txt = ("Lấy tin từ COMPANY_DATA với NEWS_TYPE_CD in ('DINH_KY','BAO_CAO'); trạng thái 'SUBMITTED_LATE'. "
           "Tên biểu đồ: XU HƯỚNG VI PHẠM CÔNG BỐ THÔNG TIN QUA CÁC NĂM")
    ids, phrases = locate.fingerprints(txt)
    assert {"COMPANY_DATA", "NEWS_TYPE_CD", "DINH_KY", "BAO_CAO", "SUBMITTED_LATE"} <= set(ids)
    assert any("XU HƯỚNG VI PHẠM" in p for p in phrases)


def test_labels_and_globs():
    assert locate.label_variants("CTĐC đăng ký với UBCKNN/ Danh sách (mới)")[:3] == [
        "ctđc đăng ký với ubcknn/ danh sách (mới)", "ctđc đăng ký với ubcknn", "danh sách (mới)"]
    assert locate._match("ids-frontend/src/app/app.routes.ts", "*-frontend/src/app/**/*.ts")          # '**/' = no folder too
    assert locate._match("ids-frontend/src/app/pages/x/a.component.ts", "*-frontend/src/app/**/*.ts")
    assert not locate._match("ids-frontend/src/assets/a.ts", "*-frontend/src/app/**/*.ts")


def test_menu_entries_keep_parents():
    text = """export const MENU = [
      { id: 'stats', title: 'menu.statistics', children: [
          { id: 'ctdc', title: 'menu.publicCompanyStats', children: [
              { id: 'gov', title: 'menu.governance', routerLink: '/statistics/ctdc/governance' },   // a comment with { brace
          ] },
      ] },
      { id: 'home', title: 'menu.dashboard', routerLink: '/dashboard' },
    ];"""
    e = {x["title"]: x for x in locate.menu_entries(text)}
    assert e["menu.governance"]["link"] == "/statistics/ctdc/governance"
    assert e["menu.governance"]["parents"] == ["menu.statistics", "menu.publicCompanyStats"]
    assert e["menu.dashboard"]["parents"] == [] and e["menu.statistics"]["link"] is None


def _fake_repo(root):
    files = {
        "web/src/assets/i18n/vi/menu.json": '{"menu": {"statistics": "Thống kê", "ctdc": "Thống kê CTĐC", "gov": "BC quản trị", "other": "BC quản trị"}}',
        "web/src/app/shared/menu.data.ts": """export const M = [
            { title: 'menu.statistics', children: [ { title: 'menu.ctdc', children: [
                { title: 'menu.gov', routerLink: '/statistics/ctdc/governance' } ] } ] },
            { title: 'menu.other', routerLink: '/elsewhere' } ];""",
        "web/src/app/pages/statistics/statistics.routes.ts": """export const routes = [
            { path: 'ctdc/governance', loadComponent: () => import('./gov/gov.component').then((c) => c.GovComponent) },
            { path: 'ctdc/other', loadComponent: () => import('./other/other.component').then((c) => c.OtherComponent) } ];""",
        "web/src/app/pages/statistics/gov/gov.component.ts": """import { ReportService } from '../../../service/report.service';
            export class GovComponent { private readonly reportService = inject(ReportService);
              readonly reportCode = ReportCode.R017_QUAN_TRI;
              load() { this.reportService.export(this.reportCode); } }""",
        "web/src/app/pages/statistics/gov/gov.component.html": "<h1>{{ 'statistics.gov.title' | translate }}</h1>",
        "web/src/app/service/report.service.ts": """export class ReportService { apiUrl = 'report';
              export(code) { return this.http.post(`${this.baseUrl}/${this.apiUrl}/${code}/export`, {}); }
              other() { return this.http.get('/unused/thing'); } }""",
        "api/src/main/java/R017QuanTriReport.java": """class R017QuanTriReport { ReportCode code() { return ReportCode.R017_QUAN_TRI; }
              String sql = "SELECT * FROM V_RPT_R017_QUAN_TRI"; String tpl = "templates/excel/R017_quan_tri.xlsx"; }""",
        "api/src/main/java/ReportCode.java": "enum ReportCode { " + ", ".join("R%03d_X" % i for i in range(1, 30)) + ", R017_QUAN_TRI }",
        "api/src/main/java/ReportController.java": '@RequestMapping("/{reportCode}") class ReportController { @PostMapping("/export") void e() {} }',
        "api/src/main/resources/db/R017_v.sql": "CREATE OR REPLACE VIEW V_RPT_R017_QUAN_TRI AS SELECT * FROM COMPANY_DATA JOIN FORMS ON 1=1",
        "api/src/main/resources/templates/excel/R017_quan_tri.xlsx": "",
    }
    for rel, body in files.items():
        p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(body, encoding="utf-8")


def test_locate_follows_menu_to_backend(tmp_path):
    root = tmp_path / "repo"; _fake_repo(root)
    prof = _mini_profile(tmp_path, {"paths": {"tools_dir": str(tmp_path / "tools"), "work_root": str(tmp_path / "w"), "code_root": str(root)},
                                    "codemap": {"include": ["web/src/**/*.ts", "web/src/**/*.html", "web/src/**/*.json",
                                                            "api/src/**/*.java", "api/src/**/*.sql"],
                                                "i18n": "web/src/assets/i18n/vi/**/*.json", "frontend": {"a": "web"}}})
    ws = prof.workspace("X_1")
    fn = {"menu": "Thống kê >> Thống kê CTĐC >> BC quản trị >> Tab chi tiết", "name": "[# X_1] Báo cáo quản trị", "system_key": "a"}
    t = locate.locate(prof, ws, fn)
    assert t["method"] == "menu path" and t["routes"] == ["/statistics/ctdc/governance"]       # 'other' has no matching parents
    assert t["menu"][0]["unmatched_tail"] == ["Tab chi tiết"]
    assert t["components"] == ["web/src/app/pages/statistics/gov/gov.component.ts"]
    assert t["endpoints"] == ["POST /report/{}/export (report.service.ts.export)"]
    assert t["report_codes"] == ["R017"]
    be = [x["file"] for x in t["top"] if x["score"] is not None]
    assert be[0] == "api/src/main/java/R017QuanTriReport.java"                                   # the registry enum ranks below
    assert be.index("api/src/main/java/ReportCode.java") > 0
    assert {"V_RPT_R017_QUAN_TRI", "COMPANY_DATA", "FORMS"} <= set(t["sql_objects"])
    assert t["views"][0]["file"] == "api/src/main/resources/db/R017_v.sql"
    assert t["templates"] == ["api/src/main/resources/templates/excel/R017_quan_tri.xlsx"]
    assert locate.locate(prof, ws, fn).get("cached")
    md = locate.trace_md(t)
    assert "Tab chi tiết" in md and "R017QuanTriReport.java" in md


def test_locate_with_route_and_without_menu(tmp_path):
    root = tmp_path / "repo"; _fake_repo(root)
    prof = _mini_profile(tmp_path, {"paths": {"tools_dir": str(tmp_path / "tools"), "work_root": str(tmp_path / "w"), "code_root": str(root)},
                                    "codemap": {"include": ["web/src/**/*.ts", "web/src/**/*.json", "api/src/**/*.java"],
                                                "i18n": "web/src/assets/i18n/vi/**/*.json"}})
    t = locate.locate(prof, prof.workspace("X_2"), {"name": "x"}, route="/statistics/ctdc/governance")
    assert t["method"] == "route given" and t["components"][0].endswith("gov.component.ts")
    t = locate.locate(prof, prof.workspace("X_3"), {"name": "[# X_3] Không có trong code"})
    assert t["method"].startswith("name only") and "screen component" in t["not_found"]


# ---------------------------------------------------------------- profile + workspace
def test_profile_loading_and_codes(tmp_path, monkeypatch):
    d = tmp_path / "proj" / ".report-kit"; d.mkdir(parents=True)
    (d / "project.yaml").write_text(yaml.safe_dump({"name": "demo", "paths": {"tools_dir": "{home}/x", "work_root": str(tmp_path / "w")},
                                                   "systems": {"a": {"match": ["App A"], "web": "http://a", "api": "http://a/api"}}}),
                                    encoding="utf-8")
    (d / "project.local.yaml").write_text(yaml.safe_dump({"paths": {"tools_dir": str(tmp_path / "tools")}}), encoding="utf-8")
    monkeypatch.chdir(tmp_path / "proj")
    monkeypatch.setenv("RK_LOGIN_USER", "u1")
    prof = P.load()
    assert prof.name == "demo" and prof.tools_dir == str(tmp_path / "tools")
    assert prof.system_for_label("App A") == "a" and prof.secret("login_user") == "u1"
    with pytest.raises(SystemExit):
        prof.secret("db_password")
    assert P.norm_code("[# 1E_117]") == "1E_117" and P.norm_code("1e117") == "1E_117" and P.norm_code("2E_50") == "2E_50"
    ws = prof.workspace("1E117")
    ws.mark("start", x=1)
    assert ws.done("start") and os.path.isdir(ws.dir) and ws.latest_run() is None


def test_engine_rejects_duplicate_ids(tmp_path, monkeypatch):
    from reportkit.checks import engine
    d = tmp_path / ".report-kit"; d.mkdir()
    (d / "project.yaml").write_text(yaml.safe_dump({"name": "demo", "paths": {"work_root": str(tmp_path / "w")},
                                                   "systems": {"a": {"web": "http://a", "api": "http://a/api"}}}), encoding="utf-8")
    prof = P.load(str(d)); ws = prof.workspace("X_1")
    with open(os.path.join(ws.dir, "checks.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump({"system": "a", "ui": [{"id": "U1", "title": "t"}, {"id": "U1", "title": "t2"}]}, f)
    with pytest.raises(SystemExit):
        engine.load(ws)


# ---------------------------------------------------------------- coverage matrix + gate
def _mini_profile(tmp_path, extra=None):
    tools = tmp_path / "tools"; tools.mkdir(exist_ok=True)
    tpl = openpyxl.Workbook(); sh = tpl.active
    sh["D3"] = "X_1"; sh["B10"] = "Mục đích"; sh["D10"] = "Kết quả mong muốn"
    tpl.save(tools / "tpl.xlsx")
    d = tmp_path / ".report-kit"; d.mkdir(exist_ok=True)
    cfg = {"name": "demo", "paths": {"tools_dir": str(tools), "work_root": str(tmp_path / "w")},
           "systems": {"a": {"web": "http://a", "api": "http://a/api"}},
           "workbook": {"template": str(tools / "tpl.xlsx"), "out_dir": str(tmp_path / "out")}}
    cfg.update(extra or {})
    (d / "project.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return P.load(str(d))


def test_coverage_sheet_ids_and_gate(tmp_path):
    import json
    from reportkit import workbook as W
    prof = _mini_profile(tmp_path); ws = prof.workspace("X_1")
    wb = W.Workbook(prof, ws, name="n", screen="s", ticket="T", ascii_name="N")
    wb.chapter("Chức năng 1"); wb.cat("Giao diện")
    wb.tc("Kiểm tra A", "1.", "kq A", status="P", actual="thấy A")
    wb.sub("Dữ liệu")
    wb.tc("Kiểm tra B", "1.", "kq B", status="F", actual="thấy B sai", bug="BUG-01")
    wb.tc("Kiểm tra C", "1.", "kq C")
    assert [cid for _, cid, _ in wb.case_ids().values()] == ["X_1_1", "X_1_2", "X_1_3"]
    with pytest.raises(ValueError):
        wb.sheet_coverage([("Quy tắc nghiệp vụ", "B1", "r", ["Kiểm tra Z"], "")], "t")         # no such case
    with pytest.raises(ValueError):
        wb.sheet_coverage([("Quy tắc nghiệp vụ", "B1", "r", [], "vì sao đó")], "t")            # no case and no reason
    wb.sheet_coverage([("Quy tắc nghiệp vụ", "B1", "r1", ["Kiểm tra A", "Kiểm tra B"], ""),
                       ("Bẫy dữ liệu (rt probe)", "lang_twins (T1)", "r2", ["Kiểm tra B"], ""),
                       ("Quy chuẩn chung", "II.3", "r3", [], "Không áp dụng: không có ô ngày")], "t")
    out = wb.save()
    s = openpyxl.load_workbook(out)[W.COV_SHEET]
    assert s["E5"].value == "X_1_1, X_1_2" and s["F5"].value == "P: 1, F: 1" and s["E7"].value == "-"
    probe = tmp_path / "probe.json"
    probe.write_text(json.dumps({"tables": {"T1": {"traps": [{"id": "lang_twins", "flagged": True}, {"id": "null_period", "flagged": False}]},
                                            "T2": {"traps": [{"id": "lang_twins", "flagged": True}, {"id": "status_mix", "flagged": True}]}}}), encoding="utf-8")
    g = W.coverage_gate(out, str(probe), first_row=12)
    assert not g["missing_sheet"] and g["rows_without_reason"] == []
    assert sorted(g["traps_not_mapped"]) == ["T2.lang_twins", "T2.status_mix"]
    assert g["cases_not_referenced"] == ["X_1_3"]


def _function_list(prof, rows, sheet_title="List chức năng"):
    fl = openpyxl.Workbook(); first = fl.active; first.title = "List báo cáo"
    first.append(["Link UC", "UC Name"]); first.append(["OLD", "[# 1E_117] Bản cũ - không dùng"])
    sh = fl.create_sheet(sheet_title)
    sh.append(["KBKT bàn giao"])
    sh.append(["Stt", "Phân hệ", "Mã Jira", "New UC Name", "Use Case Name", "Menu/tab tương ứng", "Menu/tab (cấp thấp nhất)",
               "PIC", "PIC DEV", "Link testcase của DEV"])
    for r in rows:
        sh.append(r)
    fl.save(os.path.join(prof.tools_dir, "list.xlsx"))


FL_CFG = {"inputs": {"function_list": {
    "glob": "list.xlsx", "sheet": "List chức năng", "header_contains": "Mã Jira", "code_columns": ["New UC Name"],
    "columns": {"jira": "Mã Jira", "name": "New UC Name", "system": "Phân hệ", "menu": "Menu/tab (cấp thấp nhất)",
                "pic": "PIC DEV", "testcase": "Link testcase của DEV"},
    "ticket": {"column": "testcase", "regex": "^(AI-\\d+)_"}}}}


def test_function_list_second_sheet(tmp_path):
    from reportkit import inputs
    prof = _mini_profile(tmp_path, FL_CFG)
    _function_list(prof, [
        [117, "IDS", "HSISI-806", "[# 1E_117] Trang nội bộ", "[ # 1E_130] Dashboard", "x", "Trang chủ (dashboard)",
         "Huyền", "Hoang Nghia Tuan", "AI-23_1E117_TrangNoiBo_v4.xlsx"],
        [130, "IDS", "HSISI-819", "[# 1E_130] Vi phạm định kỳ", "[ # 1E_143] Khác", "x", "Thống kê >> Vi phạm CBTT >> Định kỳ",
         "Huyền", "Tran", None]])
    fn = inputs.find_function(prof, "1E_117")
    assert fn["jira"] == "HSISI-806" and fn["pic"] == "Hoang Nghia Tuan" and fn["ticket"] == "AI-23"     # 'PIC DEV' beats 'PIC'
    assert "[List chức năng]" in fn["source"] and fn["name"].startswith("[# 1E_117]")
    fn = inputs.find_function(prof, "1E_130")             # 1E_130 also appears in 'Use Case Name' of row 117: ignored
    assert fn["jira"] == "HSISI-819" and fn["ticket"] is None
    assert inputs.menu_path(fn) == ["Thống kê", "Vi phạm CBTT", "Định kỳ"]
    assert inputs.screen_names(fn) == ["Vi phạm định kỳ"]
    with pytest.raises(SystemExit):
        inputs.find_function(prof, "1E_143")


def test_siblings_share_screen_or_code(tmp_path):
    import json
    from reportkit import inputs
    prof = _mini_profile(tmp_path, FL_CFG)
    _function_list(prof, [[117, "IDS", "J1", "[# 1E_117] Trang nội bộ"], [118, "IDS", "J2", "[# 1E_118] Trang CTĐC"],
                          [119, "IDS", "J3", "[# 1E_119] Báo cáo khác"]])
    root = tmp_path / "w2"
    for code, files, routes in (("1E_117", ["a.ts", "a.html", "z.java"], ["/dashboard"]), ("2E_50", ["a.ts", "a.html", "y.java"], []),
                                ("2E_51", ["a.ts", "q", "r"], [])):
        (root / code).mkdir(parents=True)
        (root / code / "trace.json").write_text(json.dumps({"top": [{"file": f} for f in files], "routes": routes}), encoding="utf-8")
    fn = inputs.find_function(prof, "1E_118")
    sibs = inputs.find_siblings(prof, "1E_118", fn, trace={"top": [{"file": f} for f in ["a.ts", "a.html", "x.java"]], "routes": ["/dashboard"]},
                                workspaces_root=str(root))
    assert [s["code"] for s in sibs] == ["1E_117", "2E_50"]
    assert any("cùng màn hình /dashboard" in w for w in sibs[0]["why"]) and sibs[0]["name"] == "[# 1E_117] Trang nội bộ"
    assert any("2/3" in w for w in sibs[1]["why"])
    assert inputs.find_siblings(prof, "1E_119", inputs.find_function(prof, "1E_119")) == []


def test_rules_sheet(tmp_path):
    from reportkit import workbook as W
    prof = _mini_profile(tmp_path); ws = prof.workspace("X_1")
    wb = W.Workbook(prof, ws, name="n", screen="s", ticket="T", ascii_name="N")
    with pytest.raises(ValueError):
        wb.sheet_rules([("Phạm vi", "r", "a.sql:1", "kq", "-", "Sai", "", "")], "t", "n")         # verdict not in the list
    wb.sheet_rules([("Phạm vi", "Chỉ tin đã duyệt", "a.sql:12", "118 công ty", "I.2", "Đúng", "X_1_3", ""),
                    ("Hiển thị", "Mã sàn hiện tên", "b.java:40", "550 dòng hiện OTC", "III.1", "Lỗi", "BUG-02", "")], "t", "n")
    s = openpyxl.load_workbook(wb.save())[W.RULE_SHEET]
    assert [c.value for c in s[4]] == W.RULE_HEADERS
    assert s["A6"].value == 2 and s["G6"].value == "Lỗi" and s["G6"].fill.fgColor.rgb == W.RED.fgColor.rgb


def _tiny_png(path, w=4, h=3):
    import struct, zlib
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return str(path)


def test_evidence_sheet_links_and_gate(tmp_path):
    from reportkit import evidence as E, workbook as W
    prof = _mini_profile(tmp_path); ws = prof.workspace("X_1")
    png = _tiny_png(tmp_path / "s.png")
    wb = W.Workbook(prof, ws, name="n", screen="s", ticket="T", ascii_name="N")
    wb.chapter("Chức năng 1"); wb.tc("Kiểm tra A", "1.", "kq A", status="F", actual="thấy A sai", bug="BUG-01")
    wb.sheet_bugs([("BUG-01", "Cao", "Mở", "m", "c", "n", "b"), ("BUG-02", "Thấp", "Mở", "m", "c", "n", "b"),
                   ("BUG-03", "Thấp", "Mở", "m", "c", "n", "b"), ("BUG-04", "Thấp", "Rút lại", "m", "c", "n", "b")], "t")
    mk = lambda bug: E.card(bug, ["bước 1"], "**sai**", "đúng", [E.shot(png, "ảnh")])
    cards = [mk("BUG-01"), mk("BUG-01"), mk("BUG-02")]
    for c in cards:
        c["png"] = png                                   # pre-rendered: no browser needed
    with pytest.raises(ValueError):
        wb.sheet_evidence([mk("BUG-99")], "t", "n")      # bug not in 'Danh sách lỗi'
    wb.sheet_evidence(cards, "t", "n")
    assert [c["part"] for c in cards] == ["1/2", "2/2", ""]
    assert cards[0]["title"] == "m" and cards[0]["severity"] == "Cao" and cards[0]["basis"] == "c" and cards[0]["cause"] == "n"
    assert cards[0]["status"] == "Mở - còn lỗi " + cards[0]["captured"][:5]          # from the bug row + picture date
    out = wb.save()
    book = openpyxl.load_workbook(out)
    assert book.sheetnames.index(W.EVIDENCE_SHEET) == book.sheetnames.index("Danh sách lỗi") + 1
    b = book["Danh sách lỗi"]
    assert b["H5"].value == "Xem hình BUG-01 (1/2) (+1 hình tiếp theo)" and b["H5"].hyperlink.location.endswith("!B4")
    assert W.evidence_gate(out) == ["BUG-03"]            # BUG-04 is withdrawn


def test_evidence_excel_panel_shows_file_formats(tmp_path):
    from reportkit import evidence as E
    x = openpyxl.Workbook(); sh = x.active
    sh["A1"] = 1234567.5; sh["A1"].number_format = "#,##0.00"; sh["B1"] = 1234567
    p = tmp_path / "f.xlsx"; x.save(p)
    doc = E._excel_html(E.excel(str(p), "cap", bad=["B1"], extra={1: "1,234,567"}))
    assert "1,234,567.50" in doc and ">1234567<" in doc and 'class="bad"' in doc and 'class="extra"' in doc
    with pytest.raises(ValueError):
        E.card("BUG-01", ["s"], "a", "e", [E.text("api", "500")])        # no screenshot -> captured required
    with pytest.raises(ValueError):
        E.text("api", "GET /x\nAuthorization: Bearer abcdefghijklmnop")      # credentials never go in a picture
    E.text("api", "HTTP 500: ORA-00904 invalid identifier")


def test_evidence_run_shot_and_lint(tmp_path):
    import json
    from reportkit import evidence as E
    png = _tiny_png(tmp_path / "U07_final.png", w=200, h=100)
    (tmp_path / "U07.json").write_text(json.dumps({"id": "U07", "boxes": {"shot": png, "boxes": {
        "grid": [[10, 20, 100, 50]], "cells": [[30, 30, 10, 5], [60, 30, 10, 5]]}}}), encoding="utf-8")
    p = E.run_shot(str(tmp_path), "U07", "cap", mark=["cells#1"], show=["grid"], pad=5)
    assert p["crop"] == (5, 15, 110, 60) and p["boxes"] == [[60, 30, 10, 5]]
    with pytest.raises(ValueError):
        E.run_shot(str(tmp_path), "U07", "cap", mark=["nope"])
    c = E.card("BUG-01", ["s"], "a", "e", [E.shot(png, "cap")], title="t", status="Mở", captured="01/01/2020 10:00")
    w = E.lint(c, today="05/10/2026")
    assert any("đánh dấu" in x for x in w) and any("hôm nay" in x for x in w)
    c = E.card("BUG-01", ["s"], "a", "e", [p], title="t", status="Mở", captured="05/10/2026 10:00")
    assert E.lint(c, today="05/10/2026") == []
