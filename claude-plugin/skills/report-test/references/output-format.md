# Output format: the test case workbook

One `.xlsx` per report, built with `reportkit.workbook.Workbook` from the template named in the profile (`workbook.template`, KBKT by default).
There is no reference workbook to copy wording from: follow the rules on this page.

## Level of detail to aim for

- **Data comparison:** state the scope and the result in numbers, e.g. "118 công ty, 1.837 ô có dữ liệu, 29 ô sai, 9 ô chưa rõ quy tắc". Every wrong cell is traced to the source record that causes it.
- **Each data rule has one real example** from the environment: a correction chain with the value it changes, a draft on top of an approved record, a NULL period, a deleted or out-of-scope record, duplicates. Name it (company, period, ID, value).
- **Each bug states:** the mechanism in one sentence (what the code does wrong), how many cells or rows it hits, and one concrete example. "The dedup takes the latest row with no status filter, so drafts override approved values (27 ô; ANV 2022: 18 → 23)."
- **The SRS-vs-code sheet lists every point**, including the ones that are not bugs: indicators missing from the SRS, source forms not specified, rules one report applies and a sibling report doesn't, rules nobody wrote down.

## File name and version

`AI-<jira-or-ticket>_<code without #>_<TenKhongDau>_v<N>.xlsx`, e.g. `AI-60_2E50_BaoCaoTongHopDanhSachCongTyKiemToan_v1.xlsx`.
- Ask for the AI-xx ticket number if you don't know it.
- Never overwrite a file that was sent for review. Create `v<N+1>`, because the reviewer's comments live in the old one.

## Sheet 1: test cases (template layout, sheet named `<code> <short name>`)

Header cells:
- D2 = `[# code] name (REPORT_CODE) - <subsystem> > menu path`
- D3 = the code. The formula in column A turns it into `1E_128_1`, `1E_128_2`, …
- D4–D8 = counters. They count from column **E (Lần 1)**, never from H.

