# -*- coding: utf-8 -*-
"""Workbook {code}. rt build {code} --check, then rt build {code}.
Standalone: no case may refer to another code's workbook. Numbers come from measure_{code}.py / rt check, measured today."""
from reportkit.wbhelpers import make

H = make("{code}", name="{name}", screen="[# {code}] {name} - CHANGE: system > menu path", ticket="AI-CHANGE",
         ascii_name="CHANGE", group={group_repr}, system="{system}")
wb, T, NR = H.wb, H.T, H.NR
QC, QU, FN, SELF, RT, SEC, CORRECT, WRITE, LOGIN = H.QC, H.QU, H.FN, H.SELF, H.RT, H.SEC, H.CORRECT, H.WRITE, H.LOGIN
MENU = "Mở menu CHANGE >> CHANGE"

wb.chapter("Chức năng 1: CHANGE")
wb.pre("1. Đăng nhập CHANGE.\n2. Menu CHANGE.\n3. Dữ liệu lúc kiểm (dd/mm/yyyy): CHANGE.\n"
       "4. Các thao tác ghi dữ liệu không chạy thật trên môi trường dùng chung.\n" + H.QUYUOC + ".")

wb.cat("Giao diện")
wb.sub("Giao diện chung")
T("Kiểm tra mở màn từ menu", [LOGIN, MENU, "Quan sát tiêu đề và danh sách"],
  ["Màn hình mở ra không lỗi"], FN, "P", ["Đạt.", "CHANGE: what was seen, with a number"], covers=["area:giao_dien"])

wb.cat("Chức năng")
NR("Kiểm tra CHANGE (write action)", [LOGIN, MENU, "..."], ["..."], FN, WRITE, covers=[])

wb.cat("An toàn thông tin")
wb.sub("1. Kiểm tra XSS")
wb.sub("2. Kiểm tra SQL Injection - Select")
wb.sub("Kiểm tra SQL Injection - Insert")

# wb.waive("R9", "reason")          # a requirement with no case (goes to the hand-off)
wb.finish(run_date="CHANGE", run_note=H.run_note("CHANGE", "CHANGE"))
print(wb.save())
