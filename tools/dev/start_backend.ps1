param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Missing $python . Run 'uv sync' first."
}

Set-Location $repoRoot
$env:VV_HOST = $BindHost
$env:VV_PORT = "$Port"

Write-Host "== virtual-vet backend =="
Write-Host "repo: $repoRoot"
Write-Host "url : http://$BindHost`:$Port"
Write-Host "mode: backend Flask only"
Write-Host ""

& $python "gui_app.py"
