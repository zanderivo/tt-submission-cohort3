#Requires -Version 7.0

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
    [Environment]::GetEnvironmentVariable("Path", "User")

foreach ($tool in @("iverilog", "vvp", "make", "python", "cocotb-config")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Required tool '$tool' is unavailable. Run scripts/setup-windows.ps1 first."
    }
}

Write-Host "Checking Python verification packages..."
& python -c "import cocotb, pytest; print(f'cocotb {cocotb.__version__}; pytest {pytest.__version__}')"
if ($LASTEXITCODE -ne 0) {
    throw "Python verification package check failed."
}

Write-Host "Validating Tiny Tapeout metadata and module bindings..."
& python (Join-Path $PSScriptRoot "validate_project.py")
if ($LASTEXITCODE -ne 0) {
    throw "Tiny Tapeout project metadata validation failed."
}

$testDirectory = Join-Path $PSScriptRoot "..\test"
Push-Location $testDirectory
try {
    Write-Host "Running Verilog lint compile..."
    & make lint
    if ($LASTEXITCODE -ne 0) {
        throw "Verilog lint compile failed (exit $LASTEXITCODE)."
    }

    Write-Host "Cleaning prior simulation artifacts..."
    & make clean
    if ($LASTEXITCODE -ne 0) {
        throw "Simulation clean failed (exit $LASTEXITCODE)."
    }

    Write-Host "Running Cocotb smoke test..."
    & make
    if ($LASTEXITCODE -ne 0) {
        throw "Cocotb smoke test failed (exit $LASTEXITCODE)."
    }

    $resultsPath = Join-Path $testDirectory "results.xml"
    if (-not (Test-Path $resultsPath)) {
        throw "Cocotb did not produce test/results.xml."
    }
    if (Select-String -Path $resultsPath -Pattern "<(failure|error)" -Quiet) {
        throw "Cocotb results.xml contains a failure or error."
    }

    Write-Host "Local Tiny Tapeout quality gate passed."
}
finally {
    Pop-Location
}
