"""SQL guard carried over from the original skill (db_readonly.py): only SELECT / WITH, no write/DDL
keyword outside string literals, one statement per call. db.py also runs every query inside a
READ ONLY transaction. Required by the project's DB safety rules (DB access is SELECT only).
"""
import re

_FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|CALL|EXEC|EXECUTE|"
                        r"BEGIN|DECLARE|COMMIT|ROLLBACK|LOCK|RENAME|FLASHBACK|PURGE)\b")


class Refused(Exception):
    pass


def check_sql(sql):
    body = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S).strip()
    head = body.upper()
    if not (head.startswith("SELECT") or head.startswith("WITH") or head.startswith("(")):
        raise Refused("only SELECT / WITH statements are allowed")
    no_str = re.sub(r"'(?:[^']|'')*'", "''", head)
    if _FORBIDDEN.search(no_str):
        raise Refused("statement contains a write / DDL keyword")
    if ";" in no_str.rstrip("; \n"):
        raise Refused("only one statement per call")
    return body.rstrip("; \n")
