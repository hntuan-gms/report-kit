"""Read-only measuring helpers for the scripts written in a report workspace (measure_*.py).

    from reportkit.measure import Measure
    m = Measure("2B_18", system="audit", schema="AUDIT03_DEV")
    sc, rows, body = m.rows("/audit/af-profiles", {"page": 0, "size": 3000})
    scope = m.scope_ids()
    m.save("m1.json", result)

Why a module and not `rt api` / `rt sql` in a shell:
  - Git Bash rewrites a leading "/" in arguments, so `rt api GET /x/y` can become a Windows path (404 from nginx).
    Calling the API from Python does not.
  - Comparing thousands of rows, paging, or trying 30 filter values is a loop, not one command.
Only call endpoints whose handler you have read and found read-only. SELECT only (the kit refuses anything else).
"""
import json
import os

from . import db, http
from . import profile as P


class Measure(object):
    def __init__(self, code, system=None, schema=None, login=None, profile=None):
        self.prof = profile or P.load(os.environ.get("RK_PROFILE"))
        self.ws = self.prof.workspace(code)
        self.system = system or next(iter(self.prof.systems))
        users = self.prof.get("db.users") or {}
        self.schema = schema or users.get(self.system) or "default"
        self.login = login or self.prof.secrets().get("login_user")

    # ------------------------------------------------------------------ HTTP
    def api(self, path, params=None, method="GET", body=None, headers=None):
        """(status, json or first 600 chars of text). The saved login session is used."""
        r = http.call(self.prof, self.system, method, path, params=params, body=body, headers=headers)
        ct = r.headers.get("Content-Type", "")
        try:
            j = r.json() if "json" in ct else r.text[:600]
        except Exception:
            j = r.text[:600]
        return r.status_code, j

    def rows(self, path, params=None, key="data.content", method="GET", body=None):
        sc, j = self.api(path, params, method, body)
        return sc, (http.dig(j, key) if isinstance(j, dict) else None), j

    def all_rows(self, path, params=None, key="data.content", page_param="page", size_param="size", size=3000):
        """Every row of a paged list in ONE request (size 3000). A reference that is not affected by an unstable sort.
        Compare it with `paging_stability` to find lists whose pages repeat or lose rows."""
        prm = dict(params or {}); prm.update({page_param: 0, size_param: size})
        return self.rows(path, prm, key)

    def paging_stability(self, path, params=None, key="data.content", sizes=(10, 25, 50), pages=6, page_param="page", size_param="size",
                         id_field="id"):
        """Walk the first `pages` pages at several page sizes and count distinct rows.

        {size: {rows, unique, same_as_reference}}: unique < rows means the page boundary repeats rows (sort without a
        tie-break key); same_as_reference False means the order changes with the page size. A real finding on any list.
        """
        sc, ref, _ = self.all_rows(path, params, key, page_param, size_param)
        ref_ids = [r.get(id_field) for r in ref or []]
        out = {}
        for size in sizes:
            got = []
            for p in range(pages):
                prm = dict(params or {}); prm.update({page_param: p, size_param: size})
                _, rr, _ = self.rows(path, prm, key)
                got += [r.get(id_field) for r in rr or []]
            out[size] = {"rows": len(got), "unique": len(set(got)), "same_as_reference": got == ref_ids[: len(got)]}
        return out

    def download(self, path, params=None, method="GET", body=None, tag=None):
        return http.download(self.prof, self.system, method, path, params=params, body=body, out_dir=self.ws.p("exports"), tag=tag)

    # ------------------------------------------------------------------ SQL (SELECT only)
    def sql(self, q, **binds):
        return db.q(self.prof, q, binds or None, self.schema)

    def scope_ids(self, table="LOGIN_PERMISSION_BY_CODE", id_col="AF_PROFILE_ID", login_col="LOGIN_NAME"):
        """Ids the login may see (data permission). Join to the data table: the permission table can hold ids that no
        longer exist (orphans), so its row count is not the scope."""
        q = "SELECT DISTINCT %s FROM %s WHERE %s = :l AND %s IS NOT NULL" % (id_col, table, login_col, id_col)
        return {int(r[id_col]) for r in self.sql(q, l=self.login)}

    # ------------------------------------------------------------------ output
    def save(self, name, obj):
        p = self.ws.p(name)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1, default=str)
        return p


def diff_sets(got, expected, sample=6):
    """{'got', 'expected', 'extra', 'missing'} for two collections of ids; extra / missing are sorted samples."""
    g, e = set(got), set(expected)
    return {"got": len(g), "expected": len(e), "extra": sorted(g - e)[:sample], "missing": sorted(e - g)[:sample]}
