---
name: report-test
description: Write and run the test case workbook for one report / Tra cứu / Thống kê / dashboard screen, end to end, from its code (e.g. 1E_117, 2E_50). Use when asked to test a report code, run its test cases on the deployed environment, or process a Tester's commented workbook. The `rt` tool finds the screen's code from the function list's menu path, observes the screen and compares the data with independent SQL; Claude reads the code, judges every result against the project standard (Quy chuẩn chung) and the system's own rules, and the workbook is produced in the project's template.
argument-hint: <report code> [e.g. 1E_117]
---

# /report-test <code>: one report, from inputs to workbook

Arguments: `$ARGUMENTS` (the report code; anything else is a note from the user).

**How the work is split:**
- `rt` (the reportkit CLI) does the mechanical work: find the function row, trace the code from the menu, log in, probe data, run the observation and comparison steps, build the workbook.
- **Claude does the judging.** The kit never decides P / F. Claude reads what the screen showed and what the data comparison found, and judges it with the rules below, on every run.

The project profile is `.report-kit/` in the repo. Its `rules/` folder holds the project standard summary, environment notes, lessons and data traps.

## What a verdict is based on

No SRS is read. The deployed system and its code describe what the function does; the workbook checks that it does it correctly and consistently. In this order:

1. **Quy chuẩn chung** (the project standard: the original document if found, otherwise `.report-kit/rules/standard.md`). It overrides the code on everything it covers.
2. **The system contradicting itself**: grid vs Excel file for the same filter, screen vs API, a column label vs the data in it, VI vs EN, totals vs details, page 1 vs page 2, a field the code validates as required but shows without (*), a filter the screen sends but the server ignores.
3. **Plain correctness that holds for any business rule.** Claude may judge these on its own: a count can't be negative, shares add up to 100 %, "Đến ngày" includes the whole last day, no duplicate rows from a join or a language twin, a dropdown lists every value it says it lists, a code is shown as its name, nothing is silently truncated, an i18n key is never shown raw.
4. **Runtime errors**: 4xx / 5xx, error toasts, crashes, exports that never finish.
5. **An toàn thông tin** (the KBKT_Template block): XSS, SQL Injection.
6. **Everything else follows the code.** Which statuses, which companies, which period, which report type wins, column names, messages: what the code implements is the rule. The case is P when the screen does what the code says.

Verdicts:
- **P**: the behaviour matches 1-6.
- **F**: it breaks 1, 2, 3, 4 or 5. An F needs **two independent sources**: the observation plus a screenshot, the code or the API response.
- **PE**: only when the Quy chuẩn itself is ambiguous on a point it covers. "The business might want something else" is never a PE: the code is the rule.
- **No case** for a function the code does not implement (no field, no column, no button): there is nothing to run. A half-built function (a service method nobody calls, labels with no field) gets no case either; tell the user about it in the hand-off message, not in the workbook.

## Ground rules (non-negotiable)

- **Safety.** Follow the project's DB / test-data rules (loaded from the repo's CLAUDE.md).
  - The DB is read with SELECT only, through `rt sql` or the checks. The kit refuses anything else.
  - Never create or change data on the shared environment. DEV / BA prepare test data.
  - Only call endpoints whose handler you have read and found to be read-only. Classify by what the handler does, not by the HTTP verb.
- **Workbook wording.** The workbook states each verdict and its basis, nothing about how the test set was put together:
  - never cite an SRS (no `Căn cứ: SRS …`): none was read;
  - never write that the SRS is outdated, was not used, or that the code is the reference;
  - the basis line uses the wording in `references/output-format.md` ("Căn cứ").
