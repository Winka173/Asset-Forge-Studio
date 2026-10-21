param([ValidateSet('Dev','Build','Test','Smoke','Clean')][string]$Mode='Build')
$ErrorActionPreference='Stop'
$afsRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $afsRoot
$env:CARGO_HOME=Join-Path $afsRoot '.local/desktop-tools/cargo'
$env:RUSTUP_HOME=Join-Path $afsRoot '.local/desktop-tools/rustup'
$env:PATH="$env:CARGO_HOME\bin;$env:PATH"
$afsPython=Join-Path $afsRoot '.venv/Scripts/python.exe'
$afsCli=Join-Path $afsRoot 'node_modules/.bin/tauri.cmd'
function Assert-Exit([string]$Label){if($LASTEXITCODE -ne 0){throw "$Label failed with exit code $LASTEXITCODE"}}
function Assert-WorkspacePath([string]$Path){$full=[IO.Path]::GetFullPath($Path);$prefix=[IO.Path]::GetFullPath($afsRoot).TrimEnd('\')+'\';if(-not $full.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){throw 'Refusing build filesystem operation outside workspace'};return $full}
function Frontend-Check{& npm --prefix apps/web run build;Assert-Exit 'Frontend build'}
function Backend-Check{& $afsPython -m pytest -q;Assert-Exit 'Backend tests'}
if($Mode -eq 'Clean'){
  $afsTemporary=Assert-WorkspacePath (Join-Path $afsRoot '.local/desktop-build/pyinstaller')
  if(Test-Path -LiteralPath $afsTemporary){Remove-Item -LiteralPath $afsTemporary -Recurse -Force}
  Write-Output 'Cleaned temporary packaging files; latest build, libraries, AI environments and weights preserved.'
  exit 0
}
if($Mode -eq 'Smoke'){& node desktop/smoke.mjs;Assert-Exit 'Native desktop smoke';exit 0}
if(-not(Test-Path -LiteralPath $afsCli)){& npm ci;Assert-Exit 'Desktop npm install'}
if($Mode -eq 'Dev'){& $afsCli dev;Assert-Exit 'Desktop development';exit 0}
if($Mode -eq 'Test'){Frontend-Check;Backend-Check;& cargo test --manifest-path src-tauri/Cargo.toml;Assert-Exit 'Native tests';exit 0}
$afsStamp=(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$afsCandidate=Assert-WorkspacePath (Join-Path $afsRoot ".local/desktop-build/candidates/$afsStamp")
New-Item -ItemType Directory -Force -Path $afsCandidate | Out-Null
$afsVersion=(Get-Content -LiteralPath package.json -Raw | ConvertFrom-Json).version
$afsCommit=(& git rev-parse HEAD).Trim()
$afsReport=[ordered]@{version=$afsVersion;timestamp_utc=$afsStamp;git_commit=$afsCommit;git_branch=(& git branch --show-current).Trim();git_dirty=[bool](& git status --porcelain);changed_files=@(& git status --short);changed_features=@('Tauri Windows shell and bundled API','Hybrid shared scheduler and Batch Studio','Immutable quality configuration and local SDXL concept approval');status='BUILDING';build_type='Bundled native desktop and Python API; external AI environments, model weights and Blender required';candidate=$afsCandidate;tests=@();known_issues=@('Unsigned local build; clean-machine installation not yet verified','Editor/browser tests do not establish mobile performance or Meshy visual parity')}
$afsReportFile=Join-Path $afsCandidate 'build-report.json'
try{
  Frontend-Check;$afsReport.tests+=@('Frontend TypeScript and production build PASS')
  Backend-Check;$afsReport.tests+=@('Actual backend pytest suite PASS')
  & $afsPython desktop/build_backend.py;Assert-Exit 'Bundled Python backend'
  & $afsCli build --bundles nsis;Assert-Exit 'Tauri Windows build'
  Copy-Item -LiteralPath src-tauri/target/release/asset-forge-studio.exe -Destination (Join-Path $afsCandidate 'Asset Forge Studio.exe')
  Copy-Item -LiteralPath src-tauri/binaries/afs-backend-x86_64-pc-windows-msvc.exe -Destination (Join-Path $afsCandidate 'afs-backend.exe')
  $afsInstaller=Join-Path $afsRoot "src-tauri/target/release/bundle/nsis/Asset Forge Studio_${afsVersion}_x64-setup.exe"
  if(-not(Test-Path -LiteralPath $afsInstaller)){throw 'Current-version installer missing'}
  Copy-Item -LiteralPath $afsInstaller -Destination $afsCandidate
  $afsReport.artifact_sha256=@{}
  Get-ChildItem -LiteralPath $afsCandidate -Filter '*.exe' | ForEach-Object {$afsReport.artifact_sha256[$_.Name]=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()}
  $afsReport.status='BUILT_PENDING_SMOKE';$afsReport | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $afsReportFile -Encoding UTF8
  $env:AFS_SMOKE_EXE=Join-Path $afsCandidate 'Asset Forge Studio.exe'
  & node desktop/smoke.mjs;Assert-Exit 'Newly built native desktop smoke'
  $afsReport.tests+=@('New Windows executable launch, scoped native IPC, API auth, real GLB viewer, persistence/relaunch, clean shutdown PASS')
  $afsReport.status='PASS_BUILD_AND_NATIVE_SMOKE';$afsReport.smoke_report=(Get-Content -LiteralPath .local/desktop-build/latest-smoke-path.txt -Raw).Trim()
  $afsReport.executable='Asset Forge Studio.exe';$afsReport.installer=(Get-ChildItem -LiteralPath $afsCandidate -Filter "*_${afsVersion}_x64-setup.exe" | Select-Object -First 1 -ExpandProperty Name)
  $afsReport | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $afsReportFile -Encoding UTF8
  $afsLatest=Assert-WorkspacePath (Join-Path $afsRoot 'dist/windows/latest')
  $afsReleases=Assert-WorkspacePath (Join-Path $afsRoot 'dist/windows/releases')
  New-Item -ItemType Directory -Force -Path $afsReleases | Out-Null
  if(Test-Path -LiteralPath $afsLatest){$afsBackup=Assert-WorkspacePath (Join-Path $afsReleases "known-good-before-$afsStamp");Move-Item -LiteralPath $afsLatest -Destination $afsBackup}
  Copy-Item -LiteralPath $afsCandidate -Destination $afsLatest -Recurse
  Copy-Item -LiteralPath $afsReportFile -Destination docs/evidence/desktop_build.json
  Write-Output "Desktop build and launch verified: $afsLatest"
}catch{
  $afsReport.status='FAILED';$afsReport.failure=$_.Exception.Message;$afsReport | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $afsReportFile -Encoding UTF8
  Write-Error "Desktop candidate failed. Last known-good build was preserved. $($_.Exception.Message)"
  exit 1
}finally{Remove-Item Env:AFS_SMOKE_EXE -ErrorAction SilentlyContinue}
