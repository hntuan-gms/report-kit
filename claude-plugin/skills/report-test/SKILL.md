---
name: report-test
description: Write and run the test case workbook for one report / Tra cứu / Thống kê / dashboard screen, end to end, from its code (e.g. 1E_117, 2E_50). Use when asked to test a report code, run its test cases on the deployed environment, process a Tester's commented workbook, or compare an SRS with the code. Claude reads the SRS and the code, the `rt` tool observes the screen and compares the data with independent SQL, Claude judges every result against the SRS and the project standard, and the workbook is produced in the project's template.
argument-hint: <report code> [e.g. 1E_117]
---

# /report-test <code>: one report, from inputs to workbook

Arguments: `$ARGUMENTS` (the report code; anything else is a note from the user).

**How the work is split:**
- `rt` (the reportkit CLI) does the mechanical work: find inputs, trace code, log in, probe data, run the observation and comparison steps, build the workbook.
- **Claude does the judging.** The kit never decides P / F. Claude reads what the screen showed and what the data comparison found, and judges it against the SRS and the project standard, on every run.

The project profile is `.report-kit/` in the repo. Its `rules/` folder holds the project standard summary, environment notes, lessons and data traps.

## Ground rules (non-negotiable)

- **Safety.** Follow the project's DB / test-data rules (loaded from the repo's CLAUDE.md).
  - The DB is read with SELECT only, through `rt sql` or the checks. The kit refuses anything else.
  - Never create or change data on the shared environment. DEV / BA prepare test data.
  - Only call endpoints whose handler you have read and found to be read-only. Classify by what the handler does, not by the HTTP verb.
- **No guessing.**
  - When neither the SRS, the standard nor the code settles a point, it becomes a BA question and the case is PE.
  - Every expected result cites its basis (SRS / standard § / code).
