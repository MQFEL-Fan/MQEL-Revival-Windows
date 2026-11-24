# Discord announcements: events and patch notes (Cornelius)

Two webhooks, both posting as **Cornelius Richling** with the same picture:
the in-game events channel (`server/discord_events.py`) and the patch-note
channel (`server/discord_patch_notes.py`, below).

`server/discord_events.py` posts to a Discord channel through a webhook
every time an in-game event starts: what it does, when it ends and what the
next event is. Poster: **Cornelius Richling** ("owner, founder and
occasional brochure model" of Cornelius Real Estate and Cornelius' Emporium,
the game's tutorial guide; text and picture from the Mighty Quest wiki,
picture hot-linked from static.wikia.nocookie.net). Footer: "Cornelius Real
Estate · Some settling may occur." (the wiki's fine print).

## Cornelius' voice: random greetings

Every post opens with one of ten greetings, picked at random:
`discord_events.GREETINGS` (event posts) and
`discord_patch_notes.GREETINGS` (patch notes). They follow how he talks in
the game's own tutorial texts (`OASIS_EN.JSON` 13111-13128 and
15428-15439): "buddy", "pally", "chum", "compadre", "hot stuff", "am I
right?", "a promise from your man Cornelius is cash in the bank", "Never
count out old Cornelius", "I extort... ahem, I EXHORT you", his fees,
his self-portraits and "owner, founder and occasional brochure model". The
wiki adds the full name of his shop ("Premium Talent Management & Real
Estate Emporium") and the fine print "Some settling may occur." Add or edit
lines in the lists; the introduction message keeps its fixed text.

## Cornelius' voice: audio clips

Each new post (event start, new news entry) gets one random voice clip of
Cornelius attached; Discord shows it as an audio player under the message.
Edits of a news entry keep the clip of the first post.

- Clips: `server/data/voices/cornelius/*.ogg` (also .mp3/.wav). Empty or
  missing folder = posts without audio. Add or remove files freely, no
  restart needed (the folder is read for every post).
- Where they come from: the game's streaming audio bigfile
  `client/GameData/Data/Sounds/HQAudio/PC/Atomic/STREAMING_AUDIO.BFPC`
  holds 893 Ogg Vorbis streams (mono 24 kHz voice, music, effects) without
  names. `python tools/extract_audio.py <bfpc> <out>` carves them out
  read-only. The game names the Cornelius lines in
  `GeneralSettings/AudioSettings.json` (e.g. "Obj301_PVP Attack_Cornelius",
  `VO_NUE_005_03COR`, sound resource `0008B53A`), but resolving those ids
  to streams needs the packed sound resources, so the clips were found by
  transcribing the short clips with Windows speech recognition
  (`_temp60/transcribe.ps1`, System.Speech) and matching the text against
  his lines in `OASIS_EN.JSON` (`_temp60/match_voice.py`), then listening.
- Clips (2026-11-22, 9 files, 700 KB; matched by recognized words AND by
  voice: `_temp60/voice_rank.py` compares the timbre of every clip with the
  clips the owner confirmed by ear):
  `welcome-to-my-emporium` (Oasis 13113, stream 00783),
  `havent-had-a-client-in-weeks` (13111, 00751),
  `a-few-small-formalities` (13115, retainer and signing fee, 00757),
  `no-better-investment` (13116, 00795),
  `all-this-could-be-yours` (13119, 00775),
  `up-the-ante-on-your-looting` (13121, 00755),
  `much-to-discuss` (13122, 00762),
  `shopping-your-name-around-town` (13123, 00764),
  `you-did-it-homeowner` (13124, 00758).
  Removed by the owner: "Looking good, hot stuff!" (not Cornelius), the
  gold storage and castle heart tour lines (not quotes). His tutorial
  lines sit in streams 00748-00795; the castle-shopping lines (Evening,
  Dusky, Foggy models) are not voiced in this build. More clips with his
  voice but unclear words, to audition: `_temp60/voice_candidates/` (move
  good ones into the folder). The folder is in `.gitignore` (game audio).
- Sending: multipart webhook call (`discord_events.encode`: `payload_json`
  plus `files[0]` named `cornelius.ogg`), limit 10 MB per file (the clips
  are a few hundred KB).

## Discord server icon

`tools/discord_server_icon.ps1` makes the server icon from the launcher art
(`launcher-mockups/source-art.jpg`, the castle with the red dragon cropped
square) with a word in gold Cinzel at the bottom, inside the circle
Discord cuts out: `launcher-mockups/server-icon-reborn.png` (512x512, as
asked) and `server-icon-rebirth.png` (the project's name), each with a
`-preview.png` (48 and 96 px, circle and rounded square on Discord's
dark grey). Upload: Server Settings -> Overview -> server icon.

## Setup

The webhook URL is a secret: anyone who has it can post in the channel.
The server takes the first of:

1. environment `MQEL_DISCORD_WEBHOOK` (e.g. in `server_config.bat`, see
   `server_config.example.bat`)
2. `server/state/<profile>/discord_webhook.json`: `{"url": "https://discord.com/api/webhooks/..."}`

Only `https://discord.com/api/webhooks/...` URLs count. Without one nothing
is posted (and the thread doesn't start). Since 2026-11-22 both URLs are in
preprod's `server_config.bat` (`MQEL_DISCORD_WEBHOOK`,
`MQEL_DISCORD_PATCH_WEBHOOK`); the earlier file
`state/new/discord_webhook.json` was removed. The server only sees them when
it is started with `start_servers.bat` (which calls `server_config.bat`).

Change the channel: Discord channel settings -> Integrations -> Webhooks.
If the URL ever leaks, delete the webhook there and put the new URL in
`server_config.bat` (then restart the server).

## What is announced

The same calendar the game uses (docs/95-preprod-2026-11-22.md):

- boost weekends (monthly, December everything x2) and "More Materials"
  (`community_events.py`)
- hero free trials, day 1-7 of every month (`free_trials.py`)
- Halloween, Christmas, New Year, Valentine's Day, Easter
  (`patcher.EVENTS`, Easter Sunday +- 7 days), whole UTC days

`discord_events.calendar(now)` lists them; `running(now)` and
`next_event(now)` are what the posts use. Times appear as Discord
timestamps (`<t:unix:F>` and relative `<t:unix:R>`), so every reader sees
their own time zone.

## How it runs

- The game server starts a thread at startup (`discord_events.start`) that
  checks once a minute.
- Each event is posted once: posted keys are kept in
  `state/<profile>/announced_events.json` (e.g. `boost:2026112025`,
  `trial:202612015`, `season:Christmas:2026`), so a restart doesn't post
  again. A failed post (network, Discord down) is retried a minute later.
- An event that is already running when the server starts is announced
  then (unless it's in the file).

## The introduction (2026-11-22)

Sent once by hand as the webhook test: Cornelius introduces himself, the
running event (Bling mine boost weekend until 2026-11-23 05:00 UTC) and the
next one (Runaway free trial, 2026-12-01). Discord answered 200. The
running event was then marked as announced so the server won't post it a
second time. To send the introduction again:

```
REM in cmd, from the project folder (the URL comes from server_config.bat)
call server_config.bat
cd server
python -c "import datetime,discord_events as d; n=datetime.datetime.now(datetime.timezone.utc); print(d.post(d.webhook_url('state/new'), d.intro_message(n)))"
```

Tests: `FeatureTest20261122.test_discord_event_announcer` (fake sender, no
network).

## Patch-note channel (`server/discord_patch_notes.py`)

Webhook: `MQEL_DISCORD_PATCH_WEBHOOK` (server_config.bat) or
`state/<profile>/discord_patch_webhook.json`. Same poster and picture as the
events; the greeting: "Attention, castle owners of Opulencia! Cornelius
Richling here, with fresh renovations for every castle in the realm (no
extra charge, this time)." Blue embed, footer "Cornelius Real Estate · Some
settling may occur.", date as the embed timestamp.

**Automatic: the admin tool's News page** (`/admin#news`, AdminService
SaveNews/DeleteNews, `news.News.listener`):

- new entry -> posted to the channel (title, text, "Restart your launcher to
  move right in.")
- entry edited -> its Discord message is edited (posted again if it was
  deleted in Discord)
- entry deleted -> its Discord message is deleted

Message ids: `state/<profile>/discord_news_messages.json` {news id: message
id}. Posting runs in a thread; the admin tool never waits for Discord, and
a failure is only logged (`[discord] News ... nicht gesendet`). Entries that
existed before the webhook are posted when they're next edited, not before.
So the workflow for a patch is: write `PATCH_NOTES.md` and the website card,
then add the short version in the News page: launcher, game players and
Discord get it at once.

**History (sent once, 2026-11-22):** `backfill()` posted the released
sections of `PATCH_NOTES.md` oldest first (7 messages: Bling counter fix ...
Discord status and a new launcher look; "Next update" sections are skipped,
and so are the "Short version" blocks). Marker with the message ids:
`state/new/discord_patch_backfill.json`. Don't run it again unless you
clean the channel first.

Tests: `FeatureTest20261122.test_discord_patch_notes` (fake API, no network).

**Live check (2026-11-22):** preprod server on test ports 18081/18443 with
only `MQEL_DISCORD_PATCH_WEBHOOK` (`_temp60/run_preprod_test.py`), news
entry 9 "Cornelius finds his voice" added through the signed AdminService
like the News page (`_temp60/news_demo.py`): the server posted it by itself
with a random greeting and voice clip (log `[discord] News 9 gesendet`,
message id in `discord_news_messages.json`). The entry is in preprod's
news.json and goes live with the update.
