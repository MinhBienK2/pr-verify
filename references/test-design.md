# Thiết kế ca test

Yêu cầu nói *phải đúng cái gì*; bản đồ luồng nói *đúng ở những đâu*; ca nói *chạy gì và nhìn vào đâu để tin*. Đi theo thứ tự đó: ca thiết kế thẳng từ diff thường chỉ phủ đúng chỗ code đã sửa, và bỏ sót đúng chỗ code lẽ ra phải sửa mà chưa sửa.

## Bản đồ luồng

Một luồng là *actor × điểm vào × trạng thái dữ liệu → kết quả + tác dụng phụ*. Lập bản đồ bằng cách liệt kê từng trục riêng rồi mới ghép.

**Actor / vai trò.** Mọi ai/cái gì kích hoạt hành vi: người dùng theo vai trò (khách, thành viên, quản trị, chủ sở hữu bản ghi, người ngoài tổ chức), hệ thống khác (webhook, client cũ của API), tiến trình nội bộ (cron, worker, migration), người vận hành (CLI, script admin). Một vai trò đáng tách khi code phân nhánh theo nó.

**Điểm vào.** Mọi cửa dẫn tới code bị đổi: màn hình và hành động UI, endpoint API (cả phiên bản cũ), lệnh CLI và cờ, job/cron, consumer của queue, webhook, import/export file, event bus, hàm public của thư viện, trigger DB. Tìm bằng cách đi ngược từ diff:

- grep tên hàm, class, bảng, cột, route, key config, tên event bị đổi để ra mọi nơi gọi/đọc;
- đọc nơi đăng ký route, scheduler, consumer, command để ra điểm vào thật;
- với thư viện: mọi hàm export và mọi package phụ thuộc (trong monorepo) gọi tới nó.

Nơi gọi nằm ngoài diff vẫn là luồng: chúng hỏng âm thầm khi contract đổi.

**Trạng thái dữ liệu / thực thể.** Những trạng thái mà kết quả phụ thuộc: trạng thái vòng đời của thực thể (nháp, đã gửi, đã duyệt, đã huỷ), có/không dữ liệu liên quan (giỏ rỗng, chưa có cấu hình), dữ liệu tạo trước thay đổi, giá trị flag/cấu hình, số lượng (0, 1, nhiều, rất nhiều).

**Kết quả + tác dụng phụ.** Kết quả là thứ actor thấy (màn hình, response, exit code, giá trị trả về). Tác dụng phụ là thứ thay đổi ở nơi khác: dòng DB, file ghi ra, message vào queue, email/thông báo, cache bị xoá, log/audit, lời gọi sang dịch vụ ngoài. Ca chỉ nhìn kết quả mà bỏ tác dụng phụ là ca thiếu oracle.

Ghép: không cần tích Descartes đầy đủ. Giữ tổ hợp mà code phân nhánh theo, gộp tổ hợp đi cùng một đường code. Ví dụ bản đồ (rút gọn):

| ID | Actor | Điểm vào | Trạng thái | Kết quả + tác dụng phụ | Yêu cầu |
|---|---|---|---|---|---|
| F1 | khách | UI giỏ hàng → nhập mã giảm giá | giỏ có hàng, mã còn hạn | tổng giảm đúng %; `orders.discount_code` lưu khi đặt | R1 |
| F2 | khách | như F1 | mã hết hạn / đã dùng hết lượt | thông báo lỗi, tổng không đổi | R2 |
| F3 | client mobile cũ | `POST /api/v1/orders` không gửi mã | — | đơn tạo như trước | hồi quy |
| F4 | cron 02:00 | job `expire_codes` | mã quá hạn | `codes.status=expired`, không đụng mã còn hạn | R3 |
| F5 | admin | CLI `codes import file.csv` | file có dòng trùng | nhập dòng hợp lệ, báo dòng lỗi, exit ≠ 0 | R4 |

## Các lớp

Đi qua từng lớp cho từng luồng. Lớp nào không áp dụng cho cả tính năng thì ghi một dòng vì sao trong `VERIFY.md` § Lớp không áp dụng; lý do phải cụ thể ("không có trạng thái: hàm thuần"), không phải "không cần".

