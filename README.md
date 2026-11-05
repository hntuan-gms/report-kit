# report-kit: kiểm thử màn hình báo cáo / tra cứu / thống kê bằng một lệnh

Gõ `/report-test <mã>` trong Claude Code, ví dụ `/report-test 1E_117`. Bộ kit chạy từ đầu đến cuối:

1. tìm chức năng trong danh sách chức năng, Quy chuẩn và workbook cũ, rồi dò code từ đường dẫn menu;
2. hỏi anh/chị **một lần** (tài khoản, có cho SELECT DB không, có ai đang demo không);
3. đăng nhập, dò bẫy dữ liệu;
4. quan sát màn hình và so số liệu bằng SQL độc lập;
5. xuất workbook theo mẫu của dự án (KBKT).

**Cách làm (cách A):**
- **Claude** đọc code của chức năng (đó là đặc tả), rồi **đánh giá** mọi kết quả theo Quy chuẩn chung, tính nhất quán của chính hệ thống và quy tắc mà code áp dụng. Kit không đọc SRS.
- **Lệnh `rt`** làm phần cơ học: tìm đầu vào, dò code, đăng nhập, chạy các bước quan sát và so sánh, dựng workbook.
- Kit **không tự chấm đạt / lỗi**, không sinh code test cho từng testcase, và không dùng assertion.

## Cài đặt (một lần mỗi máy)

```powershell
git clone <url-repo> report-kit
pip install -e <thư-mục-clone>          # ví dụ: pip install -e .\report-kit
python -m playwright install chromium
```

Thông tin đăng nhập nằm ở `~/.report-kit/secrets.yaml`. File này nằm ngoài mọi repo; **không bao giờ đưa vào repo**:

```yaml
my-project:              # = "name" trong .report-kit/project.yaml của dự án
  login_user: ...
  login_password: ...
  login_type: external   # hoặc internal
  db_password: ...       # chỉ dùng để SELECT
```

Có thể thay bằng biến môi trường `RK_LOGIN_USER`, `RK_LOGIN_PASSWORD`, `RK_LOGIN_TYPE`, `RK_DB_PASSWORD`.

## Gắn vào một dự án

1. **Hồ sơ dự án.** Chạy `rt init` ở gốc repo, sau đó sửa `.report-kit/project.yaml`. Hồ sơ khai báo:
   - hệ thống, cách đăng nhập SSO, DB;
   - vị trí code (`codemap`: file nhãn i18n, thư mục frontend của từng hệ thống), danh sách chức năng (sheet nào, cột nào), Quy chuẩn;
   - mẫu workbook;
   - bẫy dữ liệu riêng của dự án (`rules/traps.yaml`).
2. **Skill.** Chọn một trong hai cách:
   - `rt install-skill` (chép skill vào `.claude/skills/report-test` của dự án và thêm hook an toàn `reportkit.guard` vào `.claude/settings.json`: chặn SQL ghi / DDL, hỏi trước khi truy cập DB trực tiếp hoặc gửi request ghi);
   - hoặc cài dạng plugin: trong Claude Code gõ `/plugin marketplace add <thư-mục-clone>` (hoặc `<owner>/<repo>` / URL git), rồi `/plugin install report-kit@gms-qa`.
3. **Kiểm tra máy:** `rt doctor`. Mọi dòng phải là OK.

## Các lệnh

| Lệnh | Làm gì |
|---|---|
| `rt doctor [--db]` | Kiểm tra thư viện, trình duyệt, hồ sơ, secrets, mạng (DB chỉ khi có `--db`) |
| `rt start <mã> [--menu "A >> B >> tab"] [--route /đường-dẫn] [--retrace]` | Tìm chức năng, trích Quy chuẩn, workbook cũ (kèm comment), dò code từ menu → màn hình → API → handler / view → `brief.md`. `--menu`: đường dẫn menu như trên màn hình, khi danh sách chức năng không ghi (tester trả lời được); `--route` khi biết route; `--retrace` bỏ cache dò code |
| `rt login` | Đăng nhập SSO thật, lưu phiên. Phiên còn hạn thì dùng lại |
| `rt probe <mã> [--fresh]` | Chạy bộ bẫy dữ liệu trên các bảng của báo cáo → `probe.md` (chỉ in danh sách FOUND). Mã cùng nhóm đã dò đúng các bảng đó trong ngày thì dùng lại, không truy vấn lại; `--fresh` để truy vấn lại |
| `rt check <mã> [--only D01,U03] [--redo]` | Chạy `checks.yaml`. Mỗi mục chạy riêng; `--redo` chạy lại các mục NM / ERR |
| `rt build <mã>` | Chạy `build_workbook.py` của workspace và kiểm chất lượng workbook |
| `rt show <mã> [U03,D01\|all] [--status ERR,NM] [--keys a,b]` | In riêng các mục cần xem của lượt chạy mới nhất, thay vì đọc cả `summary.md` dài |
| `rt deployed "<chuỗi \| regex>"` | Tìm trong bộ JS frontend đang chạy trên môi trường (bản build có thể khác repo), cache theo ngày |
| `rt status <mã>` | Bước nào xong, bước nào tiếp theo (tiếp tục khi phiên bị ngắt) |
| `rt sql "<SELECT>" ["<SELECT>" …]`, `rt api GET /path` | Tra nhanh, nhiều câu SELECT trong một lần gọi (chỉ SELECT; chỉ gọi endpoint đã xác nhận là chỉ đọc) |
| `rt dump <file>`, `rt tally <file>` | Đọc xlsx / docx (kèm comment reviewer), đếm P / F / PE của workbook |

