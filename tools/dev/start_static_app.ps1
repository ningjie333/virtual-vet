param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$frontendRoot = Join-Path $repoRoot "vet-game-frontend\vite-project"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Missing $python . Run 'uv sync' first."
}
if (-not (Test-Path $frontendRoot)) {
    throw "Missing frontend directory: $frontendRoot"
}

Set-Location $frontendRoot
Write-Host "== virtual-vet static build =="
Write-Host "building frontend into static/ ..."
npm run build
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Set-Location $repoRoot
$env:VV_HOST = $BindHost
$env:VV_PORT = "$Port"

Write-Host ""
Write-Host "== virtual-vet static app =="
Write-Host "url : http://$BindHost`:$Port"
Write-Host "mode: Flask + built frontend"
Write-Host ""

& $python "gui_app.py"
