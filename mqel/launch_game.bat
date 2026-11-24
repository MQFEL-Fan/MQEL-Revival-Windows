@echo off
REM Direct game launch (bypasses PublicLauncher).
REM Logs in at the local server to get a REAL session token, then starts the client.
REM All the work is in launch_game.ps1 next to this file.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_game.ps1" %*
pause
