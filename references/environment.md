# Dựng môi trường thật

Bằng chứng chỉ có giá trị khi chạy trên đúng code của MR, đúng dữ liệu test, và chỉ chạm host test.

## Ghim SHA

- Phía head: clone local ở đúng head SHA của MR (bước 1 đã kiểm).
- Phía base: `git worktree add <dir> <base-sha>` (base SHA trong `GOAL.md`), chạy ở cổng khác. Thư mục đang chạy server thì giữ nguyên nhánh.
- Sau mỗi bản sửa, head SHA đổi: dựng lại app đó, cập nhật `ENV.md`. Mọi kết quả chụp trên SHA cũ sẽ làm `ledger.py check` đỏ cho tới khi chạy lại.
- File config local cần sửa để chạy (chuỗi kết nối, cổng) ghi vào `dirty_ok` của bản ghi `repo`; ngoài các file đó cây phải sạch.

## An toàn dữ liệu

- Trước khi bật app, đọc file config **thật sự được nạp** (vd file trong thư mục build, `.env.local`, biến môi trường của unit). Ghi host/DB mà nó trỏ tới vào `ENV.md` và đối chiếu với danh sách host test trong `GOAL.md`. Host chưa có trong danh sách: dừng, hỏi user.
- Dữ liệu test có tiền tố riêng (`prv_<slug>_…`) hoặc ID trong dải riêng, để dọn được và để các tiến trình song song không đè nhau.
- Mỗi bước phá hỏng có chủ ý (đổi tên bảng, tắt dịch vụ) chạy trong try/finally và **kiểm lại** đã khôi phục.
- Có script reset dữ liệu test và chạy nó đầu mỗi vòng (hoặc ghi vì sao không cần).
- Bí mật (mật khẩu test, token, chuỗi kết nối) đọc từ biến môi trường được `export` hoặc file ngoài git; harness, spec, prompt và bằng chứng chỉ chứa tên biến.

## Chạy bền

- Lệnh dài hơn vài phút (build, cả bộ E2E) phải sống sót khi phiên agent kết thúc: `systemd-run --user --unit=prv-<slug>-<việc> --collect -p WorkingDirectory=<dir> <cmd>` (Linux), hoặc `setsid nohup … &` ghi `$!` (macOS: `nohup … &`). Xem log bằng `journalctl --user -u <unit>`.
- Build và dev server nặng có thể bị OOM-killer: đặt giới hạn bộ nhớ (`-p MemoryMax=…`), chạy tuần tự theo giới hạn song song mà file hướng dẫn agent (AGENTS.md/CLAUDE.md) đặt ra, không có thì tối đa 2 việc nặng cùng lúc, và dùng bản build sẵn/static export khi dev server không ổn định.
- Ghi PID/unit/cổng của mọi thứ đã bật vào `ENV.md` ngay khi bật. Dừng theo PID, unit (`systemctl --user stop`) hoặc cổng (`fuser -k <port>/tcp`); pattern tên tiến trình có thể khớp chính shell của agent nên không dùng.

## Health check

Mỗi app: một request thật (vd `GET /health`, trang đăng nhập trả 200 và có chữ mong đợi) qua `capture.sh --repo <name>=<path>`, lưu vào `logs/env-<app>.txt`. Ghi phiên bản/SHA mà app tự báo nếu có.

## Đăng nhập trong test

Ưu tiên đăng nhập qua API rồi bơm phiên (cookie/localStorage/`storageState`) cho từng vai trò; chỉ đi qua form đăng nhập ở tiêu chí kiểm chính form đó. Hai app khác nhau dùng host khác nhau (vd `localhost` và `127.0.0.1`) khi cần tách cookie.
