# Original Steam UI files (not included)

`server/ui_patches.py` patches some of the game's original UI files
(CSS, JS and PNG under `Data/UI/...` and `Data/Generated/Web/...`). They are
Ubisoft's files and are not part of this repository.

Extract them from the Steam client's GameUI package
(`0.36.1.34.0_280139_GameUI.7z`) into this folder, keeping the paths, e.g.
`server/data/steam/Data/UI/Js/hyperquest.extensions.js`. Without them the
patches fall back to the files in `client/` (see `original()` in
`ui_patches.py`).
