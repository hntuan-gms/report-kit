"""Batch mode: parsing codes + note, grouping by screen, pending selection, results reading, Git Bash path fix."""
import json
import os

from reportkit import batch, cli, results


def test_parse_codes_and_note():
    codes, note = batch.parse_codes(["2B_18,", "2B_19,", "[#2b21]", "có", "thể", "dùng", "chung", "2B_22"])
    assert codes == ["2B_18", "2B_19", "2B_21"]            # 2B_22 after the note belongs to the note
    assert note == "có thể dùng chung 2B_22"
    assert batch.parse_codes("1E_117 1E_118")[0] == ["1E_117", "1E_118"]
    assert batch.parse_codes("2B_18, 2B_18")[0] == ["2B_18"]
    assert batch.parse_codes(["hello"])[0] == []


def _trace(route=None, comp=None, top=()):
    return {"routes": [route] if route else [], "components": [comp] if comp else [], "top": [{"file": f} for f in top],
            "method": "menu path" if route else "name only"}


def test_group_by_screen_union_and_unresolved():
    t = {"A": _trace("/x/company", "c.ts", ("a", "b", "c")),
         "B": _trace("/x/company", "c.ts", ("a", "b", "z")),      # same route as A
         "C": _trace("/x/auditor", "d.ts", ("m", "n", "o")),
         "D": _trace(None),                                         # nothing found
         "E": _trace("/x/other", "e.ts", ("a", "b", "q"))}          # 2 of 3 top files shared with A
    gs = {tuple(g["codes"]): g for g in batch.group_by_screen(t)}
    assert ("A", "B", "E") in gs and ("C",) in gs and ("D",) in gs
    assert gs[("D",)]["unresolved"] == ["D"]
    assert gs[("A", "B", "E")]["host"] == "A"
    joined = batch.group_by_screen(t, joins=[("D", "C")])
    assert any(set(g["codes"]) == {"C", "D"} and not g["unresolved"] for g in joined)


class _WS(object):
    def __init__(self, d):
        self.dir = str(d)

    def runs_dir(self):
        p = os.path.join(self.dir, "runs"); os.makedirs(p, exist_ok=True); return p


def _write(ws, run, cid, status, **obs):
    d = os.path.join(ws.runs_dir(), run); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, cid + ".json"), "w", encoding="utf-8") as f:
        json.dump({"id": cid, "status": status, "title": "t " + cid, "observations": obs, "kind": "ui"}, f)


def test_results_merge_across_runs_and_noise(tmp_path):
    ws = _WS(tmp_path)
    _write(ws, "20260101-000001", "U01", "ERR")
    _write(ws, "20260101-000001", "U02", "OBS", rows=[["1"]])
    _write(ws, "20260101-000002", "U01", "OBS", calls=[["GET", "/audit/profile", 200], ["GET", "/audit/af-profiles?page=0", 200]])
    assert results.statuses(ws) == {"U01": "OBS", "U02": "OBS"}                 # newest result of each entry, any run
    txt = results.show(ws, ["U01", "U02", "U09"])
    assert "af-profiles" in txt and "/audit/profile" not in txt                  # noise request hidden
    assert "U09 MISSING" in txt


def test_unmsys():
    assert cli._unmsys("C:/Program Files/Git/audit/af-profiles/1") == "/audit/af-profiles/1"
    assert cli._unmsys("C:\\Program Files\\Git\\audit\\x") == "/audit/x"
    assert cli._unmsys("/audit/x?y=1") == "/audit/x?y=1"
    assert cli._unmsys("C:/data/file") == "C:/data/file"
