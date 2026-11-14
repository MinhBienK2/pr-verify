# Triage và vòng sửa

Một FAIL là một *lời khẳng định* cho tới khi tái hiện được. Triage quyết định ai sửa cái gì; sai ở đây thì vòng lặp hoặc sửa nhầm sản phẩm, hoặc che lỗi thật.

## Phân loại mỗi FAIL / BLOCKED

| Loại | Dấu hiệu | Xử lý |
|---|---|---|
| **Sản phẩm** | Tái hiện được bằng tay/lệnh một dòng; ngược oracle; khác nhánh đích theo hướng xấu | `issue` `open`, kèm `repro` + `suspect` (bước tái hiện + `file:line` nghi ngờ) → Fix |
| **Có sẵn ở nhánh đích** | Phía base cũng hỏng y hệt (cần chạy phía base để biết) | `issue` `out-of-scope`, `reason: "pre-existing"`, đưa vào mục rủi ro của báo cáo; chỉ sửa khi user đồng ý |
| **Harness** | Selector sai, chờ chưa đủ, oracle chép tay, đọc nhầm output, file tạm dùng chung giữa tiến trình | Sửa harness, ghi lại `result` cho tiêu chí đó trong **cùng vòng** (bản ghi sau cùng của vòng được tính) |
| **Môi trường** | App chết/OOM, tunnel rớt, dữ liệu test thiếu, cổng bận | Sửa môi trường, chạy lại cùng vòng; BLOCKED chỉ khi không tự sửa được, `note` nêu lý do |
| **Không có môi trường test** | Không tồn tại app/DB test để chạy tiêu chí này, và user đã duyệt bỏ qua | `result` với `verdict: "SKIP"`, `approved_by_user` là trích lời user, `note` nêu lý do. **Không dùng cho tiêu chí `baseline`** (tiêu chí đó luôn cần ảnh "before" thật) |
| **Cần quyết định** | Spec cho phép hai cách hiểu | `issue` `needs-decision`, hỏi user theo mốc ở SKILL.md |

Kiểm trước khi kết luận "sản phẩm":
- Chạy lại lần hai từ cùng trạng thái dữ liệu. Không lặp lại thì nghi chập chờn: chạy 3–5 lần, ghi tỉ lệ.
- Lỗi trong output có đúng là lỗi của tiêu chí đang kiểm không (timeout, lỗi setup, lỗi import là harness).
- Oracle có lấy từ nguồn chuẩn không.
- Có phải hai test đang sửa chung một bản ghi.

## Fix

1. Tái hiện bằng lệnh nhỏ nhất, lưu output qua `capture.sh`.
2. Repo có bộ test: viết test hồi quy, chạy và thấy nó **đỏ vì đúng lỗi này** (đỏ vì fixture/import hỏng không tính).
3. Sửa tối thiểu, theo convention của repo (đọc `AGENTS.md`/skill sửa lỗi của repo nếu có).
4. Chạy bộ test của repo; xanh mới commit. Một bản sửa một commit, message nêu `Bxx`/`Cxx`.
5. Ghi lại issue: `"status":"fixed","fix_commit":"<sha>"` (kèm `repro`/`suspect` đã có từ lúc mở issue). Ledger đỏ nếu commit này không nằm trong HEAD của repo.

Phải sửa file không liên quan tới lỗi, hoặc phải revert lần thứ hai cho cùng lỗi: dừng, báo user cách hiểu của bạn.

## Vòng sau

- Dựng lại app có code đổi; xác nhận SHA mới đang chạy (health check).
- Vòng giữa: chạy lại tiêu chí FAIL, mọi tiêu chí có `repos` chứa repo vừa sửa (ledger đỏ vì SHA cũ cho tới khi chạy lại), và luồng chính của mỗi app như smoke.
- Khi `check --progress` đã green: **vòng cuối** chạy mọi tiêu chí (cả phía base của tiêu chí `baseline` nếu base SHA đổi) trên HEAD cuối. Đây là vòng mà báo cáo trích dẫn. Trần 5 vòng tính cả vòng cuối: tới vòng 4 mà `--progress` còn đỏ thì vòng 5 là vòng cuối, rồi báo phần còn đỏ.

## Phản biện độc lập

Sau vòng cuối, giao một subagent mới. Chỉ đưa: `GOAL.md`, `ENV.md`, `ledger.jsonl`, thư mục `shots/` `logs/` `harness/`, cách gọi app. Không đưa kết luận của bạn. Yêu cầu nó:
- với mỗi PASS, cố bác bỏ: bằng chứng có thật sự chứng minh oracle không, có chụp đúng SHA không, harness có `route`/stub mà result không đánh dấu `mock` không;
- tự chạy lại ít nhất các tiêu chí rủi ro cao (phân quyền, mất dữ liệu, bảo mật);
- mặc định nghi ngờ;
- ghi `REVIEW.md`: mỗi PASS một dòng gồm giữ/bác, lý do, file đã mở.

**Reviewer không ghi bản ghi `result` vào `ledger.jsonl`.** Kết quả chạy lại của reviewer nằm trong `REVIEW.md`; nếu reviewer bác bỏ một PASS thì *bạn* ghi `result` ở vòng mới (theo bước 4) rồi phản biện lại. Lý do: `ledger.py check` lấy vòng cuối là vòng lớn nhất trong ledger, nên một `result` viết ở vòng mới sẽ khiến mọi tiêu chí khác bị coi là "chưa chạy ở vòng cuối" và phá luật vòng cuối.

Ghi `{"kind":"review","round":<R>,"file":"REVIEW.md","refuted":[<id bị bác>]}`. Có PASS bị bác thì quay về Triage; sau vòng cuối mới phải phản biện lại.
