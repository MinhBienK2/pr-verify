# Suy ra tiêu chí nghiệm thu

Mục tiêu nói *vì sao*; diff nói *cái gì đã đổi*; tiêu chí nói *người review sẽ thấy gì để tin là đạt*. Đi theo thứ tự đó.

## Nguồn

1. Lời user về mục tiêu: nguồn chuẩn khi các nguồn khác mâu thuẫn.
2. Issue liên kết MR (checklist, AC), ADR, glossary, docs trong repo.
3. Diff từng MR: endpoint, quyền, cột/bảng/migration, job, config/flag, màn hình, xử lý lỗi.
4. Hành vi hiện tại ở nhánh đích: cái không được làm hỏng.

Mô tả MR và báo cáo kiểm thử cũ chỉ dùng để đối chiếu xem đã sót gì; chúng không phải oracle, và PASS trong đó không được thừa kế.

## Lớp luồng phải xét

Với mỗi lớp, hoặc viết tiêu chí, hoặc ghi một dòng vì sao không áp dụng trong mục "Lớp luồng" của `COVERAGE.md`.

| Lớp | Câu hỏi |
|---|---|
| Luồng chính | Người dùng đúng vai trò làm trọn việc mục tiêu nói, qua mọi app tham gia (vd tạo ở app quản trị → thấy ở app người dùng → lưu đúng ở DB) |
| Phân quyền / vai trò | Ma trận vai trò × hành động: ai được, ai bị chặn, bị chặn ở đâu (UI ẩn, URL guard, API 401/403) |
| Đầu vào sai, biên | Rỗng, quá dài, sai định dạng, trùng, giới hạn kích thước/số lượng |
| Lỗi phụ thuộc | DB/dịch vụ ngoài/API lỗi hoặc chậm: fail-closed hay fail-open, thông báo gì, có mất dữ liệu không |
| Toàn vẹn dữ liệu | Trạng thái DB trước/sau đúng; không ghi thừa, không xoá nhầm; bấm hai lần = một lần |
| Dữ liệu cũ / tương thích | Bản ghi tạo trước MR, client cũ, chế độ/flag cũ vẫn chạy |
| Cấu hình / chế độ | Mỗi giá trị flag/mode mà diff phân nhánh |
| Hồi quy | Màn hình/API lân cận đi qua code bị sửa vẫn như nhánh đích |
| Bảo mật | IDOR (đổi id của người khác), leo thang quyền, dữ liệu lộ qua export/log |
| Phi chức năng | Chỉ khi mục tiêu nêu (hiệu năng, kích thước file, thời gian), kèm ngưỡng số |

## Một tiêu chí tốt

```json
{"kind":"criterion","id":"C07","title":"Tài khoản bị khoá không gọi được API hồ sơ",
 "oracle":"GET /api/me với token của user có trạng thái khoá trả 401/403; bảng sessions không thêm dòng",
 "layers":["api","db"],"repos":["api"],"baseline":true,"flow":"phân quyền","source":"issue #41 AC3"}
```

- Quan sát được bằng máy hoặc bằng ảnh, không phải "code trông đúng".
- Oracle so với **nguồn chuẩn**: đếm trong DB, đọc config, chạy cùng thao tác ở nhánh đích. Con số chép tay (vd "phải có N bản ghi") thành FAIL giả khi dữ liệu đổi; cần chặn "xoá sạch" thì dùng mức sàn.
- Một tiêu chí, một kết quả. Hai kết quả cần kiểm là hai tiêu chí. Ngoại lệ: một tiêu chí có thể lặp trên một tập sinh từ nguồn chuẩn (vd mọi endpoint lấy bằng grep attribute); PASS khi mọi phần tử đạt, bằng chứng liệt kê từng phần tử.
- `repos`: mọi repo mà code của nó quyết định kết quả, dùng đúng tên trong bản ghi `repo`. Ledger dùng trường này để đòi chạy lại trên HEAD mới.
- `layers`: `api`, `db`, `job`, `log`, `cli`, `ui:<app>`.
- `baseline: true` khi tiêu chí sửa bug hoặc đổi hành vi đã có: chạy cả before (`side: base`) và after, ghi hành vi mong đợi ở **cả hai** phía. Tính năng mới hoàn toàn thì chỉ chạy after.

Ghi nhiều tiêu chí một lần, để tránh lỗi quote của shell:

```bash
python3 <skill-dir>/scripts/ledger.py --ws "$WS" add -f - <<'EOF'
{"kind":"criterion","id":"C01",...}
{"kind":"criterion","id":"C02",...}
EOF
```

## Khi nghiệp vụ không rõ

Hai cách hiểu hợp lý cho ra hai kết quả khác nhau: ghi `issue` với `status: needs-decision`, `found_round: 0` nếu phát sinh ở bước này, `criterion` là tiêu chí liên quan (hoặc `"-"`), nêu hai cách hiểu và đề xuất của bạn. Hỏi theo các mốc ở SKILL.md; khi user chốt, ghi lại issue với `status: decided`, `decision`, `decided_by` (trích lời user).

## COVERAGE.md

```
| Repo | File (dòng) | Thay đổi | Tiêu chí |
|---|---|---|---|
| api | src/services/access.ts:120-188 | fail-closed khi đọc quyền lỗi | C11, C12 |
| web | src/middleware/guard.ts:40-77 | chặn URL theo vai trò | C05, C06 |
| api | src/entities/* | gắn attribute hàng loạt | C42 (quét mọi entity) |
| api | migrations/20260101_add_role.sql | thêm cột | C01 (migrate) |
| api | README.md | tài liệu | — không đổi hành vi |

## Lớp luồng
- Phi chức năng: không áp dụng, mục tiêu không nêu ngưỡng.
```

- Mỗi file trong diff có một dòng; dải dòng là tuỳ chọn. Thay đổi cơ học (import, attribute hàng loạt, file sinh tự động) gom bằng glob và phủ bằng một tiêu chí quét.
- Không có tiêu chí thì ghi `— <lý do>`.
- `ledger.py coverage --diff <repo>=intake/<repo>-<iid>.diff` liệt kê file chưa có dòng và ID tiêu chí không có trong ledger.
