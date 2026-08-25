$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venvPath = Join-Path $backend ".venv"
$venvPython = Join-Path $venvPath "Scripts\\python.exe"
$venvActivate = Join-Path $venvPath "Scripts\\Activate.ps1"
$requirementsPath = Join-Path $backend "requirements.txt"
$venvRequirementsMarker = Join-Path $venvPath ".requirements.sha256"
$databaseUrl = "postgresql+psycopg://medcenters:medcenters@127.0.0.1:5434/medcenters"

Write-Host "Preparing MedCenters demo..." -ForegroundColor Cyan

function Stop-DemoContainerIfRunning {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $containerIds = @(docker ps -q --filter "name=^/$Name$")
    if ($containerIds.Count -eq 0) {
        return
    }

    Write-Host "Stopping stale Docker container $Name so the current source tree is used..." -ForegroundColor Yellow
    docker stop $Name | Out-Null
}

function Stop-RepoProcessOnPort {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    for ($attempt = 1; $attempt -le 10; $attempt++) {
        $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
        $processIds = @($connections | ForEach-Object { $_.OwningProcess } | Where-Object { $_ -gt 0 } | Select-Object -Unique)
        if ($processIds.Count -eq 0) {
            return
        }

        $retry = $false
        foreach ($processId in $processIds) {
            $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
            $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($null -eq $process -and $null -eq $processInfo) {
                $retry = $true
                continue
            }

            $commandLine = [string]$processInfo.CommandLine
            $executablePath = [string]$processInfo.ExecutablePath
            $processName = [string]$process.ProcessName
            $isCurrentRepoProcess = $commandLine.Contains($root) -or $executablePath.Contains($root)
            $isKnownDemoProcess =
                ($Label -eq "backend" -and $processName -in @("python", "python3", "uvicorn")) -or
                ($Label -eq "frontend" -and $processName -in @("node", "npm"))

            if ($isCurrentRepoProcess -or $isKnownDemoProcess) {
                Write-Host "Stopping previous $Label process on port $Port (PID $processId)..." -ForegroundColor Yellow
                Stop-ProcessTree -ProcessId $processId
                $retry = $true
                continue
            }

            throw "Port $Port is already used by PID $processId outside this checkout. Close that process and run .\start-demo.ps1 again."
        }

        if ($retry) {
            Start-Sleep -Seconds 1
            continue
        }
    }

    throw "Port $Port did not become free after stopping the previous $Label. Restart the terminal or close the process using that port."
}

function Stop-ProcessTree {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId
    )

    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId ([int]$child.ProcessId)
    }

    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-StaleBackendPythonProcesses {
    $pythonProcesses = @(
        Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue
    )
    foreach ($processInfo in $pythonProcesses) {
        $commandLine = [string]$processInfo.CommandLine
        $executablePath = [string]$processInfo.ExecutablePath
        $isBackendProcess =
            $commandLine.Contains($backend) -or
            $commandLine.Contains($venvPath) -or
            $executablePath.Contains($venvPath) -or
            $commandLine.Contains("multiprocessing.spawn")

        if ($isBackendProcess) {
            Write-Host "Stopping stale backend Python process (PID $($processInfo.ProcessId))..." -ForegroundColor Yellow
            Stop-ProcessTree -ProcessId ([int]$processInfo.ProcessId)
        }
    }
}

function Test-CurrentBackendRunning {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health" -UseBasicParsing -TimeoutSec 2
        return (
            $health.status -eq "ok" -and
            $health.database_ok -eq $true -and
            $health.database_dialect -eq "postgresql" -and
            [string]$health.database_url -like "*127.0.0.1:5434*" -and
            $health.build_revision -eq "development"
        )
    } catch {
        return $false
    }
}

function Invoke-CheckedNativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$ErrorMessage
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $ErrorMessage
    }
}

function Get-RequirementsHash {
    return (Get-FileHash -LiteralPath $requirementsPath -Algorithm SHA256).Hash
}

function Remove-DirectoryWithRetry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            if (Test-Path -LiteralPath $Path) {
                Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            }
            return
        } catch {
            if ($attempt -eq 5) {
                throw
            }
            Start-Sleep -Seconds 1
        }
    }
}

