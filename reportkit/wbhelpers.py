"""Shortcuts for a workspace's build_workbook.py, so each script is only the cases.

    from reportkit.wbhelpers import make
    H = make("2B_22", name="...", screen="[# 2B_22] ... - Kiểm toán > ...", ticket="AI-22", ascii_name="QuanLy...", group="2B.I")
    wb, T, NR = H.wb, H.T, H.NR
    T(purpose, steps, expected, H.QC("II.5.1"), "P", ["Đạt.", "..."], covers=["R3", "area:dropdown"])
    NR(purpose, steps, expected, H.FN, H.WRITE, covers=["R24"])
    wb.finish(run_date="20/10/2026", run_note=H.run_note("20/10/26", "20/10/26"))
    print(wb.save())

Text that belongs to a project (login sentence, person, environment) comes from the profile's `workbook.helpers`:
    workbook:
      helpers:
        person: "Hoang Nghia Tuan"
        by_system:
          audit: {login_line: "Đăng nhập hệ thống Kiểm toán bằng tài khoản Chuyên viên", env_label: "audit-dev-gms.net", system: audit}
          ids:   {login_line: "Đăng nhập hệ thống IDS bằng tài khoản Chuyên viên", env_label: "ids-dev-gms.net", system: ids}
    (pass system="audit" to make(); the scaffold does it)
Every workbook stays standalone: nothing here refers to another code's workbook (a Tester reads one file).
"""
import os

from . import profile as P
from . import workbook as W

PAYLOADS = {
    "script": "<script>alert('xss1')</script>",
    "encoded": "%3Cscript%3Ealert('xss2')%3C%2Fscript%3E",
    "nested": "<div><img src=x onerror=alert('xss3')><svg onload=alert('xss4')><script>alert('xss5')</script></svg></div>",
    "img": "<img src=x onerror=alert('xss')><script>alert(1)</script>",
    "sql_true": "' OR '1'='1",
    "sql_drop": "'; DROP TABLE X; --",
    "sql_union": "x' UNION SELECT NULL FROM DUAL --",
}


class Helpers(object):
    pass


def make(code, name, screen, ticket, ascii_name, version=1, group=None, system=None, profile=None):
    prof = profile or P.load(os.environ.get("RK_PROFILE"))
    ws = prof.workspace(code)
    cfg = dict(prof.get("workbook.helpers") or {})
    cfg.update((cfg.get("by_system") or {}).get(system or "", {}))          # per-system login sentence / environment
    wb = W.Workbook(prof, ws, name=name, screen=screen, ticket=os.environ.get("RK_TICKET", ticket), ascii_name=ascii_name, version=version)
    h = Helpers()
    h.prof, h.ws, h.wb, h.group, h.cfg = prof, ws, wb, group, cfg

    h.QC = lambda s: "Căn cứ: Quy chuẩn chung TC-TK mục " + s
    h.QU = lambda q: "Căn cứ: Quy ước kiểm thử nhóm %s mục %s" % (group or "?", q)
    h.FN = "Căn cứ: thiết kế chức năng"
    h.SELF = "Căn cứ: các phần của cùng một màn hình phải thống nhất"
    h.RT = "Căn cứ: chức năng phải chạy không lỗi"
    h.SEC = "Căn cứ: KBKT_Template khối An toàn thông tin"
    h.CORRECT = lambda s: "Căn cứ: " + s
    h.WRITE = "Chưa thực hiện - thao tác ghi dữ liệu trên môi trường dùng chung, chưa được phép"
    h.NEED_DATA = lambda what: "Chưa thực hiện - cần dữ liệu: " + what
    h.NEED_ACCOUNT = lambda what: "Chưa thực hiện - cần tài khoản: " + what
    h.LOGIN = cfg.get("login_line", "Đăng nhập hệ thống bằng tài khoản dùng để kiểm thử")
    h.QUYUOC = ("Điểm Quy chuẩn chung không quy định: theo Quy ước kiểm thử nhóm %s "
                "(người kiểm thử đặt thay BA, chờ BA rà lại)" % (group or "?"))
    h.PAYLOADS = PAYLOADS

    def T(purpose, steps, expected, basis, status, actual, covers=None):
        wb.tc(purpose, steps, expected, basis=basis, status=status, actual=actual, covers=covers)

    def NR(purpose, steps, expected, basis, why, covers=None):
        wb.tc(purpose, steps, expected, basis=basis, status=None, actual=[why], covers=covers)

    def build_stamp():
        """'Bản build dd/mm/yy (<env>, frontend cập nhật dd/mm/yyyy hh:mm GMT)' from the site's Last-Modified header."""
        env = cfg.get("env_label") or ""
        try:
            import email.utils
            import requests
            sysd = prof.system(cfg.get("system") or next(iter(prof.systems)))
            lm = requests.head(sysd["web"], timeout=10, allow_redirects=True).headers.get("Last-Modified")
            d = email.utils.parsedate_to_datetime(lm)
            return "Bản build %s (%s, frontend cập nhật %s GMT)" % (d.strftime("%d/%m/%y"), env, d.strftime("%d/%m/%Y %H:%M"))
        except Exception:
            return "Bản build (%s)" % env

    def run_note(date_from, date_to, person=None, login=None):
        return ("Thời gian: %s - %s\nNgười thực hiện: %s (chạy tự động bằng Claude, tài khoản %s)\n%s" % (
            date_from, date_to, person or cfg.get("person", ""), login or prof.secrets().get("login_user", ""), build_stamp()))

    h.T, h.NR, h.build_stamp, h.run_note = T, NR, build_stamp, run_note
    return h
