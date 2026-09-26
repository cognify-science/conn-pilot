$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path $PSScriptRoot -Parent
$environmentFile = Join-Path $repoRoot '.env.distributed.local'
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$logDirectory = Join-Path $repoRoot 'work\logs'
$supervisorLog = Join-Path $logDirectory 'worker-supervisor.log'

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
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$createdNew = $false
$mutex = [Threading.Mutex]::new($true, 'Local\ConnPilotDistributedWorker', [ref]$createdNew)
if (-not $createdNew) {
    exit 0
}

try {
    while ($true) {
        Add-Content -LiteralPath $supervisorLog -Value "$(Get-Date -Format o) worker starting"
        try {
            & $python -m conn_pilot.distributed_worker 2>&1 |
                ForEach-Object { Add-Content -LiteralPath $supervisorLog -Value "$(Get-Date -Format o) $_" }
            Add-Content -LiteralPath $supervisorLog -Value "$(Get-Date -Format o) worker exited code=$LASTEXITCODE"
        }
        catch {
            Add-Content -LiteralPath $supervisorLog -Value "$(Get-Date -Format o) worker failed: $($_.Exception.Message)"
        }
        Start-Sleep -Seconds 15
    }
}
finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
