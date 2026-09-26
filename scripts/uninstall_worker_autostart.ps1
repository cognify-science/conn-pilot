$ErrorActionPreference = 'Stop'

$launcher = Join-Path ([Environment]::GetFolderPath('Startup')) 'CONN Pilot Worker.cmd'
if (Test-Path -LiteralPath $launcher) {
    Remove-Item -LiteralPath $launcher -Force
    Write-Output "Removed CONN Pilot worker autostart: $launcher"
}
else {
    Write-Output 'CONN Pilot worker autostart was not installed.'
}
