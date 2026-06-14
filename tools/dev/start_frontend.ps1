param(
    [string]$ApiHost = "127.0.0.1",
    [int]$ApiPort = 5000,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$frontendRoot = Join-Path $repoRoot "vet-game-frontend\vite-project"

if (-not (Test-Path $frontendRoot)) {
    throw "Missing frontend directory: $frontendRoot"
}

Set-Location $frontendRoot
$env:VV_HOST = $ApiHost
$env:VV_PORT = "$ApiPort"

Write-Host "== virtual-vet frontend =="
Write-Host "dir : $frontendRoot"
Write-Host "ui  : http://127.0.0.1`:$FrontendPort"
Write-Host "api : http://$ApiHost`:$ApiPort"
Write-Host "mode: Vite dev server + /api proxy"
Write-Host ""

npm run dev -- --host 127.0.0.1 --port $FrontendPort
