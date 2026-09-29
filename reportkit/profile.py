"""Load the project profile and the per-user settings / secrets.

Lookup order for the profile folder:
  1. --profile <dir> (or RK_PROFILE env var)
  2. walk up from the current directory until `.report-kit/project.yaml` is found

Layers merged on top of project.yaml (later wins):
  - <profile>/project.local.yaml      per-user overrides, git-ignored (tools_dir, work_root, ...)
  - ~/.report-kit/secrets.yaml        credentials, keyed by profile name - never inside a repo
  - RK_* environment variables        RK_LOGIN_USER, RK_LOGIN_PASSWORD, RK_DB_PASSWORD, RK_TOOLS_DIR ...

Strings may use {home}, {profile_dir}, {repo_root}, {tools_dir}.
"""
import copy
import json
import os
import re

import yaml

SECRETS_FILE = os.path.join(os.path.expanduser("~"), ".report-kit", "secrets.yaml")
SECRET_KEYS = ("login_user", "login_password", "login_type", "db_password")


class ProfileError(SystemExit):
    pass


def _deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def find_profile_dir(explicit=None, start=None):
    cand = explicit or os.environ.get("RK_PROFILE")
    if cand:
        cand = os.path.abspath(cand)
        if os.path.isfile(cand):
            cand = os.path.dirname(cand)
        if not os.path.exists(os.path.join(cand, "project.yaml")):
            raise ProfileError("No project.yaml in %s" % cand)
        return cand
    d = os.path.abspath(start or os.getcwd())
    while True:
        p = os.path.join(d, ".report-kit")
        if os.path.exists(os.path.join(p, "project.yaml")):
            return p
        nd = os.path.dirname(d)
        if nd == d:
            raise ProfileError("No .report-kit/project.yaml found above %s. Run `rt init` in the project root "
                               "or pass --profile <dir>." % (start or os.getcwd()))
        d = nd


class Profile(object):
    def __init__(self, profile_dir):
        self.dir = profile_dir
        with open(os.path.join(profile_dir, "project.yaml"), encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        local = os.path.join(profile_dir, "project.local.yaml")
        if os.path.exists(local):
            with open(local, encoding="utf-8") as f:
                data = _deep_merge(data, yaml.safe_load(f) or {})
        self.raw = data
        self.name = data.get("name") or os.path.basename(os.path.dirname(profile_dir))
        self.repo_root = os.path.abspath(os.path.join(profile_dir, data.get("repo_root", "..")))
        paths = data.get("paths", {})
        self.tools_dir = ""
        self.tools_dir = self.expand(os.environ.get("RK_TOOLS_DIR") or paths.get("tools_dir", ""))
        self.work_root = self.expand(os.environ.get("RK_WORK_ROOT") or paths.get("work_root", "{home}/report-kit-work/" + _slug(self.name)))
        self.code_root = self.expand(paths.get("code_root", "{repo_root}"))
        self._secrets = None

    # ---------------------------------------------------------------- helpers
    def expand(self, s):
        if not isinstance(s, str):
            return s
        s = (s.replace("{home}", os.path.expanduser("~")).replace("{profile_dir}", self.dir)
              .replace("{repo_root}", self.repo_root).replace("{tools_dir}", self.tools_dir or ""))
        return os.path.normpath(s) if (os.sep in s or "/" in s) and not s.startswith("http") else s

    def get(self, dotted, default=None):
        cur = self.raw
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def path(self, rel):
        """A file named in the profile: absolute, {tools_dir}/..., or relative to the profile dir."""
        rel = self.expand(rel)
        return rel if os.path.isabs(rel) else os.path.join(self.dir, rel)

    # ---------------------------------------------------------------- systems
    @property
    def systems(self):
        return self.raw.get("systems", {})

    def system(self, key):
        if key not in self.systems:
            raise ProfileError("Unknown system '%s'. Known: %s" % (key, ", ".join(self.systems)))
        s = dict(self.systems[key]); s["key"] = key
        return s

    def system_for_label(self, label):
        """Map the function list's subsystem text (e.g. 'Kiểm toán') to a system key."""
        label = (label or "").strip().lower()
        for k, s in self.systems.items():
            if any(label == m.lower() for m in s.get("match", [])) or label == k.lower():
                return k
        return next(iter(self.systems)) if len(self.systems) == 1 else None

    # ---------------------------------------------------------------- secrets
    def secrets(self):
        if self._secrets is None:
            sec = {}
            if os.path.exists(SECRETS_FILE):
                with open(SECRETS_FILE, encoding="utf-8") as f:
                    allp = yaml.safe_load(f) or {}
                sec.update(allp.get(self.name) or {})
            for k in SECRET_KEYS:
                v = os.environ.get("RK_" + k.upper())
                if v:
                    sec[k] = v
            self._secrets = sec
        return self._secrets

    def secret(self, key, required=True):
        v = self.secrets().get(key)
        if required and not v:
            raise ProfileError("Missing secret '%s' for profile '%s'. Add it under '%s:' in %s or set RK_%s. "
                               "Never put it in the repo." % (key, self.name, self.name, SECRETS_FILE, key.upper()))
        return v

    # ---------------------------------------------------------------- workspace
    def workspace(self, code):
        return Workspace(self, code)


def _slug(s):
    s = re.sub(r"[\[\]#]", "", str(s)).strip()
    return re.sub(r"[^\w.-]+", "_", s, flags=re.UNICODE).strip("_") or "x"


def norm_code(code):
    """'[# 1E_117]', '1E117', '1e_117' -> '1E_117' when it looks like the usual pattern; else slug."""
    c = re.sub(r"[\[\]#\s]", "", str(code)).upper()
    m = re.match(r"^(\d+[A-Z])_?(\d+)$", c)
    return "%s_%s" % (m.group(1), m.group(2)) if m else _slug(c)


class Workspace(object):
    """<work_root>/<CODE>/ - everything produced for one report, kept between sessions.

    inputs/            function.json, srs_N.txt + images, standard.txt, previous workbook dumps
    brief.md           short summary of the inputs + code trace (read this first)
    trace.json         code trace (cached by git commit)
    probe.json/.md     data traps found
    checks.yaml        observation / comparison steps (written by Claude)
    runs/<id>/         one folder per `rt check`: <id>.json, summary.json, summary.md, shots/
    build_workbook.py  the builder script (written by Claude)
    state.json         which steps are done
    """

    def __init__(self, profile, code):
        self.profile = profile
        self.code = norm_code(code)
        self.dir = os.path.join(profile.work_root, self.code)
        os.makedirs(self.dir, exist_ok=True)

    def p(self, *parts):
        path = os.path.join(self.dir, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def state(self):
        f = os.path.join(self.dir, "state.json")
        if os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                return json.load(fh)
        return {"code": self.code, "steps": {}}

    def mark(self, step, **info):
        import datetime as _dt
        st = self.state()
        st["steps"][step] = dict(info, at=_dt.datetime.now().isoformat(timespec="seconds"))
        with open(os.path.join(self.dir, "state.json"), "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=1, default=str)

    def done(self, step):
        return step in self.state()["steps"]

    def runs_dir(self):
        d = os.path.join(self.dir, "runs"); os.makedirs(d, exist_ok=True)
        return d

    def latest_run(self):
        d = self.runs_dir()
        runs = sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x)))
        return os.path.join(d, runs[-1]) if runs else None


def load(profile_dir=None):
    return Profile(find_profile_dir(profile_dir))
