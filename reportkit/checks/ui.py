"""UI check = declared steps + observations. No verdicts: Claude reads the observations and screenshots
and judges them against the SRS / standard (the kit only records what the screen showed).

  - id: U05
    title: Tooltip biểu đồ xếp hạng
    page: /dashboard                    # opened in a fresh browser context (no state leaks between checks)
    lang: vi                            # optional; en switches with the profile's ui.lang selectors
    routes:                             # optional network stubs, only for this check
      - {pattern: "**/monthly-summary**", status: 500, body: '{"message":"Simulated"}'}
    ready: {selector: "apx-chart svg", min: 4, timeout: 20000}     # precondition, else NM
    steps:
      - hover: {selector: ".apexcharts-pie-area", nth: 0}
      - observe: {tip: {text: ".apexcharts-tooltip.apexcharts-active"}}
      - click: {selector: "...", force: true}
      - select: {selector: select, nth: 1, label: "2025"}
      - press: Enter
      - wait: 2000
      - set_lang: en
      - zoom: 150
      - tab: 16                         # records the focus order as observation 'focus_order'
      - expect_download: {click: {selector: "..."}, timeout: 6000, as: dl}
      - offline: true
      - reload: true
      - screenshot: after_click
    observe:                            # recorded at the end
      titles: {texts: ".apexcharts-title-text"}
      charts: {count: "apx-chart svg"}
      calls: requests                   # API calls made during the check (method, path, status)
      toasts: toasts
      overflow: {js: "()=>document.documentElement.scrollWidth>window.innerWidth+2"}
    require: {tip: {regex: "^Hạng A"}}  # preconditions on observations, else NM

Observation kinds: text, texts, count, attr {selector, name}, value, js, requests, toasts, url.
"""
import os
import re

from .. import http


def _obs(pg, name, spec, st):
    if spec == "requests":
        return list(st["calls"])
    if spec == "toasts":
        return _toasts(pg, st["profile"])
    if spec == "url":
        return pg.url
    kind, arg = next(iter(spec.items()))
    if kind == "text":
        loc = pg.locator(arg)
        return loc.first.inner_text(timeout=3000).strip() if loc.count() else None
    if kind == "texts":
        return [t.strip() for t in pg.eval_on_selector_all(arg, "els=>els.map(e=>e.textContent)")]
    if kind == "count":
        return pg.locator(arg).count()
    if kind == "attr":
        loc = pg.locator(arg["selector"])
        return loc.first.get_attribute(arg["name"]) if loc.count() else None
    if kind == "value":
        loc = pg.locator(arg)
        return loc.first.input_value() if loc.count() else None
    if kind == "js":
        return pg.evaluate(arg)
    raise ValueError("unknown observation kind '%s' in %s" % (kind, name))


def _toasts(pg, profile, wait=1500):
    sel = profile.get("ui.toast", "[class*=toast-body], .toast-message, [class*=toast] [class*=message]")
    try:
        pg.wait_for_selector(sel, timeout=wait)
    except Exception:
        return []
    seen = []
    for t in pg.locator(sel).all_inner_texts():
        t = " ".join(t.split())
        if t and t not in seen:
            seen.append(t)
    return seen


def _loc(pg, spec):
    if isinstance(spec, str):
        return pg.locator(spec).first
    if "text" in spec:
        loc = pg.get_by_text(spec["text"], exact=spec.get("exact", False))
    else:
        loc = pg.locator(spec["selector"])
    return loc.nth(spec.get("nth", 0))


def _set_lang(pg, profile, lang):
    ui = profile.get("ui.lang", {}) or {}
    if not ui:
        raise ValueError("profile has no ui.lang selectors")
    pg.locator(ui["open"]).click(); pg.wait_for_timeout(500)
    pg.locator(ui[lang]).click(); pg.wait_for_timeout(ui.get("settle_ms", 3000))


def _route(pg, r):
    status, body, ctype = r.get("status", 200), r.get("body", ""), r.get("content_type", "application/json")
    if r.get("abort"):
        pg.route(r["pattern"], lambda route: route.abort())
    else:
        pg.route(r["pattern"], lambda route: route.fulfill(status=status, body=body, content_type=ctype))


