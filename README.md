# Finnegans Wake — RIVERRUN (NES)

A playable NES platformer adaptation of *Finnegans Wake*, in original
wording only. No long passages from the book are reproduced — the
adaptation is in structure, not quotation.

## The idea

A dreamer in Dublin, HCE, falls asleep and dreams the book. You play
him through four Vico cycles:

1. **I — The Fall** — HCE falls from his ladder in a dream.
2. **II — The Pub** — the pub keeper pours and listens.
3. **III — The Wash** — the washerwomen talk by the river.
4. **IV — Ricorso** — the end returns to the beginning.

Each level: collect every letter, avoid water and spikes, stomp the
shades (the washer-shades / dream figures), and reach the pub door.
The door stays shut until all letters in the level are collected —
touch it early and you get knocked back with a buzz.

Finish level IV and the game does what the book does: it loops.
**THE WAKE RETURNS / RIVERRUN AGAIN** — back to level I, cycle + 1,
with the shades moving faster. Score and lives carry over.

## What it is

- A real `.nes` file, mapper 0 (NROM), 32 KiB PRG, CHR RAM.
- Single-screen levels, 16×16 player, gravity and jumping, stomp
  vs. side-hit enemy rules, lives, score, HUD (level, cycle, score,
  lives, letters, door OPEN/SHUT).
- All graphics are original tiles drawn in code. All sound is
  synthesised live by the NES APU (jump, pickup, stomp, death, door,
  buzz). No samples, no copyrighted ROMs.

## Controls (standard NES controller)

- D-pad Left / Right: move
- A: jump (only from the ground)
- Start: start the game, advance a level/cycle card early
- Level cards advance on their own after about 3 seconds if you
  don't press Start.

## Scoring

- Letter: +100
- Stomped shade: +200
- Level clear (reaching an open door): +500

## How to run it

1. Build (or rebuild) the ROM:
   ```
   python3 build_wake.py
   ```
   This writes `finnegans-wake.nes` in this folder. No cc65 needed —
   `assembler.py` contains the minimal two-pass 6502 assembler
   copied from the earlier NES drum-machine build.
2. Open `finnegans-wake.nes` in a standard NES emulator, for example
   FCEUX, Mesen, or Delta on iPhone. Load it as a normal mapper 0 /
   NROM ROM; no special settings are needed. CHR RAM is used, so
   the header CHR size is 0 and the tiles are uploaded by the code
   at startup.
3. Press Start on the title screen.

## Files

- `build_wake.py` — level data, tile art, strings, and the full
  6502 game source; running it writes the ROM and validates the
  header, size, and vectors.
- `assembler.py` — the two-pass 6502 assembler (labels, `.byte` /
  `.word`, and the opcodes and addressing modes this code uses).
- `finnegans-wake.nes` — the built ROM (32,784 bytes: 16-byte iNES
  header + 32,768 bytes PRG).
- `README.md` — this file.

## Verification — read honestly

- Built cleanly, no unresolved labels. Header, size, and vectors
  checked by `build_wake.py`: iNES magic, PRG 2 × 16 KiB, CHR 0
  (CHR RAM), mapper 0, vectors in PRG range.
- Level maps checked by script: door tiles in place, ground/pit/
  platform/spike tiles as designed, every collectible sits above a
  platform or the ground, no enemy patrol crosses a water pit, and
  a surface-reachability pass (jump rise 45 px, horizontal jump
  about 36 px) reaches every platform in all four levels.
- **Not yet played in a real emulator.** No NES emulator was
  available in the build environment, so this ROM is validated by
  assembly and by those map checks, not by a playthrough. Load it
  in Delta and smoke-test first: title → Start → level card →
  move/jump, collect a letter, stomp a shade, touch the shut door,
  clear level I, and confirm the HUD updates. If anything glitches
  there, tell me what you saw and I'll fix that build — don't treat
  it as finished until Delta says so.

## Status

Published Oct 28, 2026 to the public GitHub repo
https://github.com/yyre4/finnegans-wake-nes (main branch, no GitHub
Pages — this is a NES ROM, not a web page). The XOX Tracker remains
unpublished; that approval was for this Finnegans Wake ROM only.
