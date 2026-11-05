"""PreToolUse hook: a mechanical safety net for the DB / test-data rules (`rt install-skill` registers it).

    deny -> a DB client command carrying a write / DDL statement (INSERT, UPDATE, DELETE, MERGE, DROP, ALTER, ...)
    ask  -> any other direct DB client command (the run reads the DB through `rt sql` / the checks only),
            an HTTP client sending a write request (curl -X POST, --data, Invoke-RestMethod -Method Put, ...),
            an MCP tool whose name says it talks to a database
    deny -> token-economy habits that cost whole-context turns, each with the way to do it instead:
            `rt check` / `rt build` in the background or with a Bash timeout under 4 minutes, polling a log,
            writing code files with a heredoc, reading runs/*.json instead of `rt show`
Everything else, `rt` itself included (it refuses non-SELECT SQL on its own), falls through to the normal
permission flow. The hook does not see what scripts do inside Python: the rules still apply there.
"""
import json
import re
import sys

_WRITE_SQL = re.compile(r"\b(INSERT\s+INTO|UPDATE\s+[\w.\"]+\s+SET|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE|GRANT|REVOKE"
                        r"|(DROP|ALTER|CREATE(\s+OR\s+REPLACE)?)\s+(TABLE|VIEW|INDEX|SEQUENCE|USER|SCHEMA|SYNONYM|"
                        r"TRIGGER|PROCEDURE|FUNCTION|PACKAGE|MATERIALIZED))\b", re.I)
_DB_CLIENT = re.compile(
    r"(^|[\s;&|(\"'])(sqlplus|sqlcl|psql|mysql|sqlcmd|sqlite3|liquibase|flyway)(\.exe)?\b"
    r"|jdbc:(oracle|postgresql)|\b(oracledb|cx_Oracle|psycopg2?|pg8000|asyncpg)\b", re.I)
_HTTP_CLIENT = re.compile(r"(^|[\s;&|(])(curl|wget|Invoke-WebRequest|Invoke-RestMethod|iwr|irm)(\.exe)?\s", re.I)
_HTTP_WRITE = re.compile(r"(-X\s*|--request\s+|-Method\s+['\"]?)(POST|PUT|PATCH|DELETE)\b"
                         r"|\s(-d|--data|--data-raw|--data-binary|--json|-F|--form|-Body)\b", re.I)
_MCP_DB = re.compile(r"sql|oracle|postgres|database|jdbc", re.I)
_RULE = "report-kit safety rules (SKILL.md 'Ground rules')"

# token economy (SKILL.md 'Token economy'): habits that cost whole-context turns, refused with the way to do it instead
_RT_RUN = re.compile(r"(^|[;&|(\s])rt\s+(check|build)\b")
_POLL = re.compile(r"\bsleep\s+\d|time\.sleep\(|\buntil\s")
_POLL_TARGET = re.compile(r"\.log\b|\.output\b|[/\\]tasks[/\\]|counts")
_HEREDOC = re.compile(r"cat\s+>>?\s*['\"]?[^\s'\"<>|;]+\.(py|ya?ml|js|ts|json|sql)['\"]?\s*<<"
                      r"|cat\s+<<-?\s*['\"]?\w+['\"]?\s*>>?\s*['\"]?[^\s'\"<>|;]+\.(py|ya?ml|js|ts|json|sql)\b")
_RAW_RUN = re.compile(r"runs[/\\][^\s'\"]*[A-Z]\d{2,}\.json|runs[/\\]\S*\s*[;&|]*\s*\S*json\.load")
_RUN_ENTRY = re.compile(r"""['"][A-Z]\d{2,}\.json['"]|['"][A-Z]['"]?\s*\+?\s*\w*\s*\+\s*['"]\.json""")  # 'H23.json'
_TOKENS = "report-kit token economy (SKILL.md)"
MIN_TIMEOUT_MS = 240000


def _background(cmd):
    rest = re.sub(r"\d?>&\d|&>|&&", " ", cmd)
    return bool(re.search(r"&\s*($|\)|;|\n)", rest))


def _economy(tool, inp):
    cmd = str(inp.get("command") or "")
    if _RT_RUN.search(cmd) and (inp.get("run_in_background") or _background(cmd)
                                or int(inp.get("timeout") or 0) < MIN_TIMEOUT_MS):
        return ("%s: run `rt check` / `rt build` in the foreground with the %s tool's timeout: 300000. The run stops "
                "itself at its time budget (180 s) and leaves the rest as TODO for `rt check <code> --redo`; a "
                "background run has to be polled, one whole-context turn per poll." % (_TOKENS, tool))
    if _POLL.search(cmd) and _POLL_TARGET.search(cmd):
        return ("%s: don't poll a log or a background task. Run `rt check` / `rt build` in the foreground with "
                "timeout: 300000 instead; if one is already running in the background, wait for its "
                "completion notification." % _TOKENS)
    if _HEREDOC.search(cmd):
        return ("%s: write the file with the Write tool and change it with Edit (only the changed lines). A heredoc "
                "breaks on quotes, and rewriting after it puts the whole file in the context twice." % _TOKENS)
    raw = _RAW_RUN.search(cmd) or (re.search(r"runs[/\\]", cmd) and "json.load" in cmd and _RUN_ENTRY.search(cmd))
    if raw and "rt show" not in cmd:
        return ("%s: read run results with `rt show <code> <ids> --keys a,b` (whole values) or "
                "`rt show <code> --status ERR,NM`, not the raw JSON of runs/." % _TOKENS)
    return None


_REAL_DROP = re.compile(r"\bDROP\s+TABLE\s+(?!RK_SDETTEST)[A-Za-z_][\w$#]*", re.I)


def decide(tool, inp):
    if tool.startswith("mcp__"):
        if _MCP_DB.search(tool):
            return "ask", "%s: direct database tool %s; the run reads the DB through `rt sql` only." % (_RULE, tool)
        return None
    inp = inp or {}
    text = " ".join(str(inp.get(k) or "") for k in ("command", "content", "new_string"))
    if _REAL_DROP.search(text):
        return "deny", ("%s: an SQL-injection payload must name a table that does not exist "
                        "(`'; DROP TABLE RK_SDETTEST_NO_SUCH_TABLE --`), never a real one (%s): if the endpoint is "
                        "injectable, the real table is lost for everyone." % (_RULE, _REAL_DROP.search(text).group(0)))
    if tool in ("Write", "Edit"):
        return None
    cmd = str(inp.get("command") or "")
    if _DB_CLIENT.search(cmd):
        if _WRITE_SQL.search(cmd):
            return "deny", "%s: the DB is read with SELECT only; write / DDL statements are never allowed." % _RULE
        return "ask", "%s: this connects to the DB directly instead of `rt sql`. Run it only if the user asked." % _RULE
    if _HTTP_CLIENT.search(cmd) and _HTTP_WRITE.search(cmd):
        return "ask", ("%s: write request. Only endpoints whose handler you read and found read-only may be called; "
                       "never create or change data on the shared environment." % _RULE)
    why = _economy(tool, inp or {})
    if why:
        return "deny", why
    return None


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    try:
        res = decide(str(payload.get("tool_name") or ""), payload.get("tool_input"))
    except Exception:           # the hook runs on every shell call: never break one
        return 0
    if res:
        sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                            "permissionDecision": res[0],
                                                            "permissionDecisionReason": res[1]}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
