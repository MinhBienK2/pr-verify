# Môi trường thật

Kết quả chỉ có giá trị khi chạy trên đúng code đang kiểm, với dữ liệu test, và chỉ chạm host test. Ghi mọi thứ dưới đây vào `VERIFY.md` § Môi trường.

## Ghim SHA

- Head: ghi `git rev-parse HEAD` của mỗi repo tham gia. Cây làm việc sạch, trừ file config cục bộ cần để chạy (chuỗi kết nối, cổng) — ghi tên các file đó. Code sửa mà chưa commit thì kết quả không gắn được với SHA nào.
- Xác nhận app đang chạy **đúng** SHA đó: dựng lại sau mỗi thay đổi code, kiểm bằng health check, version endpoint, hoặc dấu thời gian build. App chạy bản build cũ là nguồn kết quả sai phổ biến nhất.
- Base (khi có ca so với base): `git worktree add <dir> <base-sha>` với `<dir>` **ngoài** thư mục clone, chạy ở cổng khác, với DB/schema riêng. Dùng chung DB thì head ghi đè dữ liệu và kết quả "base" vô nghĩa; không tách được DB thì ghi rõ các ca so với base là không xác minh được.
- Base SHA: `git merge-base <head> origin/<nhánh đích>` khi có nhánh đích; không có thì commit trước thay đổi mà user xác nhận.

## An toàn dữ liệu

- Danh sách host/DB test lấy từ lời user. Tài liệu repo gọi gì đó là "test" chỉ là gợi ý cho tới khi user xác nhận.
- Trước khi bật app, đọc config **thật sự được nạp** (file trong thư mục build, `.env.local`, biến môi trường của tiến trình), ghi host/DB nó trỏ tới, đối chiếu danh sách host test. Không khớp: dừng, hỏi user.
- Dữ liệu test mang tiền tố riêng (`prv_<slug>_…`) hoặc dải ID riêng; có cách reset và chạy nó trước mỗi lượt chạy (hoặc ghi vì sao không cần).
- Mỗi bước phá hỏng có chủ ý (tắt dịch vụ, đổi tên bảng, chặn mạng) chạy trong try/finally và kiểm lại đã khôi phục.
- Bí mật đọc từ biến môi trường hoặc file ngoài git; harness, prompt, bằng chứng chỉ chứa tên biến.

## Tiến trình

- Ghi PID/unit/cổng của mọi thứ bật lên ngay khi bật. Dừng theo PID, unit (`systemctl --user stop`) hoặc cổng (`fuser -k <port>/tcp`); pattern tên tiến trình có thể khớp chính shell của agent.
- Lệnh dài (build, cả bộ E2E) cần sống qua khi phiên agent kết thúc: `systemd-run --user --unit=prv-<slug>-<việc> --collect -p WorkingDirectory=<dir> <cmd>` (Linux) hoặc `setsid nohup … &` ghi `$!`.
- Build và dev server nặng có thể bị OOM: giới hạn bộ nhớ, giữ số việc nặng song song theo file hướng dẫn agent (mặc định tối đa 2), dùng bản build sẵn khi dev server không ổn định.

## Health check

Mỗi app một request thật (endpoint health, trang đăng nhập trả 200 có chữ mong đợi, lệnh `--version`), lưu vào `logs/env-<app>.txt`, kèm SHA mà app tự báo nếu có.

## Đăng nhập trong test

Ưu tiên đăng nhập qua API rồi bơm phiên (cookie, `storageState`) cho từng vai trò; chỉ đi qua form đăng nhập ở ca kiểm chính form đó. Hai app cần tách cookie thì dùng host khác nhau (`localhost` và `127.0.0.1`).
