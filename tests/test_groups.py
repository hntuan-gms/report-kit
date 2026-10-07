import os

from reportkit import inputs, workbook as W
from reportkit.cli import _gate
from test_core import _analysis, _mini_profile


def test_group_key_from_function_list():
    assert inputs.group_key({"group": "# 1D.I_NHÓM CHỨC NĂNG GIÁM SÁT TUÂN THỦ CÔNG BỐ THÔNG TIN"}) == "1D.I"
    assert inputs.group_key({"group": "# 1B.III.3_Quản lý thông tin cổ đông lớn"}) == "1B.III.3"
    assert inputs.group_key({"group": "# 2F_TÍCH HỢP & CHIA SẺ"}) == "2F"
    assert inputs.group_key({"group": "#N/A"}) is None and inputs.group_key({}) is None


def _conventions(prof, key, rows):
    path = inputs.group_conventions(prof, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Quy ước kiểm thử nhóm %s\n\n| Mục | Quyết định | Lý do | Trạng thái |\n|---|---|---|---|\n" % key)
        f.writelines("| %s | %s | lý do | Claude quyết định |\n" % r for r in rows)
    return path


def test_convention_items_and_gate(tmp_path, capsys):
    prof = _mini_profile(tmp_path); ws = prof.workspace("X_1"); _analysis(ws)
    path = _conventions(prof, "1D.I", [("Q1", "Phần chung của Quy chuẩn"), ("Q2", "Tin đã gửi là tin đã duyệt")])
    assert path.endswith(os.path.join("rules", "groups", "1D.I.md"))
    assert inputs.convention_items(path) == {"Q1": "Phần chung của Quy chuẩn", "Q2": "Tin đã gửi là tin đã duyệt"}

    def build(version, pre, cite):
        wb = W.Workbook(prof, ws, name="n", screen="s", ticket="T", ascii_name="N", version=version)
        wb.chapter("Chức năng 1"); wb.pre(pre); wb.cat("Chức năng")
        wb.tc("Kiểm tra trạng thái", "1. Bấm [Tìm kiếm]", "Tin đã duyệt là đã gửi", status="P", actual="Đạt. Khớp.",
              basis="Căn cứ: Quy ước kiểm thử nhóm %s" % cite, covers="R1")
        wb.finish(run_date="07/10/2026", run_note="n")
        return wb.save()

    good = build(1, "1. Đăng nhập\n2. Quy ước kiểm thử nhóm 1D.I do người kiểm thử đặt, chờ BA rà", "1D.I mục Q2")
    assert W.convention_refs(good) == ([("X_1_1", "1D.I", "Q2")], True)
    assert _gate(good, prof=prof)

    bad_item = build(2, "1. Đăng nhập\n2. Quy ước kiểm thử nhóm 1D.I do người kiểm thử đặt", "1D.I mục Q9")
    assert not _gate(bad_item, prof=prof)
    assert "not an item of" in capsys.readouterr().out

    no_pre = build(3, "1. Đăng nhập", "1D.I mục Q1")
    assert not _gate(no_pre, prof=prof)
    assert "precondition row" in capsys.readouterr().out

    old_style = build(5, "1. Quy ước kiểm thử nhóm 1D", "1D mục D2")              # an old / malformed citation is not skipped
    assert W.convention_refs(old_style)[0] == [("X_1_1", "1D", "D2")]
    assert not _gate(old_style, prof=prof)
    capsys.readouterr()

    no_file = build(4, "1. Quy ước kiểm thử nhóm 1E.I", "1E.I mục Q1")
    assert not _gate(no_file, prof=prof)
    assert "does not exist" in capsys.readouterr().out
