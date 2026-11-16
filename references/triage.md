# Khi ca hỏng

Một ca hỏng là một lời khẳng định cho tới khi tái hiện được. Phân loại sai thì hoặc sửa nhầm sản phẩm, hoặc che mất lỗi thật.

## Phân loại

| Loại | Dấu hiệu | Xử lý |
|---|---|---|
| **Lỗi sản phẩm** | Tái hiện được bằng thao tác/lệnh nhỏ nhất; ngược oracle; khác base theo hướng xấu | Ghi vào `VERIFY.md` § Lỗi: bước tái hiện, kết quả mong đợi và thực tế, `file:line` nghi ngờ, bằng chứng. Sửa chỉ khi user đã yêu cầu sửa |
| **Có sẵn ở base** | Chạy cùng ca trên base cũng hỏng y hệt | Ghi là lỗi có sẵn, đưa vào mục rủi ro của báo cáo; không tính là lỗi của thay đổi, không sửa trừ khi user muốn |
| **Lỗi harness** | Selector sai, chờ chưa đủ, oracle chép tay, đọc nhầm output, hai ca dùng chung bản ghi | Sửa harness, chạy lại ca; ghi lại vì sao lần trước sai |
| **Môi trường** | App chết/OOM, dữ liệu test thiếu, cổng bận, app chạy bản build cũ | Sửa môi trường, chạy lại; không tự sửa được thì ca là `không chạy được` kèm lý do |
| **Cần quyết định** | Spec cho phép hai cách hiểu, hoặc hành vi mới hợp lý nhưng khác yêu cầu | Hỏi user, kèm hai cách hiểu và đề xuất; ca giữ trạng thái chờ |

Kiểm trước khi kết luận "lỗi sản phẩm":

- Chạy lại từ cùng trạng thái dữ liệu. Không lặp lại thì nghi chập chờn: chạy 3–5 lần, ghi tỉ lệ; chập chờn cũng là lỗi nếu sản phẩm là nguồn của nó.
- Lỗi trong output có đúng là của ca đang kiểm không (timeout, lỗi setup, lỗi import thường là harness).
- Oracle có lấy từ nguồn chuẩn và có đối chứng không.
- App có đang chạy đúng SHA không.

## Sửa (chỉ khi user đã yêu cầu sửa)

1. Tái hiện bằng thao tác nhỏ nhất, lưu bằng chứng.
2. Repo có bộ test: viết test hồi quy và thấy nó đỏ **vì đúng lỗi này** (đỏ vì fixture hay import hỏng không tính).
3. Sửa tối thiểu theo convention của repo (đọc `AGENTS.md`/`CLAUDE.md` của repo).
4. Chạy bộ test của repo; xanh mới commit cục bộ, mỗi bản sửa một commit, message nêu lỗi.
5. Dựng lại app trên SHA mới, xác nhận nó đang chạy SHA đó.

Bản sửa đòi đụng file không liên quan tới lỗi, hoặc phải revert lần thứ hai cho cùng lỗi: dừng, báo user cách hiểu của bạn.

## Chạy lại sau khi sửa

Chạy lại: ca đã hỏng; mọi ca có luồng đi qua code vừa sửa; luồng chính của mỗi app như smoke. Trước khi báo cáo, chạy lại toàn bộ ca trên SHA cuối cùng nếu có bản sửa nào sau lượt chạy đầy đủ gần nhất: kết quả trên SHA cũ không nói gì về SHA mới. Ghi SHA của lượt chạy cuối vào `VERIFY.md`.
