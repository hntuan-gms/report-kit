# Transactions

Read this only when `brief.md` lists transactions `T1`, `T2`... (sheet "Chi tiết transaction" of the function list, written
to `inputs/transactions.json` by `rt start`). Each row says **who** does an action and **what** the system answers. It never
says how: statuses, scope, formulas and labels still come from the code, the Quy chuẩn chung and the group conventions.

**A transaction adds no work of its own except a missing action.** Do the steps exactly as without transactions, then:

- **Step 3.** While tracing the screen's code (no separate search), add one line per `T` to `analysis.md`:
  `T3: <file:line>`, `T3: thuộc 1B_39 (<screen>)` or `T3: không có - <menu, screen, routes searched>`.
  A `T` handled by another function is not traced further.
- **Step 4.** Name the roles ("roles named" in `brief.md`) in the same single question.
- **Step 9.** Tag the cases you already wrote: `covers=["T3", "R4"]`. One case per `T` is enough. Do not add cases, runs or
  stubs only to cover a `T`. `rt build` fails while a `T` has neither a case nor a reason, like any other requirement.

| The `T` is | In the workbook |
|---|---|
| Handled on this screen | Tag the cases that already test it. |
| Another function's: a sibling in `brief.md`, a report of the group with a workspace, or a scheduled job | `wb.waive("T3", "Thuộc chức năng 1B_39, xem workbook ...")` or `"Hệ thống tự chạy theo lịch"`. No case, no trace, no check. |
| Handled, but every case for it is a write the safety rules forbid | Tag the "Chưa thực hiện - ..." case the safety rules already give it. |
| Not implemented anywhere: no button, no route, no endpoint, no handler | **One F case** (below). |
| Used by a role no account given covers | One case "Chưa thực hiện - cần tài khoản <vai trò>" with that `T` in `covers`. |

'Phân loại' (Dữ liệu đầu vào / Yêu cầu truy vấn / Dữ liệu đầu ra) is the BA's sizing, not read or write. A function marked
"Sửa" / "Bổ sung": say so in the hand-off; do not re-read the previous workbook for it.

## The F case for a missing action

Two sources: the screenshot of the screen already taken in step 7, and the step-3 code search. Basis line:
`Căn cứ: Danh sách chức năng, yêu cầu "<the action, as brief.md prints it, without the roles>"`. Other cases keep the basis
line they would have without transactions. Shape only, not a verified finding:
```python
wb.tc("Kiểm tra trang tổng hợp có thống kê báo cáo giao dịch",
      ["Đăng nhập bằng tài khoản chuyên viên giám sát", "Vào Trang chủ", "Tìm phần thống kê báo cáo giao dịch"],
      ["Có phần thống kê báo cáo giao dịch", "Hiển thị số lượng báo cáo giao dịch theo điều kiện thống kê"],
      basis='Căn cứ: Danh sách chức năng, yêu cầu "xem tổng hợp báo cáo giao dịch"\n'
            "Kỹ thuật: màn hình trang chủ và các API dashboard không có phần nào cho báo cáo giao dịch",
      status="F", actual=["Sai.", "Không có chức năng xem tổng hợp báo cáo giao dịch.",
                          "Phạm vi: Trang chủ chỉ có 3 biểu đồ (Xu hướng vi phạm, Số lượng theo loại tin, Cơ cấu tỷ lệ loại tin)."],
      covers=["T4"])
```

## Hand-off

One line each: the transactions the function does not offer (their F cases), the ones waived and why, the roles not logged
in as, and the "Sửa" / "Bổ sung" flag.