Block structure (the template's colours come from `reportkit.workbook`):
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
- Do **not** include "Validate các trường" (per-field input validation). The team calls it "test dữ liệu đầu vào" and it is out of scope.
- **Always include "An toàn thông tin"**, as the last category: XSS and SQL Injection across the filter fields, the URL and the rendered data. `test-areas.md`, "An toàn thông tin", has the full list of cases, how to measure them and how to judge them. A case that does not fit the screen (no delete, no insert, login on a shared SSO) stays in the block with the reason in H.

Columns:

| Col | Content | Rule |
|---|---|---|
| B | Mục đích kiểm thử | "Kiểm tra …" in plain words, specific ("Kiểm tra số kiểm toán viên 'Hiện tại' không bị âm") |
| C | Các bước thực hiện | Numbered **screen actions** with the concrete data used ("1. Chọn Từ năm = 2026, Tên công ty = Công ty TNHH KPMG 2. Nhấn [Tìm kiếm] 3. Xem nhóm …"). No API paths |
| D | Kết quả mong muốn | What must happen, in business terms, stated independently of what the system does |
| E/F/G | Lần 1/2/3 | `P` / `F` / `PE` only, with green / red / yellow fill. Empty = not run |
| H | Kết quả hiện tại | Starts with `Đạt.` (P) / `Sai.` (F) / `Cần BA xác nhận.` (PE) / `Chưa thực hiện - <lý do>` (not run). Then **what was seen on the screen or in the file**, one concrete example (company name, year, value), and for F / PE the cause in business words. No `file:line`, table / column names, record IDs or run ids here |
| I | Mã lỗi | Bug id from sheet "Danh sách lỗi" |
| J | Ghi chú | Line 1: the **basis**: `Căn cứ: SRS …`, `Căn cứ: Quy chuẩn chung mục II.3`, `Căn cứ: code (SRS và Quy chuẩn chung không quy định) - cần BA xác nhận (BA làm rõ N)`. Line 2 `Kỹ thuật: …`: the evidence for DEV / BA: `file:line`, table.column, record IDs, SQL counts, run ids (U05, D04) |

### Writing style (test case sheet)

The test case sheet is read by Testers and BAs, not only by DEV. Write it so a reader who has never opened the code understands every row.
- Short Vietnamese sentences, one idea each. Name things the way the screen names them (the column title, the button label, the company name), not by table / column / variable names.
- No internal shorthand in B, C, D, H: no `NaN`, `MATCH`, `NM`, `view`, `dedup`, `RN = 1`, `CTE`, `API`, `request`. When a technical term is unavoidable, explain it once in plain words.
- Technical detail is never lost: it moves from H to the `Kỹ thuật:` line of J, or to the sheets "So sánh SRS - Code" / "Danh sách lỗi" / "Chi tiết sai lệch dữ liệu", which keep the full technical wording for DEV.
- Numbers use the Vietnamese format in prose (1.837 ô, 6.136 lượt); values copied from the screen stay as shown.

Example (F):

| Cột | Text |
|---|---|
| B | Kiểm tra số kiểm toán viên "Hiện tại / Cuối kỳ" không bị âm |
| C | 1. Chọn Từ năm = Đến năm = 2026, Tên công ty = Công ty TNHH KPMG<br>2. Nhấn [Tìm kiếm]<br>3. Xem nhóm "Thông tin tăng/giảm KTV", cột BTC và UBCK |
| D | Hiện tại = Đầu kỳ + Tăng − Giảm. Đây là số người nên không bao giờ âm |
| H | Sai. KPMG năm 2026 hiện Đầu kỳ 0, Tăng 0, Giảm 40, Hiện tại −40 (cả BTC và UBCK). Cũng bị âm: AISC (−29 / −23). Nguyên nhân: 40 kiểm toán viên nghỉ được trừ ở cột Giảm nhưng chưa từng được cộng vào Đầu kỳ, vì quyết định chấp thuận của họ không ghi ngày ban hành. |
| J | Căn cứ: SRS AG6.<br>Kỹ thuật: view so sánh APPROVAL_ISSUE_DATE = MIN(…), bản ghi ngày ban hành NULL bị loại (R104_v_rpt_tong_hop_ctkt.sql:272-294); API trả btcAudHienTai = −40 (D04, U14). |

Example (PE), column H: "Cần BA xác nhận. Hệ thống có hiện ngày, ví dụ PKF Việt Nam bị thu hồi ngày 11/07/2026. Nhưng SRS yêu cầu lấy ngày từ một trường khác, và trường đó đang trống ở mọi bản ghi. Nếu làm đúng SRS thì hai cột này luôn trống."

Status meaning:
- `P`: matches the expected result.
- `F`: doesn't match, and the expected result has a firm basis (SRS or Quy chuẩn).
- `PE`: the behaviour was observed but the expected result is not settled. Use it when the only basis is the code, or the SRS is vague. Link the case to a question in "BA làm rõ".

Run information: fill in the template's comment on the Lần N header (E11) and on H10:
```
Thời gian: dd/mm/yy - dd/mm/yy
Người thực hiện: <person> (chạy tự động bằng Claude, tài khoản <login>)
Bản build: Bản build dd/mm/yy (<env>, frontend cập nhật <Last-Modified of the site>)
```
Get the build date with `curl -sI <site>/ | grep -i last-modified`.

## Companion sheets (same order)

1. **So sánh SRS - Code**: the required review sheet. Columns are `reportkit.workbook.SVC_HEADERS`. One row per point:
   - SRS text → code behaviour (`file:line`) → what the dev environment showed → type (see list below) → severity → proposed SRS change → proposed DEV change → the Quy chuẩn chung ruling → status after the Quy chuẩn → 3 empty review columns (BA xác nhận, DEV xác nhận, Kết luận).
   - Types: Xung đột SRS-Code / Code có - SRS thiếu / SRS có - Code thiếu / SRS mơ hồ / SRS tự mâu thuẫn / Khác.
   - Status wording: "Đã chốt: hệ thống đang đúng", "Đã chốt - DEV phải sửa (BUG-xx)", "Còn mở", "Còn mở - SRS … phải ghi rõ".
   - The note in row 2 names every source used, including the repo commit and the dev run dates.
2. **Danh sách lỗi**: `BUG-nn`, severity, status, description, basis, cause in code, evidence (date + concrete values).
   - Statuses: Mới / Mở / Mở (chưa kiểm lại được) / Đã đóng / Rút lại theo Quy chuẩn …
   - Keep withdrawn and closed bugs listed, with the reason, so reviewers can trace them.
3. **Chi tiết sai lệch dữ liệu**: every wrong cell from the data comparison. Give the key, column, field, value shown, expected value, cause (which submission / rule) and bug id. The note states the expected-value rule and what was excluded.
4. **BA làm rõ**: topic, question, severity, status (`Đã chốt` / `Còn mở` / `Chốt một phần`), answer. When the Quy chuẩn settles a question, keep it and fill in the answer with the section number.
5. **Nguồn dữ liệu**: one row per output row or column. Give where it comes from (table.column / form field code / FIELD_ID / data type / lookup group) and its mapping to the SRS item. Mark "Không có trong SRS" where it applies.
6. **Ma trận bao phủ**: the answer to "is the set complete?". Built with `wb.sheet_coverage(rows, title)`, one row per requirement:
   - Sources, in this order: every SRS cell that states a rule; every standard section that applies (and one row for the sections that don't, with why); every data / display rule of the code (`file:line`); every FOUND trap of `probe.md`; every applicable item of `references/test-areas.md`; the sibling difference (e.g. "Tài khoản CTĐC") when the brief lists siblings.
   - Each row is `(source, item, requirement, case_keys, note)`. `case_keys` are the beginnings of the cases' "Mục đích"; the kit fills in the case ids (as column A shows them) and the P / F / PE tally, and raises an error when a key matches no case.
   - A row with no case must have a note starting `Không áp dụng: <why>` or `Chưa phủ: <why>`.
   - For a trap, put its id in "Mục" as `probe.md` prints it; when the same trap is FOUND on several tables, add the table: `soft_deleted (FORMS)`.
   - `rt build` fails when the sheet is missing, a row has no case and no reason, or a FOUND trap is in no row. It also lists cases that no requirement points to (information only).

## Hand-off message to the user

- Start with one line naming the audience ("Written for: …").
- Give the path.
- Give counts per section (P/F/PE/not run). `rt build <code>` (or `rt tally <file>`) prints them and flags rows whose H is empty or only a status, and F rows without a bug id.
- Give the data comparison coverage: cases exported, filled cells compared, number wrong.
- Give the requirement coverage from "Ma trận bao phủ": rows with cases, rows not applicable, rows not covered and why.
- List the main bugs, each with one concrete example.
- Say what could not be run and why.
- Say what changed compared with the previous version.

## The builder script (`<workspace>/build_workbook.py`)

```python
from reportkit import profile as P, workbook as W
prof = P.load(); ws = prof.workspace("1E_117")
wb = W.Workbook(prof, ws, name="Trang tổng hợp CBTT nội bộ", screen="[# 1E_117] ... - IDS > Trang chủ",
                ticket="AI-23", ascii_name="TrangTongHopCongBoThongTinNoiBo", version=2)
wb.chapter("Chức năng 1: ..."); wb.pre("1. Đăng nhập ...
2. Menu >> ...")
wb.cat("Giao diện"); wb.sub("Giao diện chung")
wb.tc(purpose, steps, expected, basis="Căn cứ: ...", status="P", actual="concrete values seen", bug=None)
...
wb.finish(run_date="dd/mm/yyyy", run_note="Thời gian: ...
Người thực hiện: ...
Bản build: ...")
wb.sheet_svc(svc_rows, title, note); wb.sheet_bugs(bug_rows, title)
wb.sheet_details(W.details_from_run(ws.latest_run()) + extra_rows, title, note)
wb.sheet_ba(ba_rows, title); wb.sheet_sources(rows, title, headers, widths)
wb.sheet_coverage([
    ("SRS sheet 2", "C49-C51", "Định kỳ / Bất thường / Tin khác theo tháng", ["Kiểm tra toàn bộ số lượng tin"], ""),
    ("Bẫy dữ liệu (rt probe)", "soft_deleted (FORMS)", "Biểu mẫu đã xoá", ["Kiểm tra tin thuộc biểu mẫu đã xoá"], ""),
    ("Quy chuẩn chung", "II.3, II.4", "Ngày xuất dữ liệu, Từ-Đến", [], "Không áp dụng: màn hình không có trường ngày"),
], "Ma trận bao phủ: [# 1E_117] ...")
print(wb.save())          # the last printed line must be the file path (rt build reads it)
```
Always write cells through `tc()` / `table()`: text starting with "=" is kept as text there.
