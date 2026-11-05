"""Behaviour review of a /report-test session: what each agent cost, where the cost went, and every known bad habit.

    python tools/agent_review.py --project "C:/Users/me/Documents/AI test v2/AI_test" --last 1
    python tools/agent_review.py <session.jsonl>

Read-only. Same measures as the November 2026 review (see docs/handoff-agent-review.md for the baselines):
- per agent: turns, cache read / write / output, cost in input-token equivalents (read x0.1, write x1.25, output x5),
  context at the start, at the first `rt check`, and at the peak; the share paid for the fixed start context;
- turns that returned under 300 characters (not a check, build or write): the "tiny turns";
- cache rewrites: a turn after a gap over 5 minutes that wrote over 40k to the cache;
- habits: rt check in the background or with a Bash timeout under 240 s, polling, heredoc code files, raw runs/*.json
  reads, one-query `rt sql` turns, reading the kit's source, screenshots opened, hook denials, refused Writes,
  destructive SQL payloads naming a real table, nested agents, cp1252 crashes, tracebacks;
- coordination: subagent type, how many `rt check` ran at once, writes to shared rule files by agents;
- the largest items carried in each agent's context (size x remaining turns).
"""
import argparse
import collections
import glob
import json
import os
import re
import sys
from datetime import datetime

RX = {
    "rt_run": re.compile(r"(^|[;&|(\s])rt\s+(check|build)\b"),
    "rt_sql": re.compile(r"(^|[;&|(\s])rt\s+sql\b"),
    "rt_sql_multi": re.compile(r'rt\s+sql\s+(?:"[^"]*"\s+){2,}|rt\s+sql\s+(?:\'[^\']*\'\s+){2,}'),
    "poll": re.compile(r"\bsleep\s+\d|time\.sleep\(|\buntil\s"),
    "poll_target": re.compile(r"\.log\b|\.output\b|[/\\]tasks[/\\]|counts"),
    "heredoc": re.compile(r"cat\s+>>?\s*['\"]?[^\s'\"<>|;]+\.(py|ya?ml|js|ts|json|sql)['\"]?\s*<<"),
    "raw_run": re.compile(r"runs[/\\][^\s'\"]*[A-Z]\d{2,}\.json|(?=.*runs[/\\])(?=.*json\.load)(?=.*['\"][A-Z]\d{2,}\.json)", re.S),
    "kit_src": re.compile(r"AI_test_tool[/\\]report-kit[/\\]reportkit", re.I),
    "real_drop": re.compile(r"\bDROP\s+TABLE\s+(?!RK_SDETTEST)[A-Za-z_][\w$#]*", re.I),
    "shared_rules": re.compile(r"\.report-kit[/\\]rules[/\\][\w./\\-]+\.(?:md|ya?ml)"),
}
ERR = {
    "cp1252 crash": r"charmap' codec",
    "traceback": r"Traceback \(most recent call last\)",
    "moved to background (Bash 2-min default)": r"moved to the background",
    "hook denial: token economy": r"report-kit token economy",
    "hook denial: safety": r"report-kit safety rules",
    "Write refused (report file)": r"should not write report files|Subagents should return findings",
    "screenshot timeout": r"Page\.screenshot: Timeout",
    "NM page not ready": r"page not ready",
    "TODO (time budget)": r"not run yet \(time budget\)",
}


