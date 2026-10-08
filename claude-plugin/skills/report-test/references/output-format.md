# Output format: the test case workbook

One `.xlsx` per report with **one sheet: the test cases**, built with `reportkit.workbook.Workbook` from the template named in the profile (`workbook.template`, KBKT by default). No other sheet and no bug pictures: Testers and BAs read only the test case sheet, so everything they need is in it.

## File name and version

`AI-<jira-or-ticket>_<code without #>_<TenKhongDau>_v<N>.xlsx`, e.g. `AI-60_2E50_BaoCaoTongHopDanhSachCongTyKiemToan_v1.xlsx`.
- Ask for the AI-xx ticket number if you don't know it.
- Never overwrite a file that was sent for review. Create `v<N+1>`: the reviewer's comments live in the old one.

## The sheet (template layout, named `<code> <short name>`)

Header cells:
- D2 = `[# code] name (REPORT_CODE) - <subsystem> > menu path`
- D3 = the code. The formula in column A turns it into `1E_128_1`, `1E_128_2`, …
- D4–D8 = counters, from column **E (Lần 1)**.

Blocks (colours come from the template):
```
Chức năng 1: <name> - Tìm kiếm/Tra cứu và Xuất Excel      (chapter, yellow)
1. Đăng nhập ... 2. Menu >> ... >> ...                     (precondition row)
Giao diện                                                  (category, green)
  Giao diện chung                                          (sub-section, blue)
  Giao diện file Excel kết quả
Chức năng
  Làm mới / Tìm kiếm - Bộ lọc / Xuất Excel - Thành công / Không thành công
  Dữ liệu báo cáo - <one sub-section per data rule family>
  Phân quyền dữ liệu
An toàn thông tin                                          (category, green - always, last)
  1. Kiểm tra XSS
  2. Kiểm tra SQL Injection - Select
  Kiểm tra SQL Injection - Insert
```
- No "Validate các trường" (per-field input validation): out of scope.
- **Always end with "An toàn thông tin"** (`test-areas.md`). A case that does not fit the screen stays, with `Không áp dụng - <lý do>` in H.

## Columns

| Col | Content |
|---|---|
| B | Mục đích: `Kiểm tra <điều gì> <ở đâu>`, one short sentence |
| C | Các bước: one screen action per line, with the data used. No API paths |
| D | Kết quả mong muốn: one expected point per line, in business words |
| E/F/G | Lần 1/2/3: `P` / `F` / `PE`, empty = not run |
| H | Kết quả hiện tại: the verdict, then what was seen (format below) |
| I | Mã lỗi: leave empty; the Tester writes the tracker's bug id after logging it |
| J | Line 1 `Căn cứ: …`. For an F only, optional line 2 `Kỹ thuật: …` for DEV |

Pass lists to `wb.tc()`: it numbers the steps, bullets the expected lines and the lines of H after the verdict.

## Writing for a Tester / BA (the main rule)

Testers complained that cases read like machine output: one long paragraph, symbols, internal names, several bugs in one row. Write so a reader who has never seen the code understands each row in one read.

1. **One case = one check = at most one bug.** If a check finds two different problems, write two cases.
2. **One idea per line.** No line over 160 characters. H has at most 5 lines.
3. **Words, not symbols.** No `Σ`, `→`, `≥`, `≤`, `×`, `|`. Write "từ 90 điểm trở lên", "cộng", "đúng ra là".
4. **Names as the screen shows them**: column titles, button labels, company names. Never table / column / variable names, `file:line`, record IDs or check ids (`D01`, `U17`) in B, C, D, H.
5. **No shorthand or tool words**: no `vd` (write "Ví dụ"), `v.v`, `API`, `view`, `dedup`, `NULL`, `MATCH`, `NM`, "ô so sánh". Count in what the reader sees: "công ty", "lượt đánh giá", "dòng", not "ô".
6. **Numbers**: Vietnamese format in prose (1.743 công ty); values copied from the screen stay as shown.

