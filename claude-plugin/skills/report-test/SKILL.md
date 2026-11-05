---
name: report-test
description: Write and run the test case workbook for report / Tra cứu / Thống kê / dashboard screens, end to end, from their codes (e.g. 1E_117, or several: 1B_47 1B_48). Use when asked to test a report code, run its test cases on the deployed environment, or process a Tester's commented workbook. `rt` traces the screen's code, observes the screen and compares its data with independent SQL; Claude judges every result and the workbook comes out in the project's template.
argument-hint: <report code> [more codes] [e.g. 1E_117]
---

# /report-test <code>: from inputs to workbook

Arguments: `$ARGUMENTS`. One code: "The run" below. Several codes: "Several codes in one request" first (`references/several-codes.md`). Anything else is a note from the user.

- `rt` (the reportkit CLI) does the mechanical work: find the function row, trace the code from the menu, log in, probe data, observe and compare, build the workbook.
- **Claude does the judging.** The kit never decides P / F.

The project profile is `.report-kit/` in the repo; its `rules/` folder holds the standard summary, environment notes, lessons and data traps.

## What a verdict is based on

No SRS is read. The deployed system and its code describe what the function does; the workbook checks that it does it correctly and consistently. In this order:

1. **Quy chuẩn chung** (the original document if found, otherwise `.report-kit/rules/standard.md`). It overrides the code on everything it covers.
2. **The system contradicting itself**: grid vs Excel file for the same filter, screen vs API, a column label vs the data in it, VI vs EN, totals vs details, page 1 vs page 2, a field validated as required but shown without (*), a filter the screen sends but the server ignores.
3. **Plain correctness that holds for any business rule**: a count can't be negative, shares add up to 100 %, "Đến ngày" includes the whole last day, no duplicate rows from a join or a language twin, a dropdown lists every value it says it lists, a code is shown as its name, nothing is silently truncated, no raw i18n key.
4. **Runtime errors**: 4xx / 5xx, error toasts, crashes, exports that never finish.
5. **An toàn thông tin** (the KBKT_Template block): XSS, SQL Injection.
6. **Everything else follows the code.** Statuses, companies, period, which report type wins, column names, messages: what the code implements is the rule.

Verdicts:
- **P**: matches 1-6.
- **F**: breaks 1-5. An F needs **two independent sources**: the observation plus a screenshot, the code or the API response.
- **PE**: only when the Quy chuẩn itself is ambiguous on a point it covers. "The business might want something else" is never a PE.
- **No case** for what the code does not implement, or half-built code (a service method nobody calls, labels with no field): mention it in the hand-off, not in the workbook.

## Ground rules (non-negotiable)

- **Safety.** Follow the project's DB / test-data rules (from the repo's CLAUDE.md).
  - Read the DB with SELECT only, through `rt sql` or the checks. Never connect with another client.
  - Never create or change data on the shared environment. DEV / BA prepare test data.
  - Only call endpoints whose handler you have read and found read-only. Classify by what the handler does, not by the HTTP verb.
  - `rt install-skill` adds a hook that refuses write SQL and asks before direct DB access or write requests. It is a safety net, not a permission.
- **Workbook wording.** State each verdict and its basis, nothing about how the test set was made: never cite an SRS, never write that the SRS is outdated or unused or that the code is the reference. The basis line uses the wording of `references/output-format.md` ("Căn cứ").
- **Independent expectations.** Expected data comes from SQL you write from the rule in plain words (`analysis.txt`) and the Quy chuẩn, never from the report's own query or view.
- **Credentials** live only in `~/.report-kit/secrets.yaml` (or `RK_*` env vars), never in the repo, the workbook or chat.

## Token economy (binding)

