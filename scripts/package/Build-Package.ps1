<#
Stages the offline tester package from this PC's tools/models into -Out (default D:\AFS_Package).
Copies only tools, models and environments. Never the library, projects, databases, desktop config or prompt files.
Re-run to resume. Then run with -Finish after the app build to add the installer, Install.ps1 and manifest.
#>
param([string]$Out = 'D:\AFS_Package', [switch]$Finish)
$ErrorActionPreference = 'Stop'
$h = $env:USERPROFILE
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$payload = Join-Path $Out 'payload'
$hf = '.cache\huggingface\hub'
$items = @(
    @{path = 'Tools\trellis2'; src = "$h\Tools\trellis2"; optional = $false},
    @{path = 'Tools\sdxl'; src = "$h\Tools\sdxl"; optional = $false},
    @{path = 'Tools\afs-ollama'; src = "$h\Tools\afs-ollama"; optional = $false},
    @{path = 'Tools\blender-5.2.3-windows-x64'; src = "$h\Tools\blender-5.2.3-windows-x64"; optional = $false},
    @{path = 'Models\black-forest-labs__FLUX.2-klein-4B'; src = "$h\Models\black-forest-labs__FLUX.2-klein-4B"; optional = $false},
    @{path = 'Tools\kimodo'; src = "$h\Tools\kimodo"; optional = $true},
    @{path = 'Tools\unirig'; src = "$h\Tools\unirig"; optional = $true},
    @{path = '.local\envs\kimodo'; src = "$repo\.local\envs\kimodo"; optional = $true; base = 'workspace'}
)
foreach ($m in 'VAST-AI--UniRig', 'nvidia--Kimodo-SOMA-RP-v1.2', 'NousResearch--Meta-Llama-3-8B-Instruct', 'McGill-NLP--LLM2Vec-Meta-Llama-3-8B-Instruct-mntp', 'McGill-NLP--LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised', 'facebook--opt-350m') {
    $items += @{path = "$hf\models--$m"; src = "$h\$hf\models--$m"; optional = $true}
}
function Bytes($dir) {
    $line = robocopy $dir (Join-Path $env:TEMP 'afs-count-nowhere') /L /E /NJH /NFL /NDL /BYTES /XF *.log | Where-Object { $_ -match '^\s*Bytes\s*:' } | Select-Object -First 1
    [int64](($line -split '\s+') | Where-Object { $_ -match '^\d+$' } | Select-Object -First 1)
}
if (-not $Finish) {
    New-Item -ItemType Directory -Force $payload | Out-Null
    foreach ($i in $items) {
        if (-not (Test-Path $i.src)) { throw "Missing source $($i.src)" }
        Write-Host "staging $($i.path)"
        robocopy $i.src (Join-Path $payload $i.path) /E /R:2 /W:2 /NFL /NDL /NJH /NJS /NP /XF *.log /XD __pycache__ | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $($i.path): $LASTEXITCODE" }
    }
    Write-Host 'STAGED'
    exit 0
}
$list = foreach ($i in $items) { [ordered]@{path = $i.path; base = $(if ($i.base) { $i.base } else { 'home' }); optional = $i.optional; bytes = (Bytes (Join-Path $payload $i.path))} }
$venvs = @(
    [ordered]@{path = 'Tools\trellis2\code\venv\Scripts\python.exe'; base = 'home'; optional = $false},
    [ordered]@{path = 'Tools\sdxl\venv\Scripts\python.exe'; base = 'home'; optional = $false},
    [ordered]@{path = 'Tools\unirig\venv\Scripts\python.exe'; base = 'home'; optional = $true},
    [ordered]@{path = '.local\envs\kimodo\Scripts\python.exe'; base = 'workspace'; optional = $true})
$manifest = [ordered]@{app_version = (Get-Content "$repo\package.json" -Raw | ConvertFrom-Json).version; build_home = $h; total_bytes = ($list | Measure-Object bytes -Sum).Sum; items = $list; venvs = $venvs}
$manifest | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $Out 'manifest.json') -Encoding UTF8
Copy-Item "$PSScriptRoot\Install.ps1" $Out -Force
Copy-Item "$PSScriptRoot\README.txt" $Out -Force
$exe = Get-ChildItem "$repo\dist\windows\stable\latest" -Filter 'Asset Forge Studio_*_x64-setup.exe' | Select-Object -First 1
New-Item -ItemType Directory -Force (Join-Path $Out 'installers') | Out-Null
Copy-Item $exe.FullName (Join-Path $Out 'installers') -Force
Write-Host "FINISHED $($manifest.app_version) total $([math]::Round($manifest.total_bytes/1GB,1)) GB"
