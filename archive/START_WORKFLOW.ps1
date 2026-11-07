$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptArgs = @($args)
$pythonDownloadUrl = "https://www.python.org/downloads/windows/"

if ($scriptArgs.Length -gt 0 -and $scriptArgs[0] -ieq "--check") {
    Write-Host "START_WORKFLOW.ps1 OK"
    exit 0
}

if ($scriptArgs.Length -gt 0 -and ($scriptArgs[0] -ieq "--help" -or $scriptArgs[0] -ieq "-h" -or $scriptArgs[0] -ieq "/?")) {
    Write-Host "Local AI video workflow"
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "  .\START_WORKFLOW.ps1"
    Write-Host "  .\START_WORKFLOW.ps1 --check"
    Write-Host "  .\START_WORKFLOW.ps1 --help"
    Write-Host "  .\START_WORKFLOW.ps1 --no-browser"
    Write-Host "  .\START_WORKFLOW.ps1 --show-download-settings"
    Write-Host "  .\START_WORKFLOW.ps1 --set-hf-endpoint https://huggingface.co"
    Write-Host "  .\START_WORKFLOW.ps1 --set-pip-index https://pypi.org/simple"
    Write-Host "  .\START_WORKFLOW.ps1 --set-proxy http://127.0.0.1:7890"
    Write-Host "  .\START_WORKFLOW.ps1 --clear-download-settings"
    Write-Host ""
    Write-Host "Beginner path: start the frontend, open Environment detection, click one-click setup, then run the generation smoke test."
    exit 0
}

function Test-Python {
    param(
        [string]$Exe,
        [string[]]$ExtraArgs = @()
    )
    try {
        & $Exe @ExtraArgs -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)" 1>$null 2>$null 3>$null 4>$null 5>$null 6>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Get-CommonPythonPaths {
    $paths = @()
    foreach ($versionDir in @("Python312", "Python311", "Python310")) {
        if ($env:LOCALAPPDATA) {
            $paths += (Join-Path $env:LOCALAPPDATA "Programs\Python\$versionDir\python.exe")
        }
        if ($env:ProgramFiles) {
            $paths += (Join-Path $env:ProgramFiles "$versionDir\python.exe")
        }
        $programFilesX86 = ${env:ProgramFiles(x86)}
        if ($programFilesX86) {
            $paths += (Join-Path $programFilesX86 "$versionDir\python.exe")
        }
    }
    return $paths | Select-Object -Unique
}

function Find-Python {
    $projectPython = Join-Path $workspace ".venv\Scripts\python.exe"
    if ((Test-Path -LiteralPath $projectPython) -and (Test-Python -Exe $projectPython)) {
        return @($projectPython)
    }

    foreach ($exe in @("python", "python3")) {
        if (Get-Command $exe -ErrorAction SilentlyContinue) {
            if (Test-Python -Exe $exe) {
                return @($exe)
            }
        }
    }

    foreach ($path in Get-CommonPythonPaths) {
        if ((Test-Path -LiteralPath $path) -and (Test-Python -Exe $path)) {
            return @($path)
        }
    }

    foreach ($minor in @("3.12", "3.11", "3.10")) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            if (Test-Python -Exe "py" -ExtraArgs @("-$minor")) {
                return @("py", "-$minor")
            }
        }
    }
    return @()
}

function Install-PythonWithWinget {
    $wingetArgs = @(
        "install",
        "-e",
        "--id",
        "Python.Python.3.12",
        "--accept-package-agreements",
        "--accept-source-agreements"
    )
    Write-Host "Installing Python 3.12 with winget..."
    & winget @wingetArgs
    if ($LASTEXITCODE -eq 0) {
        return $true
    }

    Write-Host "winget install with agreement flags failed; trying compatibility mode..."
    & winget install -e --id Python.Python.3.12
    return $LASTEXITCODE -eq 0
}

function Open-PythonDownloadPage {
    try {
        Start-Process $pythonDownloadUrl
    } catch {
        Write-Host "Open this URL in your browser: $pythonDownloadUrl"
    }
}

Set-Location -LiteralPath $workspace

# Default to ComfyUI Desktop active base. If COMFY_BASE_DIR is already set, respect the user value.
# This keeps the frontend models/custom_nodes/input/output in sync with the running ComfyUI Desktop.
if (-not $env:COMFY_BASE_DIR -and $env:LOCALAPPDATA) {
    $defaultComfyBase = Join-Path $env:LOCALAPPDATA "Comfy-Desktop\ComfyUI-Shared"
    if (Test-Path -LiteralPath $defaultComfyBase) {
        $env:COMFY_BASE_DIR = $defaultComfyBase
    }
}

$pythonCommand = @(Find-Python)
if (-not $pythonCommand.Length) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        $answer = Read-Host "Python 3.10-3.12 was not found. Install Python 3.12 with winget? Type Y to continue"
        if ($answer -match "^[Yy]") {
            [void](Install-PythonWithWinget)
            Start-Sleep -Seconds 2
            $pythonCommand = @(Find-Python)
        }
    } else {
        $answer = Read-Host "Python 3.10-3.12 was not found and winget is unavailable. Open the official Python download page? Type Y to continue"
        if ($answer -match "^[Yy]") {
            Open-PythonDownloadPage
        }
    }
}

if (-not $pythonCommand.Length) {
    Write-Host "Python 3.10-3.12 is required. You can run: winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements"
    Write-Host "Or install Python 3.12 from: $pythonDownloadUrl"
    Write-Host "If Python was just installed but is still not detected, close this window and double-click START_WORKFLOW.bat again."
    exit 1
}

$exe = $pythonCommand[0]
$pythonArgs = @()
if ($pythonCommand.Length -gt 1) {
    $pythonArgs = $pythonCommand[1..($pythonCommand.Length - 1)]
}
$launcher = Join-Path $workspace "START_WORKFLOW.py"
& $exe @pythonArgs $launcher @scriptArgs
