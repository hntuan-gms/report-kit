"""Token usage of Claude Code sessions, to compare /report-test runs before and after a change (read-only).

    python tools/token_usage.py <session.jsonl> [more.jsonl ...] [--top 8]
    python tools/token_usage.py --project "C:/Users/me/Documents/AI test v2/AI_test" --last 5

Sessions live in ~/.claude/projects/<project path with every non-alphanumeric char as '-'>/<session id>.jsonl.
Subagent transcripts (<session id>/subagents/*.jsonl) are added to their session's totals.
Per session it prints: the /report-test argument, turns, cache-read / cache-write / output tokens, context at the
start / middle / peak, images opened, `rt` calls per command, and the largest tool results (by characters).
Cost is driven by turns x context size, so cache-read is the number to watch.
"""
import argparse
import collections
import glob
import json
import os
import re


def project_dir(path):
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", re.sub(r"[^A-Za-z0-9]", "-", path))


def _lines(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def scan(path, top=8):
    usage, rt, results = collections.Counter(), collections.Counter(), []
    names, seen, ctx = {}, set(), []
    arg, images = "", 0
    files = [path] + sorted(glob.glob(os.path.join(path[:-6], "subagents", "*.jsonl")))
    for n, fp in enumerate(files):
        for o in _lines(fp):
            m = o.get("message") or {}
            if n == 0 and not arg and o.get("type") == "user" and isinstance(m.get("content"), str):
                a = re.search(r"<command-args>(.*?)</command-args>", m["content"], re.S)
                arg = (a.group(1) if a else m["content"])[:60].strip()
            if o.get("type") == "assistant":
                us = m.get("usage")
                if us and m.get("id") not in seen:
                    seen.add(m.get("id"))
                    for k in ("cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens", "input_tokens"):
                        usage[k] += us.get(k) or 0
                    if n == 0:
                        ctx.append((us.get("cache_read_input_tokens") or 0) + (us.get("cache_creation_input_tokens") or 0))
                for c in m.get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "tool_use":
                        inp = c.get("input") or {}
                        cmd = inp.get("command") or ""
                        for k in re.findall(r"\brt\s+(\w[\w-]*)", cmd):
                            rt[k] += 1
                        names[c["id"]] = (c["name"], (cmd or inp.get("file_path") or inp.get("prompt") or "")[:90].replace("\n", " "))
            if o.get("type") == "user" and isinstance(m.get("content"), list):
                for c in m["content"]:
                    if isinstance(c, dict) and c.get("type") == "tool_result":
                        s = json.dumps(c.get("content"), ensure_ascii=False)
                        if '"type": "image"' in s:
                            images += 1
                            continue
                        results.append((len(s),) + names.get(c.get("tool_use_id"), ("?", "")))
    results.sort(reverse=True)
    mid = ctx[len(ctx) // 2] if ctx else 0
    return dict(file=os.path.basename(path), arg=arg, turns=len(seen), usage=usage, rt=dict(rt), images=images,
                subagents=len(files) - 1, ctx=(ctx[0] if ctx else 0, mid, max(ctx) if ctx else 0), top=results[:top])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--project", help="project folder; with --last, take its newest sessions")
    ap.add_argument("--last", type=int, default=5)
    ap.add_argument("--top", type=int, default=8)
    a = ap.parse_args(argv)
    files = list(a.files)
    if a.project:
        found = sorted(glob.glob(os.path.join(project_dir(a.project), "*.jsonl")), key=os.path.getmtime)
        files += found[-a.last:]
    if not files:
        ap.error("give session .jsonl files or --project")
    k = lambda v: "%.1fM" % (v / 1e6) if v >= 1e6 else "%dk" % round(v / 1e3)
    for fp in files:
        r = scan(fp, a.top)
        u = r["usage"]
        print("== %s  %s" % (r["file"][:8], r["arg"]))
        print("  turns %d, subagents %d | cache-read %s, cache-write %s, output %s | context start/mid/peak %s/%s/%s | images %d"
              % (r["turns"], r["subagents"], k(u["cache_read_input_tokens"]), k(u["cache_creation_input_tokens"]),
                 k(u["output_tokens"]), k(r["ctx"][0]), k(r["ctx"][1]), k(r["ctx"][2]), r["images"]))
        if r["rt"]:
            print("  rt calls: " + ", ".join("%s=%d" % kv for kv in sorted(r["rt"].items())))
        for size, tool, what in r["top"]:
            print("  %7d  %-10s %s" % (size, tool, what))


if __name__ == "__main__":
    main()
