param(
    [string]$VenvPath = ".venv",
    [switch]$WithPostgres
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-Python311 {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        try {
            & py -3.11 --version | Out-Null
            if ($LASTEXITCODE -eq 0) {
                return @("py", "-3.11")
            }
        } catch {
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $version = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($LASTEXITCODE -eq 0 -and $version.Trim() -eq "3.11") {
            return @("python")
        }
    }

    throw "Python 3.11 not found. Install Python 3.11 and re-run this script."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$pythonCmd = Resolve-Python311
Write-Host "Using Python command: $($pythonCmd -join ' ')"

if (-not (Test-Path $VenvPath)) {
    if ($pythonCmd.Count -eq 2) {
        & $pythonCmd[0] $pythonCmd[1] -m venv $VenvPath
    } else {
        & $pythonCmd[0] -m venv $VenvPath
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create virtual environment."
    }
}

$venvPython = Join-Path $VenvPath "Scripts\python.exe"
$venvCli = Join-Path $VenvPath "Scripts\synapse-realworld.exe"

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment Python not found at $venvPython"
}

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip."
}

$installTarget = if ($WithPostgres) { ".[dev,postgres]" } else { ".[dev]" }
& $venvPython -m pip install -e $installTarget
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install Synapse Real-World Platform."
}

$version = & $venvPython -c "import synapse_realworld; print(synapse_realworld.__version__)"
Write-Host "Installed Synapse Real-World Platform version: $version"

if (-not (Test-Path $venvCli)) {
    throw "CLI executable not found at $venvCli"
}

& $venvCli --help | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Synapse CLI smoke check failed."
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "Activate with: .\$VenvPath\Scripts\Activate.ps1"
Write-Host "Run quick test: .\scripts\test.ps1 -Mode quick"
Write-Host "Run full test:  .\scripts\test.ps1 -Mode full"
