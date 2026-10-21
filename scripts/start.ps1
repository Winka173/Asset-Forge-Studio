$ErrorActionPreference = 'Stop'
$studioRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $studioRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Cần uv trong PATH.' }
uv sync --frozen
if ($LASTEXITCODE -ne 0) { throw 'Python dependency sync failed.' }
uv run python -m scripts.bootstrap
if ($LASTEXITCODE -ne 0) { throw 'Concept bootstrap failed.' }
Push-Location (Join-Path $studioRoot 'apps/web')
try {
    if (-not (Test-Path -LiteralPath 'node_modules')) {
        npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
    }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
Write-Host 'Asset Forge Studio: http://127.0.0.1:8765'
Write-Host 'Không tự tải model. Một API process/worker. Ctrl+C để dừng.'
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8765
