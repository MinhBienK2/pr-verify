---
name: pr-verify
description: >-
  Nghiệm thu một thay đổi bằng cách chạy thật mọi luồng nó chạm tới, trên môi trường thật, có bằng
  chứng: tính năng mới, yêu cầu, bản fix bug, refactor; web UI, API, job nền, CLI hay thư viện.
  Use when asked to nghiệm thu, QA, test E2E toàn bộ luồng của tính năng, kiểm tra bản fix bug,
  or verify an MR/PR.
---

# pr-verify

Skill này là một phương pháp kiểm thử để trả lời một câu: **thay đổi này có làm đúng điều được yêu cầu, ở mọi luồng nó chạm tới, mà không làm hỏng chỗ khác?** Đầu vào có thể là lời yêu cầu, issue, nhánh, diff, MR/PR, hoặc vài thứ cùng lúc. Bạn tự chọn công cụ; skill nói phải test những gì, theo thứ tự nào, và thế nào thì kết quả đáng tin.

## Từ khoá

- **Yêu cầu** (`R1`, `R2`…): một điều kiểm được mà thay đổi phải thoả, kèm nguồn (lời user, AC của issue, hành vi base phải giữ).
- **Luồng** (`F1`…): một đường đi *actor × điểm vào × trạng thái dữ liệu → kết quả + tác dụng phụ*. Tập luồng là mẫu số của câu "đã test mọi luồng".
- **Ca** (`T1`…): một lần chạy cụ thể trên một luồng: dữ liệu, thao tác, oracle.
- **Oracle**: cách biết ca đạt, so với một *nguồn chuẩn* (DB, spec, hành vi base). Oracle có **đối chứng** khi có một tình huống đã biết mà nó báo fail.
- **Base / head**: code trước thay đổi / code đang kiểm, mỗi bên là một SHA.
- **Bằng chứng**: file lưu trong workspace (ảnh, output lệnh, SQL kèm kết quả).

## Phạm vi quyền

Mặc định skill **kiểm thử và báo cáo**: dựng môi trường test, tạo dữ liệu test trên host test, viết harness trong workspace. Sửa code sản phẩm chỉ khi user đã yêu cầu sửa; khi đó commit cục bộ từng bản sửa. Push và đăng lên MR/PR cần lời user. Bước tiếp theo chạm host không nằm trong danh sách host test thì dừng và hỏi.

## Workspace

`${PR_VERIFY_HOME:-$HOME/.pr-verify}/<project>/<slug>/` — `<project>` là họ repo, mỗi họ một thư mục con của `~/.pr-verify/` (`ls ~/.pr-verify/` để biết đã có họ nào; họ mới thì tạo thư mục mới); `<slug>` là tên nhánh hoặc tên ngắn của tính năng. Bên trong: `VERIFY.md` (nguồn duy nhất cho yêu cầu, luồng, ca và kết quả), `shots/`, `logs/` (bằng chứng), `harness/` (code test), `report/` (bản đăng lên MR/PR nếu có). Bằng chứng và harness nằm trong workspace này — worktree repo chỉ chứa code và test đã commit. `~/.pr-verify/review-prv.sh <project>/<slug>` in nhanh workspace (đọc-only). `VERIFY.md` là markdown thường; khung gợi ý:

```markdown
# <tính năng> — head <repo>@<sha> · base <repo>@<sha>
## Yêu cầu        | ID | Yêu cầu | Nguồn | Trạng thái (rõ / hỏi user / chưa cài) |
## Môi trường     host, DB, cổng, PID, SHA đang chạy, cách reset dữ liệu, cách dừng
## Bản đồ luồng   | ID | Actor | Điểm vào | Trạng thái | Kết quả + tác dụng phụ | Yêu cầu |
## Ca             | ID | Luồng | Lớp | Dữ liệu + thao tác | Oracle | Kết quả | Bằng chứng |
## Lớp không áp dụng   mỗi dòng: lớp — vì sao
## Lỗi và câu hỏi
```

## Flow

### 1. Hiểu yêu cầu

