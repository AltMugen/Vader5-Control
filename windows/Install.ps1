[CmdletBinding()]
param(
    [ValidateSet('Install', 'Restore', 'Bluetooth')][string]$Action = 'Install',
    [string]$SteamDir,
    [string]$DeviceAddress,
    [string]$BackupDir,
    [ValidateSet('Auto', 'ru', 'en')][string]$Language = 'Auto'
)
$ErrorActionPreference = 'Stop'
$ru = $Language -eq 'ru' -or ($Language -eq 'Auto' -and (Get-UICulture).Name.StartsWith('ru'))
function Say([string]$English, [string]$Russian) { if ($ru) { Write-Host $Russian } else { Write-Host $English } }
function Fail([string]$English, [string]$Russian) { if ($ru) { throw $Russian } else { throw $English } }
function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
function Machine([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $reader = [IO.BinaryReader]::new($stream)
    try {
        if ($reader.ReadUInt16() -ne 0x5a4d) { throw 'Invalid PE file' }
        $stream.Position = 0x3c; $offset = $reader.ReadInt32()
        if ($offset -lt 0x40 -or $offset -gt $stream.Length - 6) { throw 'Invalid PE offset' }
        $stream.Position = $offset
        if ($reader.ReadUInt32() -ne 0x4550) { throw 'Invalid PE signature' }
        return $reader.ReadUInt16()
    } finally { $reader.Dispose() }
}
if (!$SteamDir) {
    $candidates = @()
    $userSteam = Get-ItemProperty -Path 'HKCU:\Software\Valve\Steam' -ErrorAction SilentlyContinue
    if ($userSteam.SteamPath) { $candidates += $userSteam.SteamPath }
    if ($userSteam.SteamExe) { $candidates += Split-Path -Path $userSteam.SteamExe -Parent }
    foreach ($key in @('HKLM:\SOFTWARE\Valve\Steam', 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam')) {
        $install = (Get-ItemProperty -Path $key -ErrorAction SilentlyContinue).InstallPath
        if ($install) { $candidates += $install }
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath (Join-Path $candidate 'steam.exe')) { $SteamDir = $candidate; break }
    }
}
if (!$SteamDir -or !(Test-Path -LiteralPath (Join-Path $SteamDir 'steam.exe'))) {
    Fail 'Steam not found. Pass -SteamDir.' 'Steam не найден. Укажите -SteamDir.'
}
$SteamDir = (Resolve-Path -LiteralPath $SteamDir).Path
if (Get-Process -Name steam, steamwebhelper -ErrorAction SilentlyContinue) {
    Fail 'Close Steam completely first.' 'Сначала полностью закройте Steam.'
}
if ($Action -eq 'Bluetooth') {
    if ($DeviceAddress -notmatch '^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$') {
        Fail 'Pass the Flashplay MAC with -DeviceAddress.' 'Укажите MAC геймпада Flashplay через -DeviceAddress.'
    }
    $configDir = Join-Path $env:APPDATA 'Vader5Control'
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $configDir 'bluetooth'), $DeviceAddress.ToUpperInvariant() + "`n", [Text.Encoding]::ASCII)
    $env:SDL_FLYDIGI_BT_ADDRESS = $DeviceAddress
    $env:SDL_FLYDIGI_BT_STREAM_MODE = '2'
    Say 'Bluetooth selection saved. Starting Steam.' 'Геймпад сохранён. Запускаю Steam.'
    Start-Process -FilePath (Join-Path $SteamDir 'steam.exe')
    exit
}
$store = if ($BackupDir) { [IO.Path]::GetFullPath($BackupDir) } else { Join-Path $env:LOCALAPPDATA 'Vader5Control\SteamBackups' }
$statePath = Join-Path $store 'state.json'
New-Item -ItemType Directory -Path $store -Force | Out-Null
$state = @()
if (Test-Path -LiteralPath $statePath) { $state = @(Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json) }
function Save-State {
    $temporary = Join-Path $store ('state-' + [guid]::NewGuid().ToString('N') + '.json')
    ConvertTo-Json -InputObject @($script:state) -Depth 5 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $statePath -Force
}
if ($Action -eq 'Restore') {
    foreach ($entry in $state) {
        if (!(Test-Path -LiteralPath $entry.Target)) { continue }
        if ((Hash $entry.Target) -ne $entry.PatchedHash) {
            Fail "Steam changed $($entry.Target); refusing to overwrite it." "Steam изменил $($entry.Target); восстановление остановлено."
        }
        if ((Hash $entry.Original) -ne $entry.OriginalHash) { throw 'Backup checksum mismatch' }
    }
    foreach ($entry in $state) {
        if (Test-Path -LiteralPath $entry.Target) {
            Copy-Item -LiteralPath $entry.Original -Destination $entry.Target -Force
            Say "Restored: $($entry.Target)" "Восстановлено: $($entry.Target)"
        }
    }
    $state = @(); Save-State
    exit
}
$dll = Join-Path $PSScriptRoot 'SDL3.dll'
if (!(Test-Path -LiteralPath $dll) -or (Machine $dll) -ne 0x8664) { throw 'The Windows x64 SDL3.dll is missing or invalid' }
# Search Steam client folders only, never game libraries, userdata or the whole disk.
$targets = @(Get-ChildItem -LiteralPath $SteamDir -File -Filter SDL3.dll)
foreach ($directory in @('bin', 'steamui', 'steamrt64')) {
    $path = Join-Path $SteamDir $directory
    if (Test-Path -LiteralPath $path) {
        $targets += @(Get-ChildItem -LiteralPath $path -Filter SDL3.dll -File -Recurse)
    }
}
$targets = @($targets | Where-Object { (Machine $_.FullName) -eq 0x8664 } | Sort-Object FullName -Unique)
if (!$targets.Count) { Fail 'No x64 Steam SDL3.dll found.' '64-битная SDL3.dll Steam не найдена.' }
$plans = @()
foreach ($target in $targets) {
    $entry = @($state | Where-Object { $_.Target -eq $target.FullName }) | Select-Object -First 1
    $currentHash = Hash $target.FullName
    if ($entry -and $currentHash -eq $entry.PatchedHash) {
        if ((Hash $entry.Original) -ne $entry.OriginalHash) { throw 'Backup checksum mismatch' }
        $original = $entry.Original
    } else {
        $original = Join-Path $store ($currentHash + '.dll')
        if (!(Test-Path -LiteralPath $original)) { Copy-Item -LiteralPath $target.FullName -Destination $original }
        if ((Hash $original) -ne $currentHash) { throw 'Backup checksum mismatch' }
    }
    $length = (Get-Item -LiteralPath $original).Length
    if ((Get-Item -LiteralPath $dll).Length -gt $length) {
        Fail "Patched DLL is larger than the original: $($target.FullName)" "Новая DLL больше оригинала: $($target.FullName)"
    }
    # Preserve the exact current file as well, so an interrupted re-patch can be rolled back.
    $rollback = Join-Path $store ($currentHash + '.dll')
    if (!(Test-Path -LiteralPath $rollback)) { Copy-Item -LiteralPath $target.FullName -Destination $rollback }
    $plans += @{ Target = $target.FullName; Original = $original; Length = $length; Rollback = $rollback }
}
foreach ($plan in $plans) {
    $before = @($state)
    try {
        # Same in-place copy and original-length padding as the Linux updater.
        $source = [IO.File]::OpenRead($dll)
        $destination = $null
        try {
            $destination = [IO.File]::Open($plan.Target, [IO.FileMode]::Open, [IO.FileAccess]::Write, [IO.FileShare]::None)
            $source.CopyTo($destination)
            $destination.SetLength($plan.Length)
            $destination.Flush($true)
        } finally {
            if ($destination) { $destination.Dispose() }; $source.Dispose()
        }
        $state = @($state | Where-Object { $_.Target -ne $plan.Target })
        $state += [pscustomobject]@{ Target = $plan.Target; Original = $plan.Original; OriginalHash = (Hash $plan.Original); PatchedHash = (Hash $plan.Target) }
        Save-State
    } catch {
        Copy-Item -LiteralPath $plan.Rollback -Destination $plan.Target -Force
        $state = $before
        throw
    }
    Say "Patched: $($plan.Target)" "Обновлено: $($plan.Target)"
}
Say 'Done. Backups are stored outside Steam.' 'Готово. Резервные копии сохранены вне Steam.'