| Lớp | Câu hỏi | Ví dụ ca |
|---|---|---|
| Luồng chính | Actor đúng làm trọn việc yêu cầu nói, qua mọi thành phần tham gia, ra đúng kết quả và tác dụng phụ? | Tạo ở app quản trị → hiện ở app người dùng → đúng dòng trong DB |
| Nhánh rẽ / ngoại lệ | Mọi `if`/`catch`/early-return mà diff thêm vào có ca đi qua không? Người dùng huỷ giữa chừng, quay lại, bỏ trống tuỳ chọn? | Wizard 3 bước, bấm Back ở bước 3 rồi đổi lựa chọn bước 1 |
| Đầu vào sai, biên | Mỗi lớp tương đương của đầu vào (hợp lệ, sai kiểu, rỗng, null, quá dài, unicode, ký tự đặc biệt) và giá trị biên (min−1, min, max, max+1) | Số lượng 0, 1, giới hạn, giới hạn+1; tên 255 và 256 ký tự |
| Quyền / vai trò | Ma trận vai trò × hành động: ai được, ai bị chặn, chặn ở đâu (UI ẩn, URL guard, API 401/403, CLI từ chối) | Người dùng A đổi id trên URL sang bản ghi của B |
| Vòng đời, chuyển trạng thái | Mọi chuyển hợp lệ ra đúng trạng thái; chuyển không hợp lệ bị từ chối (duyệt đơn đã huỷ, sửa bản ghi đã khoá) | Huỷ đơn đã giao; chạy lại job trên bản ghi đã xử lý |
| Đồng thời, lặp, idempotent | Bấm hai lần, gửi lại request, hai người sửa cùng lúc, job chạy chồng, retry sau timeout | Hai request đặt hàng song song với cùng mã giới hạn 1 lượt |
| Bất đồng bộ | Job/queue/thông báo có chạy, đúng một lần, đúng thứ tự, và kết quả cuối cùng nhìn thấy được ở đâu? Lỗi giữa chừng thì retry hay mất? | Enqueue → worker xử lý → email trong mailbox test; worker chết giữa chừng |
| Lỗi phụ thuộc | DB, dịch vụ ngoài, file, mạng lỗi hoặc chậm: fail-closed hay fail-open, thông báo gì, có mất/nhân đôi dữ liệu không | Dịch vụ thanh toán trả 500; ổ đĩa đầy khi export |
| Toàn vẹn dữ liệu | Trạng thái trước/sau đúng; không ghi thừa, không xoá nhầm, ràng buộc giữ; giao dịch rollback trọn khi lỗi | Đếm dòng trước/sau; lỗi ở bước 2 của 3 thì bước 1 có bị rollback |
| Dữ liệu cũ, tương thích, migration | Bản ghi tạo trước thay đổi, client/phiên bản API cũ, file định dạng cũ, migration chạy trên dữ liệu thật cỡ thật và chạy lại được | Mở đơn tạo trước khi có cột mới; migrate lên rồi rollback |
| Cấu hình, flag | Mỗi giá trị flag/mode mà diff phân nhánh, cả giá trị mặc định khi không cấu hình | Flag tắt: hành vi như base |
| Thời gian, timezone | Chỉ khi có ngày giờ: nửa đêm, cuối tháng, năm nhuận, DST, timezone của server khác của người dùng, "hôm nay" theo ai | Mã hết hạn 23:59 giờ VN, server chạy UTC |
| Hồi quy | Màn hình/API/lệnh lân cận đi qua code bị sửa vẫn như base; bộ test sẵn có của repo vẫn xanh | Báo cáo doanh thu dùng chung hàm tính tổng vừa sửa |
| Bảo mật | IDOR, leo thang quyền, injection qua đầu vào mới, dữ liệu nhạy cảm lộ qua response/log/export, CSRF cho hành động mới | Export CSV có chứa cột email của người khác không |
| Phi chức năng | Chỉ khi yêu cầu nêu, kèm ngưỡng số: thời gian, bộ nhớ, kích thước, khả năng truy cập | Export 100k dòng dưới 30 s |

## Kỹ thuật thiết kế ca

Chọn kỹ thuật theo hình dạng của luồng:

