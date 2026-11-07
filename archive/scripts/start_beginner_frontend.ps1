$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $workspace "START_WORKFLOW.ps1"

Set-Location -LiteralPath $workspace
& $launcher @args
