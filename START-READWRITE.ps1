[CmdletBinding()]
param(
    [string]$Workspace = (Join-Path $env:USERPROFILE 'ChatGPT-Workspace'),
    [int]$Port = 9900
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    throw 'The bridge is not installed. Run INSTALL.cmd first.'
}
New-Item -ItemType Directory -Force -Path $Workspace | Out-Null
Write-Host 'WARNING: READ/WRITE mode can change or delete files inside this workspace.' -ForegroundColor Yellow
Write-Host "Workspace: $Workspace" -ForegroundColor Yellow
$confirmation = Read-Host 'Type ENABLE WRITE to continue'
if ($confirmation -cne 'ENABLE WRITE') {
    Write-Host 'Cancelled. No server was started.'
    exit 1
}
Push-Location $ProjectRoot
try {
    & $Python -m src.app --root $Workspace --port $Port --write
} finally {
    Pop-Location
}
