# LsletUI - exe code signing script
# Purpose: sign packaged exes to reduce AV false positives and SmartScreen blocks
#
# Usage:
#   .\sign_exe.ps1                                        # local cert (auto-create on first run)
#   .\sign_exe.ps1 -PfxPath mycert.pfx -PfxPassword xxx   # commercial PFX cert
#
# Notes:
#   - Self-signed cert only helps on machines where the cert is trusted (internal testing)
#   - For public release, buy an OV/EV code signing cert (EV gets instant SmartScreen reputation)

param(
    [string]$PfxPath = "",
    [string]$PfxPassword = "",
    [string]$CertSubject = "LsletUI Team"
)

$ErrorActionPreference = "Stop"

# ============================================
# Paths
# ============================================
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ExeDir = Join-Path $ProjectRoot "exe"

$Targets = @(
    (Join-Path $ExeDir "LsletUI\LsletUI.exe"),
    (Join-Path $ExeDir "LsletUI\_internal\PySide6\QtWebEngineProcess.exe"),
    (Join-Path $ExeDir "PyIslandLite\PyIslandLite.exe")
)

# ============================================
# Locate signtool (Windows SDK)
# ============================================
$Signtool = $null
$SdkRoot = "C:\Program Files (x86)\Windows Kits\10\bin"
if (Test-Path $SdkRoot) {
    $Candidate = Get-ChildItem $SdkRoot -Directory | Sort-Object Name -Descending |
        ForEach-Object { Join-Path $_.FullName "x64\signtool.exe" } |
        Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($Candidate) { $Signtool = $Candidate }
}
if (-not $Signtool) {
    Write-Host "[ERROR] signtool not found. Install Windows SDK (Signing Tools)." -ForegroundColor Red
    exit 1
}
Write-Host "signtool: $Signtool"

# ============================================
# Get signing certificate
# ============================================
if ($PfxPath -and (Test-Path $PfxPath)) {
    Write-Host "Using external PFX cert: $PfxPath"
    $SignArgs = @("/f", $PfxPath)
    if ($PfxPassword) { $SignArgs += @("/p", $PfxPassword) }
}
else {
    # Find existing local cert
    $Cert = Get-ChildItem "Cert:\CurrentUser\My" |
        Where-Object { $_.Subject -like "*$CertSubject*" -and $_.HasPrivateKey } |
        Sort-Object NotAfter -Descending | Select-Object -First 1

    if (-not $Cert) {
        Write-Host "No cert found. Creating self-signed code signing certificate..."
        $Cert = New-SelfSignedCertificate `
            -Type CodeSigningCert `
            -Subject "CN=$CertSubject, O=$CertSubject" `
            -KeyUsage DigitalSignature `
            -FriendlyName "$CertSubject Code Signing" `
            -CertStoreLocation "Cert:\CurrentUser\My" `
            -NotAfter (Get-Date).AddYears(3) `
            -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3")
        Write-Host "Cert created: $($Cert.Thumbprint)"
    }
    else {
        Write-Host "Using local cert: $($Cert.Thumbprint) (expires $($Cert.NotAfter))"
    }

    Write-Host ""
    Write-Host "[TIP] To stop SmartScreen prompts on this machine, trust the cert (admin PowerShell):" -ForegroundColor Yellow
    Write-Host "  `$cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object Subject -like '*$CertSubject*' | Select-Object -First 1"
    Write-Host "  Export-Certificate -Cert `$cert -FilePath `$env:TEMP\lsletui.cer"
    Write-Host "  Import-Certificate -FilePath `$env:TEMP\lsletui.cer -CertStoreLocation Cert:\LocalMachine\TrustedPeople"
    Write-Host ""

    $SignArgs = @("/sha1", $Cert.Thumbprint)
}

# Timestamp server (signature stays valid after cert expiry)
$SignArgs += @(
    "/fd", "SHA256", "/td", "SHA256",
    "/tr", "http://timestamp.digicert.com"
)

# ============================================
# Sign
# ============================================
foreach ($Exe in $Targets) {
    if (-not (Test-Path $Exe)) {
        Write-Host "[SKIP] Not found: $Exe" -ForegroundColor Yellow
        continue
    }
    Write-Host "Signing: $Exe"
    & $Signtool sign @SignArgs $Exe
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Sign failed: $Exe" -ForegroundColor Red
        exit 1
    }
}

# ============================================
# Verify
# ============================================
Write-Host ""
Write-Host "=== Verify signatures ==="
foreach ($Exe in $Targets) {
    if (Test-Path $Exe) {
        & $Signtool verify /pa $Exe
    }
}

Write-Host ""
Write-Host "=== Signing complete ===" -ForegroundColor Green