Every turn re-reads the whole context, and new context is written to the cache once: what enters early is paid on every later turn, and what you write (scripts, cases) is paid as output.
- **Do more per turn.** A turn that only runs `ls`, `wc`, one small query or one patch costs as much as one that does real work (measured: 27% of all turns, 32% of the cost). Chain what depends on nothing new: patch every fix the last run showed, regenerate, re-run and print the result in one command; `rt check` already prints what needs a look.
- **Read little.** `grep -n`, then Read at most ~80 lines at a time; only the files the trace points to. Results: `rt show <code> --status ERR,NM` / `rt show <code> U03 --keys rows`, never the whole `summary.md` or the raw JSON. Several lookups in one call: `rt sql "SELECT …" "SELECT …"`.
- **The kit is documented, don't read its source**: `references/checks-guide.md` "Scripts" (http, db) and `references/output-format.md` "API at a glance" (workbook, evidence; its example is the builder template). An ERR reason names the blocker (`<div …> intercepts pointer events`): fix the entry from it. A blocker on every screen (tour, banner) is one shared dismiss step, noted in `.report-kit/rules/environment.md` at the end (by the main session only, when several agents run).
- **Screenshots:** don't open them unless a verdict depends on the picture (layout, alignment, truncation). An NM reason already says where the page was and what it showed (`| at /route | page shows: …`), an ERR reason what blocked the action: fix the entry from that text. Capturing and embedding are free.
- **Each `rt check` stops at its time budget** (`ui.run_budget_s`, 180 s, plus the entry in flight: the prompt cache lives ~5 minutes, and a longer wait rewrites the whole context at ~12x the read price). Entries it did not reach are `TODO`: run `rt check <code> --redo` again until none is left. **Call `rt check` and `rt build` with the Bash tool's `timeout: 300000`**: with the default 2 minutes the call moves to the background, and then every check on it is a turn (1B_50: 9 polling turns, 3 runs killed and restarted). Never run them in the background, never poll (`sleep`, `until`, a Python wait loop, Monitor).
- **Write once.** Files with the Write tool, changes with Edit (only the changed lines); no `cat <<'E'` heredocs for code (quotes break them, and the rewrite doubles the file in the context). Reuse what exists (a sibling's `shared.py`, a good run, `probe.md`); fix a script, don't rewrite it. Files go to the workspace; the chat gets conclusions only.
- Your own Python runs with `PYTHONIOENCODING=utf-8`. Measure a run with `python tools/token_usage.py --project <repo> --last 3` (in report-kit): cache-read is the cost.

## The run

Do the steps in order. Each step leaves files in the workspace (`~/report-kit-work/<profile>/<code>/`); if a session stops, `rt status <code>` shows where to continue.

1. **`rt doctor`.** Fix any FAIL line first. If `rt` is not found, tell the user to install it once per machine (`git clone <report-kit repo>`, `pip install -e <clone>`, `python -m playwright install chromium`) and stop. Missing secrets: name the keys for `~/.report-kit/secrets.yaml`, never ask for them in chat.

2. **`rt start <code>`, then read `brief.md`**: the function row and its notes (BA / Tester, "Có thể thay thế bằng"), the standard, previous workbooks with their reviewer comments, sibling reports, and the code trace (menu → route → component → services and URLs → report code → backend files, views, Excel templates).
   - "found by: name only": the function list gives no usable menu path. Look in the menu definition for the function's name first; with the menu labels found, run `rt start <code> --menu "Quản lý hồ sơ >> NNB, NLQ, CĐL, CĐSL >> <tab>"` (trailing tab names are fine), or `--route /the/route`. If nothing matches, ask the user **how they open the screen in the app** ("Màn hình này mở từ menu nào, và tab nào?") and pass the answer to `--menu`.
   - A note says the function was dropped or replaced: ask in step 4 whether to test it.
   - **Sibling reports** (same screen or same main code, e.g. 1E_117 internal / 1E_118 public company): find what differs (account type, data scope, filter); the workbook is about that difference. Cite the sibling's case for shared behaviour ("xem 1E_117_12") instead of copying it. If the difference needs an account or data you don't have, say so in step 4.
   - Then read the standard (it overrides the code), the **group conventions** the brief names (BA decisions already taken for the group: apply them, cite `Căn cứ: Quy ước kiểm thử nhóm <group> mục Qn`; a decision you take for a point the Quy chuẩn leaves open goes into that file, so the group's other functions apply the same one; when several agents run, only the main session writes it, from their proposals), `.report-kit/rules/environment.md`, `lessons.md` (grep it for the screen's words), and the previous workbook dump: every `##### COMMENT` is feedback to handle.

3. **Read the code: it is the specification.** Follow the chain: component (`.html` fields, columns, buttons, labels; `.ts` defaults, validation, what is sent) → service call → controller → handler / repository → SQL / view → Excel template or JSON shape. Where the deployed screen may differ from the repo, `rt deployed "<i18n key|text|regex>" --context 2000` shows the running code (one call, `a|b` for several names); never fetch or grep its chunks by hand. Write `<workspace>/analysis.txt`, the function as built (a working file for the next steps, not a report):
   - the screen: every field (type, default, required, values and their source), button, grid column, file column;
   - the rules, one line each, **in plain words** ("chỉ lấy tin đã duyệt, tiếng Việt; bản đính chính mới nhất thay bản gốc") with `file:line`, the Quy chuẩn section it falls under, and whether it already looks wrong by 1-4;
   - half-built functions, for the hand-off.

4. **Ask the user once**, in a single question, before touching the environment. The user is a Tester: ask in the screen's words, never for a route, a file, a class or a table, and recommend an answer for every question. Ask: which account (a super admin can't reproduce data-permission cases; for a sibling, the account type that makes this one different); OK to run read-only SELECTs this session; is anyone demoing or doing UAT on the environment; anything from step 2 that needs a decision. Don't continue without the answers.