H, line by line:
```
Đạt. | Sai. | Cần BA xác nhận. | Chưa thực hiện - <lý do> | Không áp dụng - <lý do>
- Ví dụ: <công ty, kỳ>: màn hình hiện <X>[, đúng ra là <Y>].
- Phạm vi: <bao nhiêu công ty / lượt / dòng bị, ở kỳ nào>.          (F, when it is more than the example)
- Nguyên nhân: <in business words>.                                (F, when known)
```
`rt build` checks this: H starts with the verdict of column E, no line too long, no symbol / internal name in B C D H, no run id in J, one bug per case.

### Căn cứ (line 1 of J)

The first that applies:

| Basis | Wording |
|---|---|
| The Quy chuẩn covers it | `Căn cứ: Quy chuẩn chung TC-TK mục II.5.1` |
| A group convention settles it (decided acting as BA) | `Căn cứ: Quy ước kiểm thử nhóm 1D.I mục Q2`. Also add the line "Điểm Quy chuẩn chung không quy định: theo Quy ước kiểm thử nhóm 1D.I (người kiểm thử đặt thay BA, chờ BA rà lại)" to the precondition row. `rt build` checks both. |
| The system contradicts itself | `Căn cứ: lưới và file Excel phải thống nhất` / `Căn cứ: trường bắt buộc phải có dấu (*)` |
| Plain correctness | `Căn cứ: ràng buộc dữ liệu - số kiểm toán viên không thể âm` / `Căn cứ: "Đến ngày" gồm cả ngày cuối` |
| Runtime error | `Căn cứ: chức năng phải chạy không lỗi` |
| Security | `Căn cứ: KBKT_Template khối An toàn thông tin` |
| The function's own rule | `Căn cứ: thiết kế chức năng` |

Never `Căn cứ: SRS …`, and never a sentence saying the SRS was not used, is outdated, or that the code is the reference.

`Kỹ thuật:` (F only, one line): where DEV should look, e.g. `Kỹ thuật: dòng tổng lấy điểm lưu sẵn, các nhóm tính lại (evaluation-ranking-detail.component.ts:226)`. No run ids, no SQL.

### Example: before and after (1D_116_18)

Before (one block, symbols, three companies in one sentence, run ids):
> D: TỔNG ĐIỂM = 100 + Σ Tổng điểm nhóm (các số trên cùng một bảng)
> H: Sai. AMD: Tổng điểm nhóm −3,5 / 0 / 0 / 0 nhưng TỔNG ĐIỂM 4 NHÓM = 0 (đúng ra 96,5). CPA: nhóm 1 −0,35 nhưng TỔNG ĐIỂM = 100. BMK kỳ 08/2026 khớp (−10,5 −15 −2,5 −2 → 70).

After:
```python
wb.tc("Kiểm tra dòng TỔNG ĐIỂM 4 NHÓM trên màn hình chi tiết",
      ["Mở chi tiết Công ty Cổ phần Đầu tư và Khoáng sản FLC AMD, kỳ 09/2026",
       "Cộng cột Tổng điểm nhóm của 4 nhóm", "So với dòng TỔNG ĐIỂM 4 NHÓM"],
      ["TỔNG ĐIỂM 4 NHÓM bằng 100 cộng điểm (âm) của 4 nhóm", "Hai số trên cùng màn hình phải khớp nhau"],
      basis="Căn cứ: các số liệu của cùng một lượt đánh giá phải thống nhất\n"
            "Kỹ thuật: dòng tổng lấy điểm lưu sẵn, các nhóm tính lại (evaluation-ranking-detail.component.ts:226)",
      status="F", actual=["Sai.",
          "Ví dụ: FLC AMD kỳ 09/2026: 4 nhóm cộng lại là −3,5 nhưng dòng TỔNG ĐIỂM 4 NHÓM hiện 0. Đúng ra là 96,5.",
          "Cũng sai: Cà phê Phước An kỳ 05/2026: nhóm 1 bị trừ 0,35 nhưng TỔNG ĐIỂM vẫn là 100.",
          "Nguyên nhân: dòng tổng lấy điểm đã lưu từ trước, không tính lại từ các nhóm."])
```

