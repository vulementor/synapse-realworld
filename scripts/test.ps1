param(
    [ValidateSet("quick", "unit", "milestones", "productionization", "full")]
    [string]$Mode = "quick",
    [string]$VenvPath = ".venv"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$venvPython = Join-Path $VenvPath "Scripts\python.exe"
$venvCli = Join-Path $VenvPath "Scripts\synapse-realworld.exe"
$venvPytest = Join-Path $VenvPath "Scripts\pytest.exe"
$venvRuff = Join-Path $VenvPath "Scripts\ruff.exe"

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment not found at $VenvPath. Run .\scripts\setup.ps1 first."
}

function Invoke-Checked {
    param(
        [string]$Executable,
        [string[]]$Arguments = @()
    )
    Write-Host "> $Executable $($Arguments -join ' ')"
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Executable"
    }
}

function Test-Quick {
    Write-Host "=== QUICK ==="
    Invoke-Checked -Executable $venvPython -Arguments @(
        "-c",
        "import synapse_realworld; print('version=' + synapse_realworld.__version__)"
    )
    Invoke-Checked -Executable $venvCli -Arguments @("--help")
    Invoke-Checked -Executable $venvCli -Arguments @(
        "demo",
        "--population",
        "50",
        "--seed",
        "42"
    )
}

function Test-Unit {
    Write-Host "=== UNIT / CORE ==="
    if (-not (Test-Path $venvRuff)) {
        throw "ruff not found. Re-run setup.ps1."
    }
    if (-not (Test-Path $venvPytest)) {
        throw "pytest not found. Re-run setup.ps1."
    }
    Invoke-Checked -Executable $venvRuff -Arguments @("check", ".")
    Invoke-Checked -Executable $venvPytest
}

function Test-Milestones {
    Write-Host "=== LAA MILESTONES v0.8 ==="
    Invoke-Checked -Executable $venvPytest -Arguments @(
        "-q",
        "tests/test_laa_milestones.py",
        "tests/test_laa_milestone_guards.py"
    )

    $help = & $venvCli --help | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "CLI help failed."
    }

    $required = @(
        "laa-snapshot-001-create",
        "laa-snapshot-001-verify",
        "laa-calibration-001-run",
        "laa-experiment-001-create",
        "laa-experiment-001-lock"
    )
    foreach ($command in $required) {
        if (-not $help.Contains($command)) {
            throw "Missing milestone CLI command: $command"
        }
    }
    Write-Host "Milestone CLI surface: OK"
}

function Test-Productionization {
    Write-Host "=== LAA PRODUCTIONIZATION ==="
    Invoke-Checked -Executable $venvPytest -Arguments @(
        "-q",
        "tests/test_productionization.py"
    )

    $connectors = & $venvCli laa-connectors | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "laa-connectors CLI failed."
    }
    foreach ($profile in @("crm_leads", "sap_outcomes", "inventory", "offers", "ads", "website")) {
        if (-not $connectors.Contains($profile)) {
            throw "Missing connector profile: $profile"
        }
    }
    Write-Host "Production connector surface: OK"
}

switch ($Mode) {
    "quick" {
        Test-Quick
    }
    "unit" {
        Test-Unit
    }
    "milestones" {
        Test-Milestones
    }
    "productionization" {
        Test-Productionization
    }
    "full" {
        Test-Unit
        Test-Quick
        Test-Milestones
        Test-Productionization
    }
}

Write-Host ""
Write-Host "PASS: Synapse Real-World Platform test mode '$Mode' completed successfully."
