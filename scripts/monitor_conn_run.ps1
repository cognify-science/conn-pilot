param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [int]$IntervalSeconds = 5,
    [int]$WaitForMatlabMinutes = 15,
    [int]$MaximumRunMinutes = 180
)

$ErrorActionPreference = 'SilentlyContinue'
$outputDirectory = Split-Path -Parent $OutputPath
if ($outputDirectory) {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}
Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue

$startedAt = Get-Date
$waitDeadline = $startedAt.AddMinutes($WaitForMatlabMinutes)
$runDeadline = $startedAt.AddMinutes($MaximumRunMinutes)
$matlabSeen = $false
$lastMatlabSeenAt = $null
$nvidiaSmi = (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue).Source

while ((Get-Date) -lt $runDeadline) {
    $now = Get-Date
    $matlab = @(Get-Process matlab -ErrorAction SilentlyContinue)
    if ($matlab.Count -gt 0) {
        $matlabSeen = $true
        $lastMatlabSeenAt = $now
    }

    $processor = Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor |
        Where-Object Name -eq '_Total' |
        Select-Object -First 1
    $memory = Get-CimInstance Win32_OperatingSystem
    $disk = Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk |
        Where-Object Name -eq '_Total' |
        Select-Object -First 1

    $gpuUtilization = $null
    $gpuPowerWatts = $null
    $gpuMemoryMb = $null
    if ($nvidiaSmi) {
        $gpuValues = & $nvidiaSmi --query-gpu=utilization.gpu,power.draw,memory.used `
            --format=csv,noheader,nounits 2>$null | Select-Object -First 1
        if ($gpuValues) {
            $parts = $gpuValues -split ',' | ForEach-Object { $_.Trim() }
            if ($parts.Count -ge 3) {
                $gpuUtilization = [double]$parts[0]
                $gpuPowerWatts = [double]$parts[1]
                $gpuMemoryMb = [double]$parts[2]
            }
        }
    }

    $totalMemoryKb = [double]$memory.TotalVisibleMemorySize
    $freeMemoryKb = [double]$memory.FreePhysicalMemory
    $record = [ordered]@{
        timestamp = $now.ToUniversalTime().ToString('o')
        phase = if ($matlab.Count -gt 0) { 'running' } else { 'waiting' }
        cpu_percent = [double]$processor.PercentProcessorTime
        memory_used_percent = if ($totalMemoryKb) {
            [math]::Round((1 - ($freeMemoryKb / $totalMemoryKb)) * 100, 3)
        } else { $null }
        memory_available_mb = [math]::Round($freeMemoryKb / 1024, 3)
        disk_percent_time = [double]$disk.PercentDiskTime
        disk_read_bytes_per_sec = [double]$disk.DiskReadBytesPersec
        disk_write_bytes_per_sec = [double]$disk.DiskWriteBytesPersec
        matlab_processes = $matlab.Count
        matlab_working_set_mb = [math]::Round(
            (($matlab | Measure-Object WorkingSet64 -Sum).Sum / 1MB), 3
        )
        matlab_cpu_seconds = [math]::Round(
            (($matlab | Measure-Object CPU -Sum).Sum), 3
        )
        gpu_utilization_percent = $gpuUtilization
        gpu_power_watts = $gpuPowerWatts
        gpu_memory_mb = $gpuMemoryMb
    }
    ($record | ConvertTo-Json -Compress) | Add-Content -LiteralPath $OutputPath -Encoding utf8

    # CONN briefly closes and replaces MATLAB launchers while it creates its
    # parallel background jobs. Treat only a sustained 90-second gap as the
    # end of the run so monitoring survives that hand-off.
    if (
        $matlabSeen -and
        $matlab.Count -eq 0 -and
        $lastMatlabSeenAt -and
        $now -ge $lastMatlabSeenAt.AddSeconds(90)
    ) {
        break
    }
    if (-not $matlabSeen -and $now -ge $waitDeadline) {
        break
    }
    Start-Sleep -Seconds ([math]::Max(1, $IntervalSeconds))
}
