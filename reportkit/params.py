"""Template variables for checks, so a check never hard-codes the run date.

  {today}              28/09/2026   (format with {today:%Y-%m-%d})
  {current_year}       2026         arithmetic: {current_year-1}, {current_year-4}
  {current_month}      9
  {prev_month}         8            month of today minus one month ({prev_month_year} = its year)
  {login_user}         the account used for the run (for data-permission SQL)
  {<var>}              any value from the check file's `vars:` or a matrix value
Unknown names are left untouched, so SQL like "{fn}" is not mangled.
"""
import datetime as _dt
import re

_TOKEN = re.compile(r"\{([a-z_][a-z0-9_]*)([+-]\d+)?(?::([^}]+))?\}")


def base_vars(today=None):
    t = today or _dt.date.today()
    first = t.replace(day=1); prev = first - _dt.timedelta(days=1)
    return {"today": t, "current_year": t.year, "current_month": t.month, "current_day": t.day,
            "prev_month": prev.month, "prev_month_year": prev.year}


def render(value, vars_):
    if isinstance(value, str):
        def rep(m):
            name, off, fmt = m.group(1), m.group(2), m.group(3)
            if name not in vars_:
                return m.group(0)
            v = vars_[name]
            if off:
                if isinstance(v, _dt.date):
                    v = v + _dt.timedelta(days=int(off))
                else:
                    v = int(v) + int(off)
            if isinstance(v, _dt.date):
                return v.strftime(fmt or "%d/%m/%Y")
            return format(v, fmt) if fmt else str(v)
        out = _TOKEN.sub(rep, value)
        # a string that was exactly one numeric token becomes a number (useful for API params / binds)
        if _TOKEN.fullmatch(value) and re.fullmatch(r"-?\d+", out):
            return int(out)
        return out
    if isinstance(value, list):
        return [render(v, vars_) for v in value]
    if isinstance(value, dict):
        return {k: render(v, vars_) for k, v in value.items()}
    return value


_RANGE = re.compile(r"^\s*(-?\d+)\s*\.\.\s*(-?\d+)\s*$")


def _values(vals, vars_):
    """Rendered matrix values; a string 'A..B' (after rendering) is the inclusive integer range A to B, in that order."""
    out = []
    for v in (vals if isinstance(vals, list) else [vals]):
        r = render(v, vars_)
        m = _RANGE.match(r) if isinstance(r, str) else None
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out += list(range(a, b + 1)) if a <= b else list(range(a, b - 1, -1))
        else:
            out.append(r)
    return out


def expand_matrix(matrix, vars_):
    """Cartesian product of the matrix values.

    {year: ["{current_year}", "{current_year-1}"]} -> [{year: 2026}, {year: 2025}]
    {year: "{current_year}..2016"}                 -> [{year: 2026}, {year: 2025}, ..., {year: 2016}]   (every dropdown value)
    """
    combos = [{}]
    for k, vals in (matrix or {}).items():
        combos = [dict(c, **{k: v}) for c in combos for v in _values(vals, vars_)]
    return combos