- **Independent expectations.** Expected data comes from SQL written from the SRS + standard, never from the report's own query or view.
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
   - the function row (name, Jira key, ticket, system, PIC);
   - the SRS dumped to text, with its images;
   - the standard document (or the profile's summary);
   - previous workbooks with the number of reviewer comments;
   - **sibling reports**, when another function shares this one's SRS or its main code files;
   - the **code trace**: the files ranked by how many distinct SRS fingerprints they contain, with their endpoints and SQL objects.

   **If `brief.md` lists sibling reports**, this is probably the same screen seen by another kind of user or with another filter (1E_117 internal / 1E_118 public company: one `/dashboard`, one SRS).
   - Find what differs before writing any case: the account type, the data scope, the filter. The workbook is about that difference.
   - Shared behaviour: cite the sibling's case ("xem 1E_117_12") instead of copying it, unless you re-run it with what makes this report different.
   - If the difference needs an account or data you don't have, say so in step 4, not after the workbook is built. A workbook whose own cases are all "Chưa thực hiện" tests nothing new.

   Then read, in this order:
   - the SRS text, and **every SRS image** (open them with Read: menu screenshots and mock-ups carry requirements);
   - the standard: the original document if found, otherwise `.report-kit/rules/standard.md`. **The standard overrides an individual SRS** on what it covers;
   - `.report-kit/rules/environment.md` and `.report-kit/rules/lessons.md`;
   - the previous workbook dump, if any: every `##### COMMENT` is reviewer feedback to handle.

3. **Read the code.** Start from the top files of the trace and follow the chain:
   screen component → service call → controller → service / repository → SQL / view → Excel template or JSON shape.
   - Note every data rule (WHERE, JOIN, dedup, CASE, date bounds, status and language filters, permission join) with `file:line`, and the display rules (labels, number formats, i18n).
   - If the trace misses (the SRS shares no identifiers with the code), search for the screen's route or menu entry.
   - Write the findings to `<workspace>/analysis.md`. Keep it short: rules, `file:line`, and SRS vs code differences.
   - For a large report, delegate the tracing to an Explore agent and keep only its conclusions.

4. **Ask the user once**, in a single question, before touching the environment:
   - which account to use: a super admin can't reproduce data-permission cases. With a sibling report, ask for the account type that makes this one different (e.g. a public-company login);
   - OK to run read-only SELECTs this session?
   - is another team demoing or doing UAT on the environment?

   Do not continue without the answers.

5. **Log in: `rt login --system <system>`.** Note the login name and the super-admin flag for the workbook.

6. **Probe the data: `rt probe <code>`.** It runs the profile's data traps on the tables the report reads, and writes real examples to `probe.md`: language twins, orphans, deleted / out-of-scope companies, correction chains, year-end timestamps, NULL periods, duplicates.
   - A trap marked FOUND needs a case.
   - A rule with no example on the environment becomes "Chưa thực hiện - cần dữ liệu".
   - Use `rt sql "<SELECT>"` for any other lookup (read-only, row limit).

7. **Write `<workspace>/checks.yaml` and run it: `rt check <code>`.** See `references/checks-guide.md` for the format and examples.
   - **Data entries:**
     - the app's rows (JSON API or exported Excel) against SQL you wrote from the SRS + standard;
     - add `variants` (the report's own rule, the standard with one condition dropped) so every differing cell is attributed to a cause;
     - use a `matrix` to cover the full scope, not a sample: **every value the filter or dropdown offers** (all years, all periods, all exchanges). Ranges are written `year: "{current_year}..2016"`;
     - values with no data belong in the scope too: put them in a separate entry without `require: actual_rows`, so "empty on both sides" shows as MATCH instead of NM.
   - **UI entries:**
     - steps and observations for what the cases need: titles, labels, dropdown values, tooltips, requests fired, toasts, downloads, zoom, Tab order, English mode, a simulated 500;
     - add `ready` / `require` preconditions so a bad measurement shows as NM instead of misleading you.
   - Read `runs/<id>/summary.md`:
     - **NM / ERR** means the measurement failed, not the app. Fix the entry and re-run only those with `rt check <code> --redo` (or `--only U03,U05`);
     - **DIFF**: trace each differing cell back to the source row with `rt sql`, and cite one concrete example (ID, value, date) per cause;
     - **OBS**: read the observations, and the screenshots where the verdict depends on the picture.

8. **Judge.** For every case, decide against the SRS and the standard:
   - **P**: matches the expected result.
   - **F**: doesn't match, and the expected result has a firm basis (SRS or standard). An F needs **two independent sources**: the observation plus a screenshot, the code or the API response.
   - **PE**: observed, but the expected result is not settled (code is the only basis, or the SRS is vague). Link it to a BA question.
   - **Not run**: say why ("Chưa thực hiện - cần tài khoản không phải admin", "- cần dữ liệu", "- không đo được: …").

   A point the standard settles cites its section. It is not logged as a bug or a question.

9. **Write the workbook: `<workspace>/build_workbook.py`, then `rt build <code>`.** See `references/output-format.md`.
   - The script uses `reportkit.workbook.Workbook` (the project's template, 7 sheets). `workbook.details_from_run(run_dir)` gives the "Chi tiết sai lệch dữ liệu" rows.
   - **The sheet always ends with the "An toàn thông tin" category** (XSS + SQL Injection; the cases, how to measure and how to judge them are in `references/test-areas.md`). Measure them in step 7 like any other UI / API entry, and give each case family a coverage-matrix row.
   - **Write the test case sheet for a Tester / BA reader** (`references/output-format.md`, "Writing style"): screen actions in C; H starts with `Đạt.` / `Sai.` / `Cần BA xác nhận.` and says what was seen, with one example; `file:line`, table / column names and run ids go to the `Kỹ thuật:` line of J.
   - **The set is complete when every requirement has a case, not when it reaches a number.** Build the "Ma trận bao phủ" sheet with `wb.sheet_coverage(rows, title)`: one row per SRS cell, standard section, code rule (`file:line`), FOUND trap and applicable checklist item (`references/test-areas.md`), each pointing at the cases that test it. A row with no case says `Không áp dụng: …` or `Chưa phủ: …`. Writing the matrix is how you find the missing cases: add them before building.
   - The file name comes from the profile. Never overwrite a delivered version: bump `version`.
   - `rt build` runs the quality gate. Fix what it lists:
     - every case has a concrete "Kết quả hiện tại", and every F has a bug id;
     - the coverage matrix exists, every row without a case gives its reason, and every FOUND trap of `probe.md` is named in a row (trap id in "Mục", plus the table when the trap is FOUND on several tables).

10. **Hand off.**
    - Start with one line naming the audience.
    - Give the workbook path, and the counts per section (P / F / PE / not run).
    - Give the data coverage (entries, cells compared, cells differing, with causes), and the main bugs, each with one concrete example.
    - Give the requirement coverage from the matrix: rows covered, not applicable, not covered (with why).
    - Say what could not be run and why, and what changed since the previous version.

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
