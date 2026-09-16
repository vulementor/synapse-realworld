# Synapse Real-World Platform — Cài đặt & chạy test (v0.8)

Tài liệu này là hướng dẫn vận hành local dành cho Synapse Real-World Platform v0.8, ưu tiên **Windows 10/11 + PowerShell**. Các lệnh Linux/macOS tương đương được ghi ở cuối.

> Mục tiêu của tài liệu này là giúp một máy mới clone repo, cài dependency, chạy smoke test, chạy toàn bộ test suite và kiểm tra riêng các workflow LAA v0.8 mà không cần dữ liệu production thật.

## 1. Yêu cầu

- Git
- Python **3.11**
- PowerShell 5.1+ hoặc PowerShell 7+
- Internet để cài package lần đầu

Kiểm tra:

```powershell
git --version
py -3.11 --version
```

Nếu máy không có `py`, thử:

```powershell
python --version
```

Python được khuyến nghị là 3.11 vì GitHub Actions của repo đang test trên Python 3.11.

## 2. Clone repo

```powershell
cd C:\Users\vulem\OneDrive\Documents
git clone https://github.com/vulementor/synapse-realworld.git
cd synapse-realworld
```

Nếu repo đã có sẵn:

```powershell
cd C:\duong-dan\toi\synapse-realworld
git switch main
git pull --ff-only origin main
```

## 3. Cài đặt tự động — khuyến nghị

Từ root repo:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

Script sẽ:

1. tìm Python 3.11;
2. tạo `.venv`;
3. nâng cấp pip;
4. cài repo editable với dependency dev;
5. in version package;
6. kiểm tra CLI `synapse-realworld`.

Sau đó kích hoạt môi trường:

```powershell
.\.venv\Scripts\Activate.ps1
```

Nếu PowerShell chặn activation script:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 4. Cài đặt thủ công

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Nếu cần PostgreSQL adapter:

```powershell
python -m pip install -e ".[dev,postgres]"
```

Xác minh:

```powershell
python -c "import synapse_realworld; print(synapse_realworld.__version__)"
synapse-realworld --help
```

Version mong đợi trên `main` hiện tại: `0.8.0`.

## 5. Chạy test tự động bằng PowerShell

Repo có helper:

```powershell
.\scripts\test.ps1 -Mode quick
.\scripts\test.ps1 -Mode unit
.\scripts\test.ps1 -Mode milestones
.\scripts\test.ps1 -Mode productionization
.\scripts\test.ps1 -Mode full
```

### `quick`

Dùng sau mỗi lần pull/code nhỏ:

- import package;
- kiểm tra CLI;
- chạy demo simulation nhỏ.

### `unit`

Chạy:

```text
ruff check .
pytest
```

Đây là core gate của repo.

### `milestones`

Chạy contract tests v0.8:

```text
tests/test_laa_milestones.py
tests/test_laa_milestone_guards.py
```

Các test này dùng **synthetic fixtures only** để kiểm:

- Snapshot #001 identity / tamper detection / immutability;
- Calibration Run #001 readiness guard;
- model candidate → explicit validation/approval;
- Experiment #001 approved-model guard;
- forecast lock trước assignment/outcome.

Passing test **không có nghĩa** model LAA production đã được hiệu chỉnh hoặc experiment thật đã chạy.

### `productionization`

Chạy các contract quan trọng của connector + data-readiness layer:

- LAA connector profile visibility;
- pseudonymous ingest;
- idempotency;
- data-audit fail-closed behavior.

### `full`

Chạy lần lượt:

1. Ruff;
2. full pytest;
3. demo smoke;
4. milestone tests;
5. productionization tests/CLI checks.

Đây là mode nên chạy trước khi push branch/PR.

## 6. Lệnh test thủ công tương đương CI

### Core

```powershell
ruff check .
pytest
synapse-realworld demo --population 50 --seed 42
```

### LAA v0.8 milestone contracts

```powershell
pytest -q tests/test_laa_milestones.py tests/test_laa_milestone_guards.py
```

Kiểm tra CLI surface:

```powershell
synapse-realworld --help
```

Phải thấy tối thiểu:

```text
laa-snapshot-001-create
laa-snapshot-001-verify
laa-calibration-001-run
laa-experiment-001-create
laa-experiment-001-lock
```

## 7. Chạy demo data pipeline bằng dữ liệu fixture

Các file trong `examples/data/` là **synthetic**, không phải dữ liệu khách thật.

```powershell
$DB = ".\tmp\synapse-test.duckdb"
New-Item -ItemType Directory -Force .\tmp | Out-Null

synapse-realworld init-store --db $DB
synapse-realworld ingest-sales .\examples\data\laa_sales_capture_sample.csv --db $DB
synapse-realworld ingest-outcomes .\examples\data\laa_outcomes_sample.csv --db $DB
synapse-realworld ingest-inventory `
  --units-csv .\examples\data\laa_unit_versions_sample.csv `
  --offers-csv .\examples\data\laa_offers_sample.csv `
  --db $DB
synapse-realworld store-stats --db $DB
```

Kiểm data readiness:

```powershell
synapse-realworld data-audit --db $DB --output .\tmp\data-audit.json
Get-Content .\tmp\data-audit.json
```

Fixture có thể cố ý fail một số production gates; điều này là đúng nếu fixture chỉ nhằm kiểm connector/readiness contract.

## 8. Workflow production v0.8

Thứ tự đúng với dữ liệu LAA thật là:

```text
verified exports
→ pseudonymous/idempotent ingest
→ data-audit
→ close blockers
→ laa-snapshot-001-create
→ laa-snapshot-001-verify
→ laa-calibration-001-run
→ human review
→ model validated/approved
→ laa-experiment-001-create
→ laa-experiment-001-lock
→ assignments/exposure/outcomes
→ predicted-vs-actual evaluation
```

Không bỏ qua readiness hoặc human approval bằng cách dùng fixture synthetic.

## 9. Kiểm GitHub Actions

Ba workflow phải xanh trên PR/main:

- `CI`
- `LAA Productionization`
- `LAA Milestones`

Local test giúp phát hiện lỗi sớm, nhưng merge gate cuối vẫn là GitHub Actions.

## 10. Troubleshooting Windows

### `synapse-realworld` không được nhận diện

Dùng executable trực tiếp:

```powershell
.\.venv\Scripts\synapse-realworld.exe --help
```

Hoặc xác nhận venv đã activate:

```powershell
Get-Command python
Get-Command synapse-realworld
```

### Sai Python

```powershell
py -0p
py -3.11 --version
```

Xóa venv sai và tạo lại:

```powershell
Remove-Item -Recurse -Force .venv
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

### PowerShell chặn script

Không cần đổi policy toàn máy:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

### DuckDB file đang bị lock

Đóng process Python/CLI khác đang dùng DB rồi thử lại, hoặc dùng DB test mới dưới `.\tmp\`.

### Test fail sau `git pull`

```powershell
git status
git pull --ff-only origin main
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\test.ps1 -Mode full
```

## 11. Linux/macOS tối thiểu

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
ruff check .
pytest
synapse-realworld demo --population 50 --seed 42
```

## 12. Sau khi local test xanh

Không cần tạo production snapshot từ fixture. Bước thực tế kế tiếp của LAA là bổ sung **verified outcome/transaction history** và chuẩn hóa temporal price/inventory evidence, sau đó mới freeze `LAA Real Dataset Snapshot #001`.
