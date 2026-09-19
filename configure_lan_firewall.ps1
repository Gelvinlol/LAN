param(
    [string]$Profile = 'Domain,Private',
    [int]$Port = 5000
)

$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an Administrator PowerShell.'
}

$ruleName = "LAN Unit Management TCP $Port"
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host 'The firewall rule already exists.' -ForegroundColor Yellow
    exit 0
}

$ruleParameters = @{
    DisplayName = $ruleName
    Direction = 'Inbound'
    Action = 'Allow'
    Protocol = 'TCP'
    LocalPort = $Port
    Profile = $Profile
}
New-NetFirewallRule @ruleParameters | Out-Null

Write-Host "Allowed TCP port $Port for profile $Profile." -ForegroundColor Green