def _lines(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def _text(content):
    if isinstance(content, str):
        return content
    return " ".join(x.get("text", "") if x.get("type") == "text" else "[image]" for x in content or [] if isinstance(x, dict))


def _ts(o):
    try:
        return datetime.fromisoformat(o["timestamp"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None


def scan(path):
    """One transcript (main or subagent) -> turns, tool calls with results, usage."""
    turns, calls, seen = [], {}, set()
    for o in _lines(path):
        m = o.get("message") or {}
        if o.get("type") == "assistant":
            if m.get("id") not in seen:
                seen.add(m.get("id"))
                us = m.get("usage") or {}
                turns.append({"ts": _ts(o), "read": us.get("cache_read_input_tokens") or 0,
                              "write": us.get("cache_creation_input_tokens") or 0, "out": us.get("output_tokens") or 0,
                              "model": m.get("model") or "", "calls": []})
            for b in m.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b["id"] not in calls:
                    c = {"turn": len(turns), "name": b["name"], "input": b.get("input") or {}, "ts": _ts(o),
                         "result": "", "rlen": 0, "image": False, "end": None}
                    calls[b["id"]] = c
                    turns[-1]["calls"].append(c)
        elif isinstance(m.get("content"), list):
            for b in m["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in calls:
                    c = calls[b["tool_use_id"]]
                    c["result"] = _text(b.get("content"))
                    c["rlen"] = len(c["result"])
                    c["image"] = "[image]" in c["result"]
                    c["end"] = _ts(o)
    return turns


def _cmd(c):
    i = c["input"]
    return str(i.get("command") or i.get("file_path") or i.get("prompt") or i.get("description") or "")


def review(path, top=6):
    base = path[:-6]
    files = [("main", path)] + [(os.path.basename(f)[6:14], f) for f in sorted(glob.glob(os.path.join(base, "subagents", "*.jsonl")))]
    meta = {}
    for f in glob.glob(os.path.join(base, "subagents", "*.meta.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                meta[os.path.basename(f)[6:14]] = json.load(fh)
        except ValueError:
            pass
    agents, total = [], collections.Counter()
    habits = collections.defaultdict(collections.Counter)
    errors = collections.defaultdict(collections.Counter)
    checks, shared_writes, drops = [], [], []
    for who, f in files:
        turns = scan(f)
        if not turns:
            continue
        T = len(turns)
        ctx = [t["read"] + t["write"] for t in turns]
        cost = sum(t["read"] * 0.1 + t["write"] * 1.25 + t["out"] * 5 for t in turns)
        first_check = next((t["calls"][0]["turn"] for t in turns for c in t["calls"] if RX["rt_run"].search(_cmd(c))
                            and "check" in _cmd(c)), None)
        tiny = [t for t in turns if t["calls"] and sum(c["rlen"] for c in t["calls"]) < 300
                and not any(RX["rt_run"].search(_cmd(c)) or c["name"] in ("Write", "Edit") for c in t["calls"])]
        misses = [(i + 1, round((turns[i]["ts"] - turns[i - 1]["ts"]).total_seconds() / 60, 1), turns[i]["write"] // 1000)
                  for i in range(1, T) if turns[i]["ts"] and turns[i - 1]["ts"]
                  and (turns[i]["ts"] - turns[i - 1]["ts"]).total_seconds() > 300 and turns[i]["write"] > 40000]
        carried = []
        for t in turns:
            for c in t["calls"]:
                size = (c["rlen"] + len(json.dumps(c["input"], ensure_ascii=False))) / 3.2 + (1500 if c["image"] else 0)
                carried.append((size * (1.25 + 0.1 * (T - c["turn"])), c["name"], _cmd(c)[:90].replace("\n", " ")))
        carried.sort(reverse=True)
        h = habits[who]
        for t in turns:
            for c in t["calls"]:
                s, i = _cmd(c), c["input"]
                text = " ".join(str(i.get(k) or "") for k in ("command", "content", "new_string"))
                if RX["rt_run"].search(s):
                    if i.get("run_in_background") or re.search(r"&\s*($|\)|;)", re.sub(r"\d?>&\d|&>|&&", " ", s)):
                        h["rt check/build in background"] += 1
                    elif int(i.get("timeout") or 0) < 240000:
                        h["rt check/build with Bash timeout < 240 s"] += 1
                    if "check" in s and c["ts"] and c["end"]:
                        checks.append((c["ts"], c["end"], who))
                if RX["poll"].search(s) and RX["poll_target"].search(s) or c["name"] == "Monitor":
                    h["polling"] += 1
                if RX["heredoc"].search(s):
                    h["heredoc code file"] += 1
                if RX["raw_run"].search(s) and "rt show" not in s:
                    h["raw runs/*.json read"] += 1
                if RX["rt_sql"].search(s) and not RX["rt_sql_multi"].search(s) and s.count("rt sql") == 1:
                    h["one-query rt sql call"] += 1
                if RX["kit_src"].search(s):
                    h["read the kit's source"] += 1
                if c["name"] == "Read" and s.lower().endswith(".png"):
                    h["screenshot opened"] += 1
                if c["name"] in ("Agent", "Task") and who != "main":
                    h["NESTED AGENT"] += 1
                if c["name"] == "TaskStop":
                    h["TaskStop"] += 1
                m = RX["real_drop"].search(text)
                if m:
                    drops.append((who, c["turn"], m.group(0), "BLOCKED" if "safety rules" in c["result"] else "went through"))
                if who != "main" and c["name"] in ("Write", "Edit") and RX["shared_rules"].search(s):
                    shared_writes.append((who, c["turn"], s))
                for k, p in ERR.items():
                    if re.search(p, c["result"]):
                        errors[who][k] += 1
        mt = meta.get(who, {})
        models = collections.Counter(t["model"] for t in turns if t["model"])
        written = sum(len(json.dumps(c["input"], ensure_ascii=False)) for t in turns for c in t["calls"]) / 3.2
        agents.append(dict(who=who, desc=mt.get("description", "main session" if who == "main" else ""),
                           model=(models.most_common(1)[0][0].replace("claude-", "") if models else "?"),
                           out_undercounted=sum(t["out"] for t in turns) < written,
                           type=mt.get("agentType", "-"), turns=T, read=sum(t["read"] for t in turns),
                           write=sum(t["write"] for t in turns), out=sum(t["out"] for t in turns), cost=cost,
                           start=ctx[0], peak=max(ctx), at_check=ctx[first_check - 1] if first_check else None,
                           after_check=(T - first_check) if first_check else None,
                           base=ctx[0] * 0.1 * T, tiny=len(tiny), tiny_cost=sum(t["read"] * 0.1 + t["write"] * 1.25 + t["out"] * 5 for t in tiny),
                           misses=misses, carried=carried[:top]))
        total["cost"] += cost
    return agents, habits, errors, checks, shared_writes, drops, total


def _k(v):
    return "%.1fM" % (v / 1e6) if v >= 1e6 else "%dk" % round(v / 1e3)


def report(path, top=6):
    agents, habits, errors, checks, shared_writes, drops, total = review(path, top)
    print("=" * 100)
    print("session %s" % os.path.basename(path))
    print("cost unit = input-token equivalents (read x0.1, write x1.25, output x5); total %s" % _k(total["cost"]))
    print("\n## Agents")
    print("%-9s %-15s %-13s %-24s %5s %7s %6s %7s %7s %6s %8s %5s %6s %10s" % (
        "who", "type", "model", "description", "turns", "read", "write", "out", "cost", "start", "atCheck", "after", "peak",
        "tiny(cost)"))
    for a in agents:
        print("%-9s %-15s %-13s %-24s %5d %7s %6s %7s %7s %6s %8s %5s %6s %10s" % (
            a["who"], a["type"][:15], a["model"][:13], a["desc"][:24], a["turns"], _k(a["read"]), _k(a["write"]),
            _k(a["out"]) + ("!" if a["out_undercounted"] else ""), _k(a["cost"]),
            _k(a["start"]), _k(a["at_check"]) if a["at_check"] else "-", a["after_check"] if a["after_check"] is not None else "-",
            _k(a["peak"]), "%d(%d%%)" % (a["tiny"], 100 * a["tiny_cost"] / a["cost"]) if a["cost"] else "-"))
    if any(a["out_undercounted"] for a in agents):
        print("out! = the logged output_tokens is smaller than what the agent wrote in tool inputs alone: this "
              "Claude Code version logged usage early, so output (and cost) is undercounted")
    if True:      # models differ between sessions (the user picks one per session)
        print("compare token counts only between runs on the same model; across models, weigh by each model's price")
    sub = [a for a in agents if a["who"] != "main"]
    if sub:
        sc = sum(a["cost"] for a in sub)
        print("agents: fixed start context = %d%% of their cost; tiny turns = %d%%" % (
            100 * sum(a["base"] for a in sub) / sc, 100 * sum(a["tiny_cost"] for a in sub) / sc))
    print("\n## Cache rewrites (gap > 5 min, > 40k written)")
    for a in agents:
        if a["misses"]:
            print("  %s: %s" % (a["who"], ", ".join("turn %d after %.1f min (%dk)" % m for m in a["misses"])))
    if not any(a["misses"] for a in agents):
        print("  none")
    print("\n## Habits (each is a turn that re-read the whole context, or worse)")
    keys = sorted({k for h in habits.values() for k in h})
    for k in keys:
        print("  %-42s %s" % (k, ", ".join("%s=%d" % (w, habits[w][k]) for w in habits if habits[w][k])))
    if not keys:
        print("  none")
    print("\n## Errors seen in tool results")
    keys = sorted({k for e in errors.values() for k in e})
    for k in keys:
        print("  %-42s %s" % (k, ", ".join("%s=%d" % (w, errors[w][k]) for w in errors if errors[w][k])))
    print("\n## Safety")
    print("  destructive payloads naming a real table: %s" % (drops or "none"))
    print("  agents writing shared rule files (.report-kit/rules): %s" % (shared_writes or "none"))
    print("\n## Parallel rt check runs")
    mx, when = 0, None
    for s, e, w in checks:
        who = {w2 for s2, e2, w2 in checks if s2 < e and e2 > s}       # agents, not calls: one agent's calls don't add load
        if len(who) > mx:
            mx, when = len(who), (s, sorted(who))
    print("  most agents checking at the same time: %d%s (two is the measured limit before DEV slows down)" % (
        mx, (" at %s (%s)" % (when[0].astimezone().strftime("%H:%M"), ", ".join(when[1]))) if when else ""))
    print("\n## Largest carried items per agent (size x remaining turns)")
    for a in agents:
        print("  %s: %s" % (a["who"], "; ".join("%s %s %s" % (_k(c), n, s[:60]) for c, n, s in a["carried"][:3])))


def dump(path, who, first, last, width=200):
    """Turn by turn: gap, cache read / write, each call (with its timeout) and the start of its result."""
    f = path if who == "main" else (glob.glob(os.path.join(path[:-6], "subagents", "agent-%s*.jsonl" % who)) or [None])[0]
    if not f:
        raise SystemExit("no agent %s in %s" % (who, path))
    turns = scan(f)
    for n, t in enumerate(turns[first - 1:last], first):
        prev = turns[n - 2]["ts"] if n > 1 else None
        gap = (t["ts"] - prev).total_seconds() / 60 if prev and t["ts"] else 0
        print("t%d gap %.1fm read %s write %s out %s" % (n, gap, _k(t["read"]), _k(t["write"]), _k(t["out"])))
        for c in t["calls"]:
            to = c["input"].get("timeout")
            print("   %s%s: %s" % (c["name"], "(timeout %s)" % to if to else "", _cmd(c)[:width].replace("\n", " | ")))
            print("      -> %d chars: %s" % (c["rlen"], c["result"][:width].replace("\n", " | ")))


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--project", help="project folder; with --last, take its newest sessions")
    ap.add_argument("--last", type=int, default=1)
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--dump", metavar="WHO:FROM-TO", help="turns of one agent, e.g. a85c3c11:100-120 or main:1-30")
    a = ap.parse_args(argv)
    if a.dump:
        who, rng = a.dump.split(":")
        first, last = (int(x) for x in rng.split("-"))
        f = a.files[0] if a.files else None
        if not f and a.project:
            d = os.path.join(os.path.expanduser("~"), ".claude", "projects", re.sub(r"[^A-Za-z0-9]", "-", a.project))
            f = sorted(glob.glob(os.path.join(d, "*.jsonl")), key=os.path.getmtime)[-1]
        return dump(f, who, first, last)
    files = list(a.files)
    if a.project:
        d = os.path.join(os.path.expanduser("~"), ".claude", "projects", re.sub(r"[^A-Za-z0-9]", "-", a.project))
        files += sorted(glob.glob(os.path.join(d, "*.jsonl")), key=os.path.getmtime)[-a.last:]
    if not files:
        ap.error("give session .jsonl files or --project")
    for f in files:
        report(f, a.top)


if __name__ == "__main__":
    main()
