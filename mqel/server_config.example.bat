@echo off
REM ==========================================================================
REM  MQEL server settings, read by start_servers.bat.
REM  Copy this file to server_config.bat and fill it in.
REM  server_config.bat holds your Steam Web API key: never share or commit it.
REM ==========================================================================

REM Steam login (https://steamcommunity.com/dev/apikey). Empty = no Steam login.
set "MQEL_STEAM_API_KEY="

REM Network interface the servers listen on:
REM   127.0.0.1 = only this PC (private/testing)
REM   0.0.0.0   = all interfaces (LAN, and the internet via router port forwarding)
set "MQEL_BIND=127.0.0.1"

REM Address remote players use (public IP or DynDNS name). Only used for the
REM messages and by tools\setup_public_server.ps1. Empty = local only.
set "MQEL_PUBLIC_HOST="

REM Project website (website\ folder) on its own port, e.g. 8088 -> http://<host>:8088/
REM Empty = no website. Router/firewall: forward/open this TCP port too.
set "MQEL_WEB_PORT="

REM Discord Rich Presence: Application ID of your Discord application
REM (docs/85-discord-presence.md). Empty = no Discord status.
set "MQEL_DISCORD_APP_ID="

REM Discord webhooks (docs/86-discord-events.md). Secret, anyone with the URL
REM can post. Empty = off.
REM In-game events channel: Cornelius announces every event start.
set "MQEL_DISCORD_WEBHOOK="
REM Patch-note channel: every news entry of the admin tool (News page).
set "MQEL_DISCORD_PATCH_WEBHOOK="
