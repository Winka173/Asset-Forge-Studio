param([switch]$NoBrowser, [switch]$Setup)
$ErrorActionPreference = 'Stop'
$studioRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $studioRoot
$localUrl = 'http://127.0.0.1:8765'
function Test-Studio {
    try {
        $info = Invoke-RestMethod -Uri "$localUrl/openapi.json" -TimeoutSec 2
        return $info.info.title -eq 'Asset Forge Studio'
    } catch { return $false }
}
if (Test-Studio) {
    Write-Host "Asset Forge Studio đang chạy: $localUrl"
    if (-not $NoBrowser) { Start-Process $localUrl }
    exit 0
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Cần cài uv và thêm vào PATH.' }
uv sync --frozen
if ($LASTEXITCODE -ne 0) { throw 'Không cài được dependencies Python.' }
uv run python -m scripts.bootstrap
if ($LASTEXITCODE -ne 0) { throw 'Concept bootstrap failed.' }
$webRoot = Join-Path $studioRoot 'apps/web'
if ($Setup -or -not (Test-Path -LiteralPath (Join-Path $webRoot 'dist/index.html'))) {
    Push-Location -LiteralPath $webRoot
    try {
        npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
}
$runtimeDir = Join-Path $studioRoot '.local'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$pythonExe = Join-Path $studioRoot '.venv/Scripts/python.exe'
$server = Start-Process -FilePath $pythonExe -ArgumentList @('-m', 'uvicorn', 'apps.api.main:app', '--host', '127.0.0.1', '--port', '8765') -WorkingDirectory $studioRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'server.out.log') -RedirectStandardError (Join-Path $runtimeDir 'server.err.log')
@{ pid = $server.Id; started_at = (Get-Date).ToString('o'); url = $localUrl } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $runtimeDir 'server.json')
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    if (Test-Studio) {
        Write-Host "Asset Forge Studio sẵn sàng: $localUrl (PID $($server.Id))"
        if (-not $NoBrowser) { Start-Process $localUrl }
        exit 0
    }
    if ($server.HasExited) { throw "Backend dừng sớm. Xem .local/server.err.log. Exit $($server.ExitCode)" }
    Start-Sleep -Milliseconds 500
}
throw 'Backend chưa sẵn sàng sau 30 giây. Xem .local/server.err.log.'
