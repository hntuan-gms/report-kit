"""Preconditions on observed values (the `require:` block of a check).

These never decide whether the app is right or wrong - Claude does that by reading the
observations against the SRS / standard. They only decide whether the measurement itself is
usable: when a precondition fails the check is reported as NM ("không đo được") so nobody
judges the app from an empty or wrong observation (e.g. charts not rendered yet, tooltip read
from the wrong slice). Each spec is {op: arg, ...}; all ops must hold.

  equals / not_equals          value == arg
  contains / not_contains      substring (str) or member (list)
  contains_all                 every item of arg is contained
  regex / not_regex            str(value) matches arg (search)
  all_match / none_match       every / no item of a list matches the regex arg
  any_match                    at least one item matches
  min / max                    number, or length of a list / str
  length                       exact length
  empty / not_empty            true
  in                           value is one of arg
"""
import re


def _len_or_num(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    return len(v) if v is not None else 0


def _as_list(v):
    return v if isinstance(v, list) else ([] if v is None else [v])


def check(value, spec):
    """Returns list of failure messages (empty = pass)."""
    fails = []
    for op, arg in (spec or {}).items():
        ok = True
        if op == "equals":
            ok = value == arg
        elif op == "not_equals":
            ok = value != arg
        elif op == "contains":
            ok = (arg in value) if isinstance(value, (list, str)) else False
        elif op == "not_contains":
            ok = not ((arg in value) if isinstance(value, (list, str)) else False)
        elif op == "contains_all":
            ok = all((a in value) if isinstance(value, (list, str)) else False for a in _as_list(arg))
        elif op == "regex":
            ok = re.search(arg, "" if value is None else str(value)) is not None
        elif op == "not_regex":
            ok = re.search(arg, "" if value is None else str(value)) is None
        elif op == "all_match":
            items = _as_list(value); ok = bool(items) and all(re.search(arg, str(x)) for x in items)
        elif op == "none_match":
            ok = not any(re.search(arg, str(x)) for x in _as_list(value))
        elif op == "any_match":
            ok = any(re.search(arg, str(x)) for x in _as_list(value))
        elif op == "min":
            ok = _len_or_num(value) >= arg
        elif op == "max":
            ok = _len_or_num(value) <= arg
        elif op == "length":
            ok = _len_or_num(value) == arg
        elif op == "empty":
            ok = (not value) == bool(arg)
        elif op == "not_empty":
            ok = bool(value) == bool(arg)
        elif op == "in":
            ok = value in _as_list(arg)
        else:
            fails.append("unknown assertion op '%s'" % op); continue
        if not ok:
            fails.append("%s %r failed on %s" % (op, arg, _short(value)))
    return fails


def check_all(observations, specs):
    """specs: {observation name: {op: arg}} -> {name: [failures]} for the failing ones."""
    out = {}
    for name, spec in (specs or {}).items():
        if name not in observations:
            out[name] = ["observation '%s' was not recorded" % name]; continue
        f = check(observations[name], spec)
        if f:
            out[name] = f
    return out


def _short(v, n=160):
    s = repr(v)
    return s if len(s) <= n else s[:n] + "..."
