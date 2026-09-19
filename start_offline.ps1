$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.offline-venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Offline installation is missing. Run install_offline.ps1 first.'
}

Set-Location -LiteralPath $projectRoot
$env:APP_ENV = 'production'
$env:HOST = '0.0.0.0'

Write-Host 'The system is starting without an Internet connection.' -ForegroundColor Green
Write-Host 'On this server: http://127.0.0.1:5000'
$addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.IPAddress -notlike '169.254.*' } |
    Select-Object -ExpandProperty IPAddress -Unique
foreach ($address in $addresses) {
    Write-Host "On the local network: http://${address}:5000"
}
Write-Host 'Press Ctrl+C to stop.'

& $pythonExe main.py
