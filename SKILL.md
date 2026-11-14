---
name: pr-verify
description: >-
  Nghiệm thu (acceptance) tính năng/MR bằng E2E thật, sửa lỗi theo vòng tới khi ledger GREEN,
  rồi đăng bằng chứng có ảnh lên từng MR GitLab. Use when asked to nghiệm thu, verify or prove
  a feature or MR end to end with evidence.
---

# pr-verify

Đầu vào tối thiểu là **mục tiêu** của tính năng và các MR (hoặc repo + nhánh) chứa nó. Bạn tự quyết test cái gì và bằng công cụ gì; skill này quy định quy trình, chuẩn bằng chứng và điều kiện xong.

## Leading words

- **Tiêu chí (criterion)**: một hành vi quan sát được mà mục tiêu đòi hỏi, ID `C01…`.
- **Oracle**: cách biết tiêu chí đạt, so với *nguồn chuẩn* (DB, config, spec, hành vi ở nhánh đích).
- **Vòng (round)**: một lượt chạy các tiêu chí cần chạy, trên SHA đã ghim. **Vòng cuối** chạy *mọi* tiêu chí trên HEAD cuối.
- **Ledger**: `ledger.jsonl` trong workspace, nơi duy nhất ghi repo, tiêu chí, kết quả, lỗi, phản biện. Báo cáo sinh từ ledger.
- **Green / red**: kết quả của `ledger.py check`. Chỉ *green* mới gọi là nghiệm thu.
- **Before / after**: cùng một kịch bản chạy trên SHA base (`side: base`) và SHA head.

## Công cụ đi kèm (`<skill-dir>/scripts/`)

| Script | Dùng để |
|---|---|
| `ledger.py` | `add` ghi bản ghi (từ chối bản ghi sai schema; `--supersede` thay tiêu chí, `--force` bỏ qua kiểm tra chính sách); `check` ra green/red; `table` sinh bảng báo cáo; `status` đếm theo vòng và trạng thái lỗi; `coverage` tìm file trong diff chưa có tiêu chí; `blank` bắt ảnh trắng |
| `capture.sh` | chạy một lệnh (curl, SQL, test), lưu output đầy đủ + SHA repo + `exit=` vào file bằng chứng, che bí mật |
| `evidence.mjs` | Playwright: `settle()` chờ render xong, `shot()` chụp kèm nhãn SHA, `card()` biến output API/SQL thành ảnh before/after |
| `gl_evidence.py` | kiểm head SHA của MR, upload ảnh (chỉ trong `shots/` và `logs/` của workspace), tạo hoặc sửa đúng một note/khối mô tả |

`<skill-dir>` là thư mục chứa file SKILL.md này (vd `~/.claude/skills/pr-verify`); gọi script bằng đường dẫn tuyệt đối. Tham số: `--help` của `ledger.py`, `capture.sh`, `gl_evidence.py`; comment đầu file và JSDoc từng hàm của `evidence.mjs`.

Cần có: git, bash ≥ 3, python3 ≥ 3.8; `glab` đã `glab auth login --hostname <host GitLab>` (đủ mới để có `glab api --form`); Node + Playwright trong project harness cho kiểm thử UI (`npm i -D @playwright/test && npx playwright install chromium` nếu repo chưa có). Kiểm trên Linux (`systemd-run`, `fuser`). Chỉ hỗ trợ GitLab MR.

## Quyền hạn và điểm dừng

Gọi `pr-verify` là cho phép: dựng môi trường test, tạo dữ liệu test, sửa code trên nhánh nguồn của MR và **commit cục bộ** từng bản sửa đã kiểm chứng. `git push` và đăng/sửa comment hay mô tả MR cần lời user: có sẵn trong yêu cầu (vd "…rồi push và đăng MR"), hoặc hỏi khi tới bước 8.

Khi được phép push, chỉ push vào **nhánh nguồn của MR** (cột `source→target` trong `GOAL.md`): `git push origin HEAD:<source_branch>`, và trước đó kiểm `git rev-parse --abbrev-ref HEAD` trùng `<source_branch>`. Cổng `--expect-sha` của `gl_evidence.py` phát hiện việc push sai nhánh *sau khi* đã push, không ngăn được commit rác đã lên nhánh đích.

Câu hỏi cho user có hai mốc: cuối bước 2 và cuối mỗi lần triage. Câu hỏi nghiệp vụ ghi thành issue `needs-decision` (kèm hai cách hiểu và đề xuất). Trong lúc chờ, vẫn chạy các tiêu chí không phụ thuộc câu hỏi. Khi user trả lời, ghi issue `decided` và trích lời user. Chạy không có kênh tới user (subagent, workflow) thì để câu hỏi vào báo cáo cuối — **nghiệm thu chưa xong**: `needs-decision` làm `ledger.py check` đỏ, nên báo cáo phải nói rõ phần nào chưa nghiệm thu, không được coi là xong.

