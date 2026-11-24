# MQEL Revival - prepare this PC as a public server (static IP or DynDNS name).
#
#   powershell -ExecutionPolicy Bypass -File tools\setup_public_server.ps1 [-PublicHost 203.0.113.7] [-ExtraHost name ...]
#
# 1. New certificate for 127.0.0.1, the LAN IP and the public host
#    (tools\make_local_cert.py), old one kept in server\state\tls\backup-<time>\
# 2. Bakes it into the game exe (tools\patch_ca.py) -> server\state\tls\MightyQuest_local.exe,
#    which the patcher hands to every launcher (start_servers.bat --client-exe)
# 3. Builds player-pack\ + player-pack.zip for remote players
#    (PublicLauncherSettings.json with your address, steam-launcher-patch.cmd, README)
# 4. Opens TCP 8081, 8443, 5222 in the Windows firewall (asks for admin rights)
#
# -KeepCertificate: skip 1-2 (players keep their exe; use it to refresh pack/website).
# The router part (port forwarding) you do yourself, see docs\06-public-server.md.
# Re-run this script whenever your public IP/host name changes.

param(
    [string]$PublicHost,
    [string[]]$ExtraHost = @(),
    [switch]$SkipFirewall,
    [switch]$KeepCertificate   # only rebuild player pack + website downloads (no new cert/exe)
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Tls = Join-Path $Root "server\state\tls"

function Get-ConfigValue($name) {
    $cfg = Join-Path $Root "server_config.bat"
    if (-not (Test-Path $cfg)) { return $null }
    $m = Select-String -Path $cfg -Pattern ('^\s*set\s+"' + $name + '=(.*)"\s*$') | Select-Object -First 1
    if ($m) { return $m.Matches[0].Groups[1].Value }
    return $null
}
function Test-Ip($s) { $ip = $null; return [Net.IPAddress]::TryParse($s, [ref]$ip) }

if (-not $PublicHost) { $PublicHost = Get-ConfigValue "MQEL_PUBLIC_HOST" }
if (-not $PublicHost) {
    try { $PublicHost = (Invoke-RestMethod -Uri "https://api.ipify.org" -TimeoutSec 10).Trim() } catch {}
}
if (-not $PublicHost) { throw "No public host: pass -PublicHost or set MQEL_PUBLIC_HOST in server_config.bat" }
Write-Host "Public host: $PublicHost" -ForegroundColor Cyan

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $python) { throw "Python not found in PATH" }

