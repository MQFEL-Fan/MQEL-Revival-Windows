# Client-Verzeichnis (`client/`)

Spielfertiger Baum, zusammengesetzt aus den Release-Archiven. Stand:
GameData-Extraktion + Merge-Schritte siehe `BUILD.md`. Die GameplayToolbox
ist bewusst **nicht** enthalten (Server-/Admin-Tool, kein Spieler-Bedarf).

## Layout

```text
client/
  BUILD.md                 Wie der Baum gebaut wurde (Paket → Ziel)
  GameData/                ← 0.36.1.34.0_104956_GameData.7z + …_GameUI.7z
    Bin/                   Engine-Binaries, CEF, Boot.tsc, gear.ini
      MightyQuest.exe            ← aus Game-Paket (gepacktes Ship-Binary)
      MightyQuest_release.exe    ← unverpackt, für Analyse/Debug
      MightyQuest_profile.exe    ← unverpackt (Profiling-Build)
      MightyQuestWorker*.exe     ← Simulations-Worker (3 Varianten)
      mightyquest-ui.exe         CEF-Renderprozess (Lobby-/Shop-UI)
      steam_api.dll, libcef.dll, … 
    Config/Game/*.json     Engine-/User-Settings (u. a. UserSettings.json)
    Data/GameplaySettings/ ~8700 Regel-JSONs (Items, Spells, Shop, …)
    Data/Scripts/*.tsc     Boot-/Init-Skripte (Boot via Bin/Boot.tsc)
    Data/Generated/        generierte Assets
    Data/UI/               ← aus GameUI-Paket (Lobby-Bilder, HTML)
    Bigfiles/PC            Bigfile-Pakete (werden per Boot.tsc eingebunden)
    version.GameData.txt   Paket-ID „104956“
    version.GameUI.txt     Paket-ID „280139“
    version.Game.txt       Paket-ID „280139“ (mitkopiert aus Game-Paket)
  Launcher/                ← 0.36.1.34.0_276072_PublicLauncher.7z
    PublicLauncher.exe     Qt-Launcher (Patch-Check, Login-Seite, Spielstart)
    PublicLauncherSettings.json   ← aus Template erzeugt (URLs lokal, s. u.)
    PublicLauncherSettings.Template.json (Original-Template als Referenz)
    LocalLauncher/         Launcher-WebUI (HTML/JS/CSS)
    Installer/Prerequisites/ DirectX-/VC-Redists (für Spieler-Setup)
    LauncherPatcher.exe, MQELDiagnostics.exe, 7z.exe, …
    version.PublicLauncher.txt   Paket-ID „276072“
  LauncherData/            Laufzeitdaten des Launchers (wird tlw. erzeugt)
    InstalledPackages.json Paketstand (Rekonstruktion, Format-TODO)
  Temp/_Launcher/
    LauncherPatcher.exe    Kopie (Launcher erwartet ihn unter
                           ..\Temp\_Launcher\LauncherPatcher.exe)
```

## Start-Wege

1. **Direktstart (Revival-/Debug-Weg):** CWD = `GameData/Bin`,
   `MightyQuest_release.exe -server_url http://127.0.0.1:PORT -token <t>
   -email <mail> -environmentName local -httpCompression 0`
   (weitere Args: `-steamid/-steamticket` nur für Steam,
   `-gameLanguage`, `-attackInputMode`, …). Der Launcher wird umgangen.
2. **Via Launcher (Spieler-Weg, später):** `Launcher/PublicLauncher.exe`
   mit `PublicLauncherSettings.json`:
   `LauncherWebSiteUrl` (Login-Seite, eigenes Hosting),
   `PatcherServiceUrl` (Versions-Check — muss „aktuell“ melden),
   `GameServerUrl` (unser Server), `MaintenanceModeVerificationUrl`.
   Der Launcher startet `..\GameData\Bin\MightyQuest.exe`.

## Launcher und Patcher (server/patcher.py)

`PublicLauncherSettings.json` zeigt auf den Spielserver:
`LauncherWebSiteUrl` = `/launcher/` (Anmeldeseite, setzt Cookie `t` = Token),
`PatcherServiceUrl` = `/patcher`, `MaintenanceModeVerificationUrl` =
`/launcher/maintenance` (leer = keine Wartungsprüfung). Der Launcher holt die
URL beim Start per GET (`TaskCheckMaintenance`, Antwort-Handler 0x4d6813):
Status 200 = normal, jeder andere Status zeigt die lokale
`LocalLauncher/launcher-maintenance.html`; der Body wird nicht gelesen
(`ProxyMaintenanceInfoModel` mit StartTime/EndTime nutzt dieser Weg nicht).
Der Server antwortet im Wartungsmodus (Webtool, `admin.SetMaintenance`,
gespeichert in `state/<Profil>/maintenance.json`) mit 503. `LauncherData/InstalledPackages.json` ist ein
`RMClientPackagesVersion` (Enums als Zahlen); die Steam-Installation führt
u. a. GameBin (1) 280139, DataBin (2) 104956, je Bigfile DataBF (4).
Unbekanntes Format verwirft der Launcher.

