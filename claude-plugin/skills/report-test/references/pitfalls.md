# Technical pitfalls (any project)

Project-specific lessons live in the profile's `rules/lessons.md`. These apply everywhere.

## Judging
- **The report's own query is not the oracle.** Build expected values from the SRS + standard. Otherwise the comparison only proves the query equals itself.
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
- **Text starting with "=" becomes a formula** and Excel then "repairs" the file by deleting the cell. Write cells through `Workbook.tc()` / `table()`.

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
