"""Data check: expected rows from an independent SQL (written from the SRS + standard, never from the
report's own view) vs the rows the app returns (JSON API or exported Excel). Cell by cell.

  - id: D01
    title: Số lượng tin theo tháng
    matrix: {year: ["{current_year}", "{current_year-1}"]}     # optional, one comparison per combo
    actual:
      api: {method: GET, path: /x/monthly-summary, params: {year: "{year}"}, rows: data.data}
      # or export: {method: POST, path: /report/R018/export, body: {filters: {...}},
      #             parse: records | grid, header_rows: 1, key_col: 1, first_value_col: 3, header_marker: STT}
      key: [thang]                 # fields that identify a row (records/api); grid uses the row key + header
      fields: {DK: slDinhKy, BT: slBatThuong}          # logical name -> field in the actual row
    expected:
      sql: "SELECT EXTRACT(MONTH FROM d) M, ... WHERE y = :y"
      binds: {y: "{year}"}
      schema: ids                  # profile db.users key (default: db.default_schema)
      key: [M]
      fields: {DK: DK, BT: BT}
      missing_as: 0                # value expected for a key the SQL does not return (e.g. months with no rows)
    variants:                      # optional alternative rules; a wrong cell equal to a variant is attributed to it
      vi_only: {sql: "...", binds: {...}}      # key / fields default to expected's
    compare: {numeric: true, tolerance: 0.005}
    require: {actual_rows: {min: 1}}         # otherwise status NM (not measurable)
"""
from .. import db, excel, http
from ..params import render
from .assertions import check as check_value


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _same(a, e, cmp):
    if a is None and e is None:
        return True
    if cmp.get("numeric", True):
        na, ne = _num(a), _num(e)
        if na is not None and ne is not None:
            return abs(na - ne) <= float(cmp.get("tolerance", 0))
    norm = lambda x: "" if x is None else " ".join(str(x).split())
    return norm(a) == norm(e)


def _keyed(rows, key, fields):
    out = {}
    for r in rows:
        k = tuple(str(r.get(x)) for x in key) if key else ("*",)
        out[k] = {logical: r.get(src) for logical, src in fields.items()}
    return out


def _actual(profile, system, spec, vars_, run_dir, tag):
    spec = render(spec, vars_)
    if "api" in spec:
        a = spec["api"]
        sc, body = http.json_call(profile, system, a.get("method", "GET"), a["path"], a.get("params"), a.get("body"))
        if sc != 200:
            return None, {"http_status": sc, "body": str(body)[:500]}
        rows = http.dig(body, a.get("rows"))
        rows = rows if isinstance(rows, list) else ([rows] if rows else [])
        return _keyed(rows, spec.get("key", []), spec["fields"]), {"http_status": sc, "rows": len(rows)}
    if "export" in spec:
        e = spec["export"]
        r = http.download(profile, system, e.get("method", "POST"), e["path"], e.get("params"), e.get("body"),
                          out_dir=run_dir, tag=tag)
        if "path" not in r:
            return None, r
        sh = excel.read(r["path"], header_marker=e.get("header_marker", "STT"))
        if e.get("parse", "records") == "grid":
            g = excel.grid_by_key(sh, e.get("key_col", 1), e.get("first_value_col"), e.get("header_rows", 1))
            rows = {}
            for (rk, col), v in g.items():
                rows.setdefault((rk,), {})[col] = v
            fields = spec.get("fields")
            keyed = {k: ({lg: v.get(src) for lg, src in fields.items()} if fields else v) for k, v in rows.items()}
        else:
            recs = excel.records(sh, e.get("header_rows", 1), e.get("key_col", 1))
            keyed = _keyed(recs, spec.get("key", []), spec["fields"])
        return keyed, {"file": r["path"], "fname": r.get("fname"), "meta": {k: str(v) for k, v in sh["meta"].items()}, "rows": len(keyed)}
    raise ValueError("actual needs 'api' or 'export'")


def _expected(profile, spec, vars_, base=None):
    spec = render(dict(base or {}, **spec), vars_)
    rows = db.q(profile, spec["sql"], spec.get("binds"), spec.get("schema", "default"))
    return _keyed(rows, spec.get("key", []), spec["fields"]), len(rows)


def run(profile, system, check, vars_, run_dir):
    cmp = check.get("compare", {}) or {}
    act, meta = _actual(profile, system, check["actual"], vars_, run_dir, "%s_%s" % (check["id"], _tag(vars_, check)))
    res = {"vars": {k: vars_[k] for k in (check.get("matrix") or {})}, "actual_meta": meta}
    if act is None:
        res.update(status="ERR", reason="actual source failed: %s" % meta); return res
    req = check.get("require", {}) or {}
    if "actual_rows" in req and check_value(len(act), req["actual_rows"]):
        res.update(status="NM", reason="precondition actual_rows %s not met (got %d)" % (req["actual_rows"], len(act))); return res
    exp, n_exp = _expected(profile, check["expected"], vars_)
    variants = {}
    for vname, vspec in (check.get("variants") or {}).items():
        try:
            variants[vname] = _expected(profile, vspec, vars_, base={k: v for k, v in check["expected"].items() if k in ("key", "fields", "schema", "binds")})[0]
        except Exception as ex:
            variants[vname] = {"_error": str(ex)[:200]}
    missing_as = check["expected"].get("missing_as", "__none__")
    cells, mism, extra = 0, [], []
    for k, arow in act.items():
        erow = exp.get(k)
        if erow is None:
            if missing_as == "__none__":
                if any(v not in (None, "", 0, "0") for v in arow.values()):
                    extra.append({"key": list(k), "actual": arow})
                continue
            erow = {f: missing_as for f in arow}
        for f, av in arow.items():
            ev = erow.get(f)
            cells += 1
            if not _same(av, ev, cmp):
                hit = [vn for vn, vrows in variants.items() if "_error" not in vrows and _same(av, (vrows.get(k) or {}).get(f, missing_as if missing_as != "__none__" else None), cmp)]
                mism.append({"key": list(k), "field": f, "actual": av, "expected": ev, "explained_by": hit})
    missing = [list(k) for k in exp if k not in act]
    res.update(cells=cells, mismatches=mism, extra_in_actual=extra, missing_in_actual=missing,
               expected_rows=n_exp, status="MATCH" if not mism and not extra and not missing else "DIFF")
    return res


def _tag(vars_, check):
    return "_".join("%s%s" % (k, vars_[k]) for k in (check.get("matrix") or {})) or "run"
