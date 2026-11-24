# Live co-op: research notes (2026-11-22)

Goal asked for: two to four players in the same castle at the same time,
seeing each other move and fight ("full streaming").

## What the game has

- **Deterministic attacks.** An attack is simulated from the AttackInfo
  (castle, hero, `AttackRandomSeed`) plus the hero's input commands
  (`GameCommandManager`, `SendGameCommand`). Replays store only those
  inputs (LZO, see `server/replays.py`) and the client re-simulates the
  whole fight from them; if castle or hero differ it stops ("The
  determinism has been broken"). That is the foundation lockstep
  multiplayer games use: every game runs the same simulation and only the
  inputs travel.
- **Same castle for a party** already exists (co-op raids, docs/89), and the
  server controls `AttackRandomSeed`, so every member could start from the
  identical state.
- **A way into the game process:** the WASD helper DLL (tools/wasd) runs
  inside MightyQuest.exe, hooks input and has a local endpoint. It could
  carry network traffic between the party's games.

## What is missing

- **Only one hero per simulation.** Nothing in the attack code or data
  knows a second hero: no player ids, no multi-hero lists, the replay
  plays exactly one hero. Showing a friend means creating a second hero
  entity inside the running simulation, giving it the friend's equipment
  and skills, and feeding it the friend's commands every frame.
- **The gameplay code is native and stripped.** MightyQuest.exe (27 MB)
  has 84 RTTI class names, none for heroes, entities, commands or replays;
  the names we know come from log strings and earlier call tracing
  (tools/callfinder.py, cadecode.py). The functions to spawn a hero, read
  and inject commands, and step the simulation would all have to be found
  by reverse engineering.
- **No desync detection.** There is no state checksum; any difference
  (timing, floating point, a missed command) makes the games drift apart
  silently, then loot, deaths and the end of the attack disagree.

## Possible path (if we go for it)

1. **Proof of concept (reverse engineering, the deciding step):** find the
   function that creates the hero from AttackInfo at attack start and call
   it a second time from the DLL. If a second hero can stand in the castle
   without crashing the game, live co-op is possible; if the engine
   assumes one hero everywhere (camera, AI targeting, UI, victory checks),
   it is not realistic.
2. **Drive the second hero:** capture the local hero's commands in the DLL,
   send them through the server (a relay endpoint) to the other members,
   inject them as the remote hero's commands with a small fixed delay
   (lockstep, e.g. 100-150 ms) so all games apply the same inputs on the
   same frame.
3. **Keep games in step:** pause when a member's commands are late; add our
   own checksum (hero positions, creature health) each second and end the
   co-op run cleanly on a mismatch instead of drifting.
4. **Rules:** shared or separate loot (separate is simpler: each game keeps
   the loot its own hero picks up), deaths and resurrection, what happens
   when someone leaves, one EndAttack per member.

**Effort and risk:** step 1 alone is days to weeks of reverse engineering
on a stripped binary with an uncertain outcome; steps 2-4 are weeks more.
Nothing of it can be done from the server or the UI; it is all DLL work
inside the game process, tested with two real games.

## Smaller things that are realistic now

- **Live party panel** (done, docs/89): health, gold, XP, items and
  deaths of the party during a raid.
- **Watch a friend's raid afterwards:** the server already stores replays
  of attacks on player castles; storing raid replays too and adding a
  "watch" button would show the friend's run exactly as it happened.
- **Near-live spectating:** a friend's replay could be uploaded in pieces
  during the fight and watched a little behind, but only as a viewer, not
  playing in the same castle.
