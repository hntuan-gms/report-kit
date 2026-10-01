# What to cover: the test case checklist for a report screen

A report screen has two functions: search (Tìm kiếm / Tra cứu) and Excel export. **The Tester judges a
test case set by how well it tests the calculated data in the result table / file.** The old 1E_127 set
had only 30% reuse because it was mostly filter widgets and API edge cases. Aim for roughly
one third Giao diện and two thirds Chức năng, with most of Chức năng being data cases.

Pick the items that exist on the screen. Each item below is one test case, unless it says otherwise.

## Giao diện chung

- The screen displays the right title, fields, buttons and grid (or "no grid" when the SRS says "Không hiển thị màn hình danh sách"). No error toast appears on open. Check the API calls on open for 4xx.
- Position in the menu. Compare with the SRS screenshot.
- Labels and (*) marks. IDS: follow the current system (Quy chuẩn II.1). Audit: follow the report's SRS.
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
- The header block (title, company / period, export date, data years, form number) compared with the SRS.
- Column header row. For list reports also check column order and multi-row headers.
- Rows or indicators listed compared with the SRS, and compared with the source form.
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

## Chức năng: data. This is the core; derive it from the view + Quy chuẩn I.2.

For each rule in the report's view (the WHERE conditions, joins, dedup/ROW_NUMBER, CASE, TO_CHAR), write one case:
- **Scope of source records:**
  - which forms / NEWS_TYPE_CD / report types count;
  - status: only APPROVED/CLOSE (I.2), with a case where the period has only drafts;
  - language: only VI;
  - company status (REVOKED / IPO: the report's SRS decides);
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
- **Several independent records in one period:** no duplicate rows, and a defined choice. If there is no rule, it becomes a BA question.
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
- **Cross-check with sibling reports** that show the same fields (e.g. R017 / R035 for R018). Differences go into the SRS-vs-code sheet.

## Chức năng: data permission

- The export / search API returns nothing for a company the user has no permission for (I.3.1, except the listed menus).
- This needs a non-admin account. If only an admin works, mark the case not run and cite older evidence.

## An toàn thông tin (always the last category)

A report screen takes input in three places — the filter fields, the URL, and the data it renders — so cover XSS and
SQL Injection across those. Write the cases in two sub-sections plus one Insert case. Judge each against what the app
did, not the payload. This is defensive, read-only checking; keep to the safety rules below.

**1. Kiểm tra XSS**
- *Đoạn mã kịch bản nhập vào bộ lọc.* Type a script snippet into a text field of the filter; if the screen has no
  saved text field, use the quick-search box of a dropdown. Expected: shown verbatim, never executed. Three variants —
  plain, percent/hex-encoded, and several tags nested — as one case each. Name the field as the screen labels it, and
  confirm on the screenshot which field the text actually went into. A screen with no text input (e.g. a dashboard with
  only a year list) → "Không áp dụng".
- *Đoạn mã kịch bản trong đường dẫn.* Put the snippet (a) in a query parameter of the screen's own route and (b) as an
  invalid path segment. Expected: nothing runs; an invalid path shows a "not found" page. Same three variants.
- *Dữ liệu trả về chứa đoạn mã.* Stub the search response (in the browser, nothing stored) so a few rows carry a script
  snippet or an image-with-handler in a text column, run the search, read the grid. Expected: shown as plain text, no
  element injected, nothing runs. No grid on the screen → "Không áp dụng"; can't reach the grid (required fields) →
  "Không đo được", say why.

**2. Kiểm tra SQL Injection - Select**
- *Đăng nhập bằng chuỗi chèn.* If login is a shared SSO owned by another team, don't test it from here → "Chưa thực
  hiện", say why.
- *Chuỗi chèn trong tham số lọc và ô tìm kiếm.* Send, in a filter field and in the request, strings that carry SQL
  control syntax: a lone quote with an always-true condition, a query that joins another table, a query that drops a
  table, a query that lists tables. Expected: rejected or "không tìm thấy", no data outside the user's scope, and **no
  database error or query text in the response**. Do the "or always-true", the "join", and the "drop/list" as separate
  cases.

**Kiểm tra SQL Injection - Insert.** A report screen usually can't add records → "Không áp dụng". If it can, the insert
must be blocked or store exactly the typed value.

### How to measure (kit steps, repo-agnostic)
- **UI entry:** set a trap for dialogs with a `js` step (record `alert`/`confirm`/`prompt`), type into the field with a
  `js` step, try the URL with `goto`, stub the data with `route`; observe the recorded dialogs, any injected
  `img`/`script` node, the page title and final URL. An empty observation usually means a wrong selector — look at the
  final screenshot.
- **API/data entry:** call the read-only search endpoint (handler already confirmed read-only) with the injection
  string in one filter key; record the status, whether the message contains a database error or the query text, and
  that a plain valid request still returns data afterwards.

### Safety (same as the rest of the run)
- Read-only: only the search / read endpoints, never export in a loop, never a real login attempt, nothing written.
- The URL and stub cases run in the browser; the injection strings never reach a write path.

### Judging
- **P:** not executed / rejected / nothing leaked.
- **F:** it executed, or the response leaked a DB error or the query (table and column names), or an invalid path led
  to a screen with real data instead of a "not found" page. An F needs two sources (observation + screenshot/response).
- **Không áp dụng / Chưa thực hiện / Không đo được:** state the reason (no such function, shared SSO, blocked by
  required fields).
- Coverage matrix: one row per case family above.
