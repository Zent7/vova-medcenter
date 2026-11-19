param(
    [switch]$Check,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ScriptDir ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Creating virtual environment..."
    py -3 -m venv (Join-Path $ScriptDir ".venv")
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -r (Join-Path $ScriptDir "requirements.txt")
}

$AgentArgs = @()
if ($Check) { $AgentArgs += "--check" }
if ($DryRun) { $AgentArgs += "--dry-run" }

& $Python (Join-Path $ScriptDir "main.py") @AgentArgs