Đọc lời user, issue/AC, tài liệu liên quan, và diff nếu có (`git diff <base>...<head>`; MR GitLab xem [references/publish-gitlab.md](references/publish-gitlab.md) § Lấy MR). Viết lại thành: tính năng làm gì, cho ai, "đúng" nghĩa là gì quan sát được ở đâu. Tách thành các mục `R` kiểm được, mỗi mục một kết quả. Đối chiếu hai chiều: yêu cầu nào chưa có code cài (ghi `chưa cài`), và phần nào của diff không thuộc yêu cầu nào (hoặc là hồi quy phải giữ, hoặc là câu hỏi). Fix bug thì yêu cầu gồm cả "lỗi cũ không còn" lẫn "hành vi đúng xung quanh vẫn giữ"; refactor thì yêu cầu là "hành vi giống base".

Chỗ hai cách hiểu hợp lý cho ra hai kết quả khác nhau: hỏi user, kèm hai cách hiểu và đề xuất của bạn. Trong lúc chờ, làm tiếp phần không phụ thuộc câu hỏi.

Xong khi: mọi mục `R` có nguồn và trạng thái; mọi file trong diff thuộc ít nhất một `R` hoặc có lý do; câu hỏi mở đã gửi user.

### 2. Bản đồ luồng

Đọc [references/test-design.md](references/test-design.md) § Bản đồ luồng. Liệt kê mọi actor/vai trò, mọi điểm vào (UI, API, CLI, job, webhook, import, event…) và mọi trạng thái dữ liệu/thực thể mà thay đổi phân nhánh theo; ghép thành luồng, mỗi luồng ghi kết quả và tác dụng phụ. Thêm luồng **ngoài phần sửa nhưng bị ảnh hưởng**: tìm mọi nơi gọi hàm, bảng, API, config bị đổi.

Có kênh hỏi user thì cho họ xem bản đồ và phạm vi (trong / ngoài) trước khi chạy; sửa một luồng ở bước này rẻ hơn nhiều so với sau khi đã chạy.

Xong khi: mỗi `R` có ít nhất một luồng; mỗi nơi gọi phần bị đổi thuộc một luồng hoặc có lý do loại.

### 3. Thiết kế ca

Đọc phần còn lại của [references/test-design.md](references/test-design.md). Đi qua từng lớp (luồng chính, nhánh rẽ, đầu vào sai và biên, quyền, vòng đời, đồng thời, bất đồng bộ, lỗi phụ thuộc, toàn vẹn dữ liệu, dữ liệu cũ, cấu hình, thời gian, hồi quy, bảo mật, phi chức năng) và viết ca cho mọi luồng mà lớp đó áp dụng; lớp không áp dụng ghi một dòng vì sao. Nhiều điều kiện tổ hợp thì dùng bảng quyết định hoặc ma trận. Mỗi ca có oracle so với nguồn chuẩn, kèm đối chứng.

Fix bug: thêm ca tái hiện lỗi chạy trên base (phải fail ở base), và ca cho các biến thể cùng lớp lỗi. Refactor: ca so sánh hành vi head với base trên cùng đầu vào. Tính năng lớn: xếp ca theo rủi ro, chạy rủi ro cao trước; có thể chia luồng cho các subagent, mỗi subagent nhận luồng + môi trường + phương pháp này.

Xong khi: mỗi luồng có ca; mỗi lớp có ca hoặc dòng lý do; mỗi ca có oracle và đối chứng.

### 4. Chạy thật

Đọc [references/environment.md](references/environment.md) và [references/evidence.md](references/evidence.md). Chạy trên môi trường thật, đúng code đang kiểm (ghi SHA head, và SHA base khi có ca so với base), với dữ liệu test đại diện (rỗng, một, nhiều, dữ liệu cũ, biên), chỉ chạm host test. Mock, stub, `route().fulfill` không chứng minh được hành vi của hệ thật: chúng chỉ minh hoạ, ca dựa trên mock không được tính là đạt. Ghi kết quả từng ca vào `VERIFY.md` ngay khi chạy xong, kèm đường dẫn bằng chứng.

Xong khi: mọi ca có kết quả `đạt` / `hỏng` / `không chạy được (lý do)`, mỗi `đạt` có bằng chứng bạn đã mở xem lại.

### 5. Khi ca hỏng