Dừng hẳn và báo user khi: bước tiếp theo chạm host chưa có trong danh sách host test của `GOAL.md`; hết **5 vòng** (tính cả vòng cuối) mà vẫn *red*.

Lối thoát khi **không có môi trường test**: tiêu chí nào không thể chạy được ghi `verdict: "SKIP"` kèm `approved_by_user` là trích lời user, và `note` nói rõ vì sao. SKIP không dùng cho tiêu chí `baseline` (tiêu chí đó luôn cần ảnh "before" thật), và ledger vẫn đỏ nếu còn SKIP chưa được duyệt.

## Các bước

### 1. Intake

Tạo workspace `${PR_VERIFY_HOME:-$HOME/.pr-verify}/<slug>/` (slug = tên nhánh nguồn chung, hoặc `<project>-<iid>`): `git init`, thư mục `intake/ shots/ logs/ harness/ report/` (mỗi thư mục một `.gitkeep`), và một `.gitignore` tối thiểu:

```
*.env
.env*
secrets/
*.pem
```

Mọi file ghi trong workspace nằm ở **gốc workspace** trừ khi nói khác: `GOAL.md`, `COVERAGE.md`, `ENV.md`, `REVIEW.md`, `ledger.jsonl`; ảnh và log trong `shots/r<N>/`, `logs/r<N>/`; bản báo cáo đăng lên MR trong `report/`.

Với mỗi MR, lưu `glab mr view <iid> -R <group/project> -F json` và `glab mr diff <iid> -R <group/project>` vào `intake/<repo>-<iid>.{json,diff}`. Trên GitLab self-hosted phải chọn host: `export GITLAB_HOST=<host>` (hoặc dùng `glab api --hostname <host> ...`), vì `-R` chỉ chọn *project*, không chọn host. User không đưa iid thì tìm MR theo nhánh nguồn, ghi MR đã chọn và MR đã loại (kèm lý do) trong `GOAL.md`. Đọc issue liên kết: `#N` không có tiền tố thuộc project của chính MR đó.

Ghi `GOAL.md`:
- mục tiêu một câu, lấy từ lời user;
- bảng repo: `tên (dùng trong ledger) | đường dẫn clone | project | iid | source→target | base SHA | head SHA`. Base SHA = `git merge-base <head> origin/<target>`; khác `diff_refs.base_sha` của MR thì ghi cả hai;
- trong/ngoài phạm vi;
- danh sách host/DB test, kèm nguồn xác nhận (lời user, hoặc doc của repo gọi đó là môi trường test).

Ghi mỗi repo vào ledger: `{"kind":"repo","name":…,"path":…,"project":…,"mr":…,"base":…,"dirty_ok":[…]}`. Clone local phải ở đúng head SHA của MR, và cây sạch ngoài `dirty_ok` (config môi trường local). `dirty_ok` chỉ được liệt kê **file config cục bộ**; `ledger.py` từ chối glob rộng (`*`, `*.py`, …) và `check` báo đỏ nếu có file **source code** sửa mà chưa commit — code đang chạy phải là code trong SHA đã ghi.

Xong khi: `GOAL.md` đủ các mục trên; ledger có bản ghi `repo` cho mọi repo; `git -C <clone> rev-parse HEAD` khớp head SHA của từng MR.

### 2. Tiêu chí

Đọc [references/criteria.md](references/criteria.md). Suy ra tiêu chí từ mục tiêu, diff và issue, phủ mọi lớp luồng mà tính năng chạm tới, rồi ghi bằng `ledger.py add -f`. Viết `COVERAGE.md`: mỗi file trong diff có một dòng (hoặc một glob cho thay đổi cơ học), trỏ tới tiêu chí hoặc ghi lý do. Thêm mục "Lớp luồng" ghi lớp nào không áp dụng và vì sao.

Xong khi: `ledger.py --ws <ws> coverage --diff <repo>=intake/<repo>-<iid>.diff …` báo 0 gap; mọi câu hỏi mở đã thành issue `needs-decision` và đã hỏi user (mốc 1).

### 3. Môi trường

Đọc [references/environment.md](references/environment.md). Dựng app cho head SHA. Dựng thêm phía base khi có tiêu chí `baseline` hoặc khi triage cần xác minh "có sẵn ở nhánh đích" — phía base dùng worktree **ngoài** clone và DB/schema riêng, xem environment.md. Ghi `ENV.md`: mỗi app gồm cổng, PID/unit, SHA, file config đã đọc, host/DB mà nó kết nối, cách reset dữ liệu test, cách dừng.

