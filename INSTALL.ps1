[CmdletBinding()]
param(
    [string]$Workspace = (Join-Path $env:USERPROFILE 'ChatGPT-Workspace')
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $ProjectRoot '.venv'
$Python = Join-Path $Venv 'Scripts\python.exe'

function Find-Python {
    $candidates = @(
        @('py', '-3.12'),
        @('py', '-3.11'),
        @('py', '-3'),
        @('python')
    )
    foreach ($candidate in $candidates) {
        try {
            & $candidate[0] @($candidate[1..($candidate.Count - 1)]) --version *> $null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch { }
    }
    throw 'Python 3.11 or newer was not found. Install it from python.org and enable the py launcher.'
}

Write-Host 'Installing ChatGPT Local Files Bridge...' -ForegroundColor Cyan
$launcher = Find-Python
if (-not (Test-Path $Python)) {
    Write-Host 'Creating isolated Python environment...'
    & $launcher[0] @($launcher[1..($launcher.Count - 1)]) -m venv $Venv
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $ProjectRoot 'requirements.txt')

New-Item -ItemType Directory -Force -Path $Workspace | Out-Null
$Sample = Join-Path $ProjectRoot 'sample-workspace'
if (Test-Path $Sample) {
    Copy-Item -Path (Join-Path $Sample '*') -Destination $Workspace -Recurse -Force
}

Write-Host 'Running tests...'
Push-Location $ProjectRoot
try {
    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed. Installation was not completed.' }
} finally {
    Pop-Location
}

Write-Host ''
Write-Host 'Installation complete.' -ForegroundColor Green
Write-Host "Workspace: $Workspace"
Write-Host 'Start safely with START-READONLY.cmd'
