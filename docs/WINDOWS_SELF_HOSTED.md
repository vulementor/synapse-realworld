# Synapse Real-World Platform — Windows self-hosted runner

Tài liệu này mô tả cách dùng `.github/workflows/windows-self-hosted.yml` để GitHub Actions checkout **đúng commit mới trên GitHub xuống máy Windows local** và chạy test Synapse trên chính máy đó.

Workflow được thiết kế theo convention đang dùng ở `gpt_fullproxy` và `github_review_reel`:

```text
runs-on: [self-hosted, Windows, X64, github_reel_review]
```

## 1. Khi nào workflow chạy

Workflow hỗ trợ hai cách chạy:

1. **Tự động khi `main` có commit mới** — ví dụ sau khi merge PR.
2. **Chạy thủ công bằng `workflow_dispatch`** — trong GitHub Actions có thể chọn branch/ref và chọn test mode.

Không bật `pull_request` cho self-hosted runner của repo public. Mục đích là tránh code từ PR không tin cậy được thực thi trực tiếp trên máy local của anh.

## 2. Runner cần có label nào

Runner Synapse phải match đủ:

```text
self-hosted
Windows
X64
github_reel_review
```

Ba label đầu là default labels của Windows x64 runner. `github_reel_review` là custom label đang dùng chung convention với các repo liên quan.

## 3. Đăng ký runner cho repo Synapse

Nếu runner hiện tại của `github_review_reel` / `gpt_fullproxy` là **repository-level runner**, Synapse cần một runner registration riêng cho repo `vulementor/synapse-realworld` dù có thể chạy trên cùng máy Windows.

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

GitHub sẽ sinh ra lệnh download/config có token ngắn hạn. Chạy đúng lệnh GitHub hiển thị.

Khuyến nghị dùng thư mục riêng, ví dụ:

```text
C:\actions-runner-synapse-realworld
```

Khi config runner, thêm custom label:

```text
github_reel_review
```

Tên runner có thể là:

```text
synapse-realworld-windows
```

Không commit registration token, credentials hoặc file cấu hình runner vào repo.

## 4. Chạy interactive hoặc service

Để test nhanh, mở PowerShell trong folder runner và chạy:

```powershell
.\run.cmd
```

Nếu muốn runner luôn online sau khi reboot, cài nó thành Windows service theo lệnh `svc` do GitHub runner package cung cấp.

Runner phải hiện trạng thái **Idle** trong:

```text
Settings → Actions → Runners
```

thì workflow mới nhận job.

## 5. Workflow làm gì trên máy local

Khi nhận job, workflow sẽ:

```text
GitHub commit
   ↓
actions/checkout@v4
clean=true
fetch-depth=0
   ↓
Setup Python 3.11
   ↓
.\scripts\setup.ps1
   ↓
.\scripts\test.ps1 -Mode <mode>
   ↓
In version + module path + git SHA
```

`actions/checkout` chạy trong workspace riêng của self-hosted runner. Nó checkout đúng `${{ github.sha }}` của run, vì vậy local test gắn trực tiếp với commit trên GitHub.

`clean: true` giúp tránh file build/venv cũ làm sai kết quả. `.venv` sẽ được tạo lại bởi `scripts/setup.ps1` khi cần.

## 6. Test modes

Khi chạy thủ công, có thể chọn:

```text
quick
unit
milestones
productionization
full
```

Mặc định:

```text
full
```

Ý nghĩa giống `scripts/test.ps1`:

- `quick`: import + CLI + demo nhỏ;
- `unit`: Ruff + full pytest;
- `milestones`: Snapshot #001 / Calibration #001 / Experiment #001 contract tests;
- `productionization`: connector + readiness tests;
- `full`: chạy tất cả nhóm trên.

## 7. Chạy thủ công từ GitHub UI

Vào:

```text
GitHub repo
→ Actions
→ windows-self-hosted
→ Run workflow
```

Chọn branch/ref cần test và `test_mode`, sau đó bấm **Run workflow**.

Đây là cách nên dùng nếu anh muốn test một feature branch trước khi merge mà không bật self-hosted runner cho mọi `pull_request`.

## 8. Tự động test code mới trên `main`

Sau mỗi merge/push vào `main`, workflow tự queue.

Nếu runner đang online:

```text
main push
→ self-hosted runner nhận job
→ checkout commit mới
→ setup
→ full test
```

Nếu runner offline, GitHub giữ job ở trạng thái queued cho đến khi runner phù hợp online hoặc run bị hủy/hết hạn.

## 9. Kiểm tra source identity

Cuối workflow có bước in:

```text
package version
module path
git short SHA
```

Dùng ba giá trị này để xác nhận máy local đang test đúng code GitHub vừa tạo, tránh nhầm với package/checkout cũ.

## 10. Security boundary

Self-hosted runner có quyền chạy lệnh trên máy của anh. Vì vậy:

- không chạy workflow self-hosted trên PR không tin cậy;
- không lưu secrets trong workspace repo;
- dùng account/service có quyền tối thiểu cần thiết;
- giữ runner package cập nhật;
- không đặt token registration trong file YAML;
- nếu máy chứa profile/browser/session quan trọng, chỉ cho trusted branches/manual dispatch chạy self-hosted job.

## 11. Quan hệ với Windows hosted CI

Repo vẫn giữ `.github/workflows/windows_local_runbook.yml` chạy trên `windows-latest` của GitHub.

Hai workflow phục vụ hai mục đích khác nhau:

```text
Windows Local Runbook
= kiểm tra setup/test scripts trên Windows sạch do GitHub host

windows-self-hosted
= lấy đúng code GitHub xuống máy Windows thật của anh và chạy cùng test contract
```

Nên giữ cả hai.
