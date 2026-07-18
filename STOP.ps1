[CmdletBinding()]
param([int]$Port = 9900)

$ErrorActionPreference = 'Stop'
$connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalAddress -in @('127.0.0.1', '::1') }
if (-not $connections) {
    Write-Host "No local bridge listener was found on port $Port."
    exit 0
}
foreach ($connection in $connections) {
    $process = Get-Process -Id $connection.OwningProcess -ErrorAction Stop
    Write-Host "Stopping $($process.ProcessName) (PID $($process.Id)) on port $Port..."
    Stop-Process -Id $process.Id -Force
}
Write-Host 'Bridge stopped.' -ForegroundColor Green