Der Server liefert **keine Spieldaten**, nur xdelta-Deltas (VCDIFF) auf die
Dateien der Steam-Installation. Paket DataBin (Version `104956` = Steam,
`104956.<Gruppe>` = Event) ändert in `Bin/Boot.tsc` die Gruppe `OrdinaryDay` auf das Saison-Event nach Datum
(`patcher.EVENTS`, Ostern beweglich); erzwingen per
`game_server.py --seasonal-event Halloween`. Der Launcher startet danach
`GameData\Bin\MightyQuest.exe` mit `-token/-email/-server_url`.
Im Test bestätigt (Klartext-Baum, ohne Steam-Modus): der Launcher lädt
`2_104956_104956.Halloween.7z` ohne Nachfrage, wendet es an, das Spiel
zeigt die Halloween-Deko; nach Event-Ende bietet der Server den Rückweg
`104956.Halloween → 104956` an. Im Steam-Modus verweigert der Launcher
Patches („Please update via the Steam client“).

Paket CommunityEventSettings (10, gleiche Versionsnamen) hängt an
`Data/GameplaySettings/settings2.bin` einen `SkuCommunityEvent` (Id 9000) mit
den inaktiven Katalog-SKUs des Events (`patcher.EVENT_SKU_KEYWORDS`); der
Client schaltet SKUs aus SkuCommunityEvents im Zeitfenster frei (so liefen
auch die Daily Deals). Zeiten rechnet der Client in 32 Bit, das Ende muss vor
2038 liegen. Hin- und Rückweg beider Pakete im Launcher bestätigt (15.10.2026:
`104956 → 104956.Halloween → 104956`, Deko und Shop-Artikel kommen und
gehen). Deltas passen nur auf den gemeldeten Stand: Wer Dateien oder
`InstalledPackages.json` von Hand ändert, kann Paketstand und Datei
auseinanderbringen; nach einem misslungenen Patch löscht der Launcher den
Paketeintrag, dann patcht der Server das Paket nicht mehr (Eintrag mit dem
tatsächlichen Stand von Hand nachtragen). Bestätigt für Halloween: Kreaturen-Varianten im Labor und die
vier Barrikaden im Shop. Nicht sichtbar bleiben „Knight Halloween Batwings“
(ShopContext 6) und `Halloween_Theme_2013` (`PrivateTheme`) — Reste von 2013;
das Halloween Pack Oct2014 (Pack 67) enthält genau Kreaturen, Barrikaden und
Thema 6.

**Spiel-Exe und Prüfsummen:** Nach einem Patch prüft der Launcher
(`TaskRepair`) jede Datei gegen `..\GameData\crc\{GameBin,DataBin,
CommunityEventSettings}CRC.json` (CRC32 + Größe). Bei der von Hand
getauschten `MightyQuest.exe` („CRC mismatch!“) findet er kein Paket und
stürzt ab (Nullzeiger 0x4d91a1); ein zweiter Start ging durch. Deshalb
verteilt der Server die Exe selbst: `game_server.py --client-exe <exe>`
liefert Paket GameBin (1, Version `280139.X<CRC32>`) als
`MightyQuest.exe.replace` (Launcher löscht die alte Datei und benennt um,
0x4e2d72; passt also auf jede installierte Exe). Zu jedem geänderten Paket
kommt dessen Prüfsummenliste mit den neuen Werten (GameCRC 9, DataCRC 7,
CommunityEventSettingsCRC 11, gleiche Version, ebenfalls `.replace`). Die
Listen stehen in keinem Archiv; Vorlage sind die einer Steam-Installation
in `server/data/crc/`. Die verteilte Exe baut
`tools/patch_ca.py MightyQuest_profile.exe <Wurzel.pem> --out
MightyQuest_player.exe --no-fps` (eigene CA, FPS-Anzeige aus). Die
UI-Patches (`server/ui_patches.py`) kommen als Paket GameUI (8, Version
`280139.U<CRC32>`, ganze Dateien per `.replace`); GameUI hat keine
Prüfsummenliste. `tools/patch_ui.py` wendet dieselben Patches lokal an.