- **Phân hoạch tương đương + giá trị biên** cho mọi đầu vào có miền: một ca cho mỗi lớp, thêm ca ở hai phía mỗi biên. Biên lấy từ code và spec (`<` hay `<=`), không đoán.
- **Bảng quyết định** khi kết quả phụ thuộc nhiều điều kiện cùng lúc (vai trò × trạng thái × flag). Mỗi cột là một tổ hợp có kết quả riêng; gộp cột cho cùng kết quả. Bảng làm lộ tổ hợp mà spec quên nói tới: đó là câu hỏi cho user.
- **Chuyển trạng thái**: vẽ các trạng thái và cạnh; ca cho mỗi cạnh hợp lệ, và cho mỗi cặp (trạng thái, hành động) không có cạnh.
- **Ma trận cặp (pairwise)** khi cấu hình có nhiều chiều độc lập: phủ mọi cặp giá trị thay vì mọi tổ hợp, rồi thêm tổ hợp rủi ro cao chạy riêng.
- **CRUD theo thực thể**: mỗi thực thể bị chạm có ca tạo, đọc, sửa, xoá ở mọi điểm vào cho phép thao tác đó, và kiểm nơi khác đọc thực thể ấy thấy thay đổi.
- **So sánh với base (differential)**: chạy cùng đầu vào trên base và head, so output. Dùng cho refactor, hồi quy, và khi không có spec rõ cho hành vi cũ. Khác biệt nào cũng phải giải thích được bằng một `R`.
- **Thuộc tính / metamorphic** cho thư viện và hàm tính toán: tính chất phải luôn đúng (parse rồi format ra lại chuỗi gốc; sắp xếp xong thì có thứ tự và cùng phần tử; tổng các phần = toàn bộ). Sinh nhiều đầu vào, kiểm tính chất.
- **Đoán lỗi** từ loại thay đổi: thêm cột → dữ liệu cũ null; thêm cache → dữ liệu cũ sau khi sửa; thêm job → chạy chồng; thêm quyền → endpoint cũ quên kiểm; đổi định dạng → client cũ.

## Oracle

Oracle quyết định ca có giá trị hay không. Nguồn chuẩn, theo thứ tự ưu tiên:

1. Lời user và AC đã chốt.
2. Trạng thái thật của hệ: truy vấn DB, đọc file sinh ra, đọc queue/mailbox test, log.
3. Hành vi base trên cùng đầu vào (cho phần phải giữ nguyên).
4. Spec/tài liệu của repo, giá trị tính độc lập (công thức tính lại bằng SQL hay script riêng, không gọi lại chính code đang kiểm).

Quy tắc:

- **Tính từ nguồn, không chép tay.** "Phải có 42 dòng" thành fail giả khi dữ liệu đổi và pass giả khi code sai trùng con số. Tính kỳ vọng bằng truy vấn tại thời điểm chạy; cần chặn "mất sạch" thì dùng mức sàn.
- **Oracle phải có khả năng fail.** Với mỗi oracle, chỉ ra một đối chứng: chạy nó trên base (cho fix bug và tính năng mới, phải fail ở base), trên dữ liệu cố ý sai, hoặc trên vai trò bị cấm. Oracle chưa từng thấy fail có thể là oracle luôn pass (selector không khớp gì, assert so hai biến cùng nguồn, grep chuỗi có sẵn trên mọi trang).
- **Nhìn cả tác dụng phụ.** Response 200 không chứng minh DB đúng; toast "Đã lưu" không chứng minh đã lưu. Mỗi ca ghi ít nhất một quan sát ở tầng sâu hơn tầng thao tác khi luồng có tác dụng phụ.
- **Một ca, một kết luận.** Hai điều cần kiểm là hai ca. Ngoại lệ: một ca lặp trên một tập sinh từ nguồn chuẩn (mọi endpoint lấy bằng grep), đạt khi mọi phần tử đạt, bằng chứng liệt kê từng phần tử.
- **Mock không phải oracle của hệ thật.** Ca chạy trên response giả chỉ chứng minh UI xử lý response giả. Khi buộc phải giả một phụ thuộc (dịch vụ ngoài không có bản test), ghi rõ phần nào là giả và hạ kết luận tương ứng.

## Fix bug và refactor

**Fix bug.**
1. Tái hiện lỗi trên base bằng thao tác nhỏ nhất, lưu bằng chứng. Không tái hiện được thì chưa chắc đã hiểu lỗi: hỏi lại người báo hoặc tìm điều kiện còn thiếu (dữ liệu, vai trò, thời điểm).
2. Cùng ca đó trên head phải đạt. Ca đỏ ở base, xanh ở head là đối chứng tự nhiên của oracle.
3. Quét biến thể cùng lớp lỗi: cùng nguyên nhân ở điểm vào khác (API cùng logic với UI, job dùng chung hàm), ở trạng thái khác, ở biên khác. Lỗi thường không đứng một mình.
4. Hồi quy quanh chỗ sửa: hành vi đúng trước đây của chính đoạn code đó vẫn đúng.