Xong khi: mỗi app có `logs/env-<app>.txt` (health check qua `capture.sh`) trên đúng SHA đã ghi, và mọi host/DB trong `ENV.md` nằm trong danh sách host test của `GOAL.md`.

### 4. Vòng N: chạy và ghi bằng chứng

Đọc [references/evidence.md](references/evidence.md). Viết harness trong `harness/`: ưu tiên framework E2E repo đã có, không có thì dùng Playwright Test (`npm i -D @playwright/test && npx playwright install chromium`, rồi `npx playwright test`). Harness chạy với **CWD = workspace** (`shot()` và `capture.sh` ghi đường dẫn tương đối theo CWD). Chạy các tiêu chí cần chạy ở vòng N. Mỗi tiêu chí ghi một bản ghi `result` gồm `round`, `verdict`, `evidence`, `commits` (SHA thật của mọi repo trong `repos`), và `side: base` cho phía before. Với `side: base`, `commits` là **base SHA** (`repo["base"]`), không phải HEAD. Commit workspace sau mỗi vòng.

Xong khi: mọi tiêu chí cần chạy ở vòng N có `result` của vòng N, và bạn đã mở ít nhất một ảnh của mỗi PASS.

### 5. Triage

Phân loại mọi FAIL/BLOCKED theo bảng ở [references/triage.md](references/triage.md), xử lý theo loại, rồi hỏi user các `needs-decision` mới (mốc 2).

Xong khi: mọi FAIL/BLOCKED đã thuộc đúng một loại, và mỗi lỗi sản phẩm có issue `open` kèm `repro` (bước tái hiện) và `suspect` (`file:line` nghi ngờ).

### 6. Fix

Sửa từng issue `open` trong phạm vi theo triage.md § Fix.

Xong khi: mọi issue là `fixed` (có `fix_commit`), `decided` (có `decision` và `decided_by`) hoặc `out-of-scope` (có `reason`). Issue `needs-decision` **chưa tính là xong**: nó làm `ledger.py check` đỏ, nên phải hỏi được user và chuyển sang `decided` trước khi qua bước 7.

### 7. Lặp tới green

Theo triage.md § Vòng sau: dựng lại app có code đổi, quay lại bước 4 với vòng N+1. Theo dõi tiến độ giữa các vòng bằng `ledger.py --ws <ws> check --progress`. Khi `--progress` đã green: chạy **vòng cuối** (mọi tiêu chí trên HEAD cuối), rồi phản biện độc lập theo triage.md § Phản biện độc lập. Phản biện bác PASS nào thì quay về bước 5.

Xong khi: `python3 <skill-dir>/scripts/ledger.py --ws <ws> check` in **GREEN (final)**.

### 8. Báo cáo và đăng MR

Đọc [references/report.md](references/report.md). Sinh mô tả và comment bằng chứng cho **từng** MR từ ledger, rồi chạy `gl_evidence.py --dry-run`. Khi đã có lời user: push đúng nhánh nguồn (`git push origin HEAD:<source_branch>`), đăng bằng `gl_evidence.py --expect-sha <head SHA trong ledger>`, mở MR trong trình duyệt đã đăng nhập và nhìn thấy mọi ảnh hiển thị. Chưa có lời user thì dừng ở dry-run và đưa user lệnh đăng. Đường dẫn ảnh trong body phải nằm trong `shots/` hoặc `logs/` của workspace; tên file có khoảng trắng thì bọc trong `<...>`.

Xong khi: mỗi MR có mô tả và đúng một comment bằng chứng với mọi ảnh hiển thị; hoặc user đã nhận bản dry-run và lệnh đăng.

### 9. Dọn dẹp

Xong khi: mọi PID/unit/cổng trong `ENV.md` đã dừng (cách dừng: environment.md § Chạy bền) hoặc đã báo user URL + PID của cái để lại; worktree tạm cho phía base đã gỡ.

## Báo cáo cuối cho user

Nêu đủ các mục:
- output `ledger.py check` nguyên văn và bảng `ledger.py table`;
- số vòng đã chạy;
- lỗi đã sửa, kèm commit;
- lỗi và rủi ro còn lại, câu hỏi chưa chốt;
- link từng MR, hoặc lệnh đăng nếu chưa đăng;
- phần chưa chạy được và lý do;
- tiến trình còn để lại;
- đường dẫn workspace.

`ledger.py check` không in **GREEN (final)** thì nghiệm thu **chưa đạt**: báo cáo phải nói rõ tiêu chí nào chưa đạt và vì sao, không dùng cách nói "đã nghiệm thu" cho phần chưa xanh.
