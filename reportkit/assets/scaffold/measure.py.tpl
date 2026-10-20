# -*- coding: utf-8 -*-
"""Read-only measurement of the screen group hosted by workspace {code}. Run: python measure_{code}.py
Every number a case states must come from here or from `rt check`, measured right before the workbook is written
(dev data is live and other people edit it while you work)."""
import json
from reportkit.measure import Measure, diff_sets

m = Measure("{code}", system="{system}")        # schema / login come from the profile; pass schema="..." to override
R = {}

# ---- 1. scope and grid against an independent rule written in plain words (never the app's own query)
# sc, rows, body = m.all_rows("/<api>/<list>", {"sortBy": "...", "sortDir": "DESC"})          # ONE big page = stable reference
# scope = m.scope_ids()                                                                          # data permission of the login
# exp = {int(r["ID"]) for r in m.sql("SELECT ID FROM <table> WHERE <rule> AND ID IN (<permission subquery>)")}
# R["scope"] = diff_sets([r["id"] for r in rows], exp)

# ---- 2. every filter and every dropdown value (one entry per value); accent / case / % _ / blanks for text boxes
# for term in ("abc", "ABC", "âbc", "%", "_", "  abc  "):
#     sc, rows, _ = m.all_rows("/<api>/<list>", {"<filter>": term})
#     exp = {int(r["ID"]) for r in m.sql("SELECT ID FROM <table> WHERE LOWER(<col>) LIKE '%'||LOWER(:t)||'%'", t=term)}
#     R.setdefault("text", []).append((term, diff_sets([r["id"] for r in rows], exp)))

# ---- 3. paging and sort: duplicates / missing rows across pages are a real finding on any list
# R["paging"] = m.paging_stability("/<api>/<list>", {"sortBy": "..."}, sizes=(10, 25, 50), pages=6)

# ---- 4. export against the grid (same filter), empty export (template placeholders?), number / date formats
# res = m.download("/<api>/<export>", {"<filter>": "..."}, tag="all")

# ---- 5. injection strings on every read-only endpoint the screen calls (200 with 0 rows or a type error, no query text)
# for k in ("<filter1>", "<filter2>"):
#     for v in ("' OR '1'='1", "'; DROP TABLE X; --", "x' UNION SELECT NULL FROM DUAL --"):
#         sc, body = m.api("/<api>/<list>", {"page": 0, "size": 5, k: v})

# ---- 6. data permission outside the scope: ids that exist but are not in m.scope_ids()
# out = [i for i in all_ids if i not in scope]; for i in out: m.api("/<api>/<detail>/%d" % i)

print(m.save("m_{code}.json", R))
print(json.dumps(R, ensure_ascii=False, default=str)[:4000])
