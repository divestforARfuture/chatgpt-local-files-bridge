[CmdletBinding()]
param([int]$Port = 9900)

$ErrorActionPreference = 'Stop'
$BaseUrl = "http://127.0.0.1:$Port"
Write-Host "Checking $BaseUrl..."
$health = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get -TimeoutSec 10
if (-not $health.ok) { throw 'Health endpoint did not report OK.' }
$manifest = Invoke-RestMethod -Uri "$BaseUrl/.well-known/ai-plugin.json" -Method Get -TimeoutSec 10
$schema = Invoke-WebRequest -Uri "$BaseUrl/openapi.yaml" -UseBasicParsing -TimeoutSec 10
Write-Host 'Health: OK' -ForegroundColor Green
Write-Host "Mode: $(if ($health.write_enabled) { 'READ/WRITE' } else { 'READ ONLY' })"
Write-Host "Workspace: $($health.root)"
Write-Host "Plugin: $($manifest.name_for_human)"
Write-Host "OpenAPI bytes: $($schema.RawContentLength)"
