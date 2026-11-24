@echo off
REM ==========================================================================
REM  MQEL Revival - stop game server and XMPP chat server
REM  Finds the python processes by their command line (works no matter how
REM  they were started), then closes the server windows.
REM  Only the server processes are stopped, never a game client.
REM  A pending update countdown (admin "Schedule update") is cancelled, so
REM  stopping before it reaches 0 doesn't carry it over to the next start
REM  (it would close the players' games after the restart).
REM  stop_servers.bat /nopause  -> no "press a key" at the end (scripts)
REM ==========================================================================
setlocal
set "PAUSE_CMD=pause"
if /i "%~1"=="/nopause" set "PAUSE_CMD=rem"
echo Stopping MQEL servers...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'game_server(_dev)?\.py|xmpp_server\.py' -and $_.Name -notmatch 'powershell' }; if ($p) { $p | ForEach-Object { Write-Host ('  stopping PID ' + $_.ProcessId + '  ' + $_.Name); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } } else { Write-Host '  no MQEL server processes found' }"

taskkill /F /T /FI "WINDOWTITLE eq MQEL Game Server*" >nul 2>&1
taskkill /F /T /FI "WINDOWTITLE eq MQEL XMPP Server*" >nul 2>&1

if exist "%~dp0server.pid" del "%~dp0server.pid"

REM --- cancel a pending update countdown -----------------------------------
if exist "%~dp0server\state\new\server_notice.json" (
    findstr /c:"\"At\"" "%~dp0server\state\new\server_notice.json" >nul 2>&1 && echo   update countdown cancelled
    > "%~dp0server\state\new\server_notice.json" echo {}
)

echo.
echo All servers have been stopped.
%PAUSE_CMD%
