$ErrorActionPreference = "Stop"

$ruleName = "Pro Downloader PWA - LAN TCP 8000"
$venvConfig = Join-Path $PSScriptRoot ".venv\pyvenv.cfg"

if (-not (Test-Path -LiteralPath $venvConfig)) {
    throw "Python environment was not found. Run Start Pro Downloader Server.bat first."
}

$executableLine = Get-Content -LiteralPath $venvConfig |
    Where-Object { $_ -match "^executable\s*=" } |
    Select-Object -First 1

if (-not $executableLine) {
    throw "Could not determine the Python executable from .venv\pyvenv.cfg."
}

$pythonExecutable = ($executableLine -split "=", 2)[1].Trim()

Get-NetFirewallRule -Direction Inbound -Action Block -Enabled True -ErrorAction SilentlyContinue |
    Where-Object {
        $application = $_ | Get-NetFirewallApplicationFilter
        $port = $_ | Get-NetFirewallPortFilter
        $application.Program -ieq $pythonExecutable -and $port.Protocol -eq "TCP"
    } |
    Set-NetFirewallRule -Enabled False

Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

New-NetFirewallRule `
    -DisplayName $ruleName `
    -Description "Allows iPhone and other devices on the local network to access Pro Downloader PWA." `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort 8000 `
    -Program $pythonExecutable `
    -Profile Any `
    -RemoteAddress LocalSubnet | Out-Null

Write-Host ""
Write-Host "iPhone access is enabled for TCP port 8000 on the local network." -ForegroundColor Green
Write-Host "Python: $pythonExecutable"
Write-Host ""
