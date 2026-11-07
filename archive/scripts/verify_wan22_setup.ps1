param(
    [string]$FrontendUrl = "http://127.0.0.1:7860"
)

$ErrorActionPreference = "Stop"

try {
    $environment = Invoke-RestMethod -Uri "$FrontendUrl/api/environment" -TimeoutSec 60
} catch {
    Write-Host "Could not reach beginner frontend at $FrontendUrl." -ForegroundColor Red
    Write-Host "Start it with START_WORKFLOW.ps1 or START_WORKFLOW.command, then retry." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

Write-Host "Platform strategy: $($environment.hardware.platform_strategy)"
Write-Host "Install profile:   $($environment.install_profile)"
Write-Host "Base directory:    $($environment.base_dir)"
Write-Host "ComfyUI connected: $($environment.comfy.connected)"
Write-Host "Needs install:     $($environment.needs_install)"

if ($environment.hardware.mac.is_macos) {
    Write-Host "Mac chip:          $($environment.hardware.mac.chip)"
    Write-Host "Unified memory:    $($environment.hardware.mac.unified_memory_gb) GB"
    Write-Host "Mac video tier:    $($environment.hardware.mac_video_tier)"
}

if ($environment.missing_installable.Count -gt 0) {
    Write-Host "`nMissing installable items:" -ForegroundColor Yellow
    foreach ($item in $environment.missing_installable) {
        Write-Host "- $($item.label): $($item.reason)"
    }
}

if ($environment.blocked.Count -gt 0) {
    Write-Host "`nBlocked workflow steps:" -ForegroundColor Yellow
    foreach ($item in $environment.blocked) {
        Write-Host "- $($item.step): $($item.reason)"
    }
}

if (-not $environment.ok) {
    Write-Host "`nEnvironment has warnings or blocked steps. Open the frontend for repair actions." -ForegroundColor Yellow
    exit 1
}

Write-Host "`nLocal AI video workbench setup verified." -ForegroundColor Green