A whole-report comparison case gives the scope, then one line per kind of error with its count, and leaves the detail to the case of that error:
```
Sai. Đã kiểm tra 27.754 lượt đánh giá của 16 kỳ.
- Phân loại để trống dù đã có Điểm: 15.695 lượt (chi tiết ở case "Kiểm tra cột Phân loại").
- Điểm không khớp kết quả từng tiêu chí: 7.280 lượt. Ví dụ: FLC AMD kỳ 09/2026 hiện 0, đúng ra là 45.
- Tên công ty, MDN, Sàn, MCK, Chuyên viên: khớp toàn bộ.
```

## Status meaning

- `P`: matches the expected result: the Quy chuẩn where it applies, otherwise the function's own rule. A P with exceptions is not a P: the exceptions are an F case of their own.
- `F`: breaks the Quy chuẩn, contradicts the system itself, is plainly wrong for any business rule, fails at runtime, or fails a security case.
- `PE`: rare. Only when the Quy chuẩn is ambiguous on a point it covers; put the question for BA in H.

Run information: `wb.finish(run_date, run_note)` writes it as a comment on the Lần N header and on H10:
```
Thời gian: dd/mm/yy - dd/mm/yy
Người thực hiện: <person> (chạy tự động bằng Claude, tài khoản <login>)
Bản build: Bản build dd/mm/yy (<env>, frontend cập nhật <Last-Modified of the site>)
```
Get the build date with `curl -sI <site>/ | grep -i last-modified`.

## The builder script (`<workspace>/build_workbook.py`)

```python
from reportkit import profile as P, workbook as W
prof = P.load(); ws = prof.workspace("1E_117")
wb = W.Workbook(prof, ws, name="Trang tổng hợp CBTT nội bộ", screen="[# 1E_117] ... - IDS > Trang chủ",
                ticket="AI-23", ascii_name="TrangTongHopCongBoThongTinNoiBo", version=2)
wb.chapter("Chức năng 1: ..."); wb.pre("1. Đăng nhập ...\n2. Menu >> ...")
wb.cat("Giao diện"); wb.sub("Giao diện chung")
wb.tc(purpose, [steps], [expected], basis="Căn cứ: ...", status="P", actual=["Đạt.", "Ví dụ: ..."],
      covers=["R3", "trap:lang_twins", "area:bo_loc"])     # requirement ids this case covers
...
wb.waive("area:xss", "Màn hình không có ô nhập chữ nào")    # a requirement with no case, and why (goes to the hand-off)
wb.finish(run_date="dd/mm/yyyy", run_note="Thời gian: ...\nNgười thực hiện: ...\nBản build: ...")
print(wb.save())          # the last printed line must be the file path (rt build reads it)
```
Always write cells through `tc()`: text starting with "=" is kept as text there.

**Coverage gate.** `save()` writes no file while a requirement has neither a case (`covers=`) nor a reason (`waive()`), or while
`covers` / `waive` names an id that does not exist (typo). Requirements: the `R<n>` rule lines of `analysis.md`, the
transactions `T<n>` (`inputs/transactions.json`, see `transactions.md`), the `[FOUND]` traps of `probe.md` (`trap:<name>`), and the checklist areas (`area:<key>`, list in `test-areas.md`; a profile can
replace it with `workbook.coverage.areas`). Each save writes `<workspace>/coverage.md`: requirement -> case ids or reason.
Run `rt build <code> --check` until it passes (it builds `<workspace>/_check.xlsx`, uses up no version), then `rt build <code>`.
An older `build_workbook.py` that calls `wb.sheet_*` or `reportkit.evidence` no longer runs: delete those calls.

## Hand-off message to the user

- One line naming the audience ("Written for: …").
- The path, and the counts per section (P / F / PE / not run) that `rt build` prints, and its coverage line.
- The group conventions you added or changed acting as BA (Qn, one line each), so the PIC can pass them to the real BA.
- The data comparison in one line: how many companies / rows / periods, how many wrong.
- The bugs, one line each with one concrete example.
- What could not be run and why; what changed since the previous version.
- Rules from `analysis.md` or FOUND traps with no case, and the half-built functions found in the code (no case written for them).
