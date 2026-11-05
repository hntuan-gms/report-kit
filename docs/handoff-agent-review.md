# Bàn giao: rà soát hành vi agent của /report-test

Dành cho một phiên Claude được giao đọc log của một lần chạy `/report-test` để tìm chỗ tốn token, chỗ lặp, chỗ lệch hành vi và lỗi an toàn, rồi sửa trong report-kit. Viết ngày 05/11/2026, sau ba ngày rà soát.

**Nguyên tắc của người dùng: họ tự chạy trên mã thật, bạn chỉ đọc log.** Không tự chạy `/report-test`, `rt check` hay bất kỳ thử nghiệm nào trên DEV, trừ khi người dùng yêu cầu rõ. Khi một lần chạy đang diễn ra, mọi thay đổi trong `reportkit/` có hiệu lực ngay với các agent đang chạy (cài kiểu editable), nên chỉ đọc, không sửa code.

## 1. Bối cảnh

| | |
|---|---|
| Repo công cụ | `C:\Users\tuan\Documents\AI_test_tool\report-kit`, nhánh **`best-lean`** (tách từ `best-final` = `3103ee2`, bản có sheet "Hình ảnh lỗi" và lời văn đã chỉnh) |
| Dự án được test | `C:\Users\tuan\Documents\AI test v2\AI_test`, profile `.report-kit/` (biến `RK_PROFILE` trỏ vào đây) |
| Workspace | `C:\Users\tuan\report-kit-work\gms-ids\<mã>\` |
| Workbook bàn giao | `C:\Users\tuan\Documents\AI-TestTools\` |
| Transcript | `C:\Users\tuan\.claude\projects\c--Users-tuan-Documents-AI-test-v2-AI-test\<session>.jsonl`, subagent ở `<session>\subagents\agent-*.jsonl`, mô tả và loại agent ở `agent-*.meta.json` |
| Kết quả cũ đã cất đi | `C:\Users\tuan\report-kit-work\_old\` (run 08/10 và run 03/11 của 1B_47–50, file quy ước `1B.III.5.md`) |

Skill, agent `report-runner`, hook và `env` được cài vào dự án bằng `rt install-skill "<dự án>"`, và chỉ được nạp khi **một phiên mới** bắt đầu. Kiểm tra phiên được rà có đúng bản mới: trong `.meta.json` của subagent, `agentType` phải là `report-runner`.

## 2. Những gì lẽ ra phải thấy (cơ chế đã đặt)

**Cơ chế cứng (hook `reportkit/guard.py`, chạy trên Bash/PowerShell/Write/Edit/mcp, kể cả của subagent):**
- `rt check` / `rt build` chạy nền hoặc Bash timeout < 240000 ms → bị chặn.
- Vòng chờ (`sleep`, `until`, `time.sleep`) đọc log / output → bị chặn.
- Ghi file code bằng heredoc (`cat > x.py <<`) → bị chặn.
- Đọc JSON thô trong `runs/` (kể cả `cd runs/…` rồi `open('H23.json')`) → bị chặn, dùng `rt show`.
- Nội dung có `DROP TABLE <bảng thật>` (khác `RK_SDETTEST…`) ở Write/Edit/Bash → bị chặn (guard đọc mọi trường chuỗi của Write/Edit, vì Write đã đổi tên trường).
- Tự tải hoặc tự grep bundle frontend (`deployed/chunks`, `chunk-*.js`, cache `_deployed/`, crawler `urlopen` + `chunk-`) → bị chặn, dùng `rt deployed`. `curl -I` (lấy ngày build) và file i18n/Excel lưu trong `deployed/` vẫn được.
- Agent `report-runner` đọc mã nguồn kit (`reportkit/*.py` qua shell, Read, Grep) → bị chặn, trỏ về checks-guide / output-format. Phiên chính và agent loại khác vẫn đọc được (sửa kit). Hook dựa vào trường `agent_type` của input.
- `rt check|build --help` không cần timeout.
- SQL ghi / DDL qua client DB → chặn; DB trực tiếp, `curl` POST/PUT/DELETE → hỏi.

**Kit tự làm:**
- `rt check` dừng ở ngân sách 180 s (`ui.run_budget_s`), phần còn lại là `TODO`, `--redo` chạy tiếp; in luôn các mục ERR/NM/DIFF kèm lý do.
- Lý do ERR nêu phần tử chặn (`intercepts pointer events`, `matched nothing (...)`); lý do NM nêu route và chữ trên trang (`| at /… | page shows: …`).
- Thao tác click/gõ timeout 10 s; chụp màn hình 60 s.
- `rt show --keys` in đủ giá trị; `rt sql "…" "…"` nhiều câu; `rt deployed "<chuỗi>"` tìm trong bundle JS đang chạy.
- `rt probe` chỉ in danh sách FOUND, dùng lại kết quả của mã cùng nhóm trong ngày (không chạm DB).
- `rt start --quiet` một dòng; brief ghi file quy ước nhóm (`rules/groups/<nhóm>.md`).
- Cổng chất lượng báo mọi lỗi cùng lúc; build lại bản nháp của chính lần chạy không cần xoá file hay tăng version.
- Khoá đăng nhập: nhiều tiến trình hết phiên cùng lúc → một lần SSO (`_sessions/login.log` ghi mỗi lần SSO thật).
- Lỗi mạng / DB / trình duyệt → một dòng `network: …` / `browser: …`, không traceback.

**Quy tắc viết (không ép được bằng cơ chế, phải kiểm bằng log):**
- Mỗi mã hai agent A → B (`report-runner`); A chạy thử 2–3 mục rồi viết `handoff.txt`; mã chỉ khác tài khoản/bộ lọc thì một agent.
- Thứ tự: A dẫn đầu → (B dẫn đầu ∥ A các mã cùng màn hình) → B của từng mã; **tối đa 2 agent B chạy check cùng lúc**.
- Chỉ phiên chính ghi `.report-kit/rules/*`; `shared.py` do mã dẫn đầu tạo, mã khác chỉ import.
- Gộp lượt: vá mọi lỗi rồi chạy lại trong một lệnh; đọc ≤ ~80 dòng/lần; không mở ảnh khi lý do NM/ERR đã đủ.

## 3. Cách rà

Trong thư mục report-kit:

```powershell
python tools/agent_review.py --project "C:/Users/tuan/Documents/AI test v2/AI_test" --last 1
```
In: bảng từng agent (loại, model, lượt, read/write/output, chi phí quy đổi, context lúc đầu / lúc check đầu tiên / đỉnh, lượt vụn), các lần ghi lại cache, các thói quen, lỗi, an toàn, số agent check cùng lúc, thứ chiếm context nhiều nhất.

Soi một đoạn:
```powershell
python tools/agent_review.py --project "C:/Users/tuan/Documents/AI test v2/AI_test" --dump <8 ký tự đầu của agent>:100-120
python tools/agent_review.py --project "..." --dump main:1-40
```

Thêm:
- Báo cáo bàn giao của từng agent nằm trong transcript phiên chính (tin nhắn có `Subagent hand-back`): đọc phần quyết định, câu hỏi mở, "Proposed rules".
- Chất lượng: `rt tally "<workbook>"` cho từng workbook; so số case P/F/PE/không chạy, có đối chiếu dữ liệu không, mỗi lỗi có ảnh không.
- Request ghi: quét `runs/*/U*.json`, trường `observations.calls`, tìm method khác GET; quét lệnh `rt api POST` (POST tra cứu danh mục là đọc, cần xem handler).
- Kiểm tra từng chỗ bất thường đến tận nguyên nhân (đọc lượt trước đó, kết quả của nó, khoảng chờ) trước khi kết luận.

## 4. Con số mốc

Đơn vị chi phí: token input tương đương (đọc cache × 0,1, ghi cache × 1,25, output × 5).

| Lần chạy | Model | Agent | Lượt | Đọc cache | Chi phí | Context lúc check đầu → đỉnh |
|---|---|---|---|---|---|---|
| 08/10 (`91c9532b`, nhánh `lite`) | Opus 5.5 | một agent cho 1B_47–50 | 179 | 46,5M | 6,7M (output ghi thiếu) | 341k → 456k |
| 03/11 (`16afc058`, `best-lean` sửa giữa chừng) | Sonnet 5.5 | 1B_47 | 162 | 33,5M | 5,2M | 168k → 375k |
| | | 1B_48 | 71 | 11,1M | 1,9M | 165k → 256k |
| | | 1B_49 | 89 | 15,6M | 2,7M | 178k → 293k |
| | | 1B_50 | 168 | 40,6M | 5,4M | 229k → 391k |

Lần 03/11: đọc cache 66% chi phí, ghi 17%, output 17%; context cố định 14%; lượt vụn 25–32%; 2 lần hết cache ở 1B_47 và 1 ở 1B_49; 3 agent check cùng lúc (mỗi mục UI 23 s → 54 s).

Kỳ vọng với bản mới: không lần hết cache; không chạy nền / chờ / heredoc / đọc JSON thô (hoặc chỉ một lần rồi bị hook chặn); context lúc check đầu của agent B khoảng 60–100k thay vì 165–228k; context cố định nhỏ hơn 45k (agent `report-runner`); tối đa 2 agent check cùng lúc; không DROP bảng thật.

## 5. Bẫy khi phân tích (đã dính, đừng lặp lại)

- **Model khác nhau giữa các phiên** (người dùng chọn). Chỉ so token khi cùng model; khác model thì quy theo giá. Cột `model` của `agent_review.py`.
- **`output_tokens` có thể bị ghi thiếu** ở phiên cũ (log ghi usage sớm). `agent_review.py` đánh dấu `!` khi output nhỏ hơn lượng agent đã viết.
- Mỗi tin nhắn có thể lặp trong log (cùng id, dòng `api-request-blob`): luôn khử trùng theo `message.id` / `tool_use.id`.
- Thời gian trong transcript là UTC; giờ địa phương +7.
- Kết quả có `carried_from` là kết quả cũ mang sang, không phải lần chạy mới.
- `rt check` có tiến trình cũ đang chạy dùng code cũ; một lỗi xuất hiện sau khi sửa có thể do tiến trình khởi động trước khi sửa: đối chiếu giờ.
- Chạy test của kit: `env -u RK_PROFILE python -m pytest -q` (biến `RK_PROFILE` làm hỏng một test).
- **Không vá file bằng Python heredoc**: `\n` và `\b` bị biến thành ký tự thật (đã làm hỏng `cli.py` một lần, `rt` hỏng ~1 phút). Dùng Edit / Write; sau khi sửa chạy `python -c "import ast;…"` và `rt --help`.
- Không sửa `.claude/settings.json` của dự án khi phiên đang chạy (hook được chụp lúc khởi động).
- Đo số agent check cùng lúc theo **agent**, không theo số lệnh.
- **Tên trường input của công cụ có thể đổi giữa các bản Claude Code**: Write gửi `content`, rồi `file_text` (11/2026), có lúc `file_content`. Guard và `agent_review.py` đọc mọi trường chuỗi (`guard._strings`); khi thêm luật mới, đếm lại các bộ khoá trong transcript trước.
- Khi chạy lại transcript qua `guard.decide`, truyền `agentType` từ `.meta.json` của subagent (tham số thứ ba), nếu không luật dành cho `report-runner` sẽ không chạy. Mẫu: `tools/` không có sẵn, script trong scratchpad của phiên 05/11.

## 6. Khi tìm ra vấn đề

1. Tìm đến nguyên nhân gốc, đo chi phí của nó (lượt, token quy đổi).
2. Ưu tiên chặn bằng cơ chế: kit (`reportkit/`) hoặc hook (`reportkit/guard.py`); chỉ dùng câu chữ trong skill khi không ép được.
3. Mọi thay đổi có test (`tests/`); với hook, chạy lại mọi lệnh thật trong transcript qua `guard.decide` để chắc không chặn nhầm.
4. Không lặp nội dung giữa `SKILL.md`, `references/*.md` và `claude-plugin/agents/report-runner.md`.
5. Báo người dùng bằng tiếng Việt, ngắn: vấn đề, bằng chứng, đã sửa gì, đã kiểm chứng ra sao, còn gì chỉ là quy tắc viết.
