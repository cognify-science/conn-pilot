param(
    [string]$CredentialFile = (Join-Path (Split-Path $PSScriptRoot -Parent) '.env.distributed.local')
)

$token = $env:CONN_PILOT_TOKEN
if ([string]::IsNullOrWhiteSpace($token) -and (Test-Path -LiteralPath $CredentialFile)) {
    foreach ($line in Get-Content -LiteralPath $CredentialFile) {
        if ($line -match '^(CONN_PILOT_TOKEN|CONN_PILOT_ADMIN_TOKEN)=(.+)$') {
            $token = $Matches[2]
            break
        }
    }
}

if ([string]::IsNullOrWhiteSpace($token)) {
    throw 'CONN Pilot credential was not found'
}

@{ Authorization = "Bearer $token" } | ConvertTo-Json -Compress
