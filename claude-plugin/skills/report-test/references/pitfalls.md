# Technical pitfalls (any project)

Project-specific lessons live in the profile's `rules/lessons.md`. These apply everywhere.

## Judging
- **The report's own query is not the oracle.** Build expected values from the rule written in plain words + the standard, not by copying the view's SQL. Otherwise the comparison only proves the query equals itself.
- **Attribute every differing cell to a cause** by adding variants (the app's rule, the standard with one condition dropped).
  - A cell equal to a variant is explained by that rule.
  - A cell no variant explains must be traced with `rt sql` before it goes in the workbook.
- **An F needs two independent sources:** observation + screenshot, code, or API response.
- **An empty observation usually means a wrong selector, not an app bug.** Look at the final screenshot first.
- **An admin account hides permission bugs.** Say so; don't pass permission cases with it.
- **The deployed build can differ from the repo.** Test the deployed behaviour, and state which commit your `file:line` references point to.

## Data
- **Dev data is live.** Counts change between two queries minutes apart. `rt check` computes the expectation right next to each call; don't reuse figures from an earlier query as evidence.
- **"Latest value" dedups** (`ROW_NUMBER() ... ORDER BY id DESC`) across all rows pick up drafts, rejected rows and other-language rows. Check every dedup for its status and language filter.
- **Upper date bounds like `TO_DATE(:y || '-12-31')` are midnight**, so rows later that day are lost. Compare with `< next day`.
- **Rows can point to parents that no longer exist** (orphans), not only to parents flagged deleted. The `orphan_company` trap finds them.
- **Slow correlated `EXISTS` queries** on big tables can take minutes. Prefer `GROUP BY ... HAVING`. The DB call timeout stops a runaway query.

## Excel
- **Compare what Excel displays, not the raw value.** The kit applies number and date formats: 2.0 with `#,##0` shows "2".
- **Text starting with "=" becomes a formula** and Excel then "repairs" the file by deleting the cell. Write cells through `Workbook.tc()`.

## UI
- **Never wait for "networkidle".** SPAs and SSO pages keep background requests open. Wait for "load", then for the element you need (`ready`).
- **The SSO URL contains `redirect_uri=<web>`**, so wait for a URL that *starts with* the web base, not a glob.
- **One entry must not leak state into the next.** The kit gives each UI entry its own browser context; don't try to chain entries.
- **Hovering the first slice of a chart can land on its neighbour.** Add a `require` on the text you expect to read.
- **Buttons named like "Xuất" also match "Đăng xuất"** (log out). Select by component or attribute, not by visible text.
- **Hidden `<select>` elements behind custom dropdowns** keep options from earlier searches. Count the visible options instead.
- **Each export call can write an audit-log row.** One export per case is fine; avoid pointless loops.

## Environment
- **Windows console:** the kit forces UTF-8 output. When running other scripts, set `PYTHONIOENCODING=utf-8`.
- **Git Bash rewrites a leading `/`** in arguments into a Windows path. `rt` takes API paths as arguments, so run it from PowerShell, or prefix the call with `MSYS_NO_PATHCONV=1`.

## Batch / shared-screen lessons (2B.I, October 2026)
- **A sort without a tie-break key repeats and loses rows across pages.** Fetch the first pages at page sizes 10 / 25 / 50 and count distinct ids; compare with one big page. Seen on an auditor list (14 distinct created dates for 1,707 rows: 60 rows over 6 pages were 43 people) and on a block of 54 approvals.
- **A filter parameter with a wrong name is silently ignored** and returns everything: it looks like "the filter does nothing". Take the parameter names from the screen's component (`searchFilters`), not from the entity.
- **Detail / tab endpoints take the parent id and often skip the data-permission check** that the list and export apply. Test with ids that exist but are outside the permission scope.
- **The permission table can hold ids of parents that no longer exist.** Scope = permission joined to the data table, not the permission row count.
- **A server error that looks like "no data":** stub a 500 for every list the screen loads and check for a message. Silent empty lists make users think nothing exists.
- **Raw i18n keys in English mode** (`companyDetail.form.xxx`) and untranslated suffixes are common on history / popup components; open every popup and tab in English.
- **Number and date formats in Excel cells:** a number stored with the General format shows `8000000000`; open the cell's format, not only its value.
- **The empty export:** some templates keep their placeholder row (`${item.name}`) when there is no data. Export once with a filter that matches nothing.
- **Duplicates in the data are findings** (the same record twice, identical periods without a document number): group by the natural key before judging a list.
- **Dev data moves while you work.** Re-measure just before writing a number into a case; two measurements that differ are both facts, quote the later one.
- **A one-off failure after login** (connection toast, raw codes) is not a bug: re-run it once before judging.
- **Sub-agents cannot Write report files and must not wait.** Use them for read-only code tracing with a 5-minute limit; never for `rt check`, polling, or anything that sleeps (the prompt cache expires while they wait).