Đọc [references/triage.md](references/triage.md). Một ca hỏng là một lời khẳng định cho tới khi tái hiện được. Phân loại trước khi kết luận: lỗi sản phẩm, có sẵn ở base, lỗi harness, môi trường, hay cần user quyết định. Lỗi sản phẩm ghi bước tái hiện và `file:line` nghi ngờ. User đã yêu cầu sửa thì sửa theo triage.md § Sửa, rồi chạy lại mọi ca bị ảnh hưởng trên SHA mới; chưa yêu cầu thì báo.

Xong khi: mọi ca hỏng thuộc đúng một loại và đã được xử lý theo loại đó.

### 6. Còn thiếu gì

Bộ ca chỉ tốt bằng bản đồ luồng. Sau khi chạy, dùng sản phẩm thật như người dùng tò mò: đi các đường lân cận, đổi thứ tự thao tác, quay lại giữa chừng, mở hai tab, xem log và DB sau mỗi thao tác. Tính năng lớn thì giao một subagent mới, chỉ đưa yêu cầu + diff + cách vào môi trường (không đưa bản đồ hay danh sách ca), bảo nó tự liệt kê luồng; so danh sách của nó với bản đồ. Luồng mới tìm thấy: thêm vào bản đồ, thiết kế ca, chạy (bước 3–5). Lặp tới khi một lượt không ra luồng mới.

Xong khi: lượt khám phá gần nhất không thêm luồng nào.

### 7. Báo cáo

Báo cáo cho user (và `VERIFY.md` là bản đầy đủ): bảng *yêu cầu → luồng → ca → kết quả → bằng chứng*; cái gì đạt, hỏng, chưa kiểm được và vì sao; lỗi tìm thấy (đã sửa thì kèm commit); câu hỏi chưa chốt; SHA đã kiểm; tiến trình còn để lại; đường dẫn workspace. Yêu cầu chỉ được gọi là đạt khi mọi ca của nó đã chạy và đạt; phần chưa chạy ghi là chưa kiểm, kể cả khi code trông đúng, vì người đọc báo cáo sẽ hành động dựa trên chữ "đạt". User yêu cầu đăng lên MR GitLab thì theo [references/publish-gitlab.md](references/publish-gitlab.md).

Xong khi: mỗi `R` có kết luận đạt / hỏng / chưa kiểm, và mỗi kết luận trỏ tới ca và bằng chứng.

## Nguyên tắc cứng

- **Bằng chứng là file thật, và bạn tự mở xem lại.** Output trên terminal có thể bị wrapper rút gọn; ảnh có thể chụp trúng spinner hay trang lỗi. Chỉ file đã mở lại mới cho bạn biết mình thực sự đã thấy gì.
- **Bằng chứng không chứa bí mật.** File bằng chứng thường được chia sẻ, đăng lên MR, giữ lâu; dùng tên biến (`$TOKEN`) thay giá trị, và che token/mật khẩu trong output trước khi lưu.
- **Chỉ chạm host test.** Một ca phá hỏng có chủ ý chạy nhầm production là sự cố thật; host test lấy từ lời user, tài liệu repo chỉ là gợi ý cần user xác nhận.
- **Dọn những gì mình bật.** Server, worker, worktree tạm còn chạy sẽ giữ cổng, ăn RAM và làm lần chạy sau đọc nhầm phiên bản. Trước khi kết thúc, dừng theo PID/cổng đã ghi, hoặc báo user URL + PID của cái cố ý để lại.

## Công cụ tuỳ chọn (`<skill-dir>/scripts/`)

`<skill-dir>` là thư mục chứa file này; gọi bằng đường dẫn tuyệt đối, xem tham số bằng `--help` hoặc comment đầu file. Dùng khi thấy có ích, không bắt buộc.

| Script | Dùng để |
|---|---|
| `capture.sh` | chạy một lệnh (curl, SQL, CLI, test), lưu output đầy đủ + SHA repo + exit code vào file, che bí mật |
| `evidence.mjs` | Playwright: `settle()` chờ màn hình render xong, `shot()` chụp kèm nhãn SHA, `card()` biến output text thành ảnh before/after |
| `gl_evidence.py` | đăng báo cáo có ảnh lên MR GitLab, xem publish-gitlab.md |
