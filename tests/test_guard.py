import json
import subprocess
import sys

from reportkit import cli, guard


def d(cmd, tool="Bash"):
    r = guard.decide(tool, {"command": cmd})
    return r and r[0]


def test_db_clients():
    assert d('sqlplus u/p@db <<< "DELETE FROM AF_PROFILES WHERE ID = 1"') == "deny"
    assert d('python -c "import oracledb; c.execute(\'DROP TABLE X\')"') == "deny"
    assert d('python -c "import oracledb; c.execute(\'UPDATE LOGINS SET A = 1\')"') == "deny"
    assert d('sqlplus u/p@db <<< "SELECT * FROM AF_PROFILES"') == "ask"
    assert d('python -c "import oracledb"', tool="PowerShell") == "ask"


def test_http_writes():
    assert d("curl -X POST https://api.example.test/api/v1/audit/x -d '{}'") == "ask"
    assert d("Invoke-RestMethod -Method Put -Uri https://x/y", tool="PowerShell") == "ask"
    assert d("curl -s https://api.example.test/api/v1/report/r1") is None


def test_rt_and_other_commands_pass():
    assert d('rt sql "SELECT 1 FROM DUAL"') is None
    assert guard.decide("Bash", {"command": "rt check 1E_117 --only U03", "timeout": 300000}) is None
    assert d("git status") is None
    assert guard.decide("mcp__oracle__query", {})[0] == "ask"
    assert guard.decide("mcp__claude_ai_Slack__send", {}) is None
    assert guard.decide("Read", {"file_path": "x"}) is None


def test_hook_protocol():
    p = subprocess.run([sys.executable, "-m", "reportkit.guard"], capture_output=True, text=True,
                       input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "psql -c 'TRUNCATE x'"}}))
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and out["hookEventName"] == "PreToolUse"
    p = subprocess.run([sys.executable, "-m", "reportkit.guard"], capture_output=True, text=True,
                       input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}))
    assert p.stdout == "" and p.returncode == 0


def test_install_skill_adds_hook_once(tmp_path, capsys):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text('{"permissions": {"allow": ["Bash(rt:*)"]}}', encoding="utf-8")
    for _ in range(2):
        cli.main(["install-skill", str(tmp_path)])
    s = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert s["permissions"] == {"allow": ["Bash(rt:*)"]} and s["env"] == {"PYTHONIOENCODING": "utf-8"}
    assert len(s["hooks"]["PreToolUse"]) == 1
    assert "reportkit.guard" in s["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert s["hooks"]["PreToolUse"][0]["matcher"] == "Bash|PowerShell|Write|Edit|mcp__.*"
    assert (tmp_path / ".claude" / "skills" / "report-test" / "SKILL.md").exists()
    agent = (tmp_path / ".claude" / "agents" / "report-runner.md").read_text(encoding="utf-8")
    assert "tools: Bash, PowerShell, Read, Write, Edit, Glob, Grep" in agent and "Agent" not in agent.split("---")[1]


def e(cmd, timeout=None, bg=None, tool="Bash"):
    r = guard.decide(tool, {"command": cmd, "timeout": timeout, "run_in_background": bg})
    return r and r[0]


def test_economy_rt_check_must_run_in_the_foreground_with_a_long_timeout():
    assert e("rt check 1B_47 --only U01") == "deny"                                   # default 2 min timeout
    assert e("rt check 1B_47", timeout=120000) == "deny"
    assert e("rt check 1B_47", timeout=300000, bg=True) == "deny"
    assert e("(rt check 1B_47 > b1.log 2>&1 &)", timeout=300000) == "deny"
    assert e("cd ws && python gen_checks.py && rt check 1B_47 --redo 2>&1 | tail -5", timeout=300000) is None
    assert e("rt build 1B_47", timeout=300000) is None
    assert e('grep -n "rt check" SKILL.md') is None and e("rt show 1B_47 --status ERR") is None
    assert e("rt check 1B_47", timeout=300000, tool="PowerShell") is None


def test_economy_polling_heredocs_and_raw_json():
    assert e("sleep 60; tail -5 C:/x/tasks/b1.output") == "deny"
    assert e("until grep -q counts: redo3.log; do sleep 6; done") == "deny"
    assert e("python -c \"import time,os\nfor _ in range(55):\n  if 'counts' in open('b1.log').read(): break\n  time.sleep(2)\"") == "deny"
    assert e("sleep 2; rt status 1B_47") is None                                      # not a poll on a log
    assert e("cat > gen_checks.py <<'E'\nui = []\nE") == "deny"
    assert e("cat <<'E' > api_checks.py\nx = 1\nE") == "deny"
    assert e("cat > notes.txt <<'E'\nfree text\nE") is None and e("cat gen_checks.py | head") is None
    assert e("python - <<'E'\nimport json\nd=json.load(open('runs/20261103-154757/U12.json'))\nE") == "deny"
    assert e("python - <<'E'\nimport json\nd=json.load(open('probe.json'))\nE") is None


def test_hook_survives_bad_input():
    p = subprocess.run([sys.executable, "-m", "reportkit.guard"], capture_output=True, text=True,
                       input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "rt check x", "timeout": "abc"}}))
    assert p.returncode == 0


def test_economy_raw_json_after_cd_into_a_run():
    assert e("cd /w/1B_50/runs/20261103-164015; python -c \"import json\nd=json.load(open('H23.json'))\"") == "deny"
    assert e("cd /w/1B_50/runs; python -c \"import json\nd=json.load(open('summary.json'))\"") is None
    assert e("cd /w/1B_50; python -c \"import json\nd=json.load(open('probe.json'))\"") is None


def test_injection_payloads_never_name_a_real_table():
    w = lambda content, tool="Write": (guard.decide(tool, {"file_path": "x.py", "content": content}) or ("pass",))[0]
    assert w("PAYLOADS = [\"83405;DROP TABLE COMPANY_SHAREHOLDING\"]") == "deny"
    assert w("p = \"'; drop table ACCOUNT_NUMBERS --\"") == "deny"
    assert guard.decide("Edit", {"file_path": "c.yaml", "old_string": "a", "new_string": "text: \"x; DROP TABLE STOCK_CONTROLS\""})[0] == "deny"
    assert w("p = \"'; DROP TABLE RK_SDETTEST_NO_SUCH_TABLE --\"") == "pass"
    assert w("print('ok')") == "pass" and w("x = 'rt check 1B_47'") == "pass"          # Write is not a shell call
    assert e("python api.py --q \"1; DROP TABLE LEGAL_ENTITIES\"", timeout=60000) == "deny"
    assert e('grep -n "DROP TABLE" SKILL.md') is None


def test_err_reason_names_get_by_text_targets():
    from reportkit.checks import ui
    r = ui._err_reason(Exception('Locator.click: Timeout 60000ms exceeded.\nCall log:\n  - waiting for get_by_text("Người dùng bên ngoài")'))
    assert "matched nothing" in r and "Người dùng bên ngoài" in r
