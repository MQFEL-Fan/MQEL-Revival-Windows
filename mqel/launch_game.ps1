# MQEL Revival - direct game launch
#
# Why: the game server only accepts session tokens it issued itself
# (server/auth.py). Starting the client with "-token test" makes every call
# fail with 401 InvalidConnectionTokenException and the client closes.
# This script logs in at /launcher/login (same as the launcher page),
# gets the real 24-char token and passes it to MightyQuest.exe.
#
# Usage:  launch_game.bat                      (asks for name + password)
#         launch_game.bat -ClientDir "...\client-steam\GameData\Bin"

param(
    [string]$ServerUrl = 'http://127.0.0.1:8081',
    [string]$ClientDir = (Join-Path $PSScriptRoot 'client-debug\GameData\Bin'),
    [string]$Exe       = 'MightyQuest.exe'
)

Write-Host '========================================'
Write-Host '  Mighty Quest: Epic Legacy - Direct Launch'
Write-Host '========================================'
Write-Host "Server : $ServerUrl"
Write-Host "Client : $ClientDir\$Exe"
Write-Host ''

$exePath = Join-Path $ClientDir $Exe
if (-not (Test-Path $exePath)) {
    Write-Host "[ERROR] $exePath not found." -ForegroundColor Red
    exit 1
}

# 1. Server reachable?
try {
    Invoke-WebRequest "$ServerUrl/launcher/maintenance" -UseBasicParsing -TimeoutSec 5 | Out-Null
} catch {
    $code = $null
    if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
    if ($code -eq 503) {
        Write-Host '[ERROR] Server is in maintenance mode (only admins can log in).' -ForegroundColor Yellow
    } else {
        Write-Host '[ERROR] Game server is not reachable. Run start_servers.bat first.' -ForegroundColor Red
        Write-Host "        ($($_.Exception.Message))"
        exit 1
    }
}

# 2. Login or register
$mode = Read-Host 'Press Enter to LOG IN, or type R to REGISTER a new account'
$action = if ($mode -match '^[Rr]') { 'register' } else { 'login' }

$user = (Read-Host 'Username').Trim()
if (-not $user) { Write-Host '[ERROR] No username given.' -ForegroundColor Red; exit 1 }
$sec  = Read-Host 'Password' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$pw   = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

$body = @{ name = $user; password = $pw } | ConvertTo-Json
try {
    $r = Invoke-RestMethod -Uri "$ServerUrl/launcher/$action" -Method Post `
         -ContentType 'application/json' -Body $body -TimeoutSec 30
} catch {
    Write-Host "[ERROR] Login request failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

if (-not $r.Token) {
    $msg = switch ($r.Error) {
        'bad_login'         { 'Wrong username or password (or the account does not exist - choose R to register).' }
        'name_taken'        { 'That name is already taken.' }
        'name_invalid'      { 'Name must be 3-24 characters: letters, digits, _ . -' }
        'password_short'    { 'Password must be at least 6 characters.' }
        'too_many_attempts' { 'Too many failed attempts - wait a few minutes.' }
        'maintenance'       { 'Server is in maintenance mode.' }
        default             { "Server said: $($r.Error) $($r.Until)" }
    }
    Write-Host "[ERROR] $msg" -ForegroundColor Red
    exit 1
}

$token = $r.Token
$name  = $r.Name
Write-Host "[OK] Logged in as $name (session token received)" -ForegroundColor Green

# 3. Start the client with the real token
$gameArgs = @(
    '-server_url', $ServerUrl,
    '-token', $token,
    '-email', "$name@mqel.local",
    '-environmentName', 'local',
    '-httpCompression', '0'
)
Start-Process -FilePath $exePath -ArgumentList $gameArgs -WorkingDirectory $ClientDir
Write-Host ''
Write-Host 'Game started.'
Write-Host 'Note: logging in again (here or on the /launcher/ page) ends this session and'
Write-Host '      the running game gets kicked - that is the normal one-session-per-account rule.'
