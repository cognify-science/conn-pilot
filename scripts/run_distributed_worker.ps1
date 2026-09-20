$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path $PSScriptRoot -Parent
$environmentFile = Join-Path $repoRoot '.env.distributed.local'
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $environmentFile)) {
    throw "Missing local worker configuration: $environmentFile"
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing project Python environment: $python"
}

foreach ($line in Get-Content -LiteralPath $environmentFile) {
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $parts = $line -split '=', 2
        [Environment]::SetEnvironmentVariable($parts[0], $parts[1], 'Process')
    }
}

Set-Location -LiteralPath $repoRoot
$createdNew = $false
$mutex = [Threading.Mutex]::new($true, 'Local\ConnPilotDistributedWorker', [ref]$createdNew)
if (-not $createdNew) {
    exit 0
}

try {
    while ($true) {
        & $python -m conn_pilot.distributed_worker
        Start-Sleep -Seconds 15
    }
}
finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