function New-BackendVenv {
    Write-Host "Creating backend virtual environment..." -ForegroundColor Yellow
    Push-Location $backend
    try {
        $created = $false
        if (Get-Command py -ErrorAction SilentlyContinue) {
            foreach ($version in @("3.12", "3.11")) {
                & py "-$version" -m venv .venv
                if ($LASTEXITCODE -eq 0) {
                    $created = $true
                    break
                }
            }
        }

        if (-not $created) {
            $candidatePythonPaths = @(
                (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
                (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
                "C:\Program Files\Python312\python.exe",
                "C:\Program Files\Python311\python.exe"
            )
            foreach ($candidatePython in $candidatePythonPaths) {
                if (-not (Test-Path -LiteralPath $candidatePython)) {
                    continue
                }

                & $candidatePython -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 12) else 1)"
                if ($LASTEXITCODE -ne 0) {
                    continue
                }

                & $candidatePython -m venv .venv
                if ($LASTEXITCODE -eq 0) {
                    $created = $true
                    break
                }
            }
        }

        if (-not $created) {
            & python -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 12) else 1)"
            if ($LASTEXITCODE -eq 0) {
                Invoke-CheckedNativeCommand -Command { python -m venv .venv } -ErrorMessage "Could not create backend virtual environment."
                $created = $true
            }
        }

        if (-not $created) {
            throw "Python 3.11 or 3.12 is required for backend dependencies. Install one of them or make the py launcher see it."
        }
    }
    finally {
        Pop-Location
    }
}

@(
    "vova-medcenter-preview",
    "vova-medcenter-backend",
    "vova-medcenter-frontend",
    "vova-medcenter-db"
) | ForEach-Object {
    Stop-DemoContainerIfRunning -Name $_
}

$backendAlreadyRunning = Test-CurrentBackendRunning
if ($backendAlreadyRunning) {
    Write-Host "Current local backend is already running on http://127.0.0.1:8000." -ForegroundColor Green
} else {
    Stop-RepoProcessOnPort -Port 8000 -Label "backend"
}
Stop-RepoProcessOnPort -Port 5173 -Label "frontend"

Push-Location $root
try {
    docker compose -p medcenters up -d db
    Write-Host "Database container is up." -ForegroundColor Green
}
finally {
    Pop-Location
}

if (-not $backendAlreadyRunning) {
    if (Test-Path -LiteralPath $venvPython) {
        $recreateVenv = $false
        & $venvPython -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 12) else 1)"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Backend virtual environment uses an unsupported Python; recreating it..." -ForegroundColor Yellow
            $recreateVenv = $true
        } else {
            & $venvPython -m pip --version | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Host "Backend virtual environment is broken; recreating it..." -ForegroundColor Yellow
                $recreateVenv = $true
            } else {
                $expectedRequirementsHash = Get-RequirementsHash
                $installedRequirementsHash = if (Test-Path -LiteralPath $venvRequirementsMarker) {
                    (Get-Content -LiteralPath $venvRequirementsMarker -Raw).Trim()
                } else {
                    ""
                }
                if ($installedRequirementsHash -ne $expectedRequirementsHash) {
                    Write-Host "Backend dependencies are missing or out of date; recreating virtual environment..." -ForegroundColor Yellow
                    $recreateVenv = $true
                }
            }
        }

        if ($recreateVenv) {
            Write-Host "Backend virtual environment is broken; recreating it..." -ForegroundColor Yellow
            Stop-StaleBackendPythonProcesses
            Remove-DirectoryWithRetry -Path $venvPath
        }
    }

    if (-not (Test-Path -LiteralPath $venvPython)) {
        New-BackendVenv
    }

    Write-Host "Installing backend dependencies..." -ForegroundColor Yellow
    Push-Location $backend
    try {
        Invoke-CheckedNativeCommand -Command { & $venvPython -m pip install --upgrade pip } -ErrorMessage "Could not upgrade pip in backend virtual environment."
        Invoke-CheckedNativeCommand -Command { & $venvPython -m pip install -r requirements.txt } -ErrorMessage "Could not install backend dependencies."
        Set-Content -LiteralPath $venvRequirementsMarker -Value (Get-RequirementsHash) -Encoding ASCII
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $frontend "node_modules"))) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    Push-Location $frontend
    try {
        Invoke-CheckedNativeCommand -Command { npm install } -ErrorMessage "Could not install frontend dependencies."
    }
    finally {
        Pop-Location
    }
}

$backendCommand = @"
cd "$backend"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
`$env:DATABASE_URL="$databaseUrl"
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
"@

$frontendCommand = @"
cd "$frontend"
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
"@

if (-not $backendAlreadyRunning) {
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand
}

$backendReady = $backendAlreadyRunning
if (-not $backendReady) {
    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 1
        try {
            Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
            $backendReady = $true
            break
        } catch {
        }
    }
}

if (-not $backendReady) {
    throw "Backend did not become ready on http://127.0.0.1:8000."
}

try {
    $importResult = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/imports/demo-legacy" -TimeoutSec 120
    Write-Host "Legacy demo DB synced. Created: $($importResult.created). Updated: $($importResult.updated). Total: $($importResult.total)." -ForegroundColor Green
} catch {
    Write-Host "Could not sync legacy demo DB automatically." -ForegroundColor Yellow
    Write-Host $_.Exception.Message -ForegroundColor Yellow
}

Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand
Start-Sleep -Seconds 5
Start-Process "http://127.0.0.1:5173/demo/index.html"

Write-Host "Demo UI opened: http://127.0.0.1:5173/demo/index.html" -ForegroundColor Green
