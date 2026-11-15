<#
.SYNOPSIS
    LsletUI 构建产物自签名脚本（可重复执行，一键重签）

.DESCRIPTION
    用当前用户证书存储中的自签名代码签名证书给 dist\LsletUI\LsletUI.exe 签名。
    - 证书已存在（主题匹配、含私钥、未过期）时直接复用，不会每次更换签名者
    - 证书不存在时新建一张 3 年有效期的自签名代码签名证书并导入 Cert:\CurrentUser\My
    - 优先带 RFC3161 时间戳；时间戳服务不可达时退化为不带时间戳，不阻塞签名
    - 签名后立即回读 Get-AuthenticodeSignature 结果并打印

    注意：自签名证书不在系统信任链中，SmartScreen/「未知发布者」提示依然存在，
    这是预期行为，不代表签名失败。签名只保证文件带上了可验证的发布者信息与篡改校验。

.PARAMETER ExePath
    要签名的 exe 路径。默认 <脚本目录>\dist\LsletUI\LsletUI.exe

.PARAMETER Subject
    证书主题。默认 CN=LsletUI Self Signed（改这个值会生成另一张证书）

.PARAMETER TimestampUrl
    RFC3161 时间戳服务地址。默认 http://timestamp.digicert.com

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\sign_build.ps1
#>
param(
    [string]$ExePath = "",
    [string]$Subject = "CN=LsletUI Self Signed",
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"

# --- 1. 定位要签名的 exe ---
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($ExePath)) {
    $ExePath = Join-Path $scriptDir "..\exe\LsletUIFree\LsletUIFree.exe"
}
if (-not (Test-Path $ExePath)) {
    Write-Host "[FAIL] 找不到待签名的 exe: $ExePath" -ForegroundColor Red
    Write-Host "       请先执行 PyInstaller 打包（exe\LsletUIFree\LsletUIFree.exe）" -ForegroundColor Yellow
    exit 2
}
$ExePath = (Resolve-Path $ExePath).Path
Write-Host "[1/4] 待签名文件: $ExePath" -ForegroundColor Cyan

# --- 2. 复用已有证书，没有则新建 ---
# 复用判据：主题匹配 + 有私钥 + 未临近过期 + 含代码签名 EKU(1.3.6.1.5.5.7.3.3)
# 注意：EKU 的 FriendlyName 在中文系统是「代码签名」，不能按英文名匹配，必须按 OID 判断
$cert = Get-ChildItem Cert:\CurrentUser\My |
    Where-Object {
        $_.Subject -eq $Subject -and
        $_.HasPrivateKey -and
        $_.NotAfter -gt (Get-Date).AddDays(30) -and
        (($_.Extensions | Where-Object { $_.Oid.Value -eq "2.5.29.37" } |
            ForEach-Object { $_.EnhancedKeyUsages.Value }) -contains "1.3.6.1.5.5.7.3.3")
    } |
    Sort-Object NotAfter -Descending |
    Select-Object -First 1

if ($cert) {
    Write-Host "[2/4] 复用已有证书: $($cert.Thumbprint) (有效期至 $($cert.NotAfter.ToString('yyyy-MM-dd')))" -ForegroundColor Cyan
} else {
    Write-Host "[2/4] 未找到可用证书，新建自签名代码签名证书（3 年有效期）..." -ForegroundColor Cyan
    $cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $Subject `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -KeyUsage DigitalSignature `
        -KeyExportPolicy Exportable `
        -HashAlgorithm SHA256 `
        -NotAfter (Get-Date).AddYears(3)
    Write-Host "      已创建: $($cert.Thumbprint) (有效期至 $($cert.NotAfter.ToString('yyyy-MM-dd')))" -ForegroundColor Cyan
}

# --- 3. 确保证书链可被验证（Set-AuthenticodeSignature 要求证书链可信）---
# 自签名证书的根就是自己，默认不在任何信任存储中，直接签名会报：
#   "A certificate chain processed, but terminated in a root certificate
#    which is not trusted by the trust provider"
# 解决方式：把该证书的公钥导入【当前用户】的「受信任的根证书颁发机构」。
# 只影响当前用户，不改动 LocalMachine 全局信任；卸载可执行：
#   Remove-Item Cert:\CurrentUser\Root\<Thumbprint>
Write-Host "[3/5] 检查证书链信任状态..." -ForegroundColor Cyan
$chain = New-Object System.Security.Cryptography.X509Certificates.X509Chain
if ($chain.Build($cert)) {
    Write-Host "      证书链已可信，无需导入" -ForegroundColor Cyan
} else {
    Write-Host "      当前用户未信任该证书，导入到 Cert:\CurrentUser\Root ..." -ForegroundColor Yellow
    $cerPath = Join-Path $env:TEMP "lsletui_codesign_$($cert.Thumbprint).cer"
    Export-Certificate -Cert $cert -FilePath $cerPath -Type CERT | Out-Null
    Import-Certificate -FilePath $cerPath -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null
    $chain2 = New-Object System.Security.Cryptography.X509Certificates.X509Chain
    if ($chain2.Build($cert)) {
        Write-Host "      已加入当前用户受信任根，证书链验证通过" -ForegroundColor Cyan
    } else {
        Write-Host "[WARN] 导入后证书链仍不可信，签名可能失败" -ForegroundColor Yellow
    }
}

# --- 4. 签名（带时间戳，失败则退化）---
Write-Host "[4/5] 开始签名..." -ForegroundColor Cyan
$timestampUsed = $true
try {
    $sig = Set-AuthenticodeSignature -FilePath $ExePath -Certificate $cert `
        -TimestampServer $TimestampUrl -HashAlgorithm SHA256
    if ($sig.Status -ne "Valid") {
        throw "签名返回状态为 $($sig.Status): $($sig.StatusMessage)"
    }
} catch {
    Write-Host "      带时间戳签名失败: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "      退化为不带时间戳签名（签名本身仍有效，只是没有可信时间戳）" -ForegroundColor Yellow
    $timestampUsed = $false
    $sig = Set-AuthenticodeSignature -FilePath $ExePath -Certificate $cert -HashAlgorithm SHA256
    if ($sig.Status -ne "Valid") {
        Write-Host "[FAIL] 签名失败: $($sig.Status) - $($sig.StatusMessage)" -ForegroundColor Red
        exit 3
    }
}

# --- 4. 回读校验结果 ---
$v = Get-AuthenticodeSignature -FilePath $ExePath
Write-Host "[5/5] 签名结果:" -ForegroundColor Cyan
Write-Host "      Status          : $($v.Status)"
Write-Host "      StatusMessage   : $($v.StatusMessage)"
Write-Host "      SignerSubject   : $($v.SignerCertificate.Subject)"
Write-Host "      SignerThumbprint: $($v.SignerCertificate.Thumbprint)"
Write-Host "      TimestampUsed   : $timestampUsed"
if ($v.TimeStamperCertificate) {
    Write-Host "      TimeStamper     : $($v.TimeStamperCertificate.Subject)"
} else {
    Write-Host "      TimeStamper     : (无)"
}

Write-Host ""
Write-Host "提示：自签名证书不受系统信任，SmartScreen 仍会提示「未知发布者」，属预期行为。" -ForegroundColor Yellow
Write-Host "      可重复执行本脚本，证书会复用，签名者不会变化。" -ForegroundColor Yellow

if ($v.Status -ne "Valid") {
    exit 4
}
exit 0
