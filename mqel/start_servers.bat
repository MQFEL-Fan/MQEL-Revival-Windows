@echo off
REM ==========================================================================
REM  MQEL Revival - start game server (8081) and XMPP chat server (5222)
REM  Each server runs in its own minimized window, so closing THIS window
REM  no longer kills them. Stop them with stop_servers.bat.
REM ==========================================================================
setlocal
REM start_servers.bat /nopause  -> no "press a key" (scripts, tools\restart_servers.py)
set "PAUSE_CMD=pause"
if /i "%~1"=="/nopause" set "PAUSE_CMD=rem"

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"
REM The server uses paths relative to the project folder (server\requests.log.jsonl ...)
cd /d "%BASE_DIR%"

echo Starting MQEL servers in: %BASE_DIR%
echo.

REM --- Settings (server_config.bat: Steam key, bind address, public host) ----
set "MQEL_BIND=127.0.0.1"
set "MQEL_PUBLIC_HOST="
set "MQEL_WEB_PORT="
if exist "%BASE_DIR%\server_config.bat" call "%BASE_DIR%\server_config.bat"
if not defined MQEL_BIND set "MQEL_BIND=127.0.0.1"
if defined MQEL_STEAM_API_KEY (
    echo [OK] Steam login enabled ^(MQEL_STEAM_API_KEY set^)
) else (
    echo [WARN] MQEL_STEAM_API_KEY not set: Steam login is disabled.
    echo        Copy server_config.example.bat to server_config.bat and add your key.
)
echo [OK] Listening on: %MQEL_BIND%

REM --- Python ---------------------------------------------------------------
set "PYTHON_CMD="
where python >nul 2>&1 && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    where py >nul 2>&1 && set "PYTHON_CMD=py -3"
)
if not defined PYTHON_CMD (
    echo [ERROR] Python not found in PATH. Install Python 3.9+ from https://www.python.org/downloads/
    %PAUSE_CMD%
    exit /b 1
)
echo [OK] Python: %PYTHON_CMD%

if not exist "server\game_server.py" (
    echo [ERROR] server\game_server.py not found.
    %PAUSE_CMD%
    exit /b 1
)
if not exist "server\state\new" mkdir "server\state\new"

REM --- Already running? ------------------------------------------------------
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8081 -State Listen -ErrorAction SilentlyContinue) { exit 1 }"
if errorlevel 1 (
    echo [WARN] Something is already listening on port 8081 - servers probably already running.
    echo        Run stop_servers.bat first if you want a clean restart.
    %PAUSE_CMD%
    exit /b 0
)

REM --- Game server ----------------------------------------------------------
REM --names-as-tokens: dev option, also accepts an existing login NAME as -token.
REM Only used when the server listens on 127.0.0.1, never on a public server.
REM --tls-port 8443: the Steam MightyQuest.exe quits on http:// server URLs.
REM --client-exe: game exe with our certificate (server\state\tls\cert.pem,
REM tools\make_local_cert.py + tools\patch_ca.py); the launcher installs it.
set "TLS_ARGS="
if exist "server\state\tls\MightyQuest_local.exe" set "TLS_ARGS=--tls-port 8443 --client-exe server\state\tls\MightyQuest_local.exe"
set "DEV_ARGS="
set "WEB_ARGS="
if defined MQEL_WEB_PORT set "WEB_ARGS=--web-port %MQEL_WEB_PORT%"
if "%MQEL_BIND%"=="127.0.0.1" set "DEV_ARGS=--names-as-tokens"
start "MQEL Game Server" /min cmd /c "%PYTHON_CMD% -u server\game_server.py --host %MQEL_BIND% --port 8081 --profile new %DEV_ARGS% %TLS_ARGS% %WEB_ARGS% > game_server.log 2>&1"

REM --- XMPP chat server -----------------------------------------------------
start "MQEL XMPP Server" /min cmd /c "%PYTHON_CMD% -u server\xmpp_server.py --host %MQEL_BIND% --port 5222 --state server\state\new > xmpp_server.log 2>&1"

REM --- Verify ----------------------------------------------------------------
echo Waiting for the game server to come up...
powershell -NoProfile -Command "for ($i=0; $i -lt 20; $i++) { if (Get-NetTCPConnection -LocalPort 8081 -State Listen -ErrorAction SilentlyContinue) { exit 0 }; Start-Sleep -Milliseconds 500 }; exit 1"
if errorlevel 1 (
    echo [ERROR] Game server did not start. Last lines of game_server.log:
    powershell -NoProfile -Command "Get-Content game_server.log -Tail 20"
    %PAUSE_CMD%
    exit /b 1
)
echo [OK] Game server listening on 127.0.0.1:8081

powershell -NoProfile -Command "for ($i=0; $i -lt 10; $i++) { if (Get-NetTCPConnection -LocalPort 5222 -State Listen -ErrorAction SilentlyContinue) { exit 0 }; Start-Sleep -Milliseconds 500 }; exit 1"
if errorlevel 1 (
    echo [WARN] XMPP chat server is not listening on 5222. See xmpp_server.log
) else (
    echo [OK] XMPP chat server listening on 127.0.0.1:5222
)

echo.
echo ========================================
echo   MQEL Servers are running
echo ========================================
echo   Game Server : http://127.0.0.1:8081
echo   Login Page  : http://127.0.0.1:8081/launcher/
echo   Admin Panel : http://127.0.0.1:8081/admin
echo   Logs        : game_server.log, xmpp_server.log
if "%MQEL_BIND%"=="127.0.0.1" goto :no_public
if not defined MQEL_PUBLIC_HOST goto :no_public
echo   Public      : http://%MQEL_PUBLIC_HOST%:8081/launcher/
echo                 game https://%MQEL_PUBLIC_HOST%:8443, chat %MQEL_PUBLIC_HOST%:5222
echo   Players     : send them player-pack.zip (tools\setup_public_server.ps1)
if defined MQEL_WEB_PORT echo   Website     : http://%MQEL_PUBLIC_HOST%:%MQEL_WEB_PORT%/
:no_public
echo ========================================
echo   Next: run launch_game.bat
echo   Stop: run stop_servers.bat
echo.
echo You can close this window - the servers keep running.
%PAUSE_CMD%