**Refactor.** Yêu cầu là "hành vi không đổi". Chọn tập đầu vào đại diện cho mọi nhánh của code cũ (cả nhánh lỗi), chạy trên base và head, so output và tác dụng phụ. Khác biệt nào cũng là lỗi cho tới khi user nói nó được phép.

## Dữ liệu test

Mỗi luồng chạy với dữ liệu đại diện chứ không chỉ một bản ghi đẹp: rỗng, một, nhiều, rất nhiều (khi có phân trang/giới hạn), bản ghi tạo trước thay đổi, bản ghi ở biên (tên dài nhất, giá trị 0, ngày cuối tháng), bản ghi của người khác (cho quyền). Dữ liệu test mang tiền tố hoặc dải ID riêng để dọn được và để các lần chạy song song không đè nhau.

## Ưu tiên và chia việc

Tính năng lớn có thể có hàng trăm ca. Xếp theo rủi ro = khả năng sai × hậu quả khi sai: mất/sai dữ liệu, quyền, tiền, bất khả hồi (migration, xoá) lên trước; hiển thị phụ xuống sau. Chạy theo thứ tự đó để nếu hết thời gian thì phần còn lại là phần ít rủi ro, và báo cáo nói rõ phần đó chưa chạy.

Chia cho subagent theo luồng (hoặc theo nhóm luồng có chung dữ liệu), mỗi subagent nhận: yêu cầu, các luồng của nó, thông tin môi trường, tiền tố dữ liệu riêng, và đường dẫn tới skill này. Gộp kết quả vào `VERIFY.md` của bạn; bằng chứng của subagent bạn vẫn phải mở xem lại.

## Ví dụ theo miền

**Web UI — mã giảm giá ở trang giỏ hàng.** Luồng: khách nhập mã còn hạn / hết hạn / sai chữ hoa-thường / đã dùng hết lượt; khách áp mã rồi xoá hàng làm giỏ dưới mức tối thiểu; áp hai mã. Ca biên: giỏ đúng bằng mức tối thiểu và kém 1 đồng. Đồng thời: hai tab cùng dùng mã 1 lượt. Oracle: tổng tiền trên màn hình bằng tổng tính lại bằng SQL từ giá và %; sau khi đặt, `orders.discount_code` và số lượt còn lại trong DB đúng; đối chứng: mã hết hạn phải ra lỗi.

**Job nền — gửi email nhắc hạn hằng đêm.** Luồng: cron kích hoạt; người vận hành chạy tay; job chạy lại sau khi chết giữa chừng. Trạng thái: không có ai tới hạn, một người, 10k người; người đã nhận nhắc hôm qua; người đã huỷ đăng ký. Ca: chạy hai lần liền thì không ai nhận hai email (idempotent); SMTP lỗi ở email thứ 50 thì 49 email đầu không bị gửi lại và 51 trở đi được retry; hạn lúc 00:30 giờ VN khi server chạy UTC. Oracle: mailbox test (vd Mailpit) đếm theo người nhận, bảng `reminder_log`; đối chứng: người đã huỷ đăng ký có trong dữ liệu và không được nhận.

**CLI / thư viện — hàm `parse_duration("1h30m")` và lệnh `tool sleep <duration>`.** Phân hoạch: hợp lệ (`90s`, `1h30m`, `0s`), sai (`""`, `1x`, `-5m`, `h`), biên (giá trị lớn nhất trước khi tràn). Thuộc tính: `format(parse(s))` tương đương `s`; `parse(a+b) = parse(a)+parse(b)`. CLI: exit code 0 khi hợp lệ, khác 0 và thông báo trên stderr khi sai; `--help` liệt kê định dạng mới. Hồi quy: mọi nơi trong repo gọi `parse_duration` (grep) vẫn qua bộ test của chúng; định dạng cũ (`90` không đơn vị) vẫn được chấp nhận nếu base chấp nhận. Oracle: so với base trên cùng tập đầu vào; đối chứng: đầu vào sai phải ra exit khác 0.
