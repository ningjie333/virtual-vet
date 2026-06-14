$ErrorActionPreference = "Stop"

$backendPorts = @(5000)
$frontendPorts = @(5173, 5174, 4173)
$watchPorts = $backendPorts + $frontendPorts

$listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in $watchPorts } |
    Sort-Object LocalPort

$pythonProcesses = Get-CimInstance Win32_Process |
    Where-Object {
        ($_.Name -eq "python.exe" -or $_.Name -eq "pythonw.exe" -or $_.Name -eq "uv.exe") -and
        ($_.CommandLine -match "gui_app.py" -or $_.CommandLine -match "vp dev" -or $_.CommandLine -match "vite")
    } |
    Select-Object ProcessId, ParentProcessId, Name, CommandLine

$backendUp = @($listeners | Where-Object { $_.LocalPort -in $backendPorts }).Count -gt 0
$frontendUp = @($listeners | Where-Object { $_.LocalPort -in $frontendPorts }).Count -gt 0

Write-Host "== virtual-vet runtime status =="
Write-Host ("backend : " + $(if ($backendUp) { "UP" } else { "DOWN" }))
Write-Host ("frontend: " + $(if ($frontendUp) { "UP" } else { "DOWN" }))
Write-Host ""

if ($listeners) {
    Write-Host "[listeners]"
    $listeners | Select-Object LocalAddress, LocalPort, OwningProcess, State | Format-Table -AutoSize
} else {
    Write-Host "[listeners]"
    Write-Host "none on 5000 / 5173 / 5174 / 4173"
}

Write-Host ""
if ($pythonProcesses) {
    Write-Host "[processes]"
    $pythonProcesses | Format-Table -Wrap -AutoSize
} else {
    Write-Host "[processes]"
    Write-Host "no gui_app.py or frontend dev process found"
}
