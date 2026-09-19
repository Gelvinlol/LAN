param(
    [switch]$SkipDatabaseUpgrade
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot 'offline_runtime'
$pythonRoot = Join-Path $runtimeRoot 'python311'
$pythonExe = Join-Path $pythonRoot 'python.exe'
$installer = Join-Path $runtimeRoot 'python-3.11.9-amd64.exe'
$venvRoot = Join-Path $projectRoot '.offline-venv'
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
$packageRoot = Join-Path $projectRoot 'offline_packages'
$requirements = Join-Path $projectRoot 'offline-requirements.txt'
$checksumManifest = Join-Path $projectRoot 'offline_checksums.sha256'

Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath $checksumManifest)) {
    throw 'The offline checksum manifest is missing.'
}
Write-Host 'Verifying offline bundle integrity...' -ForegroundColor Cyan
foreach ($line in Get-Content -LiteralPath $checksumManifest) {
    if (-not $line.Trim()) { continue }
    $parts = $line -split '\s{2}', 2
    if ($parts.Count -ne 2) { throw "Invalid checksum line: $line" }
    $expectedHash = $parts[0].Trim()
    $relativePath = $parts[1].Trim().Replace('/', '\')
    $targetPath = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $targetPath)) {
        throw "Offline bundle file is missing: $relativePath"
    }
    $actualHash = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedHash) {
        throw "Offline bundle integrity check failed: $relativePath"
    }
}
Write-Host 'Offline bundle integrity verified.' -ForegroundColor Green

if (-not (Test-Path -LiteralPath $pythonExe)) {
    if (-not (Test-Path -LiteralPath $installer)) {
        throw 'The bundled Python installer is missing from offline_runtime.'
    }
    Write-Host 'Installing local Python 3.11...' -ForegroundColor Cyan
    $arguments = @(
        '/quiet',
        'InstallAllUsers=0',
        "TargetDir=`"$pythonRoot`"",
        'Include_launcher=0',
        'PrependPath=0',
        'Include_test=0',
        'Shortcuts=0'
    )
    $process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $pythonExe)) {
        throw "Python installation failed (exit code $($process.ExitCode))."
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host 'Creating the isolated application environment...' -ForegroundColor Cyan
    & $pythonExe -m venv $venvRoot
}

Write-Host 'Installing dependencies strictly from local packages...' -ForegroundColor Cyan
& $venvPython -m pip install --disable-pip-version-check --no-index --find-links $packageRoot --requirement $requirements
if ($LASTEXITCODE -ne 0) { throw 'Offline dependency installation failed.' }

$environmentFile = Join-Path $projectRoot '.env'
if (-not (Test-Path -LiteralPath $environmentFile)) {
    $randomBytes = New-Object byte[] 48
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($randomBytes) } finally { $generator.Dispose() }
    $secret = [Convert]::ToBase64String($randomBytes)
    $environment = Get-Content -LiteralPath (Join-Path $projectRoot '.env.example') -Raw
    $environment = $environment.Replace('replace-with-at-least-32-random-bytes', $secret)
    [System.IO.File]::WriteAllText($environmentFile, $environment, [System.Text.UTF8Encoding]::new($false))
    Write-Host 'Created a secure local .env file.' -ForegroundColor Green
}

if (-not $SkipDatabaseUpgrade) {
    Write-Host 'Checking and upgrading the database...' -ForegroundColor Cyan
    & $venvPython -m flask --app app db upgrade
    if ($LASTEXITCODE -ne 0) { throw 'Database upgrade failed.' }
}

Write-Host ''
Write-Host 'Offline installation completed.' -ForegroundColor Green
Write-Host 'Start: powershell -ExecutionPolicy Bypass -File .\start_offline.ps1'
Write-Host 'LAN access may require configure_lan_firewall.ps1 once from an Administrator PowerShell.'
