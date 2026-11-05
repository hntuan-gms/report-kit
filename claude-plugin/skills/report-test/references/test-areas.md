# What to cover: the test case checklist for a report screen

A report screen has two functions: search (Tìm kiếm / Tra cứu) and Excel export. **The Tester judges a
test case set by how well it tests the calculated data in the result table / file.** The old 1E_127 set
had only 30% reuse because it was mostly filter widgets and API edge cases. Aim for roughly
one third Giao diện and two thirds Chức năng, with most of Chức năng being data cases.

Pick the items that exist on the screen. Each item below is one test case, unless it says otherwise.

## Giao diện chung

- The screen displays its title, fields, buttons and grid as the component defines them (`.html`), with no raw i18n key. No error toast appears on open. Check the API calls on open for 4xx.
- Position and name in the menu: the function list's menu path and the menu definition, in VI and EN. The screen must be reachable from the menu, not only by typing its URL.
- Labels and (*) marks: a field the component validates as required shows (*), and a field with (*) is validated (Quy chuẩn II.1).
- Default values and placeholders. Keep what the system does (II.2).
- One case per dropdown:
  - its values and source, `DELETE_FLG = 0`, and `IPO_COMPANY_FLG = 0` for COMPANY_PROFILES;
  - quick search when it has more than 10 values;
  - VI/EN display;
  - sort order: DISPLAY_ORDER for LOOKUP_VALUES, otherwise by the displayed text (II.5.1).
- Date fields: DD/MM/YYYY. "Ngày xuất dữ liệu" defaults to today, today is highlighted and later days are disabled (II.3).
- Collapse / expand the filter panel. Tab / Shift-Tab order. Zoom 50–200 %.
- Enter key: it only stands in for the [Tìm kiếm] button. With no search button, Enter does nothing (IV).
- Toasts: one message per event, no spelling errors. Test success, a simulated 500, and a simulated offline.
- Buttons are disabled while exporting.
- English mode (I.1):
  - the menu, report title, field labels, buttons, **dropdown values**, the export success message and the grid column headers switch language;
  - **data in the grid and the file stays Vietnamese**. Make this a separate case.

## Giao diện file Excel / Bảng kết quả

- File name. Keep whatever DEV does (IV), so this always passes unless no file is produced.
- The header block (title, company / period, export date, data years, form number): same title as the screen, and the values chosen in the filters.
- Column header row. For list reports also check column order and multi-row headers.
- Rows or indicators listed: the same as the screen offers (e.g. every indicator chosen), and every one filled from the source form.
- Cell formatting: borders, wrap, width. Grid alignment: text left, numbers right, STT and dates centred (III.2).
- Long text is shown in full.

## Chức năng: filters

- Reset (Làm mới) restores the defaults and clears the errors.
- Search inside dropdowns / textboxes: approximate, case-insensitive, accent-sensitive (II.5.3). Test lowercase, and unaccented input (which should find nothing).
- Từ–Đến pairs (II.4). If the system validates, a warning must appear and nothing is exported. If it doesn't, the result must contain no row that violates the range.
- Required fields block the search / export.
- The dropdown applies data permission (I.3). This needs a non-admin account.
- Items beyond the first page of a preloaded dropdown can still be found by search.

## Chức năng: search / export

- Success with data: the file downloads and the success toast shows.
- No data (III.3): the grid shows "Không có dữ liệu". The file still exports with all headers and an empty body, with no "Không có dữ liệu" text. For fixed-row reports, every value cell must be empty.
- A server error or being offline: an error toast, no file, and the buttons come back.
- Filter values end up in the file header (export date chosen, blank export date → today).
- Grid pagination / page size, when the report has a grid.
- The grid and the file show the same rows and values, for the same filter.

## Chức năng: data. This is the core; derive it from the rules of `analysis.txt` + Quy chuẩn I.2.