**Spieler-Setup aus der Steam-Installation** (bestätigt 17.10.2026):
Steam die Installation prüfen/reparieren lassen (setzt auch
`LauncherData/InstalledPackages.json` auf den Steam-Stand zurück, das Depot
enthält sie), `Launcher/PublicLauncherSettings.json` durch die Fassung mit
unseren URLs ersetzen und `website/steam-launcher-patch.cmd` im
Installationsordner ausführen. Danach das Spiel aus Steam starten: der
Patcher bringt Exe, UI-Patches, Daten und Prüfsummenlisten, das Spiel
startet. Für HTTPS mit selbstsigniertem Zertifikat zusätzlich der
`certutil`-Import (s. o.).

**Steam-Modus** (`SteamAPI_Init` erfolgreich, Flag `[Launcher+0x61]`, z. B.
mit `steam_appid.txt` oder Start aus Steam): Der Launcher verdrahtet beim Aufbau
des Zustandsautomaten „Version alt“ (Spiel, Launcher, Reparatur) direkt auf
`TaskExit` (`jne` bei VA 0x4e10a7/0x4e1135/0x4e1225) und zeigt vorher den
Dialog 0x4def05 („Please update via the Steam client“). `steam-launcher-patch.cmd`
(Batch/PowerShell-Hybrid, patcht die Exe des Spielers, keine Ubisoft-Datei
auf der Website) setzt die drei `jne` auf `nop` und 0x4def05 auf `ret`;
seitdem patcht und startet der Launcher auch aus Steam (getestet 19.10.2026).
**Steam-Anmeldung** (`server/steam_auth.py`, Umgebungsvariable
`MQEL_STEAM_API_KEY`, Steam-Web-API-Key): Die Login-Seite hat ein verstecktes
`<form>` (Ziel: versteckter Iframe, `POST /launcher/steam`) und löst nach 0,8 s
ein künstliches `submit` aus; der Steam-Launcher fängt es ab, hängt
`steam_ticket` (Hex, `GetAuthSessionTicket`) an und schickt es ab (ohne Steam
bleibt das Ticket leer, die Seite bleibt still). Der Server prüft das Ticket bei
`ISteamUserAuth/AuthenticateUserTicket` (appid 239220). Bekannte SteamID → sofort
angemeldet. Unbekannte → Beweis (`proof`, 10 min, nur im Speicher): „Als neuer
Steam-Spieler spielen“ legt einen Account ohne Passwort an (Name vom Steam-Profil,
`logins.json`: `SteamId` ohne `Hash`), oder ein Altspieler meldet sich einmal mit
Name + Passwort an und verknüpft damit seinen Account. Ein Account hat höchstens
eine SteamID und umgekehrt. Im Test bestätigt: Ticket kommt an, Steam liefert die
SteamID.

Steam-Achievements setzt die Spiel-Exe selbst (`SteamUserStats`
SetAchievement/StoreStats, `SteamId` in `AchievementSettings.json`): live bei
`AchievementCompleted` und per Abgleich der schon abgeschlossenen; im Test
kamen beim ersten Kampf alle 13 nachträglich.

`server/settings_archive.py` liest/schreibt das Archivformat von
`settings.bin`/`settings2.bin`: verschlüsselt (Schlüsselstrom 0x116ae60)
LZO1X + u32 Größe, darin ein Ordnerbaum aus JSON-Dateien mit CRC32 am Ende.
Änderungen am Dateiende lassen den Anfang Byte für Byte gleich (kleines
xdelta).

Original-Ship-Config (Steam): `LauncherWebSiteUrl`
`https://launcher.themightyquest.com/mqel-live/launcher/load/`, `GameServerUrl`
`https://gs.themightyquest.com/mqel-live.gameserver`, `PatcherServiceUrl`
`https://gs.themightyquest.com/mqel-live.distribution`,
`MaintenanceModeVerificationUrl` `https://launcher.themightyquest.com/mqel-live/launcher/`,
`EnvironmentName` `mqel-live`, `HttpCompression` `true`, Fenster 822×588,
View 9/12 787×552, `TwitterFeedName` `Sir_Painhammer`.

**Ship-Exe braucht https:** Die finale `MightyQuest.exe` vergleicht die
Server-URL mit `"https"` und führt sonst das Skript `Exit` aus (aus dem
Speicher-Dump: Ship-Abbild Basis 0x460000, Prüfung bei 0x7e9b4a,
`strncmp(url, "https", 5)`). Der Server bedient deshalb mit
`--tls-port 8443` zusätzlich HTTPS (selbstsigniertes Zertifikat in
`server/state/tls/`). Das hilft nicht: die Exe vertraut nur eingebetteten
CAs (DigiCert High Assurance EV Root, COMODO RSA, AddTrust) und liest
weder `SSL_CERT_FILE` (OpenSSL-Standardpfade werden nie geladen) noch eine
CA-Datei für curl. Unter diesen Roots stellt heute praktisch niemand mehr
aus. Ohne Eingriff in die (gepackte) Exe läuft sie also nicht; lokal
getestet wird mit `MightyQuest_profile.exe` als `MightyQuest.exe` und
`GameServerUrl` = `http://…:8081`.

