---
name: report-test
description: Write and run the test case workbook for one report or for SEVERAL ("/report-test 2B_18, 2B_19, 2B_20") / Tra cứu / Thống kê / dashboard / management screen, end to end, from its code (e.g. 1E_117, 2E_50). With several codes it runs the batch flow by itself: group the codes that share a screen, measure each screen once, write one standalone workbook per code. Use when asked to test a report code, run its test cases on the deployed environment, or process a Tester's commented workbook. The `rt` tool finds the screen's code from the function list's menu path, observes the screen and compares the data with independent SQL; Claude reads the code, judges every result against the project standard (Quy chuẩn chung) and the system's own rules, and the workbook is produced in the project's template.
argument-hint: <report code> [<report code> ...] [note, e.g. 1E_117 or 2B_18, 2B_19, 2B_20]
---

# /report-test <code> [<code> ...]: from inputs to workbook

Arguments: `$ARGUMENTS` (one or more report codes; whatever follows the last code is a note from the user).
**One code: follow "The run" below. Several codes: follow "Batch mode" first, it uses "The run" for every step.**

**How the work is split:**
- `rt` (the reportkit CLI) does the mechanical work: find the function row, trace the code from the menu, log in, probe data, run the observation and comparison steps, build the workbook.
- **Claude does the judging.** The kit never decides P / F. Claude reads what the screen showed and what the data comparison found, and judges it with the rules below, on every run.

The project profile is `.report-kit/` in the repo. Its `rules/` folder holds:
- the project standard summary (the Quy chuẩn chung, for every test case);
- `groups/<group>.md`, the conventions of each function group, which Claude decides acting as BA;
- environment notes, lessons and data traps.

## Batch mode (several codes in one request)

`/report-test 2B_18, 2B_19, 2B_20, 2B_21` is the whole instruction. Everything below is standing practice: do it without being asked and do not ask the user to repeat it. A note after the codes (e.g. "share what can be shared", "no sub-agent may wait more than 5 minutes") adds to these rules and never replaces them.

**The idea:** the measuring is done once per *screen*, the workbook is written once per *code*.

1. **Plan: `rt batch <codes...>`.** It starts every code, groups the codes that share a screen (same route / component / top code files) and writes `<work_root>/_batch/<id>.md`.
   - Read the plan. A code with no screen found ("name only") is probably a popup, tab or detail page of another code's screen: find where it lives (menu, routes file, the other screens' tabs and buttons), then `rt start <code> --route /...` or `rt batch ... --join <code>:<host code>`.
   - If no screen exists for a function at all, test the nearest thing users really see, decide it as BA (group file, one Q row saying what the function is taken to be) and say so in the hand-off; do not write cases for code that is not wired to a screen.
   - The first resolved code of a group is its **host**: the group's `checks.yaml`, measure scripts and `runs/` live in the host workspace.
2. **Share the measuring, never the wording.** Each code's workbook is standalone: its own full set of cases (aim for what a stand-alone workbook of that screen needs, usually 40-90), built from the host's measurements. No cell may say "xem <other code>", "dùng chung", or cite another workbook. Numbers measured with this account are used only for what this code covers; a case that depends on an account or data this account cannot see is "Chưa thực hiện - cần ...". (This replaces the "cite the sibling's case" advice under "The run".)
3. **Trace the code in parallel with sub-agents, one per screen group (or per half of a big one), under hard limits.**
   - Brief each agent: goal, the files to start from (the brief.md trace), the output format of `analysis.md` below, and these limits: read only (no `rt`, no URL, no DB), about 30 file reads, finish within 5 minutes, never sleep or wait, return the result as text.
   - Sub-agents cannot Write report files. **You** save one `analysis.md` per code (each code needs its own complete file with its own `R1.` lines; copy the shared rules into each).
   - What an agent says "looks wrong" is a hypothesis. The deployed build can differ from the repo (a filter, a block, a label); measure before you judge.
