<#
Asset Forge Studio offline installer (tester package).
Copies the local AI tools and model weights next to the user profile, installs Python 3.11.5 for the bundled
environments, repairs their absolute paths, then installs the desktop app with a blank library.

  powershell -ExecutionPolicy Bypass -File Install.ps1 [-Profile Full|Core] [-DataRoot D:\AFS] [-SkipApp]

  -Profile   Core = text/image to 3D model, concepts, Blender, local language model (~76 GB).
             Full (default) = Core + motion (Kimodo) and auto-rigging (UniRig) (~117 GB).
  -DataRoot  put the tools/models on another drive; junctions are created in the user profile.
No user data is shipped: the app starts with zero projects and an empty library.
#>
param([ValidateSet('Full', 'Core')][string]$Profile = 'Full', [string]$DataRoot = '', [switch]$SkipApp, [switch]$SkipCopy, [string]$HomeOverride = '')
$ErrorActionPreference = 'Stop'
$pkg = Split-Path -Parent $MyInvocation.MyCommand.Path
$home_ = if ($HomeOverride) { $HomeOverride } else { $env:USERPROFILE }
$local = if ($HomeOverride) { Join-Path $HomeOverride 'AppData\Local' } else { $env:LOCALAPPDATA }
$workspace = Join-Path $local 'AssetForgeStudio\Workspace'
$payload = Join-Path $pkg 'payload'
$manifest = Get-Content (Join-Path $pkg 'manifest.json') -Raw | ConvertFrom-Json
$items = @($manifest.items | Where-Object { $Profile -eq 'Full' -or -not $_.optional })
function Step($t) { Write-Host "`n== $t" -ForegroundColor Cyan }
function Fail($t) { Write-Host "ERROR: $t" -ForegroundColor Red; exit 1 }
function Target($item) { if ($item.base -eq 'workspace') { Join-Path $workspace $item.path } else { Join-Path $dataBase $item.path } }

Step 'Checking this PC'
if (-not $HomeOverride) {
    if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) { Fail 'No NVIDIA driver found (nvidia-smi). Install the NVIDIA driver first.' }
    $gpu = (& nvidia-smi --query-gpu=name,memory.total --format=csv,noheader).Split("`n")[0]
    $vram = [int](($gpu -split ',')[1] -replace '[^0-9]', '')
    Write-Host "GPU: $gpu"
    if ($vram -lt 15000) { Fail "Needs an NVIDIA GPU with at least 16 GB VRAM (found $vram MiB)." }
    $ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
    Write-Host "RAM: $ram GB"
    if ($ram -lt 30) { Write-Host 'WARNING: 32 GB RAM or more is recommended; large jobs may be refused.' -ForegroundColor Yellow }
}
$dataBase = if ($DataRoot) { $DataRoot } else { $home_ }
New-Item -ItemType Directory -Force $dataBase | Out-Null
$needBytes = ($items | Measure-Object bytes -Sum).Sum
$needGB = [math]::Ceiling($needBytes / 1GB) + 10
$freeGB = [math]::Floor((Get-PSDrive (Split-Path -Qualifier (Resolve-Path $dataBase).Path).TrimEnd(':')).Free / 1GB)
Write-Host "Profile $Profile needs about $needGB GB free, found $freeGB GB"
if ($freeGB -lt $needGB -and -not $SkipCopy) { Fail 'Not enough free space. Use -DataRoot with another drive or -Profile Core.' }

Step 'Python 3.11.5 for the bundled environments'
$pyDir = Join-Path $local 'Programs\Python\Python311'
$pyExe = Join-Path $pyDir 'python.exe'
$have = $false
if (Test-Path $pyExe) { $have = ((& $pyExe --version) -match '3\.11\.') }
if (-not $have) {
    $setup = Join-Path $pkg 'installers\python-3.11.5-amd64.exe'
    $sig = Get-AuthenticodeSignature $setup
    if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Python Software Foundation') { Fail 'Python installer signature is not valid.' }
    if ($HomeOverride) { Fail "Test home needs Python 3.11 at $pyDir" }
    Start-Process $setup -ArgumentList '/quiet', 'InstallAllUsers=0', 'PrependPath=0', 'Include_launcher=0', 'Include_test=0', "TargetDir=$pyDir" -Wait
    if (-not (Test-Path $pyExe)) { Fail 'Python install did not produce python.exe' }
}
Write-Host "Python: $(& $pyExe --version)"