Mọi file làm việc nằm ở `~/report-kit-work/<hồ sơ>/<mã>/`, ngoài repo:

| File | Nội dung |
|---|---|
| `brief.md` | Tóm tắt đầu vào và kết quả dò code |
| `analysis.txt` | Chức năng như đã xây dựng: các trường, cột, quy tắc (kèm `file:line`), do Claude viết |
| `inputs/` | Dòng chức năng, Quy chuẩn, workbook cũ đã trích ra text |
| `trace.json` | Kết quả dò code, cache theo commit |
| `probe.md` | Bẫy dữ liệu tìm được |
| `checks.yaml` | Các bước quan sát và so sánh |
| `runs/<id>/summary.md` + `shots/` | Kết quả từng lượt chạy và ảnh chụp |
| `build_workbook.py` | Script dựng workbook |
| `state.json` | Bước nào đã xong |

## So với cách làm cũ (skill `report-testcase`, đã gỡ bỏ)

| | Cũ | report-kit |
|---|---|---|
| Dò code | Claude / agent grep tay (1E_117: khoảng 5 phút) | `rt start`: đi theo menu → route → component → service → mã báo cáo (R017…) → handler / view, xếp hạng file (khoảng 3 giây mỗi báo cáo; 52/63 báo cáo tìm thấy màn hình từ đường dẫn menu), cache theo commit |
| Dò dữ liệu | Viết query tay từng bẫy | `rt probe`: 12 bẫy khai báo sẵn, có ví dụ thật (1E_117: 7,7 giây) |
| Quan sát giao diện | Viết script Python / JS mới mỗi lần, cố định ngày | Khai báo bước trong `checks.yaml`, biến động `{current_year}` / `{prev_month}` …, mỗi mục một trang riêng |
| Đo sai im lặng | Không phát hiện | Tiền đề `ready` / `require` → NM "không đo được" |
| Chạy lại phần hỏng | Viết thêm script | `rt check --redo` / `--only` |
| Quy nguyên nhân ô lệch | Viết tay | `variants`: mỗi ô lệch ghi quy tắc giải thích nó; sheet chi tiết sinh tự động |
| Hình minh chứng lỗi | Dựng tay từng hình theo file mẫu | `reportkit.evidence` + `wb.sheet_evidence`: thẻ minh chứng (bước, thực tế / mong đợi, ảnh khoanh đỏ, Excel ô sai tô đỏ, dữ liệu nguồn) sinh vào sheet "Hình ảnh lỗi", liên kết hai chiều với "Danh sách lỗi"; `rt build` chặn lỗi đang mở mà không có hình |
| Đăng nhập | Lỗi `networkidle`, khớp URL sớm | Đã sửa; tự đăng nhập lại khi phiên hết hạn |
| Dự án khác | Sửa code | Viết hồ sơ `.report-kit/`; lõi không chứa gì riêng của dự án |

## Nhiều mã trong một yêu cầu

`/report-test 1B_47 1B_48 1B_49 1B_50`: phiên chính chỉ chạy `rt start` cho từng mã, gom các mã cùng màn hình, hỏi người dùng một lần, rồi giao mỗi mã cho **một agent mới**. Mã dẫn đầu của mỗi nhóm chạy trước (song song giữa các nhóm); các mã còn lại chạy song song sau đó, bắt đầu từ `analysis.txt` / `checks.yaml` / `build_workbook.py` của mã dẫn đầu. Không để một agent làm nhiều mã nối tiếp: context của nó phình ra và mọi lượt sau phải đọc lại (đo trên 1B_47-50: 179 lượt, context 43k → 456k, 46,5M token đọc).

## Đo token

```powershell
python tools/token_usage.py --project "<thư mục dự án>" --last 3
```

In mỗi phiên: số lượt, cache-read (chi phí thật), context đầu / giữa / đỉnh, ảnh đã mở, số lệnh `rt`, từng subagent (số lượt, cache-read, context đỉnh) và các kết quả công cụ lớn nhất. Con số `subagent_tokens` Claude Code in ra khi một agent xong chỉ là cỡ context cuối của agent đó, không phải chi phí.

## Kiểm thử bộ kit

```powershell
cd <thư-mục-clone>
python -m pytest -q
```
