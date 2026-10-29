[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Installer, [string]$SteamDir)
$ErrorActionPreference = 'Stop'
# Paths may contain spaces, Cyrillic or apostrophes; pass PowerShell literals via
# encoded command rather than concatenating executable command-line fragments.
function Literal([string]$Value) { "'" + $Value.Replace("'", "''") + "'" }
$backup = Join-Path $env:LOCALAPPDATA 'Vader5Control\SteamBackups'
$command = '& ' + (Literal $Installer) + ' -Action Install -BackupDir ' + (Literal $backup)
if ($SteamDir) { $command += ' -SteamDir ' + (Literal $SteamDir) }
$command += '; if (!$?) { exit 1 }'
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
$process = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand',$encoded)
if ($process.ExitCode -ne 0) { throw "Steam patch failed (exit $($process.ExitCode))." }
Write-Output 'OK'
