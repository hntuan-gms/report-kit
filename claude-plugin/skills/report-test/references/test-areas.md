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
