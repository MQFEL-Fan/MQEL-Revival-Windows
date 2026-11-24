# Public server with Steam login (Windows)

How to run the server from your PC so that other people can play over the
internet, logging in with their Steam account. It builds on the local setup in
[05-windows-setup.md](05-windows-setup.md) (Python, `cryptography`, patched game
exe).

```
 Player PC (anywhere)                      Router(s)              Server PC (LAN IP, e.g. 192.168.1.50)
 Steam -> PublicLauncher.exe  --TCP 8081-->  port forwarding  -->  game_server.py  login, patcher
          MightyQuest.exe     --TCP 8443-->                   -->  game_server.py  game (HTTPS)
          (chat)              --TCP 5222-->                   -->  xmpp_server.py  chat
 Web browser                  --TCP 8088-->                   -->  game_server.py  website (website\)
```

In this guide, `<host>` means your public address: your public IP
(<https://api.ipify.org>) or a DynDNS name such as `yourname.duckdns.org`.

## Why a public IP and not a domain or Cloudflare Tunnel

- **A domain is optional.** The server's certificate carries its addresses.
  The game exe that the patcher hands out trusts exactly that certificate, so
  you need no certificate authority and no domain.
- **A fixed name is still useful.** If your ISP changes your public IP, every
  player needs a new `PublicLauncherSettings.json`. A free DynDNS name (DuckDNS,
  No-IP, or your router's DynDNS feature) avoids that: run the setup with
  `-PublicHost yourname.duckdns.org` and the settings never change again.
- **Cloudflare Tunnel does not fit this game:**
  - Chat is raw TCP on 5222. A normal tunnel can't carry it for players who
    don't run `cloudflared` themselves.
  - Cloudflare would present its own certificate on the game port, and the
    game exe doesn't trust it.
  - A permanent tunnel needs a domain on Cloudflare anyway.

  Use port forwarding. Your ISP may block incoming connections (CGNAT: the
  router's WAN IP differs from <https://api.ipify.org>). Then use a VPN overlay
  such as ZeroTier, Tailscale or Radmin VPN instead, with the VPN IP as
  `-PublicHost`.

## Files

| File | Purpose |
|---|---|
| `server_config.bat` | Your settings: Steam Web API key, bind address, public host, website port, Discord application id (`MQEL_DISCORD_APP_ID`, docs/85-discord-presence.md), Discord webhooks for events and patch notes (`MQEL_DISCORD_WEBHOOK`, `MQEL_DISCORD_PATCH_WEBHOOK`, docs/86-discord-events.md). **Secret, never share.** Created from `server_config.example.bat`. |
| `start_servers.bat` | Reads `server_config.bat`. With `MQEL_BIND=0.0.0.0` both servers listen on all interfaces and the dev option `--names-as-tokens` is off. With `MQEL_WEB_PORT` it also serves the website. |
| `tools\setup_public_server.ps1` | Builds the certificate and game exe for the public host, then `player-pack.zip` and the website downloads, and opens the firewall. `-KeepCertificate`: pack and website only. |
| `tools\open_firewall.ps1` | Inbound firewall rules for TCP 8081, 8443, 5222, 8088 (`-Remove` deletes them). |
| `tools\import_account.py` | Imports exported accounts (zip with `manifest.json`, `account.json`, `blings.jsonl`). |
| `tools\link_steam.py` | Links or unlinks SteamIDs while the server is stopped. |
| `player-pack.zip` | What you send to players (created by the setup, also downloadable from the website). |
| `website\` | Project website: `index.html`, `style.css`, `blings.html` (generated at start), downloads. |
| `PATCH_NOTES.md` | Patch notes to publish; the website shows them under "Patch notes". |

## One-time setup

### 1. Steam Web API key

Get a key at <https://steamcommunity.com/dev/apikey> (any domain name works in
the form). Copy `server_config.example.bat` to `server_config.bat` and fill it
in:

```bat
set "MQEL_STEAM_API_KEY=<your key>"
set "MQEL_BIND=0.0.0.0"
set "MQEL_PUBLIC_HOST=<host>"
set "MQEL_WEB_PORT=8088"
```

The server sends the launcher's Steam ticket to
`ISteamUserAuth/AuthenticateUserTicket` (app 239220) and gets the player's
SteamID back, so nobody can fake a SteamID. Without a key, the login page only
offers name and password.

### 2. Certificate, game exe, player pack, firewall

```bat
python -m pip install cryptography
powershell -ExecutionPolicy Bypass -File tools\setup_public_server.ps1
```

Without `-PublicHost`, the script uses `MQEL_PUBLIC_HOST`, or your current
public IP if that isn't set. You can add one more address with
`-ExtraHost`. A typical call:
`-PublicHost yourname.duckdns.org -ExtraHost <public IP>`. An earlier
certificate and exe are copied to `server\state\tls\backup-<time>\`.

The game only trusts certificate **slot 3** of the exe (1,057 bytes). A
certificate in another slot is rejected with `unknown CA`. The game's OpenSSL
also has no ECDSA cipher suites, so an EC certificate fails with
`no shared cipher`. The script therefore builds a small RSA-2048 certificate
(`make_local_cert.py --minimal`, about 1,050 bytes). It names only
`127.0.0.1`, the host name and the public IP. Don't add more than one extra
name, or it no longer fits. The script always patches the untouched
`server\state\tls\MightyQuest_base.exe`.

Use the same address in the certificate and in `PublicLauncherSettings.json`.
The game rejects `https://<name>:8443` if the certificate only names the IP.

`-KeepCertificate` skips the certificate and exe and only rebuilds
`player-pack.zip` and the website downloads. Use it when you only changed the
pack or the website. A new certificate forces every player's launcher to
download a new game exe, and players who installed the shop certificate have
to install it again.

The firewall step needs admin rights (a UAC prompt). You can also run
`tools\open_firewall.ps1` on its own in an admin PowerShell.

### 3. Router: port forwarding

Forward these TCP ports to the server PC's LAN IP:

| External port | Protocol | Internal port | Purpose |
|---|---|---|---|
| 8081 | TCP | 8081 | launcher login page and patcher |
| 8443 | TCP | 8443 | game (HTTPS) |
| 5222 | TCP | 5222 | chat |
| 8088 | TCP | 8088 | website (`MQEL_WEB_PORT`) |

Give the server PC a fixed LAN address (DHCP reservation in the router).
Otherwise the forwarding breaks when the PC gets a new LAN IP.

**Several routers in a row** (ISP modem → firewall → Wi-Fi router → PC): every
router needs the same four forwards. Each one forwards to the **WAN address of
the next router down**, and only the last one forwards to the PC. A router
can't forward straight to a network behind another router's NAT. It has no
route there and sends the packets back out its WAN port.

Testing from inside your own network often fails even when everything is
right, because many routers don't support NAT loopback. Test from outside
instead, for example on a phone with Wi-Fi off:
`http://<host>:8081/launcher/` should show the login page. An online port
checker for 8081, 8443, 5222 and 8088 also works.

### 4. Start

Run `stop_servers.bat`, then `start_servers.bat`. It should report
`Listening on: 0.0.0.0` and `Steam login enabled`.

On the server PC you can keep playing through `127.0.0.1`, because the
certificate covers it too. On the next start from Steam, the launcher
downloads the new game exe.

### 5. First admin

As long as no account has admin rights, the admin page
<http://127.0.0.1:8081/admin> opens without a login from the server PC and the
local network, never from the internet. The server log warns about it at
every start. Do this right after the first start:
1. Register your own account in the launcher, with a password.
2. In the admin page, open Players → your account and make it an admin.

From then on, the admin page asks for that login.

## What players do

Send them `player-pack.zip`. Its `README.txt` tells them to:

1. Own the game on Steam (free, app 239220) and install it.
2. Copy `PublicLauncherSettings.json` into `<game>\Launcher\`.
3. Run `steam-launcher-patch.cmd` from the game folder.
4. Start the game from Steam. The launcher logs them in with Steam. A new
   player gets an account named after their Steam profile, and the patcher
   installs the game exe with your certificate.

Optional: `install-shop-certificate.bat` (Bling shop page over HTTPS).

Everything is also on the website (`http://<host>:8088/`):
- the install guide
- the files `PublicLauncherSettings.json`, `steam-launcher-patch.cmd`,
  `player-pack.zip`, `mqel-server-cert.pem` and `install-shop-certificate.bat`
- the patch notes

The setup script keeps the website's download files up to date. Edit the page
text in `website\index.html`.

The same Steam account is the same game account on every device, and only one
session can exist at a time. Starting the game on a second device (a Steam
Deck, say) kicks the session on the first one. Changing a player's password or
Steam link in the admin page also logs them out. The game shows all of these
as "network error"; restarting the launcher fixes it.

## Importing existing accounts

```bat
stop_servers.bat
python tools\import_account.py player1.zip player2.zip [--replace]
start_servers.bat
```

- Accounts keep their AccountId, so friendships between imported accounts
  survive.
- The SteamID from `manifest.json` is linked to the account, so the owner is
  logged in directly through Steam.
- `--replace` renames an existing account with the same name to `<name>_old`.
  Its password moves to the imported account.
- The tool backs up the state folder first (`server\state\new_backup_<time>`).

## Linking a SteamID to an account

A SteamID64 is the 17-digit number starting with `7656119`. You find it in the
player's Steam profile URL (`steamcommunity.com/profiles/<id>`), or in
`game_server.log` as `/launcher/?steamID=<id>` whenever they open the
launcher. A SteamID can belong to only one account.

**While the server runs (web tool):**

1. Open <http://127.0.0.1:8081/admin> on the server PC and log in with an
   admin account.
2. Go to Players and click the account.
3. Under access:
   - If the account has no SteamID, enter it in **Link SteamID** and click
     **Link Steam**.
   - If it has the wrong one, click **Unlink Steam** first.

Linking or unlinking logs the player out. Their next launcher start logs them
in through Steam.

**Server stopped (command line):**

```bat
stop_servers.bat
python tools\link_steam.py --list
python tools\link_steam.py PlayerName 76561198000000001
python tools\link_steam.py --unlink PlayerName
start_servers.bat
```

Don't edit `logins.json` while the server runs. The server keeps the file in
memory and overwrites your changes.

Unlinking a Steam-only account (one without a password) locks the player out
until you link it again or set a password. If a player logs in through Steam
while their SteamID isn't linked, the launcher creates a new account named
after their Steam profile, such as `<Name>_2`. Delete those in the web tool
(Players → Delete account).

## Security notes

- `server_config.bat` holds the API key. It is in `.gitignore`. Don't zip the
  whole server folder for anyone. If the key leaks, revoke it on the apikey
  page and create a new one.
- Port 8081 is plain HTTP. Steam logins only send a one-time ticket, but name
  and password logins travel unencrypted. Prefer Steam login for remote
  players.
- The admin page `/admin` only answers requests from the server PC
  (`--admin-net` opens it for other networks, over HTTPS only).
- Only forward the four ports above. Never forward anything else to the
  server PC.
- If your public IP changes, re-run `setup_public_server.ps1` and send the new
  `player-pack.zip`. A DynDNS name avoids this.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Login page: Steam login disabled | `MQEL_STEAM_API_KEY` missing; check `server_config.bat` and restart. |
| `steam_http_403` / `steam_invalid` | The key is wrong or revoked, or the ticket expired; start the launcher again. |
| `steam_unreachable` | The server PC can't reach `api.steampowered.com`. |
| Remote player: launcher stays blank | 8081 not forwarded, blocked by the firewall, or wrong address in their settings. |
| Remote player: game closes after the launcher | 8443 not reachable, or the player still has an old game exe. Restarting the launcher lets the patcher replace it. |
| Log: `TLSV1_ALERT_UNKNOWN_CA` | A client with an old exe (from before the new certificate). It goes away once the launcher has patched it. |
| No chat | 5222 not forwarded or blocked. |
| Second device: "network error" in game (log: `401 InvalidConnectionTokenException`) | Session ended: the same account logged in elsewhere, or an admin changed the password or Steam link. Restart the launcher. |
| Launcher shows "Maintenance", but maintenance is off | The launcher can't reach the server under that name (typo, or DNS on that device). It shows its maintenance page for any failed check. Test `http://<host>:8081/launcher/maintenance` in that device's browser. |
| Log: `hqbloomberg.ubisoft.org:11234` / `Awesomium/Plugins` errors | Harmless: Ubisoft's old crash reporter and a missing launcher plugins folder. |
| Steam browser marks the Bling shop "Not secure" | Self-signed certificate. Optional fix: `install-shop-certificate.bat`. Repeat it after every new certificate. |
| Website not reachable from outside | Port 8088 (`MQEL_WEB_PORT`) not forwarded on every router, or not open in the firewall. |
| New account `<Name>_2` after Steam login | That SteamID wasn't linked to the old account. Link it (admin page → Link Steam) and delete the empty new account. |


## Multiple accounts (2026-11-22)

`server/iplog.py` records the IP of every launcher login and game request
per account (`state/new/ip_log.json`: first/last seen, count). A **new**
account (launcher registration or new Steam player) is refused with "An
account already plays from this internet connection" when another account
already played from that IP, unless the IP is on the whitelist. The server
PC (loopback) is always allowed; existing accounts can always log in.

Admin tool: Players list column **Shared IP** (accounts seen on the same
non-whitelisted IP), player page **IP addresses** (with the other accounts
on each IP), button **Multiple accounts** (edit the whitelist, one IP per
line; last refused registrations). The whitelist lives only in the state
file, never in the code or docs. AdminService `GetAccountIps`,
`GetIpWhitelist`, `SetIpWhitelist`.

## Privacy policy

`website/privacy.html` (linked in every page footer and on the launcher
login page, `patcher.privacy_url()`): what is stored (account, password
hash, Steam ID, IPs and country, save game, chat, trades, logs), who sees
it, kept as long as the server runs, no deletion option; using the client
means agreeing to it.

## Renames and battle logs (2026-11-22)

- Players > player > Login > **Rename** also updates the name in every
  friend list (friend lists store a copy of each friend's summary).
- Players > player > **Empty battle log** (`ClearDefendLog`) clears the
  defend log, e.g. entries of players that no longer exist.

## Test accounts and the update countdown (2026-11-23)

- Players > player > **Clear records** (`ClearEconomyRecords`): removes the
  player's purchases (tracking tags Blings / Pack / Shop) and bling ledger,
  so the Purchases and Economy stats tabs leave them out.
- The update countdown no longer logs out every session at 0 (the game
  closes itself through the WASD helper). The logout made Steam players
  start the launcher twice to be recognised again.
