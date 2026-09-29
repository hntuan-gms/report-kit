# checks.yaml: observation and comparison steps

`checks.yaml` lives in the report workspace. It describes **what to measure**, never what the right
answer is: the kit records, Claude judges. Each entry runs on its own (a fresh browser page per UI entry),
so one broken entry never spoils the others, and you re-run only what broke with `rt check <code> --redo`
or `--only <ids>`.

```yaml
system: ids                          # a system key from .report-kit/project.yaml
vars: {company_id: 1234}             # optional extra variables
data: [...]                          # data entries
ui: [...]                            # UI entries
```

## Template variables

Never hard-code the run date. Use these instead:
- `{today}` (DD/MM/YYYY; `{today:%Y-%m-%d}` for another format);
- `{current_year}`, `{current_year-1}` (arithmetic works on any number);
- `{current_month}`, `{prev_month}`, `{prev_month_year}`;
- `{login_user}`: the account of the run, for data-permission SQL;
- any key of `vars` or of the entry's `matrix`.

Unknown `{names}` are left as they are.

## Data entry: the app's rows vs independent SQL

```yaml
- id: D01
  title: Số lượng tin theo tháng (biểu đồ 2)
  matrix: {year: ["{current_year}", "{current_year-1}"]}          # one comparison per value; cover the whole scope
  actual:
    api: {method: GET, path: /masterdata/dashboard/cbtt/monthly-summary, params: {year: "{year}"}, rows: data.data}
    key: [thang]                                                  # identifies a row
    fields: {DK: slDinhKy, BT: slBatThuong, KH: slTinKhac}        # logical name -> field in the app's row
  expected:                                                       # written from the SRS + standard, NOT from the app's SQL
    sql: |
      SELECT EXTRACT(MONTH FROM cd.SUBMISSION_DATE) M,
             COUNT(CASE WHEN cd.NEWS_TYPE_CD IN ('DINH_KY','BAO_CAO') THEN 1 END) DK,
             COUNT(CASE WHEN cd.NEWS_TYPE_CD = 'BAT_THUONG' THEN 1 END) BT,
             COUNT(CASE WHEN cd.NEWS_TYPE_CD IN ('GD_CDL','GD_NNB_NLQ','GD_CDSL','BCKQ_CBPH','TB_CBPH','THEO_YEU_CAU','TIN_TU_SSC') THEN 1 END) KH
      FROM COMPANY_DATA cd JOIN COMPANY_PROFILES cp ON cp.ID = cd.COMPANY_PROFILE_ID
      WHERE cp.IPO_COMPANY_FLG = 0 AND cp.DELETE_FLG = 0 AND cp.STATUS_IDS_CD = 'APPROVED_PUBLIC'
        AND cp.ID IN (SELECT COMPANY_PROFILE_ID FROM LOGIN_PERMISSION_BY_CODE WHERE LOGIN_NAME = :login)
        AND cd.NEWS_STATUS_CD IN ('APPROVED','CLOSE') AND cd.LANGUAGE_CD = 'VI'
        AND cd.SUBMISSION_DATE >= TO_DATE(:y || '-01-01','YYYY-MM-DD') AND cd.SUBMISSION_DATE < TO_DATE((:y + 1) || '-01-01','YYYY-MM-DD')
      GROUP BY EXTRACT(MONTH FROM cd.SUBMISSION_DATE)
    binds: {y: "{year}", login: "{login_user}"}
    key: [M]
    fields: {DK: DK, BT: BT, KH: KH}
    missing_as: 0                        # months with no rows are expected to show 0
  variants:                              # alternative rules - each differing cell is attributed to the one it equals
    no_language_filter: {sql: "<same SQL without LANGUAGE_CD = 'VI'>"}
    cut_at_dec31_midnight: {sql: "<same SQL with the app's upper bound TO_DATE(:y||'-12-31')>"}
  compare: {numeric: true, tolerance: 0}
  require: {actual_rows: {min: 1}}       # otherwise NM (e.g. the API answered but returned nothing)
```

**Actual from an exported Excel file**: replace `api` with `export`:

```yaml
  actual:
    export: {method: POST, path: /report/R018_BAO_CAO_QUAN_TRI/export, body: {filters: {companyId: "{company_id}", periods: ["2"]}},
             parse: grid, header_rows: 2, key_col: 1, first_value_col: 3, header_marker: STT}
    # parse: records -> one row per data line keyed on `key` columns (list reports)
    # parse: grid    -> key = (row key, column header) (fixed-row pivot reports); `fields` optional
    key: [STT]
    fields: {ten: "Tên công ty", ma: "Mã chứng khoán"}
```

The kit reads the file **as Excel displays it**: number and date formats are applied, so 2.0 with `#,##0` compares as "2".

Rules for the expected SQL:
- It is written from the SRS + standard, e.g. status APPROVED/CLOSE, language VI, the latest correction, the company scope and data permission the SRS gives.
- **Cover the full scope with `matrix`**: every value the filter or dropdown offers, not a sample, and state the coverage in the workbook.
  - A range is written as one string: `matrix: {year: "{current_year}..2016"}` gives 2026, 2025, …, 2016 (in the order written). Lists can mix ranges and single values: `["2016..2019", "{current_year}"]`.
  - `require: {actual_rows: {min: 1}}` turns a value with no data into NM for the whole entry. Put the values with no data in their own entry without `require`: when the app and your SQL both return nothing, it shows as MATCH (0 cells), which is the evidence for "Không có dữ liệu".
  - Rows that exist only in your SQL (e.g. a record dated in the future, outside the months the screen shows) appear as "missing rows". Trace them with `rt sql` before calling them an app bug.
- Add a variant for every rule you suspect the app gets wrong. `summary.md` then says, for each differing cell, which rule explains it.
- A cell no variant explains is "unexplained": trace it with `rt sql` before writing anything.

## UI entry: steps + observations

```yaml
- id: U04
  title: Tooltip + click trên biểu đồ xếp hạng
  page: /dashboard
  ready: {selector: "apx-chart svg", min: 4, timeout: 20000}    # NM if the charts never render
  steps:
    - hover: {selector: ".apexcharts-pie-area", nth: 0}
    - observe: {tip_a: {text: ".apexcharts-tooltip.apexcharts-active"}}
    - expect_download: {click: {selector: ".apexcharts-pie-area", nth: 0, force: true}, timeout: 6000, as: dl}
  observe:
    legend: {texts: ".apexcharts-legend-text"}
    calls: requests
  require: {tip_a: {regex: "^Hạng A"}}    # NM if the tooltip read belongs to another slice
```

Every UI entry starts in a fresh browser context with the saved login, and a final screenshot is taken automatically.

**Steps:**
- mouse and keyboard: `hover`, `click`, `select` (`label` / `value`, `nth`), `fill`, `press`, `tab: N` (records `focus_order`);
- waiting and navigation: `wait` (ms), `wait_for`, `goto`, `reload`;
- page state: `set_lang: en|vi`, `zoom: 150`, `offline: true`, `route` (stub one request; also allowed at entry level as `routes:`);
- evidence: `expect_download` (records `{downloaded, name}`), `screenshot: name`, `observe`;
- `js` (last resort).

**Observations:**
- page content: `text` (first match), `texts` (all), `count`, `attr {selector, name}`, `value`, `js: "() => ..."`;
- recorded activity: `requests` (API calls made during the entry: method, path, status), `toasts`, `url`.

**Preconditions** (`ready`, `require`) only decide whether the measurement is usable. They never decide whether the app is right. Use them wherever a wrong measurement could look like an app bug, for example:
- charts not rendered yet;
- the tooltip read from the wrong element;
- a route left over from another step. This can't happen here: each entry has its own context.

**Writing selectors**: open the screen's template (`.html`) before writing a selector. After the first run, look at the final screenshot of every entry whose observation is empty or surprising: an empty result usually means the selector is wrong, not the app.

## Statuses in summary.md

| Status | Meaning | What you do |
|---|---|---|
| MATCH | all compared cells equal the expectation | judge (usually P, if the expectation's basis is firm) |
| DIFF | cells differ; each lists the variant that explains it | trace causes, judge (F with a firm basis, else PE) |
| OBS | UI observed | read observations / screenshots, judge against SRS / standard |
| NM | not measurable (precondition failed) | fix the entry, `rt check <code> --redo` |
| ERR | the entry itself failed (selector, HTTP, SQL) | fix the entry, `rt check <code> --redo` |
