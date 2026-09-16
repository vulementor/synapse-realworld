# Synapse Real-World Platform — Windows self-hosted runner

Tài liệu này mô tả cách dùng `.github/workflows/windows-self-hosted.yml` để GitHub Actions đồng bộ code mới xuống đúng máy Windows local của anh và chạy test Synapse trên chính máy đó.

Workflow dùng convention giống `gpt_fullproxy` và `github_review_reel`:

```text
runs-on: [self-hosted, Windows, X64, github_reel_review]
```

## 1. Canonical local repo của Synapse

Đường dẫn làm việc local chính thức:

```text
C:\Users\vulem\OneDrive\Documents\ChatGPT\Kabin Toolkit Test\synapse-realworld
```

Workflow lưu đường dẫn này trong biến:

```text
SYNAPSE_LOCAL_REPO
```

Khi có push/merge mới vào `main`, self-hosted runner sẽ đồng bộ **chính repo ở đường dẫn này** rồi chạy setup/test ngay tại đây.

## 2. Quy tắc an toàn khi đồng bộ local repo

Workflow không dùng `git reset --hard` và không tự xóa code local.

Trước khi cập nhật, nó chạy:

```text
git status --porcelain
```

Nếu repo local có file modified/untracked chưa xử lý, workflow **dừng ngay** và báo lỗi. Anh cần commit, stash hoặc xóa các file đó trước khi chạy lại.

Nếu repo sạch:

```text
git fetch origin main --prune
→ git switch main
→ git merge --ff-only origin/main
→ xác nhận local HEAD == github.sha
```

Nếu thư mục canonical chưa tồn tại, workflow sẽ clone repo vào đúng đường dẫn trên.

Nếu đường dẫn đã tồn tại nhưng không phải Git repo và có dữ liệu bên trong, workflow dừng để tránh ghi đè nhầm folder.

## 3. Khi nào workflow chạy

Workflow có hai chế độ:

1. **Push/merge vào `main`**
   - tự động đồng bộ canonical local repo;
   - chạy setup/test trong đúng folder `Kabin Toolkit Test\synapse-realworld`.

2. **Manual `workflow_dispatch`**
   - cho phép chọn branch/ref và test mode;
   - chỉ test branch đó trong workspace của runner;
   - **không thay đổi canonical local working repo**.

Không bật `pull_request` cho self-hosted runner của repo public để tránh code PR không tin cậy chạy trực tiếp trên máy anh.

## 4. Runner cần label nào

Runner phải match:

```text
self-hosted
Windows
X64
github_reel_review
```

Ba label đầu là default label của Windows x64 runner. `github_reel_review` là custom label đang dùng chung convention với các repo toolkit khác.

## 5. Đăng ký runner cho repo Synapse

Nếu runner hiện tại của `github_review_reel` / `gpt_fullproxy` là repository-level runner, Synapse cần registration riêng cho `vulementor/synapse-realworld`, dù vẫn có thể chạy trên cùng máy Windows.

Trong GitHub:

```text
synapse-realworld
→ Settings
→ Actions
→ Runners
→ New self-hosted runner
→ Windows
→ x64
```

GitHub sẽ sinh lệnh download/config có token ngắn hạn. Chạy đúng lệnh GitHub hiển thị.

Khuyến nghị folder runner riêng:

```text
C:\actions-runner-synapse-realworld
```

Custom label:

```text
github_reel_review
```

Tên runner gợi ý:

```text
synapse-realworld-windows
```

Không commit registration token, credentials hoặc config runner vào repo.

## 6. Quyền truy cập OneDrive rất quan trọng

Canonical repo nằm dưới profile:

```text
C:\Users\vulem\OneDrive\...
```

Vì vậy process chạy GitHub Runner phải có quyền đọc/ghi vào profile `vulem` và folder OneDrive này.

Cách đơn giản nhất khi test ban đầu là chạy runner interactive từ session Windows của anh:

```powershell
cd C:\actions-runner-synapse-realworld
.\run.cmd
```

Nếu cài runner thành Windows service, kiểm tra service đang chạy bằng account có quyền truy cập folder `C:\Users\vulem\OneDrive\...`. Nếu service chạy bằng account hệ thống không thấy OneDrive/profile của anh, bước sync canonical repo sẽ fail.

## 7. Workflow làm gì khi `main` có code mới

```text
GitHub main commit
   ↓
self-hosted runner nhận job
   ↓
actions/checkout vào runner workspace để xác định exact SHA
   ↓
kiểm canonical local repo sạch
   ↓
fetch + fast-forward main
   ↓
assert local HEAD == github.sha
   ↓
SYNAPSE_TEST_ROOT =
C:\Users\vulem\OneDrive\Documents\ChatGPT\Kabin Toolkit Test\synapse-realworld
   ↓
setup Python 3.11
   ↓
scripts/setup.ps1
   ↓
scripts/test.ps1 -Mode full
   ↓
in version + module path + git SHA
```

Như vậy khi job xanh, folder mà anh mở trong VS Code/Codex/terminal cũng chính là code vừa được GitHub cập nhật và test.

## 8. Test modes

Manual dispatch hỗ trợ:

```text
quick
unit
milestones
productionization
full
```

Mặc định là `full`.

- `quick`: import + CLI + demo nhỏ;
- `unit`: Ruff + full pytest;
- `milestones`: Snapshot #001 / Calibration #001 / Experiment #001 contract tests;
- `productionization`: connector + readiness tests;
- `full`: chạy toàn bộ.

## 9. Chạy thủ công từ GitHub UI

```text
GitHub repo
→ Actions
→ windows-self-hosted
→ Run workflow
```

Chọn branch/ref và `test_mode`.

Manual dispatch dùng runner workspace và không đổi canonical local repo, nên phù hợp để test feature branch trước khi merge.

## 10. Tự động lấy code mới về local

Sau mỗi merge/push `main`:

```text
main push
→ windows-self-hosted
→ canonical local repo fast-forward
→ full test
```

Nếu runner offline, GitHub giữ job queued cho đến khi runner phù hợp online hoặc run bị hủy/hết hạn.

Nếu canonical repo đang có local changes, job fail-safe thay vì ghi đè.

## 11. Kiểm tra source identity

Cuối workflow sẽ in:

```text
validated root
package version
module path
git short SHA
```

Expected validated root trên `main` push:

```text
C:\Users\vulem\OneDrive\Documents\ChatGPT\Kabin Toolkit Test\synapse-realworld
```

## 12. Security boundary

Self-hosted runner có quyền chạy lệnh trên máy anh. Vì vậy:

- không chạy self-hosted workflow trên PR không tin cậy;
- chỉ auto-trigger branch `main`;
- branch khác test bằng manual dispatch;
- không lưu secrets trong repo/worktree;
- dùng account/service có quyền tối thiểu;
- giữ runner package cập nhật;
- workflow không tự reset/xóa local changes.

## 13. Quan hệ với Windows hosted CI

Repo vẫn có `.github/workflows/windows_local_runbook.yml` chạy trên máy Windows sạch của GitHub.

```text
Windows Local Runbook
= chứng minh setup/test scripts chạy trên Windows sạch

windows-self-hosted
= đồng bộ code GitHub về canonical repo trên máy anh và chạy cùng test contract
```

Nên giữ cả hai.
