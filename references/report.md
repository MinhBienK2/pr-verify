# Báo cáo và đăng MR

Mỗi MR nhận hai thứ: **mô tả** (đọc trong 1 phút để quyết định review) và **một comment bằng chứng** (bảng tiêu chí, ảnh, lịch sử vòng). Mọi con số lấy từ `ledger.py table`/`check` và file bằng chứng của vòng cuối.

## Mô tả MR (mỗi repo một bản, chỉ nói phần của repo đó)

Khung mô tả MR theo `show-me` của humanlayer (xem CREDITS.md): Summary · Nghiệm thu (thay cho Evidence) · Merge Danger:

```markdown
## Mục tiêu
<một câu, lấy từ GOAL.md> · MR liên quan: <project>!<iid>, <project>!<iid>

## Summary
<sơ đồ nhỏ nhất kể được thay đổi của repo này: pseudocode, call tree, cây file, Mermaid hoặc diff-sketch vài dòng>

## Nghiệm thu (vòng cuối <R>, <ngày>, <repo>@<sha> cho mọi repo trong GOAL.md)
`ledger.py check`: **GREEN (final)** — <x>/<x> tiêu chí PASS · <k> lỗi tìm thấy và đã sửa · <m> rủi ro còn lại
Chi tiết + ảnh: comment "Bằng chứng nghiệm thu" bên dưới.

## Merge Danger
**Door:** one-way | two-way — <vì sao: migration, xoá dữ liệu, đổi contract API…>
**Blast Radius:** <một từ> — <ai/cái gì bị ảnh hưởng nếu sai>
**Rủi ro cần người chốt:** <needs-decision / pre-existing / out-of-scope, mỗi dòng một mục>
```

## Comment bằng chứng (mỗi MR một comment, sửa tại chỗ khi chạy lại)

```markdown
## Bằng chứng nghiệm thu — <tính năng>
Môi trường: <mô tả ngắn, không lộ bí mật> · SHA: <repo>@<sha> cho mọi repo trong GOAL.md · Vòng cuối: <R> · <ngày giờ>

<output `python3 <skill-dir>/scripts/ledger.py --ws <ws> table --repo <repo>`>

### Ảnh
**<Cxx> · <tiêu đề tiêu chí>** (<before|after>, <repo>@<sha>)
![<Cxx>](../shots/r<R>/<Cxx>-after-<mô-tả>.png)

### Lỗi tìm thấy trong quá trình nghiệm thu
| Lỗi | Tiêu chí | Vòng | Commit sửa | Bằng chứng sau sửa |

### Chưa kiểm được / rủi ro
<mỗi dòng: cái gì, vì sao, đề xuất>

### Tái lập
<lệnh chạy harness, đường dẫn workspace, cách reset dữ liệu>
```

- Ảnh nhúng bằng đường dẫn **cục bộ** tương đối với file markdown (`![](…)`, `<img src>` hoặc định nghĩa reference đều được); `gl_evidence.py` upload và thay bằng URL tuyệt đối đúng project.
- Ưu tiên ảnh cho tiêu chí người review khó tin nhất (phân quyền, mất dữ liệu, before/after của bug đã sửa); 4–12 ảnh mỗi MR là vừa, phần còn lại liệt kê tên file.
- Mục "Chưa kiểm được" luôn có mặt; một báo cáo thiếu mục này đọc như "đã phủ hết".

## Đăng

```bash
G=<skill-dir>/scripts/gl_evidence.py
python3 $G --repo <clone> --mr <iid> --body report/<repo>-comment.md --key <slug> --expect-sha <head sha> --dry-run
# có lời user: push nhánh, rồi
python3 $G --repo <clone> --mr <iid> --body report/<repo>-comment.md --key <slug> --expect-sha <head sha>
python3 $G --repo <clone> --mr <iid> --body report/<repo>-desc.md    --key <slug> --expect-sha <head sha> --target description
```

- `--expect-sha` là SHA trong `commits` của vòng cuối; script dừng nếu head của MR khác (chưa push, hoặc có commit mới sau vòng cuối).
- `--key` = slug của tính năng: chạy lại sửa đúng note/khối mô tả cũ của bạn thay vì đăng thêm.
- `--target description` chỉ thay khối nằm giữa marker của skill; phần người khác viết được giữ nguyên.
- Sau khi đăng, mở link MR in ra trong trình duyệt đã đăng nhập và nhìn thấy ảnh hiển thị; script chỉ kiểm được dạng URL.
- Mỗi project có kho upload riêng: chạy script cho từng repo, nó tự upload lại ảnh dùng chung.