**HTTPS mit `MightyQuest_profile.exe`** (getestet 17.10.2026): Die Exe
(libcurl + OpenSSL 1.0.1e, TLS 1.2) setzt bei `https`-URLs
`SSL_VERIFYPEER`/`VERIFYHOST` (0xfe0f89) und lädt ihre vier PEM-Wurzeln
unverpackt aus `.rdata` (0xfe145d ff.). `tools/patch_ca.py` ersetzt eine
davon (Vorgabe: AddTrust) durch ein eigenes Zertifikat, z. B.
`server/state/tls/cert.pem` des Spielservers (`--tls-port 8443`, gilt nur
für dessen IPs). Mit `GameServerUrl` = `https://…:8443` läuft das Spiel
dann verschlüsselt. Der Chat (5222) bleibt Klartext (kein STARTTLS).
Launcher und Bling-Shop (CEF, Chromium Juli 2015) sprechen TLS 1.0/1.1
(der Server erlaubt es, nur ECDHE) und prüfen gegen den
Windows-Zertifikatspeicher: ein selbstsigniertes Zertifikat muss dort
importiert sein (`certutil -addstore -user Root cert.pem`), mit einer
Domain und Let's Encrypt entfällt das (noch ungetestet).

## Bekannte Stolperfallen

- `Data/UI/Js` + `Data/UI/scripts` aus `0.36.1.34.0_280139_GameUI.7z`
  müssen mit entpackt sein, sonst lädt die Lobby endlos (272× 404 im
  `static.log`). `http://localhost/gamedata/` bedient der Client selbst
  (CEF-Handler `CEFClient_Z.cpp` → `../Data`); ein Webserver auf Port 80
  ist nicht nötig (früheres `server/static_server.py` entfernt).
- Daten (GameData 104956) und Exe (Branch Update3) passen nicht exakt
  zusammen (`Unhandled member`-Warnungen u. a. `Spec.IsVisible`,
  `GeneralSettings.*`).
- **Unser Client ist die finale veröffentlichte Version**: byteidentisch zum
  finalen Steam-Depot, gebaut einen Tag vor dessen Freischaltung (Abgleich
  durch den Projektbetreiber, 16.10.2026). Die Server-DLLs aus dem
  GameplayToolbox-Archiv sind fast 17 Monate älter (die Kopie der Toolbox,
  nicht der Live-Server). Belegt durch Build-Nummern (Dateinamen der
  Archive) und die jüngsten Dateidaten darin: Client `280139` (Game/GameUI,
  21.07.2015), Launcher `276072` (22.05.2015), Toolbox `main.348.1_232184`
  (27.02.2014); GameData `104956` zählt eigenständig (17.07.2015); der Server wurde danach weiterentwickelt, der
  finale Client kennt Felder, die dort fehlen (`MineDestroyedTimeBonusCount`,
  `TrophyScoreRestart*`, `LoseTrophyCooldownTimer`,
  `CastleInfoSummary.TrophyCooldownTimer`). Konsequenz: Spielregeln und
  Formeln aus dem Server-Code (dnSpy-Export, lokal in `decompiled/`); bei
  Abweichungen gilt immer der Client (Feldleser im Binary,
  `tools/client_members.py -t`), nicht die Contracts.

## Offene Punkte (Laufzeit erzeugt / zu verifizieren)

- `Config/Synergy/Game.ini` (`ReadGameConfigFile ..\Config\Synergy\Game.ini`
  in `Init_Game.tsc`) ist in keinem Paket — vermutlich generiert oder
  optional. Dynamischer Test zeigt, ob/was fehlt.
- `GameData/Config/Game/{CustomUserSettings,EngineSettings}.json`
  (+ `.bak`) werden zur Laufzeit angelegt.
- `LauncherData/Background.png` (per `BackgroundImageUrl` geladen),
  `LauncherData/Awesomium/` (Browser-Cache) entstehen zur Laufzeit.
- `PublicLauncherSettings.json`-Fensterwerte sind Schätzwerte
  (Template-Platzhalter); ggf. am laufenden Launcher korrigieren.
- Spieler-Setup braucht zusätzlich: DirectX (Installer/Prerequisites),
  VC++ 2010/2012 x86, ggf. Steam-Client für Steam-Tickets.