def _step(pg, step, st, shots):
    kind, arg = next(iter(step.items()))
    profile = st["profile"]
    if kind == "hover":
        _loc(pg, arg).hover(force=arg.get("force", True) if isinstance(arg, dict) else True); pg.wait_for_timeout(600)
    elif kind == "click":
        _loc(pg, arg).click(force=arg.get("force", False) if isinstance(arg, dict) else False); pg.wait_for_timeout(800)
    elif kind == "select":
        loc = pg.locator(arg["selector"]).nth(arg.get("nth", 0))
        loc.select_option(label=str(arg["label"])) if "label" in arg else loc.select_option(value=str(arg["value"]))
        pg.wait_for_timeout(arg.get("settle_ms", 3000))
    elif kind == "fill":
        _loc(pg, arg).fill(str(arg["text"]))
    elif kind == "press":
        pg.keyboard.press(arg); pg.wait_for_timeout(1500)
    elif kind == "wait":
        pg.wait_for_timeout(int(arg))
    elif kind == "wait_for":
        pg.wait_for_selector(arg["selector"], timeout=arg.get("timeout", 15000))
    elif kind == "set_lang":
        _set_lang(pg, profile, arg)
    elif kind == "zoom":
        pg.evaluate("z=>document.body.style.zoom=z+'%'", int(arg)); pg.wait_for_timeout(1200)
    elif kind == "tab":
        order = []
        for _ in range(int(arg)):
            pg.keyboard.press("Tab")
            order.append(pg.evaluate("()=>{const e=document.activeElement;return e.tagName+':'+(e.innerText||e.value||e.getAttribute('aria-label')||'').trim().slice(0,30)}"))
        st["obs"]["focus_order"] = order
    elif kind == "route":
        _route(pg, arg)
    elif kind == "offline":
        st["ctx"].set_offline(bool(arg))
    elif kind == "reload":
        try:
            pg.reload(wait_until="load", timeout=30000)
        except Exception as e:
            st["obs"].setdefault("errors", []).append("reload: " + str(e).splitlines()[0][:150])
        pg.wait_for_timeout(st["settle_ms"])
    elif kind == "goto":
        pg.goto(st["web"] + arg, wait_until="load"); pg.wait_for_timeout(st["settle_ms"])
    elif kind == "expect_download":
        name = arg.get("as", "download"); n0 = len(st["calls"])
        try:
            with pg.expect_download(timeout=arg.get("timeout", 8000)) as d:
                _loc(pg, arg["click"]).click(force=arg["click"].get("force", False) if isinstance(arg["click"], dict) else False)
            p = os.path.join(shots, "%s_%s" % (st["id"], d.value.suggested_filename)); d.value.save_as(p)
            st["obs"][name] = {"downloaded": True, "file": p, "name": d.value.suggested_filename}
        except Exception as e:
            st["obs"][name] = {"downloaded": False, "error": str(e).splitlines()[0][:150], "calls": st["calls"][n0:]}
    elif kind == "screenshot":
        p = os.path.join(shots, "%s_%s.png" % (st["id"], arg)); pg.screenshot(path=p, full_page=True)
        st["obs"].setdefault("screenshots", []).append(p)
    elif kind == "observe":
        for name, spec in arg.items():
            st["obs"][name] = _obs(pg, name, spec, st)
    elif kind == "js":
        pg.evaluate(arg)
    else:
        raise ValueError("unknown step '%s'" % kind)


def run(profile, system, check, browser, run_dir):
    """Runs one UI check in a fresh context. Returns {status: OBS|NM|ERR, observations, ...}."""
    from .assertions import check_all
    sysd = profile.system(system)
    web = sysd["web"].rstrip("/")
    api_marker = profile.get("ui.api_marker", "/api/")
    state, _ = http.session_paths(profile, system)
    shots = os.path.join(run_dir, "shots"); os.makedirs(shots, exist_ok=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale=profile.get("ui.locale", "vi-VN"),
                              storage_state=state if os.path.exists(state) else None, accept_downloads=True)
    pg = ctx.new_page()
    st = {"profile": profile, "calls": [], "obs": {}, "ctx": ctx, "id": check["id"], "web": web,
          "settle_ms": int(check.get("settle_ms", profile.get("ui.settle_ms", 6000)))}
    pg.on("response", lambda r: st["calls"].append([r.request.method, re.sub(r"^.*?/api/v\d+", "", r.url)[:140], r.status])
          if api_marker in r.url else None)
    res = {"id": check["id"]}
    try:
        for r in check.get("routes", []) or []:
            _route(pg, r)
        pg.goto(web + check.get("page", "/"), wait_until="load", timeout=60000)
        pg.wait_for_timeout(st["settle_ms"])
        if check.get("lang") == "en":
            _set_lang(pg, profile, "en")
        ready = check.get("ready")
        if ready:
            n = pg.locator(ready["selector"]).count()
            if n < ready.get("min", 1):
                try:
                    pg.wait_for_function("([s,m])=>document.querySelectorAll(s).length>=m", arg=[ready["selector"], ready.get("min", 1)],
                                         timeout=ready.get("timeout", 15000))
                except Exception:
                    pass
                n = pg.locator(ready["selector"]).count()
            if n < ready.get("min", 1):
                p = os.path.join(shots, "%s_not_ready.png" % check["id"]); pg.screenshot(path=p, full_page=True)
                res.update(status="NM", reason="page not ready: %d x '%s' (need %d)" % (n, ready["selector"], ready.get("min", 1)),
                           observations=st["obs"], screenshot=p)
                return res
        for s in check.get("steps", []) or []:
            _step(pg, s, st, shots)
        for name, spec in (check.get("observe") or {}).items():
            st["obs"][name] = _obs(pg, name, spec, st)
        final = os.path.join(shots, "%s_final.png" % check["id"]); pg.screenshot(path=final, full_page=True)
        st["obs"].setdefault("screenshots", []).append(final)
        pre = check_all(st["obs"], check.get("require"))
        if pre:
            res.update(status="NM", reason="precondition failed: %s" % pre, observations=st["obs"]); return res
        res.update(status="OBS", observations=st["obs"])
    except Exception as e:
        try:
            p = os.path.join(shots, "%s_error.png" % check["id"]); pg.screenshot(path=p, full_page=True)
        except Exception:
            p = None
        res.update(status="ERR", reason=str(e).splitlines()[0][:300], observations=st["obs"], screenshot=p)
    finally:
        ctx.close()
    return res