For each rule in the report's view (the WHERE conditions, joins, dedup/ROW_NUMBER, CASE, TO_CHAR), write one case:
- **Scope of source records:**
  - which forms / NEWS_TYPE_CD / report types count;
  - status: only APPROVED/CLOSE (I.2), with a case where the period has only drafts;
  - language: only VI;
  - company status (REVOKED / IPO: the report's code decides; check that the dropdown, the grid and the file apply the same scope);
  - deleted companies;
  - records with a NULL period / quarter.
- **Period assignment:**
  - each value lands in the right year / quarter / half-year column;
  - multi-year ranges don't mix;
  - records outside the range are excluded;
  - column order is independent of the order options were clicked.
- **Corrections (tin đính chính)** (I.2):
  - an approved correction replaces the original, and with N corrections the latest SUBMISSION_DATE wins. Find real chains with PARENT_ID/REF_ID and cite one concrete changed value;
  - an **unapproved** correction (draft / rejected / pending) changes nothing;
  - a correction that blanks a field makes it blank.
- **Several independent records in one period:** no duplicate rows, and the choice the code makes (latest, highest priority…). F when the choice is not deterministic (rows can swap between two runs) or duplicates appear.
- **Each output column / indicator group:** the value equals the source. Use one case per group of columns and cite the wrong cells.
- **Display rules** (III.1):
  - lookup codes are shown as names, and the name still shows when the lookup value has since been deleted;
  - an unmatched value is shown verbatim;
  - FLG 1/0 → Có/Không;
  - numbers as 1,234.56 (check the cell's number format when the file stores numbers);
  - dates as DD/MM/YYYY;
  - empty values stay empty (no "null" / "0").
- **Calculated columns** (totals, ratios, counts, rankings): recompute them from the source rows in SQL and compare. Also check the totals row.
- **The whole-report comparison:** one case that reports coverage, e.g. "118/118 companies, 1,837 cells, 1,808 match". Run it as data entries with a `matrix` over the whole scope (`rt check`).
- **Cross-check with sibling reports** that show the same fields (e.g. R017 / R035 for R018). A different scope goes into "Quy tắc nghiệp vụ" as `Lưu ý`; two screens showing different values for the same data and the same filter is an F.

## Chức năng: data permission

- The export / search API returns nothing for a company the user has no permission for (I.3.1, except the listed menus).
- This needs a non-admin account. If only an admin works, mark the case not run and cite older evidence.

## An toàn thông tin (always the last category)

A report screen takes input in three places: the filter fields, the URL and the data it renders. Defensive, read-only checks; judge what the app did, not the payload. Two sub-sections plus one Insert case:

**1. Kiểm tra XSS** (three variants each, one case per variant: plain, percent / hex encoded, nested tags)
- *Đoạn mã kịch bản nhập vào bộ lọc*: a script snippet in a text field of the filter (or a dropdown's quick-search box). Name the field as the screen labels it and confirm on the screenshot that the text went into it. Expected: shown verbatim, never run. No text input → "Không áp dụng".
- *Đoạn mã kịch bản trong đường dẫn*: the snippet in a query parameter of the screen's route, and as an invalid path segment. Expected: nothing runs; an invalid path shows a "not found" page.
- *Dữ liệu trả về chứa đoạn mã*: stub the search response in the browser (`route`, nothing stored) so a few rows carry a script / image-with-handler in a text column. Expected: plain text, nothing injected or run. No grid → "Không áp dụng"; grid unreachable (required fields) → "Không đo được", with why.

**2. Kiểm tra SQL Injection - Select**
- *Đăng nhập bằng chuỗi chèn*: login on a shared SSO owned by another team → "Chưa thực hiện", with why.
- *Chuỗi chèn trong tham số lọc và ô tìm kiếm*: in a filter field and in the request, one case each for a quote with an always-true condition, a query joining another table, a drop / list-tables query. **A destructive payload names a table that does not exist** (`'; DROP TABLE RK_SDETTEST_NO_SUCH_TABLE --`), never a real one: an injectable endpoint then answers with a "table does not exist" error, which proves the bug, and nothing on the shared environment can be lost. Expected: rejected or "không tìm thấy", no data outside the user's scope, **no DB error or query text in the response**.

**Kiểm tra SQL Injection - Insert**: a report screen usually can't add records → "Không áp dụng"; if it can, the insert is blocked or stores exactly the typed value.

How to measure:
- UI entry: a `js` step trapping `alert` / `confirm` / `prompt`, typing with `js`, the URL with `goto`, the data stub with `route`; observe the recorded dialogs, any injected `img` / `script` node, the title and final URL. An empty observation usually means a wrong selector: look at the final screenshot.
- API entry: the read-only search endpoint (handler confirmed read-only) with the string in one filter key; record the status, whether the message has a DB error or query text, and that a plain request still returns data afterwards.
- Only search / read endpoints, never an export loop, never a real login attempt; the strings never reach a write path.

Judging: **P** not run / rejected / nothing leaked. **F** it ran, the response leaked a DB error or the query (table, column names), or an invalid path reached a screen with real data; two sources as for any F. Otherwise "Không áp dụng" / "Chưa thực hiện" / "Không đo được" with the reason. Coverage matrix: one row per case family.