5. **`rt login --system <system>`.** Note the login name and the super-admin flag for the workbook.

6. **`rt probe <code>`**: the profile's data traps on the tables the report reads, with real examples in `probe.md` (it prints only the FOUND list; grep `probe.md` for a trap's examples when a case needs them). A sibling that probed the same tables today is reused, with no new queries. A FOUND trap needs a case; a rule with no example on the environment becomes "Chưa thực hiện - cần dữ liệu". Other lookups: `rt sql "<SELECT>"`.

   **One code in the main session: hand steps 7-10 to a fresh agent** once `analysis.txt`, `probe.md` and a first `checks.yaml` exist (its selectors proven by one `rt check --only` on two or three entries), plus a `handoff.txt` (at most 30 lines: planned cases, uncertain selectors, open points). Spawn it with `subagent_type: "report-runner"`, the code, workspace, "part B" and the user's answers from step 4. By this point the context holds everything read in step 3 (165-228k measured), and steps 7-10 take most of the turns: a fresh start cuts their reading by about a third. Then hand off its summary.

7. **Write `<workspace>/checks.yaml`, run `rt check <code>`** (`references/checks-guide.md`).
   - Data entries: the app's rows (API or exported Excel) against your SQL; `variants` so every differing cell gets a cause; a `matrix` over **every value the filter offers**; values with no data in a separate entry without `require: actual_rows`.
   - UI entries: what the cases need (titles, labels, dropdown values, tooltips, requests, toasts, downloads, zoom, Tab order, English mode, a simulated 500), with `ready` / `require` so a bad measurement shows as NM; `boxes:` for the areas a bug picture would need.
   - Results (`rt show <code> …`, see `references/checks-guide.md` "Reading the results"): **NM / ERR** = the measurement failed; fix the entry and `rt check <code> --redo` (or `--only U03,U05`). **DIFF**: trace each cause to a source row with `rt sql`, one concrete example (ID, value, date) per cause. **OBS**: read the observations.

8. **Judge** every case by "What a verdict is based on". Not run: say why ("Chưa thực hiện - cần tài khoản không phải admin" / "- cần dữ liệu" / "- không đo được: …"). A difference the code explains on purpose (a status, a scope, a priority) is not a bug: correct the expectation, unless 1-4 says otherwise.

9. **A picture for every open bug** in "Hình ảnh lỗi" (`references/output-format.md`, "Hình ảnh lỗi"). Reuse step 7 first (`E.run_shot` from recorded positions, `E.excel` on the downloaded file, `E.table` on rows already fetched); capture only what step 7 didn't show, all in one `rt check --only …`; open only the cards `rt build` warns about.

10. **Write `<workspace>/build_workbook.py`, run `rt build <code>`** (`references/output-format.md`).
   - The test case sheet is written for a Tester / BA ("Writing style"); it always ends with "An toàn thông tin" (`references/test-areas.md`).
   - The set is complete when every requirement has a case: build "Ma trận bao phủ" from `analysis.txt`, the standard, FOUND traps and the checklist, and add the missing cases it reveals.
   - Never overwrite a delivered version: bump `version`.
   - Fix everything the quality gate of `rt build` lists.

11. **Hand off.** One line naming the audience, then: the workbook path; counts per section (P / F / PE / not run; `rt build` and `rt tally <file>` print them); data coverage (entries, cells compared, cells differing, with causes); the main bugs, each with one concrete example and its pictures; requirement coverage from the matrix (covered / not applicable / not covered, with why); what could not be run and why; what changed since the previous version; half-built functions found in step 3.

## Several codes in one request

The main session only prepares and delegates: read `references/several-codes.md` first and follow it. Agents that run one code never need it.

## Reviewer comments on a delivered workbook

1. `rt dump <file>` shows every comment.
2. Handle each one and create version N+1; re-run only the affected entries with `rt check <code> --only …`.
3. Lessons that apply to other reports go to `.report-kit/rules/lessons.md`, new standard rules to `.report-kit/rules/standard.md`.

## References

- `references/test-areas.md`: what to cover.
- `references/checks-guide.md`: the `checks.yaml` format, with worked examples.
- `references/output-format.md`: the workbook, column by column, and the bug pictures.
- `references/pitfalls.md`: technical pitfalls that apply to any project.
- `references/several-codes.md`: several codes in one request (main session only).