if ($KeepCertificate) { Write-Host "Keeping the current certificate and game exe." } else {
# --- 1. certificate ---------------------------------------------------------
$exe = Join-Path $Tls "MightyQuest_local.exe"
if (-not (Test-Path $exe)) { throw "$exe missing: set up the local HTTPS client first (docs\05-windows-setup.md)" }
$backup = Join-Path $Tls ("backup-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Force $backup | Out-Null
Copy-Item (Join-Path $Tls "*.pem"), $exe $backup
Write-Host "Backup of the old certificate and exe: $backup"

$certArgs = @("tools\make_local_cert.py", "--force", "--minimal")
foreach ($h in @($PublicHost) + $ExtraHost) {
    if (Test-Ip $h) { $certArgs += @("--ip", $h) } else { $certArgs += @("--dns", $h) }
}
& $python @certArgs
if ($LASTEXITCODE) { throw "make_local_cert.py failed" }

# --- 2. game exe with the new certificate -------------------------------------
# Only slot 3 (expired AddTrust root, 1057 bytes) works: the game rejected a
# certificate in slot 1 with "unknown CA", and it offers no ECDSA ciphers
# (tested 2026-11-20). So: RSA, and --minimal (no localhost/LAN IP, short
# serial) to fit. Keep the host list short: 127.0.0.1 + host name + public IP.
# Always patch the untouched base exe (MightyQuest_base.exe, saved on the first
# run), so slots filled by an earlier run don't shrink the room.
$base = Join-Path $Tls "MightyQuest_base.exe"
if (-not (Test-Path $base)) { Copy-Item (Join-Path $backup "MightyQuest_local.exe") $base }
$patched = $false
foreach ($slot in @(3)) {
    & $python tools\patch_ca.py $base (Join-Path $Tls "cert.pem") --out $exe --no-fps --slot $slot
    if (-not $LASTEXITCODE) { $patched = $true; break }
}
if (-not $patched) { throw "patch_ca.py failed" }
}

# --- 3. player pack ------------------------------------------------------------
$pack = Join-Path $Root "player-pack"
if (Test-Path $pack) { Remove-Item -Recurse -Force $pack }
New-Item -ItemType Directory $pack | Out-Null
$settings = Get-Content -Raw (Join-Path $Root "website\PublicLauncherSettings.json")
# every URL host -> $PublicHost (the template may already hold an older host)
$settings = [regex]::Replace($settings, '(https?://)[^/:"]+', { param($m) $m.Groups[1].Value + $PublicHost })
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText((Join-Path $pack "PublicLauncherSettings.json"), $settings, $utf8)
Copy-Item (Join-Path $Root "website\steam-launcher-patch.cmd") $pack
Copy-Item (Join-Path $Tls "cert.pem") (Join-Path $pack "mqel-server-cert.pem")
$certBat = @'
@echo off
REM Optional: trust the MQEL server certificate for the in-game Bling shop
REM (launcher login and the game itself work without it). Current user only.
certutil -addstore -user Root "%~dp0mqel-server-cert.pem"
pause
'@
[IO.File]::WriteAllText((Join-Path $pack "install-shop-certificate.bat"), $certBat.Replace("`n", "`r`n"), $utf8)
$readme = @"
MQEL Revival - joining the server at $PublicHost
================================================

You need The Mighty Quest for Epic Loot in your Steam library
(Steam: steam://install/239220).

1. Right-click the game in Steam > Manage > Browse local files.
   That opens the install folder (it contains the "Launcher" folder).
2. Copy PublicLauncherSettings.json into the "Launcher" folder
   (replace the existing file).
3. Copy steam-launcher-patch.cmd into the install folder and double-click it.
   It lets the launcher install updates from this server.
4. Start the game from Steam. The launcher logs you in with your Steam account
   (first time: pick "new account" or link an existing one), then downloads a
   game update from the server and starts the game.

Optional: install-shop-certificate.bat makes the Bling shop page work.

Server: launcher http://${PublicHost}:8081/launcher/, game https://${PublicHost}:8443, chat ${PublicHost}:5222
"@
[IO.File]::WriteAllText((Join-Path $pack "README.txt"), $readme.Replace("`r`n", "`n").Replace("`n", "`r`n"), $utf8)
$zip = Join-Path $Root "player-pack.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path (Join-Path $pack "*") -DestinationPath $zip
Write-Host "Player pack: $zip" -ForegroundColor Green

# --- 3b. website downloads (served by --web-port, start_servers.bat MQEL_WEB_PORT) ---
$web = Join-Path $Root "website"
Copy-Item (Join-Path $pack "PublicLauncherSettings.json") $web -Force
Copy-Item (Join-Path $pack "mqel-server-cert.pem") $web -Force
Copy-Item (Join-Path $pack "install-shop-certificate.bat") $web -Force
Copy-Item $zip (Join-Path $web "player-pack.zip") -Force
Write-Host "Website downloads updated: $web" -ForegroundColor Green

# --- 4. firewall ---------------------------------------------------------------
if (-not $SkipFirewall) {
    $fw = Join-Path $PSScriptRoot "open_firewall.ps1"
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($admin) { & $fw }
    else {
        Write-Host "Opening the firewall needs admin rights, a UAC prompt follows..."
        try { Start-Process powershell -Verb RunAs -Wait -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$fw`"" }
        catch { Write-Host "Skipped. Run as admin later: tools\open_firewall.ps1" -ForegroundColor Yellow }
    }
}

Write-Host ""
Write-Host "Done. Next:" -ForegroundColor Green
Write-Host "  - Router: forward TCP 8081, 8443, 5222 to this PC (docs\06-public-server.md)"
Write-Host "  - server_config.bat: MQEL_BIND=0.0.0.0, MQEL_PUBLIC_HOST=$PublicHost"
Write-Host "  - restart: stop_servers.bat, start_servers.bat"
Write-Host "  - send player-pack.zip to your players"
