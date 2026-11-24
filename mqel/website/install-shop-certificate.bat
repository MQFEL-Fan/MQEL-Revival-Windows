@echo off
REM Optional: trust the MQEL server certificate for the in-game Bling shop
REM (launcher login and the game itself work without it). Current user only.
certutil -addstore -user Root "%~dp0mqel-server-cert.pem"
pause