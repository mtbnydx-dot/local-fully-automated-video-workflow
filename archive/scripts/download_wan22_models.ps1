param(
    [ValidateSet("cuda-full", "mac-low", "mac-balanced", "mac-wan5b", "post-only")]
    [string]$Profile = "cuda-full",
    [string]$BaseDir = "",
    [switch]$SkipT2V,
    [switch]$SkipLoras
)

$ErrorActionPreference = "Stop"

if (-not $BaseDir) {
    if ($env:COMFY_BASE_DIR) {
        $BaseDir = $env:COMFY_BASE_DIR
    } else {
        $BaseDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    }
}

$script = Join-Path $PSScriptRoot "install_workflow_assets.py"
$python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

$args = @(
    "-u",
    $script,
    "--base-dir",
    $BaseDir,
    "--profile",
    $Profile
)
if ($SkipT2V) { $args += "--skip-t2v" }
if ($SkipLoras) { $args += "--skip-loras" }

Write-Host "[profile] $Profile"
Write-Host "[base] $BaseDir"
Write-Host "[run] $python $($args -join ' ')"
& $python @args
exit $LASTEXITCODE
