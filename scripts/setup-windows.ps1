#Requires -Version 7.0

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Install-PinnedWingetPackage {
    param(
        [Parameter(Mandatory)] [string] $Id,
        [Parameter(Mandatory)] [string] $Version
    )

    Write-Host "Ensuring $Id $Version is installed..."
    & winget install --id $Id --exact --version $Version --silent `
        --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "WinGet failed while installing $Id $Version (exit $LASTEXITCODE)."
    }
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "WinGet is required. Install or update Windows App Installer first."
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git for Windows is required. Install it before running this script."
}

Install-PinnedWingetPackage -Id "GitHub.cli" -Version "2.101.0"
Install-PinnedWingetPackage -Id "Icarus.Verilog" -Version "12.2022.06.11"
Install-PinnedWingetPackage -Id "ezwinports.make" -Version "4.4.1"
Install-PinnedWingetPackage -Id "Python.Python.3.12" -Version "3.12.10"

$pythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312"
$pythonExe = Join-Path $pythonRoot "python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "python.org Python was not found at $pythonExe after installation."
}

Write-Host "Installing pinned Python verification packages..."
& $pythonExe -m pip install --requirement (Join-Path $PSScriptRoot "..\test\requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Python package installation failed (exit $LASTEXITCODE)."
}

$preferredPaths = @(
    (Join-Path $pythonRoot "Scripts"),
    $pythonRoot,
    "C:\iverilog\bin",
    "C:\iverilog\gtkwave\bin",
    "C:\Program Files\Git\usr\bin"
)
$userPathParts = @(
    [Environment]::GetEnvironmentVariable("Path", "User") -split ";" |
        Where-Object { $_ -and ($preferredPaths -notcontains $_) }
)
[Environment]::SetEnvironmentVariable(
    "Path",
    (($preferredPaths + $userPathParts) -join ";"),
    "User"
)
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
    [Environment]::GetEnvironmentVariable("Path", "User")

Write-Host "Verifying toolchain..."
& iverilog -V | Select-Object -First 1
& python -c "import cocotb, pytest; print(f'Python verification ready: cocotb {cocotb.__version__}, pytest {pytest.__version__}')"
& make --version | Select-Object -First 1
& gtkwave --version
& gh --version | Select-Object -First 1

& gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "GitHub CLI is installed but not authenticated. Run: gh auth login"
}

Write-Host "Setup complete. Open a new terminal, then run: pwsh -File .\scripts\check.ps1"
