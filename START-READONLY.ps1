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
Write-Host 'Starting in READ-ONLY mode.' -ForegroundColor Green
Write-Host "Workspace: $Workspace"
Push-Location $ProjectRoot
try {
    & $Python -m src.app --root $Workspace --port $Port
} finally {
    Pop-Location
}
