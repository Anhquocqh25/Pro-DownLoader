param(
    [string]$Python = "$PSScriptRoot\..\.venv\Scripts\python.exe",
    [string]$Iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment not found: $Python"
}
if (-not (Test-Path -LiteralPath $Iscc)) {
    throw "Inno Setup compiler not found: $Iscc"
}

Push-Location $root
try {
    & $Python -m pip install -r requirements-build.txt
    & $Python scripts\generate_icons.py
    & $Python -m unittest discover -s tests -v
    & $Python -m PyInstaller --clean --noconfirm "Pro Downloader.spec"
    & $Iscc "packaging\windows\ProDownloader.iss"

    $installer = Get-Item -LiteralPath (Join-Path $root "release\Pro-Downloader-Setup-1.0.0.exe")
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $installer.FullName
    "$($hash.Hash)  $($installer.Name)" | Set-Content -Encoding ascii -LiteralPath (Join-Path $root "release\SHA256SUMS.txt")

    Write-Host ""
    Write-Host "Installer: $($installer.FullName)"
    Write-Host "SHA256:    $($hash.Hash)"
}
finally {
    Pop-Location
}