- **Independent expectations.** Expected data comes from SQL you write from the rule stated in plain words (`analysis.md`) and the Quy chuẩn, never by copying the report's own query or view. That is how a wrong join, a midnight upper bound or a missing status filter shows up.
- **Credentials** live only in `~/.report-kit/secrets.yaml` (or `RK_*` env vars). Never write them in the repo, the workbook or chat.
- **Save tokens.**
  - Read `brief.md`, `probe.md` and `runs/<id>/summary.md`, not the raw JSON.
  - Open a screenshot when a verdict depends on it.
  - Open only the code files the trace points to, then follow references from there.

## The run

Do the steps in order and don't skip one. Each step leaves files in the workspace (`~/report-kit-work/<profile>/<code>/`), so if a session stops, run `rt status <code>` and continue from there.

1. **Check the machine: `rt doctor`.**
   - If the `rt` command is not found, the plugin was installed without the Python package. Tell the user to install it once per machine and stop: `git clone <report-kit repo>`, then `pip install -e <clone folder>` and `python -m playwright install chromium`.
   - Fix any FAIL line before going on (packages, browser, profile, secrets, network).
   - If secrets are missing, tell the user which keys to add to `~/.report-kit/secrets.yaml`, and never ask for them in chat.

2. **Gather the inputs: `rt start <code>`.** Then read the printed `brief.md`. It gives:
   - the function row (name, Jira key, ticket, system, menu path, status) and the **function list notes** (BA / Tester notes, "Có thể thay thế bằng");
   - the standard document (or the profile's summary);
   - previous workbooks with the number of reviewer comments;
   - **sibling reports**, when another report uses the same screen or the same main code files;
   - the **code trace**: menu entry → route → screen component → services and the URLs they call → the report code (e.g. R017) → backend files ranked by the screen's fingerprints (handler, entity, repository, view SQL), the views behind them and the Excel templates.

   **If the trace says "found by: name only"**, the menu path is missing or matches no menu entry. Find the screen's route (menu definition, routes file, or ask the user) and run `rt start <code> --route /the/route`.

   **If a note says the function was dropped or replaced** (e.g. "Nghiệp vụ confirm bỏ chức năng này"), say so in step 4 and ask whether to test it.

   **If `brief.md` lists sibling reports**, this is probably the same screen seen by another kind of user or with another filter (1E_117 internal / 1E_118 public company: one `/dashboard`).
   - Find what differs before writing any case: the account type, the data scope, the filter. The workbook is about that difference.
   - Shared behaviour: cite the sibling's case ("xem 1E_117_12") instead of copying it, unless you re-run it with what makes this report different.
   - If the difference needs an account or data you don't have, say so in step 4, not after the workbook is built. A workbook whose own cases are all "Chưa thực hiện" tests nothing new.

   Then read, in this order:
   - the standard. **It overrides the code** on what it covers;
   - `.report-kit/rules/environment.md` and `.report-kit/rules/lessons.md`;
   - the previous workbook dump, if any: every `##### COMMENT` is reviewer feedback to handle.

3. **Read the code: it is the specification.** Start from the trace and follow the chain:
   screen component (`.html`: fields, columns, buttons, labels; `.ts`: defaults, validation, what is sent) → service call → controller → handler / service / repository → SQL / view → Excel template or JSON shape.
   - Note every data rule (WHERE, JOIN, dedup, CASE, date bounds, status and language filters, permission join) and every display rule (labels, number formats, i18n), each with `file:line`.
   - Write `<workspace>/analysis.md`, the function as built:
     - the screen: every field (type, default, required, values and where they come from), button, grid column, file column;
     - the rules, one line each, **in plain words** ("chỉ lấy tin đã duyệt, tiếng Việt; bản đính chính mới nhất thay bản gốc") with `file:line`;
     - for each rule, the Quy chuẩn section it falls under, and whether it already looks wrong by 1-4 above;
     - functions that are half built (code present but not wired), for the hand-off message.
   - For a large report, delegate the tracing to an Explore agent and keep only its conclusions.

4. **Ask the user once**, in a single question, before touching the environment:
   - which account to use: a super admin can't reproduce data-permission cases. With a sibling report, ask for the account type that makes this one different (e.g. a public-company login);
   - OK to run read-only SELECTs this session?
   - is another team demoing or doing UAT on the environment?
   - anything from step 2 that needs a decision (a dropped function, an unknown ticket number).

   Do not continue without the answers.

5. **Log in: `rt login --system <system>`.** Note the login name and the super-admin flag for the workbook.

6. **Probe the data: `rt probe <code>`.** It runs the profile's data traps on the tables the report reads (from the trace), and writes real examples to `probe.md`: language twins, orphans, deleted / out-of-scope companies, correction chains, year-end timestamps, NULL periods, duplicates.
   - A trap marked FOUND needs a case.
   - A rule with no example on the environment becomes "Chưa thực hiện - cần dữ liệu".
   - Use `rt sql "<SELECT>"` for any other lookup (read-only, row limit).

7. **Write `<workspace>/checks.yaml` and run it: `rt check <code>`.** See `references/checks-guide.md` for the format and examples.
   - **Data entries:**
     - the app's rows (JSON API or exported Excel) against SQL you wrote from the rules of `analysis.md` + the standard;
     - add `variants` (the view's own condition, the standard with one condition dropped) so every differing cell is attributed to a cause;
     - use a `matrix` to cover the full scope, not a sample: **every value the filter or dropdown offers** (all years, all periods, all exchanges). Ranges are written `year: "{current_year}..2016"`;
     - values with no data belong in the scope too: put them in a separate entry without `require: actual_rows`, so "empty on both sides" shows as MATCH instead of NM.
   - **UI entries:**
     - steps and observations for what the cases need: titles, labels, dropdown values, tooltips, requests fired, toasts, downloads, zoom, Tab order, English mode, a simulated 500;
     - add `ready` / `require` preconditions so a bad measurement shows as NM instead of misleading you;
     - name the areas a bug picture would need (`boxes: {filters: …, grid: …}`): their positions are recorded with the final screenshot, so step 9 can crop it without a new capture.
   - Read `runs/<id>/summary.md`:
     - **NM / ERR** means the measurement failed, not the app. Fix the entry and re-run only those with `rt check <code> --redo` (or `--only U03,U05`);
     - **DIFF**: trace each differing cell back to the source row with `rt sql`, and cite one concrete example (ID, value, date) per cause;
     - **OBS**: read the observations, and the screenshots where the verdict depends on the picture.

8. **Judge** every case with "What a verdict is based on" above.
   - **Not run**: say why ("Chưa thực hiện - cần tài khoản không phải admin", "- cần dữ liệu", "- không đo được: …").
   - A point the standard settles cites its section.
   - A difference between the data and your expectation that the code explains on purpose (a status, a scope, a priority) is not a bug: correct the expectation to the code's rule, unless the Quy chuẩn or 2-4 says otherwise.

9. **Evidence of every bug, at the lowest cost** (`references/output-format.md`, "Hình ảnh lỗi"). Every bug that is not withdrawn or closed gets a picture card in "Hình ảnh lỗi"; the layout comes from `reportkit.evidence`, no sample workbook is needed. Spend as little as possible:
   - **Reuse step 7 first.** Its pictures are from today's build. For a screen bug that an entry already observed, use `E.run_shot(run, "U07", caption, mark=[obs name], show=[area])`: the kit crops and outlines from the positions recorded during `rt check`. **Don't open a screenshot to find coordinates.** For a data / format bug, use the Excel already downloaded in step 7 (`shots/<id>_<file>`) with `E.excel`, and the source rows you already fetched with `rt sql` while tracing the cause, with `E.table`.
   - **Capture only what step 7 did not show** (a dropdown that must be open, a hover, another account, an element no entry observed). Add those entries with `screenshot: {name, selector, highlight}` and run them **all in one** `rt check <code> --only …`. A bug common to every screen (wrong-URL page, future date allowed) is one small entry.
   - **Write only what the bug list doesn't have.** Leave `title`, `severity`, `status`, `basis`, `cause` empty: they come from the bug's row of "Danh sách lỗi", and the status becomes "Mở - còn lỗi <date of the picture>". Write the steps, actual, expected, panels, note. Put the shared `account` / `env` / `build` / `screen` in one dict and pass it to every card.
   - **Look only where the kit warns.** `rt build` prints one line per card (`evidence BUG-03: 1360x1420 px, 3 panels, OK` or the warnings: nothing marked, marked cell hidden, picture not from today, card too long). Open the first card of the run, to check the layout, and the cards with warnings. Fix them, then rebuild.
   - The card's date is the picture's. An older picture is evidence of its own build only: the status must say "chưa kiểm lại" (the lint checks it).
   - A bug no picture can show goes to `no_image` with the reason.

10. **Write the workbook: `<workspace>/build_workbook.py`, then `rt build <code>`.** See `references/output-format.md`.
   - The script uses `reportkit.workbook.Workbook` (the project's template). `wb.sheet_rules(...)` writes "Quy tắc nghiệp vụ" from `analysis.md`; `workbook.details_from_run(run_dir)` gives the "Chi tiết sai lệch dữ liệu" rows; `wb.sheet_evidence(cards, title, note, no_image)` builds "Hình ảnh lỗi" and links it with "Danh sách lỗi".
   - **The sheet always ends with the "An toàn thông tin" category** (XSS + SQL Injection; the cases, how to measure and how to judge them are in `references/test-areas.md`). Measure them in step 7 like any other UI / API entry, and give each case family a coverage-matrix row.
   - **Write the test case sheet for a Tester / BA reader** (`references/output-format.md`, "Writing style"): screen actions in C; H starts with `Đạt.` / `Sai.` and says what was seen, with one example; `file:line`, table / column names and run ids go to the `Kỹ thuật:` line of J.
   - **The set is complete when every requirement has a case, not when it reaches a number.** Build the "Ma trận bao phủ" sheet with `wb.sheet_coverage(rows, title)`: one row per screen element and rule of `analysis.md`, standard section, FOUND trap and applicable checklist item (`references/test-areas.md`), each pointing at the cases that test it. A row with no case says `Không áp dụng: …` or `Chưa phủ: …`. Writing the matrix is how you find the missing cases: add them before building.
   - The file name comes from the profile. Never overwrite a delivered version: bump `version`.
   - `rt build` runs the quality gate. Fix what it lists:
     - every case has a concrete "Kết quả hiện tại", and every F has a bug id;
     - the coverage matrix exists, every row without a case gives its reason, and every FOUND trap of `probe.md` is named in a row (trap id in "Mục", plus the table when the trap is FOUND on several tables);
     - every open bug has a picture in "Hình ảnh lỗi", or `Không có hình: <lý do>`.

11. **Hand off.**
    - Start with one line naming the audience.
    - Give the workbook path, and the counts per section (P / F / PE / not run).
    - Give the data coverage (entries, cells compared, cells differing, with causes), and the main bugs, each with one concrete example and the number of pictures.
    - Give the requirement coverage from the matrix: rows covered, not applicable, not covered (with why).
    - Say what could not be run and why, and what changed since the previous version.
    - List the half-built functions found in step 3 (no case was written for them).

## Reviewer comments on a delivered workbook

1. `rt dump <file>` shows every comment.
2. Handle each one and create version N+1.
3. Re-run only the affected entries with `rt check <code> --only …`.
4. Add lessons that apply to other reports to `.report-kit/rules/lessons.md`, and new standard rules to `.report-kit/rules/standard.md`.

## References

- `references/test-areas.md`: what to cover.
- `references/checks-guide.md`: the `checks.yaml` format, with worked examples.
- `references/output-format.md`: the workbook, column by column, and the hand-off.
- `references/pitfalls.md`: technical pitfalls that apply to any project.