4. **Never give a sub-agent anything that waits.** `rt check` of UI entries runs 30-60 seconds each; a batch takes tens of minutes. You start it yourself in the background and wait once (below). Writing a workbook builder is your job too unless the user hands it over explicitly.
5. **Ask the user once**, in one question: the account (and the roles the transactions name), OK for read-only SELECT, whether another team is using the environment. Everything else (business rules) you decide as BA. Then `rt login`, and `rt probe <code> --schema <schema> --tables ...` for every code (the coverage gate reads each workspace's `probe.md`).
6. **Group conventions first.** Create or extend `rules/groups/<group>.md` as each decision comes up and before you judge; the group file is shared by every code of the group; Q ids are only ever appended.
7. **Measure once per screen group** (in the host workspace):
   - `rt scaffold <host>` writes `measure_<host>.py`, `gen_checks.py` and `build_workbook.py` skeletons (`--like <code>` starts from a sibling).
   - **Data and API facts: Python, not shell.** `from reportkit.measure import Measure` gives `api`, `rows`, `all_rows` (one big page = a stable reference), `paging_stability`, `download`, `sql`, `scope_ids`, `save`. Only read-only endpoints (you read the handler). `rt api GET /path` in Git Bash is rewritten into a Windows path: use Python, or `MSYS_NO_PATHCONV=1`.
   - **UI facts:** `gen_checks.py` -> `checks.yaml`; the profile's `ui.pre_steps` already removes onboarding tours / banners; stubs go in the entry-level `routes:` (before load).
   - What to measure on every list screen: scope against permission and SQL (all rows, all columns), every filter and every dropdown value, text filters (case, accents, `%` `_`, spaces), **paging stability at several page sizes** (a sort without a tie-break repeats and loses rows), every sortable column (case, blanks last, displayed vs stored value), export vs grid for the same filters, the **empty export** (template placeholders left in?), number / date formats in the file, English mode (labels, **raw i18n keys**, data stays Vietnamese), simulated 500 (a message, or does it look like "no data"?), XSS typed / in the URL / in stubbed data, injection strings on every read-only parameter, ids outside the permission scope on detail endpoints.
   - On every detail tab / popup: each list against SQL for every in-scope parent, soft-deleted rows, order, a parent with more than one page, empty parent, server-error stub, code-to-name display, duplicates in the data.
   - **Run the UI batch in the background, wait once:** `rt check <host> --pending > log &` followed by one background `until grep -q finished log; do sleep 15; done`. No per-entry monitor, no polling loop in the conversation. Read results with `rt show <host> <ids|all>` (merged across runs, noise requests hidden). A run you stopped half way is finished by `rt check <host> --pending`.
   - **Before writing a number into a case, re-measure it** if the data may have moved (others edit the shared environment); say "lúc đo" in the precondition row.
   - **A failure that looks transient** (a connection toast once, raw codes once, a first call after login) is re-run before it becomes an F.
8. **One workbook per code:** `rt scaffold <code>` (or the host's build script as a start), then cases with `reportkit.wbhelpers.make` (constants for the "Căn cứ" lines, `T` for run cases, `NR` for not-run cases), `wb.waive` for requirements with no case, `rt build <code> --check` until the gate prints OK (coverage, wording, group conventions), then `rt build <code>`. Write operations and anything that sends data out (mail, another system) are "Chưa thực hiện" with the reason, never run.
9. **Progress.** When the user asks how far you are, answer from a per-code checklist (read / measured / workbook written / gate / delivered), with a real percentage and what is left; say in one line what you are doing before any long step.
10. **One hand-off for the whole batch** (`output-format.md`): the audience line, one table (code, file, cases, F, not run), the group conventions added (Qn, one line each, for the BA), bugs one line each with one example per code, what was not run and why, functions found half-built, how codes without their own screen were understood, the sharing statement (measured once, standalone workbooks), and the lessons you added to `rules/lessons.md`.

**`analysis.md` format** (what sub-agents return, what you save): `## Màn hình` (every field / column / button with label and source), `## Quy tắc` (one line per rule, each starting `R1. `, `R2. `..., plain words with `file:line`), `## Có vẻ sai` (hypotheses with both sides' `file:line`), `## Endpoint đọc/ghi` (verb, URL, READ-ONLY or WRITES by what the handler does), `## Chưa nối dây` (half-built parts).

## Token economy

- Trace code in sub-agents (read only, 5 minutes, text result); keep only their conclusions in `analysis.md`.
- Several codes in one request (`rt batch`): measure each screen once, reuse the host's scripts (`rt scaffold --like`).
- Keep tool output small: `rt show` (not raw JSON), `--keys`, `--limit`; screenshots only when a verdict depends on the picture.
- Start long runs in the background and wait once; never poll, never arm one monitor per entry, never let a sub-agent wait.
- It changes how the work is done, never the workbook.

## What a verdict is based on

No SRS is read. **What** the function must offer comes from its **transactions** in the function list (see "Transactions"): which actions, for which roles. **How** it does them is described by the deployed system and its code; the workbook checks that it does them correctly and consistently. In this order:

1. **Quy chuẩn chung** (the project standard: the original document if found, otherwise `.report-kit/rules/standard.md`). It overrides the code on everything it covers.
1b. **The group's conventions** (`rules/groups/<group>.md`): points the Quy chuẩn chung does not settle for this function group, decided by Claude acting as BA (see "Acting as BA"). They override the code on what they cover and never contradict the Quy chuẩn chung.
2. **The system contradicting itself**: grid vs Excel file for the same filter, screen vs API, a column label vs the data in it, VI vs EN, totals vs details, page 1 vs page 2, a field the code validates as required but shows without (*), a filter the screen sends but the server ignores.
3. **Plain correctness that holds for any business rule.** Claude may judge these on its own: a count can't be negative, shares add up to 100 %, "Đến ngày" includes the whole last day, no duplicate rows from a join or a language twin, a dropdown lists every value it says it lists, a code is shown as its name, nothing is silently truncated, an i18n key is never shown raw.
4. **Runtime errors**: 4xx / 5xx, error toasts, crashes, exports that never finish.
5. **An toàn thông tin** (the KBKT_Template block): XSS, SQL Injection.
6. **Everything else follows the code.** Which statuses, which companies, which period, which report type wins, column names, messages: what the code implements is the rule. The case is P when the screen does what the code says.

Verdicts:
- **P**: the behaviour matches 1-6.
- **F**: it breaks 1, 1b, 2, 3, 4 or 5, or the function does not offer one of its transactions. An F needs **two independent sources**: the observation plus a screenshot, the code or the API response.
- **PE**: not used for business questions. When the Quy chuẩn chung is silent or ambiguous and the point needs a business decision, decide it as BA (below), record it, and judge P / F against it. Use PE only when the user asks to leave a point for the real BA. "The business might want something else" is never a PE on its own: the code is the rule unless a decision is needed.
- **No case** for a function the code does not implement (no field, no column, no button) **unless a transaction asks for it**: then it gets an F case (see "Transactions"). Otherwise there is nothing to run. A half-built function (a service method nobody calls, labels with no field) gets no case either; tell the user about it in the hand-off message, not in the workbook.

## Transactions (what the function must offer)

The function list has a sheet "Chi tiết transaction". For each function, it lists one row per user action: who does it, what they do, and what the system answers ("LĐGSĐC; CVGSĐC xem tổng hợp báo cáo giao dịch. Hệ thống hiển thị thông tin thống kê"). `rt start` reads them into `inputs/transactions.json` and lists them in `brief.md` as `T1`, `T2`... with the roles. They say **what** must exist and **who** uses it, never how: statuses, scope, formulas, labels still come from the code, the Quy chuẩn chung and the group conventions.

- **A transaction is a requirement, not a test case.** Each `T` needs at least one case (`covers=["T3"]`), and usually several: the main behaviour, the data, the filters, the permission for the roles it names. One case may cover several `T`. `rt build` fails while a `T` has neither a case nor a reason.
- **The 'Phân loại' column** (Dữ liệu đầu vào / Yêu cầu truy vấn / Dữ liệu đầu ra) is the BA's sizing. It says nothing about read or write: "xem" rows are marked "Dữ liệu đầu vào". Classify the action by what its handler does.
- **A function marked "Sửa" or "Bổ sung"** has a changed requirement. Check the previous workbook against every `T` before reusing its cases, and say in the hand-off which `T` the previous version did not cover.
- **No transactions** (the sheet covers only IDS; a KT function prints "none" in `brief.md`): coverage comes from the code as before.

For each `T`, find in step 3 where the code implements it, then:

| Situation | In the workbook |
|---|---|
| Implemented on this screen | Cases as usual, `covers=["T3", ...]`. |
| Implemented on another screen or by another function, or done by a scheduled job instead of the user | No case: `wb.waive("T3", "Thuộc màn hình ... / chức năng 1D_xxx, xem workbook ...")` or `"Hệ thống tự chạy theo lịch, kết quả kiểm tra ở case ..."`. When it is unclear whether that satisfies the transaction, decide as BA (group file) first. |
| Not implemented anywhere: not on the screen, no route, no endpoint, no handler | **One F case.** B: the action in the screen's words. D: what the transaction says the system does. H: `Sai.` then `Không có chức năng ...` and where you looked (menu, screen, buttons). J: the basis line, then `Kỹ thuật:` the code search (no route / API / handler for it). Two sources: the screenshot of the screen and the code search. |
| Implemented, but it can't be run here | A case with the reason: "Chưa thực hiện - cần dữ liệu", "- cần tài khoản <vai trò>", "- thao tác ghi dữ liệu trên môi trường dùng chung, chưa được phép". Actions that write data (thiết lập, sửa, xoá, kích hoạt job) follow the safety rules: ask the user first, never run them on your own. |

Basis line of a case that rests on a transaction: `Căn cứ: Danh sách chức năng, yêu cầu "<the action, as in brief.md>"`.

## Acting as BA (group conventions)

The PIC has asked Claude to take the business decisions itself instead of waiting for a BA. There are two levels:
- `rules/standard.md`: the **Quy chuẩn chung**, for every test case of the project. It summarises the BA's document; Claude does not change its rules on its own.
- `rules/groups/<group>.md`: the **conventions of one function group**. The key comes from the function list's "Nhóm" column: `1D.I`, `1E.I`, `2E.I`, `1B.III.3`… `brief.md` names the file. Claude writes these, acting as BA.

**When to decide.** A point needs a decision when the verdict depends on a business rule that neither the Quy chuẩn chung nor the group file settles, and one of these holds:
- the code shows no deliberate rule, e.g. the logic is outside the repo;
- two parts of the system disagree;
- a section of the Quy chuẩn chung was written for another kind of screen, and it is unclear whether it fits this one;
- you would otherwise write a PE or ask the user.

Where the code implements a rule on purpose and nothing contradicts it, the code is still the rule and no decision is needed.

**How to decide.** Apply these in order:
1. Stay inside the Quy chuẩn chung. A convention says how a section applies to the group, never the opposite of it.
2. Keep the system consistent: take the rule another screen of the same system already applies to the same data, e.g. the dashboard's company scope.
3. Serve the purpose of the function for its user. A supervisor needs every real obligation once, nothing invented, nothing lost.
4. Keep it deterministic: the same data always gives the same result, so pick a tie-break.
5. Choose the smallest rule that settles the case. Add no requirement beyond what the screen offers.

Do not decide what is not a business rule. Safety, accounts, SELECT permission, demos and test data stay with the user.

**How to record.** Before judging, add a row to the group file. To create a new file, copy the header of an existing group file.
`| Qn | quyết định (one sentence, business words) | lý do | Claude quyết định dd/mm/yyyy (<code>) |`

Never renumber or reuse a Q id. To change a decision, edit its row and add the date. Then:
- cite it in column J: `Căn cứ: Quy ước kiểm thử nhóm 1D.I mục Q2`;
- make the precondition row say: "Điểm Quy chuẩn chung không quy định: theo Quy ước kiểm thử nhóm <key> (người kiểm thử đặt thay BA, chờ BA rà lại)". Never write that the BA confirmed them;
- `rt build` checks both: an unknown Qn, or a missing precondition line, fails the gate;
- list the new or changed items in the hand-off.

**When a real BA answers**, change the row's status to "BA xác nhận dd/mm", or to "BA sửa dd/mm" together with the new text. Then re-judge every case that cites the item (search column J for "mục Qn") in the next version of each workbook.

## Ground rules (non-negotiable)

- **Safety.** Follow the project's DB / test-data rules (loaded from the repo's CLAUDE.md).
  - The DB is read with SELECT only, through `rt sql` or the checks. The kit refuses anything else.
  - Never create or change data on the shared environment. DEV / BA prepare test data.
  - Only call endpoints whose handler you have read and found to be read-only. Classify by what the handler does, not by the HTTP verb.
- **Workbook wording.** The workbook states each verdict and its basis, nothing about how the test set was put together (and nothing about another code's workbook):
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
   - the **transactions** `T1`, `T2`... with their roles, and the "Sửa" / "Bổ sung" flag (see "Transactions");
   - the standard document (or the profile's summary);
   - previous workbooks with the number of reviewer comments;
   - **sibling reports**, when another report uses the same screen or the same main code files;
   - the **code trace**: menu entry → route → screen component → services and the URLs they call → the report code (e.g. R017) → backend files ranked by the screen's fingerprints (handler, entity, repository, view SQL), the views behind them and the Excel templates.

   **If the trace says "found by: name only"**, the menu path is missing or matches no menu entry. Find the screen's route (menu definition, routes file, or ask the user) and run `rt start <code> --route /the/route`.

   **If a note says the function was dropped or replaced** (e.g. "Nghiệp vụ confirm bỏ chức năng này"), decide as BA.
   - Follow the note: no workbook. The exception is when the code shows the function live on the screen; then test what is there.
   - Record the decision in the group file and say so in the hand-off.

   **If `brief.md` lists sibling reports**, this is probably the same screen seen by another kind of user or with another filter (1E_117 internal / 1E_118 public company: one `/dashboard`).
   - Find what differs before writing any case: the account type, the data scope, the filter. The workbook is about that difference.
   - Shared behaviour: rebuild it as this code's own case (each workbook is read alone by a Tester; never cite another workbook), re-measured or "Chưa thực hiện" when this account cannot see it.
   - If the difference needs an account or data you don't have, say so in step 4, not after the workbook is built. A workbook whose own cases are all "Chưa thực hiện" tests nothing new.

   Then read, in this order:
   - the standard. **It overrides the code** on what it covers;
   - the group's conventions file named in `brief.md`, if it exists. Its items settle points for every report of the group;
   - `.report-kit/rules/environment.md` and `.report-kit/rules/lessons.md`;
   - the previous workbook dump, if any: every `##### COMMENT` is reviewer feedback to handle.

3. **Read the code: it is the specification.** Start from the trace and follow the chain:
   screen component (`.html`: fields, columns, buttons, labels; `.ts`: defaults, validation, what is sent) → service call → controller → handler / service / repository → SQL / view → Excel template or JSON shape.
   - Note every data rule (WHERE, JOIN, dedup, CASE, date bounds, status and language filters, permission join) and every display rule (labels, number formats, i18n), each with `file:line`.
   - Write `<workspace>/analysis.md`, the function as built:
     - the screen: every field (type, default, required, values and where they come from), button, grid column, file column;
     - the rules, one line each, **in plain words** ("chỉ lấy tin đã duyệt, tiếng Việt; bản đính chính mới nhất thay bản gốc") with `file:line`.
       **Start each rule line with its id: `R1. ...`, `R2. ...`.** The ids are the requirements the coverage gate of `rt build` checks;
     - for each rule, the Quy chuẩn section it falls under, and whether it already looks wrong by 1-4 above;
     - for each transaction, one line `T3: <where it is implemented, file:line>` or `T3: không có - <what you searched>`, and the rules `R` it leads to;
     - functions that are half built (code present but not wired), for the hand-off message.
   - For a large report, delegate the tracing to an Explore agent and keep only its conclusions.

4. **Ask the user once**, in a single question, before touching the environment:
   - which account to use: a super admin can't reproduce data-permission cases. With a sibling report, ask for the account type that makes this one different (e.g. a public-company login). Name the roles the transactions list ("roles named" in `brief.md`) that the cases need;
   - OK to run read-only SELECTs this session?
   - is another team demoing or doing UAT on the environment?
   - an unknown ticket number. Do not ask business questions: decide them as BA ("Acting as BA").

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
     - add `ready` / `require` preconditions so a bad measurement shows as NM instead of misleading you.
   - Read `runs/<id>/summary.md`:
     - **NM / ERR** means the measurement failed, not the app. Fix the entry and re-run only those with `rt check <code> --redo` (or `--only U03,U05`);
     - **DIFF**: trace each differing cell back to the source row with `rt sql`, and cite one concrete example (ID, value, date) per cause;
     - **OBS**: read the observations, and the screenshots where the verdict depends on the picture.

8. **Judge** every case with "What a verdict is based on" above.
   - **Not run**: say why ("Chưa thực hiện - cần tài khoản không phải admin", "- cần dữ liệu", "- không đo được: …").
   - A point the standard settles cites its section.
   - A point that needs a business decision: take it as BA, write it in the group file first, then judge and cite `Quy ước kiểm thử nhóm <key> mục Qn`.
   - A difference between the data and your expectation that the code explains on purpose (a status, a scope, a priority) is not a bug: correct the expectation to the code's rule, unless the Quy chuẩn or 2-4 says otherwise.

9. **Write the workbook: `<workspace>/build_workbook.py`, then `rt build <code>`.** See `references/output-format.md`.
   - **One sheet only: the test cases.** No rules / bug list / pictures / details / coverage sheets: Testers and BAs read only the test case sheet.
   - **Write it for a Tester / BA** (`output-format.md`, "Writing for a Tester / BA"): one case per check and per bug, one idea per line, words not symbols, names as the screen shows them. H starts with the verdict, then `Ví dụ` / `Phạm vi` / `Nguyên nhân`. Pass lists to `wb.tc()`.
   - **It always ends with "An toàn thông tin"** (XSS + SQL Injection, `references/test-areas.md`), measured in step 7 like any other entry.
   - **Complete = every requirement has a case. `rt build` enforces it** and writes no file while one is missing:
     - the requirements are the rule ids of `analysis.md` (`R1`...), the transactions (`T1`...), the FOUND traps of `probe.md` (`trap:<name>`) and the checklist areas of `test-areas.md` (`area:<key>`);
     - tag each case with what it covers: `wb.tc(..., covers=["T2", "R4", "trap:lang_twins", "area:bo_loc"])`. A rule branch with no data still gets its own case ("Chưa thực hiện - cần dữ liệu");
     - a requirement with no case gets `wb.waive("R9", "reason")`; the reasons go in the hand-off, never in the sheet;
     - run `rt build <code> --check` first: it builds `<workspace>/_check.xlsx` with every gate and uses up no version. `coverage.md` in the workspace lists requirement -> case or reason.
     - The gate checks that every requirement is named, not that the case is right: still re-read each P whose claim covers several years or periods (e.g. a deadline in a year with no holiday calendar).
   - The file name comes from the profile. Never overwrite a delivered version: bump `version`.
   - `rt build` runs the quality gate: coverage (above), every case has a concrete H, no row is hidden, and the wording check (verdict first, no line over 160 characters, no symbols or internal names in B C D H, no run id in J, one bug per case). Fix every line it lists and rebuild.

10. **Hand off** (`output-format.md`, "Hand-off message"): audience line, path, counts, data comparison in one line, bugs one line each, what was not run, what changed, requirements without a case, transactions the function does not offer, half-built functions, group conventions added or changed.

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
