$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path $PSScriptRoot -Parent
$workerScript = Join-Path $PSScriptRoot 'run_distributed_worker.ps1'
$startupDirectory = [Environment]::GetFolderPath('Startup')
$launcher = Join-Path $startupDirectory 'CONN Pilot Worker.cmd'

if (-not (Test-Path -LiteralPath $workerScript)) {
    throw "Worker supervisor is missing: $workerScript"
}

$content = @(
    '@echo off',
    ('start "" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $workerScript)
) -join "`r`n"
[IO.File]::WriteAllText($launcher, $content + "`r`n", [Text.Encoding]::ASCII)
Write-Output "Installed CONN Pilot worker autostart: $launcher"
