"""Read-only Oracle access (SELECT only, READ ONLY transaction). Other drivers can be added per profile.

Direct DB access still needs the user's OK for the session - the skill asks in chat before any query.
"""
import warnings

from . import safety

warnings.filterwarnings("ignore")
_conns = {}


def _conn(profile, schema_key):
    k = (profile.name, schema_key)
    if k not in _conns:
        import oracledb
        db = profile.get("db", {})
        user = (db.get("users") or {}).get(schema_key) or schema_key
        _conns[k] = oracledb.connect(user=user, password=profile.secret("db_password"), dsn=db["dsn"])
        # a slow query must not hang the run (the EXISTS twin check took >3 min on 1E_117)
        _conns[k].call_timeout = int(db.get("call_timeout_ms", 120000))
    return _conns[k]


def q(profile, sql, params=None, schema="default"):
    sql = safety.check_sql(sql)
    if schema == "default":
        schema = profile.get("db.default_schema") or next(iter(profile.get("db.users", {"x": 1})))
    con = _conn(profile, schema)
    c = con.cursor()
    c.execute("SET TRANSACTION READ ONLY")
    try:
        c.execute(sql, params or {})
        cols = [d[0] for d in c.description]
        return [dict(zip(cols, [v.read() if hasattr(v, "read") else v for v in r])) for r in c.fetchall()]
    finally:
        con.rollback()


def columns(profile, table, schema="default"):
    rows = q(profile, "SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME = :t ORDER BY COLUMN_ID", {"t": table.upper()}, schema)
    return [r["COLUMN_NAME"] for r in rows]


def tables(profile, schema="default"):
    return [r["TABLE_NAME"] for r in q(profile, "SELECT TABLE_NAME FROM USER_TABLES UNION SELECT VIEW_NAME FROM USER_VIEWS", None, schema)]
