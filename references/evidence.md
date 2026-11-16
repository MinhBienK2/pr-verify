# Bằng chứng

Người đọc báo cáo không chạy lại được; họ chỉ tin cái họ thấy. Mỗi ca `đạt` cần bằng chứng mà một người hoài nghi đọc xong cũng phải đồng ý, và bạn là người hoài nghi đầu tiên.

## Chung cho mọi loại sản phẩm

- Bằng chứng là file trong `shots/` (ảnh) hoặc `logs/` (text) của workspace, ghi vào cột Bằng chứng của `VERIFY.md` bằng đường dẫn tương đối theo gốc workspace.
- Tên file: `<ca>-<base|head>-<mô-tả-ngắn>.<ext>`, không khoảng trắng (vd `T07-head-locked-user-403.txt`). Chạy lại sau khi sửa thì thêm thư mục con theo lần chạy (`logs/run2/`) thay vì ghi đè.
- Mỗi bằng chứng ghi nó được tạo trên SHA nào: nhãn trên ảnh, dòng đầu của file log, hoặc cột trong `VERIFY.md`.
- Ca so với base: cùng kịch bản, cùng dữ liệu đầu vào, chỉ khác SHA; hai file riêng.
- Lưu cả câu lệnh/thao tác, không chỉ kết quả: người khác phải tái lập được.
- Mở lại file sau khi ghi. Ảnh có thể là trang đăng nhập, spinner, trang lỗi có màu; log có thể là lỗi kết nối với exit 0.
- Không chứa bí mật: tên biến thay giá trị; che token, cookie, mật khẩu, chuỗi kết nối trong output trước khi lưu. `scripts/capture.sh` làm việc này cho output lệnh.

## Theo loại

**Web UI.** Ảnh chụp đủ ngữ cảnh (URL, người dùng/vai trò đang đăng nhập, vùng liên quan), sau khi dữ liệu đã về chứ không phải sau khi trang load. `scripts/evidence.mjs` có `shot()` chờ `settle()` (network yên, selector `ready` xuất hiện, nội dung ổn định, không spinner) rồi chụp kèm nhãn SHA; luôn truyền `ready` mô tả "dữ liệu đã về" của màn hình đó, và để lỗi của nó nổi lên thay vì bọc `.catch()`. Thu `console` error và response ≥ 400 của trang vào `logs/`: chúng thường là bằng chứng hỏng tốt hơn ảnh. Màn hình bị chặn/trống đúng như mong đợi cũng là bằng chứng (`shot(…, { intentionalBlank: true })`). Luồng nhiều bước mà ảnh rời không kể được (kéo thả, race bấm hai lần): giữ trace/video.

**API.** Request (method, URL, vai trò/credential dùng, body), status, header liên quan, body response. Ví dụ:

```bash
<skill-dir>/scripts/capture.sh logs/T07-head-me-locked.txt --repo api="$API_REPO" -- \
  curl -sS -i -H "Authorization: Bearer $TOKEN_LOCKED" "$API/api/me"
```

**DB.** Câu SQL cùng kết quả, DB nào, thời điểm; trạng thái trước và sau thao tác bằng cùng một câu. Tính đếm/tổng ngay trong SQL. Client dòng lệnh có thể cắt giá trị dài và trả exit 0 khi SQL lỗi: đặt độ rộng đủ, kiểm chuỗi lỗi trong output. Dùng client mà file hướng dẫn agent của máy/repo quy định nếu có.

**Job nền, queue, thông báo.** Thời điểm enqueue, log của worker (lọc theo ID của ca), trạng thái cuối trong DB, và thứ người nhận thấy (mailbox test, webhook receiver, file sinh ra). Ghi rõ đã chờ bao lâu và điều kiện chờ (poll tới khi trạng thái đổi, có giới hạn thời gian) — "chờ 5 giây rồi xem" không phân biệt được chậm với không chạy.

**CLI.** Lệnh nguyên văn, stdout và stderr tách hay gộp (ghi rõ), exit code, file/thư mục bị tạo hoặc sửa (liệt kê, checksum hoặc diff trước/sau). `capture.sh` ghi exit code và SHA.

**Thư viện.** Đoạn test hoặc script gọi API public, phiên bản/SHA đã import (in ra từ chính tiến trình test để chắc không import nhầm bản cài sẵn), output của bộ test. Kiểm thuộc tính sinh nhiều đầu vào thì lưu seed và các đầu vào làm fail.

## Biến text thành ảnh (tuỳ chọn)

Khi báo cáo đi tới người chỉ lướt ảnh (vd comment trên MR), `card()` trong `evidence.mjs` dựng ảnh từ file log, có thể đặt base và head cạnh nhau. File log gốc vẫn là bằng chứng chính.
