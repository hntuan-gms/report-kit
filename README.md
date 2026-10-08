# report-kit: kiểm thử màn hình báo cáo / tra cứu / thống kê bằng một lệnh

Gõ `/report-test <mã>` trong Claude Code, ví dụ `/report-test 1E_117`. Bộ kit chạy từ đầu đến cuối:

1. tìm chức năng trong danh sách chức năng, Quy chuẩn và workbook cũ, rồi dò code từ đường dẫn menu;
2. hỏi anh/chị **một lần** (tài khoản, có cho SELECT DB không, có ai đang demo không);
3. đăng nhập, dò bẫy dữ liệu;
4. quan sát màn hình và so số liệu bằng SQL độc lập;
5. xuất workbook theo mẫu của dự án (KBKT), **chỉ một sheet test case**: Tester / BA chỉ đọc sheet này, nên không còn sheet phụ hay hình minh chứng.

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
   - `rt install-skill` (chép skill vào `.claude/skills/report-test` của dự án);
   - hoặc cài dạng plugin: trong Claude Code gõ `/plugin marketplace add <thư-mục-clone>` (hoặc `<owner>/<repo>` / URL git), rồi `/plugin install report-kit@gms-qa`.
3. **Kiểm tra máy:** `rt doctor`. Mọi dòng phải là OK.

## Các lệnh

| Lệnh | Làm gì |
|---|---|
| `rt doctor [--db]` | Kiểm tra thư viện, trình duyệt, hồ sơ, secrets, mạng (DB chỉ khi có `--db`) |
| `rt start <mã> [--route /đường-dẫn]` | Tìm chức năng, trích Quy chuẩn, workbook cũ (kèm comment), dò code từ menu → màn hình → API → handler / view → `brief.md`. `--route` khi đường dẫn menu không khớp |
| `rt login` | Đăng nhập SSO thật, lưu phiên. Phiên còn hạn thì dùng lại |
| `rt probe <mã>` | Chạy bộ bẫy dữ liệu trên các bảng của báo cáo → `probe.md` |
| `rt check <mã> [--only D01,U03] [--redo]` | Chạy `checks.yaml`. Mỗi mục chạy riêng; `--redo` chạy lại các mục NM / ERR |
| `rt summary <mã> [--only D01,U03] [--status DIFF,NM]` | In riêng các mục đó của `summary.md` lần chạy mới nhất (đỡ đọc lại cả file) |
| `rt build <mã>` | Chạy `build_workbook.py` của workspace và kiểm chất lượng sheet test case: kết quả cụ thể, không dòng ẩn, câu chữ dễ đọc cho Tester / BA |
| `rt status <mã>` | Bước nào xong, bước nào tiếp theo (tiếp tục khi phiên bị ngắt) |
| `rt sql "<SELECT>"`, `rt api GET /path` | Tra nhanh (chỉ SELECT; chỉ gọi endpoint đã xác nhận là chỉ đọc) |
| `rt dump <file>`, `rt tally <file>` | Đọc xlsx / docx (kèm comment reviewer); đếm P / F / PE và chạy lại cổng chất lượng trên một workbook |

Mọi file làm việc nằm ở `~/report-kit-work/<hồ sơ>/<mã>/`, ngoài repo:

| File | Nội dung |
|---|---|
| `brief.md` | Tóm tắt đầu vào và kết quả dò code |
| `analysis.md` | Chức năng như đã xây dựng: các trường, cột, quy tắc (kèm `file:line`), do Claude viết |
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
| Quy nguyên nhân ô lệch | Viết tay | `variants`: mỗi ô lệch ghi quy tắc giải thích nó |
| Câu chữ trong testcase | Không kiểm | `rt build` chặn: H không mở đầu bằng kết luận, dòng quá 160 ký tự, ký hiệu (Σ → ≥), tên bảng / cột, `file:line`, mã lượt chạy, nhiều lỗi trong một case |
| Đăng nhập | Lỗi `networkidle`, khớp URL sớm | Đã sửa; tự đăng nhập lại khi phiên hết hạn |
| Dự án khác | Sửa code | Viết hồ sơ `.report-kit/`; lõi không chứa gì riêng của dự án |

## Kiểm thử bộ kit

```powershell
cd <thư-mục-clone>
python -m pytest -q
```
