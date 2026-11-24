# Decoration loot

Status: live 2026-11-22 (needs the launcher update: settings `.L` part).
Code: `server/loot.py` (`decoration_loot`, constants `DECO_*`, `BLING_CRYSTALS`),
`server/attack.py` (StartAttack `DecorationLoot`, EndAttack payout),
`server/level60.py` (`attacker_rewards`: `AllowDecorationLoot` true).

## Rules

| What | Chance | Amount |
|---|---|---|
| Gold or life force (50/50), every decoration except Bling Crystals | 75% per decoration | 20-50% of an average creature drop of that castle (always less than a creature, at least 1) |
| Basic crafting material | 0.4% per decoration (instead of gold/life force) | 1 |
| Bling (green Bling Crystal, decorations 237/238) | 1% per crystal; crystals drop nothing else | 1, at most 2 per attack, within the weekly bling loot cap (`balance` Loot.WeeklyCap, 4000) and only with the bling economy on |

(First version the same day: 30-40% chance, 15-30% of a creature, crystals
also dropped gold.)

No decoration loot in practice/visit attacks, castle validation, tutorial
castles and competitions.

## How it works

- The client spawns loot from `AttackInfo.DecorationLoot`
  (`DefenseIngredientLoot` per decoration Id, like `CreatureLoot`) only when
  `AttackerRewardSettings.AllowDecorationLoot` is true. The original data
  had it false; the level-60 settings edit switches it on, so it ships
  with the DataBin version (players get it from the launcher).
- EndAttack reports what was picked up: `LootedGoldDecorationIds`,
  `LootedLifeForceDecorationIds`, `LootedHeroItemDecorationIds`
  ({ItemId, ItemIndex}); `DestroyedDecorationIds` pays the blings (like
  creature blings on kill). The amounts come from the table stored at
  StartAttack (`session.current["deco_loot"]`/`["deco_items"]`), so the
  client can't claim more. Gold/life force go into TotalGold/
  TotalLifeForce (not KillsGold), blings into the bling loot log.
- Treasure room ratios and stealable mines still use creature loot only.

Tested: simulation over real castles (drop rate 35%, crystal bling 1%),
StartAttack/EndAttack on a copy of the data (payout = drops picked up).

## Fix: decorations need a LootableSpec (2026-11-22, evening)

The first version sent `DecorationLoot` and switched `AllowDecorationLoot`
on, but nothing dropped: the client only spawns loot for entities with a
`LootableSpec` (creatures and traps have one, decorations didn't). The
level-60 settings edit (`level60.decoration_lootable`) adds one to every
`Decorations/*/GAMEPLAY.JSON` (159): drop distance 1-2, radius 0.25, loot
type masks 127 (all types, PVE and PVP castles; traps use 126 for PVP).

## Infinite Pack rings and Extra XP (2026-11-23)

- Infinite XP Ring (template 84243): Extra XP effect level 48 -> 12 (98 % ->
  26 %); Infinite Material Ring (84244): Bonus Random Material level 19 -> 5
  (47.5 % -> 12.5 %): a quarter of the pay-to-win values
  (`level60.INFINITE_RINGS`, shipped with the item templates; owned rings
  are corrected when the account loads, `AccountState._fix_infinite_rings`).
- The server now applies Extra XP from equipment to the attack's XP
  (`attack.end_attack`, `item_drops.EXTRA_XP`); before, only the client
  showed it.
- Hero corpses get ids that never repeat (`HeroCorpseNextId`): a reused id
  left the old corpse's harvest marker on screen.
