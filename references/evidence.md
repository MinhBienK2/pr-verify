# Chuẩn bằng chứng

Người review không chạy lại được; họ chỉ tin cái họ nhìn thấy. Mỗi PASS cần bằng chứng mà một người hoài nghi đọc xong cũng phải đồng ý.

## Quy tắc chung

- Bằng chứng là **file** trong `shots/r<N>/` hoặc `logs/r<N>/` của workspace, ghi đường dẫn tương đối vào `evidence` của `result` (ledger từ chối đường dẫn ngoài hai thư mục này). Output trên terminal có thể bị wrapper rút gọn hoặc tóm tắt, nên luôn đọc lại từ file.
- Mỗi bằng chứng biết nó chụp trên SHA nào: nhãn trên ảnh (`shot({stamp})`), dòng `# repo … sha=` (`capture.sh --repo`), trường `commits` trong ledger.
- Tên file: `<id>-<before|after>-<mô-tả-ngắn>.<ext>`, ví dụ `C07-after-locked-user-403.txt`.
- Before và after chạy **cùng một kịch bản**, chỉ khác SHA.
- Bằng chứng dựng từ response giả lập (`page.route().fulfill`, stub, mock): ghi `"mock": true` trên result và chụp với `shot({mock: true})`. Ledger từ chối PASS có cờ này: mock chỉ để minh hoạ.

## UI

```js
import { shot, card } from '<skill-dir>/scripts/evidence.mjs'
await page.goto(APP + '/orders')
await shot(page, `shots/r${R}/C05-after-admin-orders.png`, {
  stamp: `C05 · after · web@${SHA}`,
  settleOpts: { ready: 'table tbody tr' },
})
```

- `shot()` chờ `settle()`: network yên, `ready` thoả, nội dung trang ổn định khoảng 2 giây, không còn skeleton/spinner/ảnh đang tải trong khung nhìn, trang có nội dung. Hết giờ thì nó **ném lỗi**: để lỗi nổi lên, vì `.catch(() => {})` quanh nó biến một ảnh thiếu thành PASS không bằng chứng.
- Luôn truyền `ready` (selector hoặc hàm) mô tả "dữ liệu đã về" của màn hình đó: dữ liệu về muộn mà không có spinner thì chỉ `ready` bắt được. Trang có loading riêng thì thêm `busySelectors`.
- Lazy-load / carousel: cuộn xuống cuối rồi lên đầu, đưa carousel về slide đầu trước khi chụp `fullPage`.
- Màn hình trắng/403 **là** bằng chứng: `shot(page, p, { intentionalBlank: true, stamp })` ghim nhãn đỏ, và `note` của result chứa `intentional-blank`.
- Ảnh cho người đọc: chụp đủ ngữ cảnh (menu, URL, tên người dùng/vai trò), không chỉ một ô. Toast/thông báo thoáng qua: chờ nó hiện rồi chụp ngay, thêm ảnh riêng phần tử nếu nhỏ.
- `ledger.py check` bắt ảnh trắng và ảnh trùng byte giữa hai tiêu chí (thường là trang lỗi/redirect giống nhau). Trang lỗi có màu (banner đỏ, trang 404 có header) thì máy không bắt được: mở ảnh và nhìn.
- Bắt `console` error và response ≥ 400 của trang (`page.on('console')`, `page.on('response')`) vào `logs/`; chúng thường là bằng chứng FAIL tốt hơn ảnh.

## API

```bash
export TOKEN_LOCKED=…   # biến môi trường, không viết giá trị vào lệnh
<skill-dir>/scripts/capture.sh logs/r2/C07-after-me-locked.txt --repo api="$API_REPO" --expect-exit 0 -- \
  curl -sS -i -H "Authorization: Bearer $TOKEN_LOCKED" "$API/api/me"
```

Ghi request (method, URL, vai trò dùng), status, header quan trọng, body (rút gọn ở mức vẫn đủ chứng minh). `capture.sh` thay giá trị của biến môi trường có tên chứa PASS/TOKEN/SECRET/KEY bằng tên biến, và che các dạng bí mật quen thuộc trong output.

## DB

- Lưu **câu SQL cùng kết quả** qua `capture.sh`, kèm thời điểm và DB nào. Dùng client truy vấn mà file hướng dẫn agent (AGENTS.md/CLAUDE.md) của repo hoặc của máy quy định, nếu có.
- Tính đếm/độ dài/tổng ngay trong SQL. Client dòng lệnh có thể cắt hoặc bẻ dòng giá trị dài: đặt độ rộng tối đa (vd `sqlcmd -w 65535 -y 0`, `SET NOCOUNT ON`; MySQL client với charset utf8mb4).
- Nhiều client trả exit 0 cả khi SQL lỗi: kiểm chuỗi lỗi trong output (vd `Msg <số>`, `ERROR <số>`), coi đó là lỗi harness.
- Trạng thái trước và sau thao tác: hai lần chạy cùng câu SQL.

## Biến API/SQL thành ảnh

Người review MR thường chỉ lướt ảnh. Với tiêu chí quan trọng ở tầng API/DB, thêm một ảnh `card()`: tiêu đề tiêu chí, panel BEFORE (đỏ) và AFTER (xanh) chứa nội dung file `logs/` tương ứng.

## Video / trace

Luồng nhiều bước mà ảnh rời không kể được (kéo thả, wizard, race bấm hai lần): bật trace/video của Playwright cho test đó và giữ file trong `logs/`. Trong MR, ảnh vẫn là chính; trace là phụ lục.
