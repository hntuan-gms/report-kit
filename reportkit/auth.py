"""Login strategies. The session is saved per system and reused by http.py and the UI runner.

keycloak_sso (profile `auth:` block):
    choose_button: {internal: "<text>", external: "<text>"}   # button on the landing page, optional
    username: "#username"   password: "#password"   submit: "#kc-login"
    profile_endpoint: /auth/profile                            # GET, used to verify the session (a system may override it)
    profile_fields: {login: loginName, name: fullName, super_admin: isSuperAdmin}

Lessons built in (1E_117, 28/09/2026):
  - never wait for "networkidle": SSO and SPA pages keep background requests open;
  - the SSO URL contains redirect_uri=<web>, so wait for a URL that *starts with* the web base.
"""
import contextlib
import os
import pickle
import time

from . import http


LOCK_POLL_S = 2      # how often a waiting process looks at the login lock (a login takes 15-60 s)


@contextlib.contextmanager
def _login_lock(profile, system, wait_s=150, stale_s=240):
    """One SSO login at a time per system: parallel agents whose session expired together would otherwise all log in
    and overwrite each other's session files. A lock older than `stale_s` (a killed login) is taken over."""
    state, _ = http.session_paths(profile, system)
    lock = state + ".lock"
    end = time.time() + wait_s
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except (FileExistsError, PermissionError):
            # PermissionError: Windows answers so while another process is deleting the lock ("delete pending")
            try:
                if time.time() - os.path.getmtime(lock) > stale_s:
                    os.remove(lock); continue
            except OSError:
                time.sleep(0.05)
                continue
            if time.time() > end:
                raise SystemExit("another rt process has been logging in to %s for over %d s; run the command again" % (system, wait_s))
            time.sleep(LOCK_POLL_S)
    try:
        yield
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def login(profile, system, login_type=None, headless=True):
    with _login_lock(profile, system):
        return _login(profile, system, login_type, headless)


def _login(profile, system, login_type=None, headless=True):
    state, _ = http.session_paths(profile, system)
    with open(os.path.join(os.path.dirname(state), "login.log"), "a", encoding="utf-8") as f:
        f.write("%s pid %d SSO login %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), os.getpid(), system))
    return _login_browser(profile, system, login_type, headless)


def _login_browser(profile, system, login_type=None, headless=True):
    import requests
    from playwright.sync_api import sync_playwright
    a = profile.get("auth", {}) or {}
    if a.get("type", "keycloak_sso") != "keycloak_sso":
        raise SystemExit("auth.type %s is not implemented" % a.get("type"))
    sysd = profile.system(system)
    web = sysd["web"].rstrip("/")
    login_type = login_type or profile.secrets().get("login_type") or a.get("default_type", "external")
    state, jar_path = http.session_paths(profile, system)
    with sync_playwright() as p:
        b = p.chromium.launch(headless=headless)
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale=profile.get("ui.locale", "vi-VN"))
        pg = ctx.new_page()
        pg.goto(web + "/", wait_until="load", timeout=60000)
        btn = (a.get("choose_button") or {}).get(login_type)
        if btn:
            pg.get_by_text(btn).click(timeout=60000)
        pg.locator(a.get("username", "#username")).fill(profile.secret("login_user"), timeout=60000)
        pg.locator(a.get("password", "#password")).fill(profile.secret("login_password"))
        pg.locator(a.get("submit", "#kc-login")).click()
        pg.wait_for_url(lambda u: u.startswith(web), timeout=60000)
        pg.wait_for_function("() => location.pathname !== '/auth/sign-in'", timeout=60000)
        pg.wait_for_timeout(3000)
        ctx.storage_state(path=state)
        jar = requests.cookies.RequestsCookieJar()
        for c in ctx.cookies():
            jar.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
        with open(jar_path, "wb") as f:
            pickle.dump(jar, f)
        b.close()
    http.reset(profile, system)
    who = whoami(profile, system)
    if not who.get("ok"):
        raise SystemExit("Login finished but the session is not valid (%s). Check the auth selectors in project.yaml." % who)
    return who


def whoami(profile, system):
    a = profile.get("auth", {}) or {}
    # a system may override the endpoint (the audit API serves the profile at /audit/profile)
    ep = (profile.get("systems", {}).get(system, {}) or {}).get("profile_endpoint") or a.get("profile_endpoint")
    if not ep:
        return {"ok": True, "note": "no profile_endpoint configured"}
    _, jar = http.session_paths(profile, system)
    if not os.path.exists(jar):
        return {"ok": False, "status": "no session"}
    sc, body = http.json_call(profile, system, "GET", ep)
    if sc != 200 or not isinstance(body, dict):
        return {"ok": False, "status": sc}
    d = body.get("data", body) or {}
    f = a.get("profile_fields", {}) or {}
    return {"ok": True, "login": d.get(f.get("login", "loginName")), "name": d.get(f.get("name", "fullName")),
            "super_admin": d.get(f.get("super_admin", "isSuperAdmin"))}


def ensure(profile, system, login_type=None):
    """Reuse the saved session when it is still valid; log in again otherwise."""
    w = whoami(profile, system)
    if w.get("ok"):
        return w
    with _login_lock(profile, system):
        http.reset(profile, system)
        w = whoami(profile, system)          # another process may have just logged in while this one waited
        return w if w.get("ok") else _login(profile, system, login_type)
