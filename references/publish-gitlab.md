# MR GitLab (tuỳ chọn)

Dùng khi đầu vào là MR GitLab, hoặc khi user yêu cầu đăng kết quả lên MR. Phương pháp kiểm thử không phụ thuộc vào file này.

Cần: `glab` đã `glab auth login --hostname <host>`, đủ mới để có `glab api --form`.

## Lấy MR

```bash
export GITLAB_HOST=<host>          # GitLab self-hosted: -R chỉ chọn project, không chọn host
glab mr view <iid> -R <group/project> -F json > <ws>/report/<repo>-<iid>.json
glab mr diff <iid> -R <group/project>         > <ws>/report/<repo>-<iid>.diff
```

Từ JSON lấy nhánh nguồn/đích, head SHA, `diff_refs.base_sha` và mô tả. User không đưa iid thì tìm MR theo nhánh nguồn và ghi MR đã chọn. Issue liên kết `#N` không có tiền tố thuộc project của chính MR đó. Clone local phải ở đúng head SHA của MR trước khi chạy ca.

## Đăng (chỉ khi user yêu cầu)

Mỗi MR nhận một comment kết quả (và tuỳ user, một khối trong mô tả), chỉ nói phần của repo đó. Viết vào `<ws>/report/<repo>-comment.md`, lấy nội dung từ `VERIFY.md`:

```markdown
## Nghiệm thu — <tính năng>
SHA đã kiểm: <repo>@<sha> · <ngày> · môi trường: <mô tả ngắn, không lộ bí mật>

| Yêu cầu | Luồng | Ca | Kết quả | Bằng chứng |
|---|---|---|---|---|

### Ảnh
**T05 · <mô tả ca>** (head, <repo>@<sha>)
![T05](../shots/T05-head-admin-orders.png)

### Lỗi tìm thấy
### Chưa kiểm được / rủi ro
### Tái lập
```

- Mục "Chưa kiểm được" luôn có mặt; thiếu nó, comment đọc như "đã phủ hết".
- Ảnh nhúng bằng đường dẫn cục bộ tương đối với file markdown, nằm trong `shots/` hoặc `logs/` của workspace, đuôi ảnh; tên có khoảng trắng thì bọc `<...>`. Ưu tiên 4–12 ảnh cho ca người đọc khó tin nhất (quyền, dữ liệu, base/head của bug đã sửa).

```bash
G=<skill-dir>/scripts/gl_evidence.py
python3 $G --repo <clone> --mr <iid> --body <ws>/report/<repo>-comment.md --key <slug> --dry-run
# user đã đồng ý push và đăng:
git -C <clone> rev-parse --abbrev-ref HEAD      # phải trùng nhánh nguồn của MR
git -C <clone> push origin HEAD:<nhánh nguồn>
python3 $G --repo <clone> --mr <iid> --body <ws>/report/<repo>-comment.md --key <slug> --expect-sha <sha đã kiểm>
python3 $G --repo <clone> --mr <iid> --body <ws>/report/<repo>-desc.md    --key <slug> --expect-sha <sha đã kiểm> --target description
```

- `--expect-sha` là SHA của lượt chạy cuối; script dừng nếu head của MR khác (chưa push, hoặc có commit mới sau khi kiểm).
- `--key` là slug của tính năng: chạy lại thì sửa đúng note/khối cũ thay vì đăng thêm. `--target description` chỉ thay khối giữa marker của skill.
- Script upload ảnh vào đúng project, đọc lại note trước khi ghi và dừng nếu ai đó vừa sửa nó. Mỗi project có kho upload riêng: chạy cho từng repo.
- Sau khi đăng, mở link MR trong trình duyệt đã đăng nhập và nhìn thấy ảnh hiển thị; script chỉ kiểm được dạng URL.
- Chưa có lời user: dừng ở `--dry-run`, đưa user bản nháp và lệnh đăng.