if (-not $SkipCopy) {
    Step 'Copying tools and models (large; run again to resume)'
    foreach ($item in $items) {
        $src = Join-Path $payload $item.path
        $dst = Target $item
        Write-Host "  $($item.path)  ($([math]::Round($item.bytes/1GB,1)) GB)"
        robocopy $src $dst /E /R:2 /W:2 /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { Fail "Copy failed for $($item.path) (robocopy $LASTEXITCODE)" }
    }
    if ($DataRoot) {
        foreach ($link in 'Tools', 'Models') {
            $lp = Join-Path $home_ $link
            if (-not (Test-Path $lp)) { New-Item -ItemType Junction -Path $lp -Target (Join-Path $dataBase $link) | Out-Null }
        }
        $hf = Join-Path $home_ '.cache\huggingface'; New-Item -ItemType Directory -Force $hf | Out-Null
        $hl = Join-Path $hf 'hub'
        if (-not (Test-Path $hl)) { New-Item -ItemType Junction -Path $hl -Target (Join-Path $dataBase '.cache\huggingface\hub') | Out-Null }
    }
}

Step 'Repairing environment paths for this user'
$old = $manifest.build_home
$oldDouble = $old.Replace('\', '\\'); $newDouble = $home_.Replace('\', '\\')
$oldFwd = $old.Replace('\', '/'); $newFwd = $home_.Replace('\', '/')
$roots = @((Join-Path $home_ 'Tools'), (Join-Path $workspace '.local\envs')) | Where-Object { Test-Path $_ }
foreach ($root in $roots) {
    foreach ($cfg in (Get-ChildItem $root -Recurse -Filter pyvenv.cfg -Depth 4 -ErrorAction SilentlyContinue)) {
        $text = Get-Content $cfg.FullName -Raw
        $text = $text.Replace("$old\AppData\Local\Programs\Python\Python311", $pyDir)
        $text = $text.Replace($old, $home_)   # bundled pythons (for example Tools	rellis2	ools\python) live under the profile
        Set-Content -Path $cfg.FullName -Value $text -NoNewline -Encoding ASCII
        $site = Join-Path $cfg.DirectoryName 'Lib\site-packages'
        if (Test-Path $site) {
            foreach ($f in (Get-ChildItem $site -File | Where-Object { $_.Name -like '*.pth' -or $_.Name -like '__editable__*.py' -or $_.Name -like '*.egg-link' })) {
                $c = Get-Content $f.FullName -Raw
                $n = $c.Replace($oldDouble, $newDouble).Replace($old, $home_).Replace($oldFwd, $newFwd)
                if ($n -ne $c) { Set-Content $f.FullName $n -NoNewline -Encoding UTF8 }
            }
        }
        Write-Host "  fixed $($cfg.DirectoryName)"
    }
}
foreach ($v in $manifest.venvs | Where-Object { $Profile -eq 'Full' -or -not $_.optional }) {
    $py = if ($v.base -eq 'workspace') { Join-Path $workspace $v.path } else { Join-Path $home_ $v.path }
    if (-not (Test-Path $py)) { Fail "Missing environment $($v.path)" }
    $line = & $py -c "import sys; print('ok', sys.version.split()[0], sys.base_prefix)"
    if ($line -match [regex]::Escape($old)) { Fail "Environment still points at the build machine: $($v.path)" }
    if ($LASTEXITCODE -ne 0) { Fail "Environment does not start: $($v.path)" }
    Write-Host "  starts: $($v.path) ($line)"
}

if (-not $SkipApp) {
    Step 'Installing Asset Forge Studio (blank library, zero projects)'
    $setupExe = Get-ChildItem (Join-Path $pkg 'installers') -Filter 'Asset Forge Studio_*_x64-setup.exe' | Select-Object -First 1
    if (-not $setupExe) { Fail 'App installer missing' }
    Start-Process $setupExe.FullName -ArgumentList '/S' -Wait
    Write-Host 'Installed. Start it from the Start menu: Asset Forge Studio.'
}
Write-Host "`nDone ($Profile). First launch shows setup checks; the library starts empty." -ForegroundColor Green
