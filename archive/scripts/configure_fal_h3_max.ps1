[CmdletBinding()]
param(
    [switch]$Clear,
    [switch]$ProcessOnly
)

$ErrorActionPreference = "Stop"
$scope = if ($ProcessOnly) { "Process" } else { "User" }

if ($Clear) {
    [Environment]::SetEnvironmentVariable("FAL_KEY", $null, $scope)
    Remove-Item Env:FAL_KEY -ErrorAction SilentlyContinue
    Write-Host "FAL_KEY has been removed from the $scope environment."
    Write-Host "No ComfyUI process was started or changed."
    exit 0
}

$secureKey = Read-Host "Enter your fal API key (input is hidden)" -AsSecureString
if ($secureKey.Length -eq 0) {
    throw "No API key was entered. Nothing was changed."
}

$bstr = [IntPtr]::Zero
$plainKey = $null
try {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    if ([string]::IsNullOrWhiteSpace($plainKey)) {
        throw "The API key is empty. Nothing was changed."
    }
    [Environment]::SetEnvironmentVariable("FAL_KEY", $plainKey.Trim(), $scope)
    $env:FAL_KEY = $plainKey.Trim()
}
finally {
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    $plainKey = $null
}

Write-Host "FAL_KEY is configured in the $scope environment. The key was not printed or written to this project."
Write-Host "Restart only the Local AI Video Workbench frontend so it can read the new variable."
Write-Host "This script did not start, stop, restart, or call ComfyUI and did not load any local GPU model."
