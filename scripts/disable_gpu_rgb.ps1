param(
    [string]$OpenRgbPath = 'C:\Program Files\OpenRGB\OpenRGB.exe',
    [string]$DeviceName = 'MSI GeForce RTX 3060 Ti Gaming X Trio',
    [int]$MaxAttempts = 8,
    [int]$RetrySeconds = 30
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $OpenRgbPath)) {
    throw "OpenRGB is missing: $OpenRgbPath"
}

$logDirectory = Join-Path $env:APPDATA 'OpenRGB\logs'
$stateDirectory = 'D:\ConnPilot\logs'
$stateLog = Join-Path $stateDirectory 'gpu-rgb-off.log'
New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null

for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    Get-Process OpenRGB -ErrorAction SilentlyContinue | Stop-Process -Force
    $startedAt = Get-Date
    $refreshArguments = '--device "{0}" --mode Direct --color FFFFFF --noautoconnect -vv' -f $DeviceName
    $offArguments = '--device "{0}" --mode Direct --color 000000 --noautoconnect -vv' -f $DeviceName
    $refreshProcess = Start-Process -FilePath $OpenRgbPath -ArgumentList $refreshArguments -Wait -PassThru
    Start-Sleep -Seconds 2
    $process = Start-Process -FilePath $OpenRgbPath -ArgumentList $offArguments -Wait -PassThru
    Start-Sleep -Seconds 2

    $detectionLog = Get-ChildItem -LiteralPath $logDirectory -Filter '*.log' -File -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $startedAt.AddSeconds(-2) } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    $detected = $false
    if ($detectionLog) {
        $detected = [bool](Select-String -LiteralPath $detectionLog.FullName -SimpleMatch 'Registering RGB controller MSI GeForce RTX 3060 Ti Gaming X Trio' -Quiet)
    }

    $line = '{0:o} attempt={1} refresh_exit_code={2} off_exit_code={3} gpu_detected={4}' -f (Get-Date), $attempt, $refreshProcess.ExitCode, $process.ExitCode, $detected
    Add-Content -LiteralPath $stateLog -Value $line -Encoding UTF8

    if ($process.ExitCode -eq 0 -and $detected) {
        exit 0
    }
    if ($attempt -lt $MaxAttempts) {
        Start-Sleep -Seconds $RetrySeconds
    }
}

exit 1
