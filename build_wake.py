#!/usr/bin/env python3
"""Build FINNEGANS WAKE - RIVERRUN, a playable NES platformer.

A video-game adaptation of Finnegans Wake, in original wording only:
no long passages from the book are reproduced. The adaptation is in
structure, not quotation: a dreamer in Dublin, four Vico cycles
(The Fall / The Pub / The Wash / Ricorso), washer-shades as enemies,
letters to collect, a pub door to reach, and a ending that loops
straight back to the beginning - the next cycle, harder.

Mapper 0 (NROM), 32 KiB PRG, CHR RAM. No cc65 needed: the 6502
assembler lives in assembler.py, copied from the earlier NES drum
machine build. No samples, no copyrighted ROMs, all graphics and
sound are original and synthesised live by the NES APU.

Controls: D-pad move, A jump, Start start / advance cards.
Stomp a shade to defeat it, avoid water and spikes, collect every
letter in the level to open the door, reach the door to clear it.
After level IV the game loops to level I with cycle + 1.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from assembler import (assemble, AsmError, TILE_INDEX, font_tiles_bytes,
                       fmt_bytes, tiles_for)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "finnegans-wake.nes")

# ---------------------------------------------------------------- tiles
# Tile indices after the 46 font tiles (0-45):
# 46 block, 47 brick, 48 water, 49 spike, 50-53 door 2x2,
# 54-57 player 2x2, 58 enemy, 59 gem
T_BLOCK, T_BRICK, T_WATER, T_SPIKE = 46, 47, 48, 49
T_DOOR_TL, T_DOOR_TR, T_DOOR_BL, T_DOOR_BR = 50, 51, 52, 53
T_P_TL, T_P_TR, T_P_BL, T_P_BR = 54, 55, 56, 57
T_ENEMY, T_GEM = 58, 59


def tile(p0, p1=None):
    """p0/p1: 8 strings of 8 chars, '#' = bit set."""
    def plane(rows):
        out = []
        for r in rows:
            b = 0
            for i, ch in enumerate(r):
                if ch == '#':
                    b |= 1 << (7 - i)
            out.append(b)
        return out
    out = plane(p0)
    out += plane(p1) if p1 is not None else [0] * 8
    return out


CUSTOM_TILES = []
CUSTOM_TILES += tile(
    ["########", "########", "########", "########",
     "########", "########", "########", "########"],
    ["#.#.#.#.", ".#.#.#.#", "#.#.#.#.", ".#.#.#.#",
     "#.#.#.#.", ".#.#.#.#", "#.#.#.#.", ".#.#.#.#"])
CUSTOM_TILES += tile(
    ["########", "#..#..#.", "#..#..#.", "########",
     "..#..#..", "..#..#..", "########", "........"])
CUSTOM_TILES += tile(
    ["........", "........", ".#.#.#.#", "#.#.#.#.",
     ".#.#.#.#", "#.#.#.#.", "........", "........"],
    ["........", ".#.#.#.#", "........", "........",
     ".#.#.#.#", "........", "........", "........"])
_spike = ["...##...", "..####..", ".######.", "########",
          "........", "........", "........", "........"]
CUSTOM_TILES += tile(_spike, _spike)
CUSTOM_TILES += tile(
    ["########", "#.......", "#.......", "#.......",
     "#.......", "#.......", "#.......", "#......."])
CUSTOM_TILES += tile(
    ["########", ".......#", ".......#", ".......#",
     ".......#", ".......#", ".......#", ".......#"])
CUSTOM_TILES += tile(
    ["#.......", "#.......", "#.......", "#.......",
     "#.......", "#.......", "#.......", "########"])
CUSTOM_TILES += tile(
    [".......#", ".......#", ".......#", ".......#",
     ".......#", ".......#", ".......#", "########"])

# Player 16x16 silhouette, split into 4 tiles. Hat rows get plane 1
# (red hat in the sprite palette, white body).
PLAYER_ART = [
    "....######......",
    "...########.....",
    "...########.....",
    "....######......",
    "....######......",
    ".....####.......",
    "....########....",
    "...##########...",
    "...##########...",
    "....########....",
    "....########....",
    "....###..###....",
    "....###..###....",
    "....###..###....",
    "...####..####...",
    "................",
]


def split_player():
    tiles = []
    for ty in (0, 1):
        for tx in (0, 1):
            p0, p1 = [], []
            for ry in range(8):
                row = PLAYER_ART[ty * 8 + ry][tx * 8:tx * 8 + 8]
                p0.append(row)
                # hat: rows 0-2 of the whole figure
                if ty == 0 and ry < 3:
                    p1.append(row)
                else:
                    p1.append("........")
            tiles.append(tile(p0, p1))
    # split_player order is TL, TR, BL, BR - matches T_P_* order
    return tiles


# The loop above yields TL, TR, BL, BR in that order.
for _t in split_player():
    CUSTOM_TILES += _t
CUSTOM_TILES += tile(
    ["..####..", ".######.", "########", "##.##.##",
     "########", ".######.", "..####..", "........"])
CUSTOM_TILES += tile(
    ["...##...", "..####..", ".######.", "########",
     ".######.", "..####..", "...##...", "........"])

CHR_BYTES = font_tiles_bytes() + CUSTOM_TILES
assert len(CHR_BYTES) == 60 * 16, len(CHR_BYTES)

PALETTE = [
    0x0F, 0x30, 0x27, 0x16, 0x0F, 0x30, 0x2A, 0x16,
    0x0F, 0x30, 0x27, 0x16, 0x0F, 0x30, 0x27, 0x16,
    0x0F, 0x30, 0x27, 0x16, 0x0F, 0x2A, 0x30, 0x16,
    0x0F, 0x28, 0x30, 0x27, 0x0F, 0x30, 0x27, 0x16,
]

# ---------------------------------------------------------------- levels
# Map rows are 0-27, screen rows are map row + 2 (rows 0-1 are the HUD).
# Ground is map row 27. Platforms are map row 22 or 23 only, so every
# platform is reachable from the ground with the -9 jump (45 px rise).
# Door is always map cols 29-30, rows 25-26, standing on the ground.
# Collectibles are one map row above a platform, or on the ground.
# Enemies walk on the ground only.


def make_map(pits, platforms, spikes):
    grid = [[' '] * 32 for _ in range(28)]
    for c in range(32):
        grid[27][c] = '~' if c in pits else '#'
    for (r, c0, c1) in platforms:
        for c in range(c0, c1 + 1):
            grid[r][c] = '='
    for c in spikes:
        grid[26][c] = '^'
    return grid


def map_bytes(grid, door_col=29, door_row=25):
    out = []
    for r in range(28):
        for c in range(32):
            ch = grid[r][c]
            if r == door_row and c == door_col:
                out.append(T_DOOR_TL)
            elif r == door_row and c == door_col + 1:
                out.append(T_DOOR_TR)
            elif r == door_row + 1 and c == door_col:
                out.append(T_DOOR_BL)
            elif r == door_row + 1 and c == door_col + 1:
                out.append(T_DOOR_BR)
            elif ch == '#':
                out.append(T_BLOCK)
            elif ch == '=':
                out.append(T_BRICK)
            elif ch == '~':
                out.append(T_WATER)
            elif ch == '^':
                out.append(T_SPIKE)
            else:
                out.append(0)
    assert len(out) == 28 * 32
    return out


LEVELS = [
    dict(name="I  THE FALL",
         desc=["HCE FALLS FROM", "HIS LADDER IN A DREAM"],
         pits=[10, 11, 20, 21], spikes=[18],
         platforms=[(22, 4, 7), (22, 13, 16), (22, 24, 27)],
         coll=[(5, 21), (14, 21), (25, 21), (28, 26)],
         enemies=[(3, 2, 9), (15, 12, 19), (23, 22, 27)]),
    dict(name="II  THE PUB",
         desc=["THE PUB KEEPER", "POURS AND LISTENS"],
         pits=[8, 9, 17, 25], spikes=[16, 24],
         platforms=[(23, 3, 6), (22, 11, 14), (23, 19, 22)],
         coll=[(4, 22), (12, 21), (20, 22), (28, 26)],
         enemies=[(3, 2, 7), (12, 10, 16), (26, 26, 28)]),
    dict(name="III  THE WASH",
         desc=["THE WASHERWOMEN", "TALK BY THE RIVER"],
         pits=[6, 7, 14, 15, 22, 23], spikes=[10, 19],
         platforms=[(22, 5, 8), (22, 13, 16), (22, 21, 24)],
         coll=[(6, 21), (14, 21), (22, 21), (28, 26)],
         enemies=[(3, 2, 5), (11, 9, 13), (19, 17, 21)]),
    dict(name="IV  RICORSO",
         desc=["THE END RETURNS", "TO THE BEGINNING"],
         pits=[5, 12, 19, 26], spikes=[9, 16, 23],
         platforms=[(22, 2, 4), (22, 8, 11), (22, 15, 18), (22, 23, 26)],
         coll=[(3, 21), (9, 21), (16, 21), (24, 21)],
         enemies=[(2, 2, 4), (10, 8, 11), (20, 20, 25)]),
]

LEVEL_MAP_BYTES = []
for _lv in LEVELS:
    LEVEL_MAP_BYTES += map_bytes(
        make_map(_lv["pits"], _lv["platforms"], _lv["spikes"]))

# Enemy data per level: count byte, then 3 x (start_col, min_col, max_col)
ENEMY_BYTES = []
for _lv in LEVELS:
    ENEMY_BYTES.append(len(_lv["enemies"]))
    for _e in _lv["enemies"]:
        ENEMY_BYTES += list(_e)
    for _i in range(3 - len(_lv["enemies"])):
        ENEMY_BYTES += [0, 0, 0]
# Coll data per level: count byte, then 4 x (col, map_row)
COLL_BYTES = []
for _lv in LEVELS:
    COLL_BYTES.append(len(_lv["coll"]))
    for _c in _lv["coll"]:
        COLL_BYTES += list(_c)
    for _i in range(4 - len(_lv["coll"])):
        COLL_BYTES += [0, 0]

# ---------------------------------------------------------------- strings
# Every string becomes a tile-index byte string terminated by $FF.
STRINGS = []  # (label, text)


def add_str(text):
    label = "str_%d" % len(STRINGS)
    STRINGS.append((label, text))
    return label


def write_str_asm(label, row, col):
    off = row * 32 + col
    hi = 0x20 + (off >> 8)
    lo = off & 0xFF
    return (
        "  LDA #<%s\n  STA ptr_lo\n  LDA #>%s\n  STA ptr_hi\n"
        "  LDA #$%02X\n  STA ppu_hi\n  LDA #$%02X\n  STA ppu_lo\n"
        "  JSR WriteStr\n" % (label, label, hi, lo))


def centred(text, row):
    col = max(0, (32 - len(text)) // 2)
    return write_str_asm(add_str(text), row, col)


# Title screen
TITLE_CODE = ""
TITLE_CODE += centred("FINNEGANS WAKE", 4)
TITLE_CODE += centred("RIVERRUN", 6)
TITLE_CODE += centred("A DREAM IN DUBLIN", 8)
TITLE_CODE += centred("HELP HCE WAKE", 10)
TITLE_CODE += centred("AND WAKE AGAIN", 11)
TITLE_CODE += centred("PRESS START", 14)
TITLE_CODE += centred("D PAD MOVE  A JUMP", 17)
TITLE_CODE += centred("COLLECT LETTERS", 18)
TITLE_CODE += centred("STOMP SHADES", 19)
TITLE_CODE += centred("REACH THE DOOR", 20)

GAMEOVER_CODE = ""
GAMEOVER_CODE += centred("GAME OVER", 8)
GAMEOVER_CODE += centred("THE DREAMER SLEEPS", 10)
GAMEOVER_CODE += centred("PRESS START", 14)

CYCLE_CODE = ""
CYCLE_CODE += centred("THE WAKE RETURNS", 6)
CYCLE_CODE += centred("RIVERRUN AGAIN", 8)
CYCLE_CODE += centred("PRESS START", 14)

# Level cards, one block per level, each ending in a jump to CardCommon.
CARD_BLOCKS = ""
for _i, _lv in enumerate(LEVELS):
    _code = centred(_lv["name"], 4)
    _code += centred(_lv["desc"][0], 6)
    _code += centred(_lv["desc"][1], 7)
    # LEVEL digit: WriteStr for "LEVEL" then the digit tile follows
    # automatically at the next PPU address.
    _code += write_str_asm(add_str("LEVEL"), 10, 13)
    _code += "  LDA level_idx\n  CLC\n  ADC #$1C\n  STA $2007\n"
    _code += write_str_asm(add_str("CYCLE"), 11, 13)
    _code += "  LDA cycle_num\n  CLC\n  ADC #$1B\n  STA $2007\n"
    CARD_BLOCKS += "DrawCard%d:\n%s  JMP CardCommon\n" % (_i, _code)

CARD_COMMON = ""
CARD_COMMON += centred("COLLECT LETTERS", 14)
CARD_COMMON += centred("REACH THE DOOR", 15)
CARD_COMMON += centred("PRESS START", 18)

# HUD static rows. '?' marks a digit/status position written by NMI.
HUD_ROW0_TMPL = "LV? CY? SCORE ?????"
HUD_ROW1_TMPL = "LIFE ? LET ?/? DOOR ????"
HUD_ROW0 = HUD_ROW0_TMPL.replace("?", " ").rstrip()
HUD_ROW1 = HUD_ROW1_TMPL.replace("?", " ").rstrip()
HUD_LVL_COL = HUD_ROW0_TMPL.index("?", 0)
# positions, computed so the ASM below cannot drift from the strings
HUD_CYC_COL = HUD_ROW0_TMPL.index("?", HUD_LVL_COL + 1)
HUD_SCORE_COL = HUD_ROW0_TMPL.index("?????")
HUD_LIFE_COL = HUD_ROW1_TMPL.index("?")
HUD_COLL_COL = HUD_ROW1_TMPL.index("?", HUD_LIFE_COL + 1)
HUD_TOT_COL = HUD_ROW1_TMPL.index("?", HUD_COLL_COL + 1)
HUD_DOOR_COL = HUD_ROW1_TMPL.index("????")


def hud_addr(row, col):
    return 0x2000 + row * 32 + col


HUD_CODE = write_str_asm(add_str(HUD_ROW0), 0, 0)
HUD_CODE += write_str_asm(add_str(HUD_ROW1), 1, 0)

# Digit tile for a decimal digit d is 27 + d (font order: blank, A-Z, 0-9).
# Level digit in the card uses 28 + level (level 0 shows "1"): the card
# code above adds $1C (28) to a 0-based level index, giving tile 28..31
# for digits 1..4. Cycle adds $1B (27) to a 1-based cycle number.

# ---------------------------------------------------------------- ASM
ASM_TEMPLATE = r'''
  .org $0000
ptr_lo: .res 1
ptr_hi: .res 1
ppu_hi: .res 1
ppu_lo: .res 1
tmp_lo: .res 1
tmp_hi: .res 1
tmp2: .res 1
tmp3: .res 1
tmp4: .res 1
tmp5: .res 1
idx_lo: .res 1
idx_hi: .res 1
frame_cnt: .res 1
state: .res 1
level_idx: .res 1
cycle_num: .res 1
lives: .res 1
letters_col: .res 1
letters_total: .res 1
door_open: .res 1
door_cool: .res 1
score_lo: .res 1
score_hi: .res 1
score_d0: .res 5
player_x: .res 1
player_y: .res 1
player_vy: .res 1
player_ground: .res 1
player_dir: .res 1
invuln: .res 1
card_timer: .res 1
btn_cur: .res 1
btn_prev: .res 1
btn_press: .res 1
hud_dirty: .res 1
vblank_flag: .res 1
door_x: .res 1
door_y: .res 1
start_x: .res 1
start_y: .res 1
enemy_count: .res 1
coll_count: .res 1
move_speed: .res 1
tile_col: .res 1
tile_row: .res 1
tile_val: .res 1
check_x: .res 1
check_y: .res 1
place_lo: .res 1
place_hi: .res 1
sub_lo: .res 1
sub_hi: .res 1
spr_idx: .res 1
spr_y: .res 1
spr_tile: .res 1
spr_attr: .res 1
spr_x: .res 1
loop_idx: .res 1
coll_idx: .res 1
enemy_idx: .res 1

  .org $0300
level_map: .res 896
  .org $0680
enemy_x: .res 3
enemy_y: .res 3
enemy_dir: .res 3
enemy_alive: .res 3
enemy_min: .res 3
enemy_max: .res 3
coll_x: .res 4
coll_y: .res 4
coll_alive: .res 4

  .org $8000
Reset:
  SEI
  CLD
  LDX #$FF
  TXS
  LDA #$00
  STA $2000
  STA $2001
  STA $4015
  STA $4010
  LDA #$40
  STA $4017
  JSR WaitVBlank
  JSR WaitVBlank
  JSR ClearRAM
  LDA #$00
  STA $2006
  STA $2006
  JSR UploadCHR
  JSR LoadPalette
  JSR DrawTitle
  LDA #$80
  STA $2000
  LDA #$1E
  STA $2001
  LDA #$00
  STA state
MainLoop:
  LDA vblank_flag
  BEQ MainLoop
  LDA #$00
  STA vblank_flag
  LDA state
  CMP #$00
  BNE SkipTitle
  JMP TitleUpdate
SkipTitle:
  CMP #$01
  BNE SkipPlay
  JMP PlayUpdate
SkipPlay:
  CMP #$02
  BNE SkipCard
  JMP CardUpdate
SkipCard:
  CMP #$03
  BNE SkipOver
  JMP GameOverUpdate
SkipOver:
  CMP #$04
  BNE SkipCycle
  JMP CycleUpdate
SkipCycle:
  JMP MainLoop

TitleUpdate:
  JSR PollController
  LDA btn_press
  AND #$10
  BNE TitleGo
  JMP MainLoop
TitleGo:
  LDA #$00
  STA level_idx
  LDA #$01
  STA cycle_num
  LDA #$03
  STA lives
  LDA #$00
  STA score_lo
  STA score_hi
  JSR ConvertScore
  JSR DrawCard
  LDA #$02
  STA state
  LDA #$B4
  STA card_timer
  JMP MainLoop

CardUpdate:
  JSR PollController
  LDA card_timer
  BEQ CardGo
  DEC card_timer
  LDA btn_press
  AND #$10
  BNE CardGo
  JMP MainLoop
CardGo:
  JSR LoadLevel
  LDA #$01
  STA state
  JMP MainLoop

CycleUpdate:
  JSR PollController
  LDA card_timer
  BEQ CycleGo
  DEC card_timer
  LDA btn_press
  AND #$10
  BNE CycleGo
  JMP MainLoop
CycleGo:
  JSR DrawCard
  LDA #$02
  STA state
  LDA #$B4
  STA card_timer
  JMP MainLoop

GameOverUpdate:
  JSR PollController
  LDA btn_press
  AND #$10
  BNE GameOverGo
  JMP MainLoop
GameOverGo:
  JSR DrawTitle
  LDA #$00
  STA state
  JMP MainLoop

PlayUpdate:
  JSR PollController
  JSR HandlePlayInput
  JSR UpdatePhysics
  LDA state
  CMP #$01
  BEQ PlayCont1
  JMP MainLoop
PlayCont1:
  JSR UpdateEnemies
  JSR CheckHazards
  LDA state
  CMP #$01
  BEQ PlayCont2
  JMP MainLoop
PlayCont2:
  JSR CheckColls
  JSR CheckEnemies
  LDA state
  CMP #$01
  BEQ PlayCont3
  JMP MainLoop
PlayCont3:
  JSR CheckDoor
  JSR CheckFall
  LDA state
  CMP #$01
  BEQ PlayCont4
  JMP MainLoop
PlayCont4:
  LDA invuln
  BEQ PlayNoInv
  DEC invuln
PlayNoInv:
  LDA door_cool
  BEQ PlayNoCool
  DEC door_cool
PlayNoCool:
  JSR BuildSprites
  JMP MainLoop

WaitVBlank:
  LDA $2002
  BPL WaitVBlank
  RTS

ResetScroll:
  LDA $2002
  LDA #$00
  STA $2005
  STA $2005
  RTS

HideSprites:
  LDA #$FF
  LDX #$00
HideSpritesLoop:
  STA $0200,X
  INX
  BNE HideSpritesLoop
  RTS

ClearRAM:
  LDA #$00
  LDX #$00
ClearRAMLoop:
  STA $0000,X
  STA $0200,X
  STA $0300,X
  STA $0400,X
  STA $0500,X
  STA $0600,X
  STA $0700,X
  INX
  BNE ClearRAMLoop
  RTS

UploadCHR:
  LDA #<chr_tiles
  STA ptr_lo
  LDA #>chr_tiles
  STA ptr_hi
  LDA #$C0
  STA idx_lo
  LDA #$03
  STA idx_hi
  LDY #$00
UploadLoop:
  LDA idx_lo
  ORA idx_hi
  BEQ UploadDone
  LDA (ptr_lo),Y
  STA $2007
  INC ptr_lo
  BNE UploadNoHi
  INC ptr_hi
UploadNoHi:
  LDA idx_lo
  SEC
  SBC #$01
  STA idx_lo
  LDA idx_hi
  SBC #$00
  STA idx_hi
  JMP UploadLoop
UploadDone:
  RTS

ClearNametable:
  LDA #$20
  STA $2006
  LDA #$00
  STA $2006
  LDA #$00
  LDX #$04
  LDY #$00
ClearNTLoop:
  STA $2007
  INY
  BNE ClearNTLoop
  DEX
  BNE ClearNTLoop
  RTS

LoadPalette:
  LDA #$3F
  STA $2006
  LDA #$00
  STA $2006
  LDX #$00
PalLoop:
  LDA palette_data,X
  STA $2007
  INX
  CPX #$20
  BNE PalLoop
  RTS

WriteStr:
  LDA ppu_hi
  STA $2006
  LDA ppu_lo
  STA $2006
  LDY #$00
WriteStrLoop:
  LDA (ptr_lo),Y
  CMP #$FF
  BEQ WriteStrDone
  STA $2007
  INY
  JMP WriteStrLoop
WriteStrDone:
  RTS

DrawTitle:
  LDA #$00
  STA $2000
  STA $2001
  JSR HideSprites
  JSR ClearNametable
@@TITLE_CODE@@
  JSR ResetScroll
  LDA #$80
  STA $2000
  LDA #$1E
  STA $2001
  RTS

DrawGameOver:
  LDA #$00
  STA $2000
  STA $2001
  JSR HideSprites
  JSR ClearNametable
@@GAMEOVER_CODE@@
  JSR ResetScroll
  LDA #$80
  STA $2000
  LDA #$1E
  STA $2001
  RTS

DrawCycleCard:
  LDA #$00
  STA $2000
  STA $2001
  JSR HideSprites
  JSR ClearNametable
@@CYCLE_CODE@@
  JSR ResetScroll
  LDA #$80
  STA $2000
  LDA #$1E
  STA $2001
  RTS

DrawCard:
  LDA #$00
  STA $2000
  STA $2001
  JSR HideSprites
  JSR ClearNametable
  LDA level_idx
  CMP #$00
  BNE SkipCard0
  JMP DrawCard0
SkipCard0:
  CMP #$01
  BNE SkipCard1
  JMP DrawCard1
SkipCard1:
  CMP #$02
  BNE SkipCard2
  JMP DrawCard2
SkipCard2:
  JMP DrawCard3
@@CARD_BLOCKS@@
CardCommon:
@@CARD_COMMON@@
  JSR ResetScroll
  LDA #$80
  STA $2000
  LDA #$1E
  STA $2001
  RTS

PollController:
  LDA #$01
  STA $4016
  LDA #$00
  STA $4016
  LDA #$00
  STA btn_cur
  LDX #$08
PollLoop:
  LDA $4016
  AND #$01
  STA tmp_lo
  ASL btn_cur
  LDA tmp_lo
  ORA btn_cur
  STA btn_cur
  DEX
  BNE PollLoop
  LDA btn_prev
  EOR #$FF
  AND btn_cur
  STA btn_press
  LDA btn_cur
  STA btn_prev
  RTS

ConvertScore:
  LDA score_lo
  STA sub_lo
  LDA score_hi
  STA sub_hi
  LDX #$00
ConvPlace:
  LDA score_place_lo,X
  STA place_lo
  LDA score_place_hi,X
  STA place_hi
  LDA #$00
  STA tmp2
ConvSub:
  LDA sub_hi
  CMP place_hi
  BCC ConvStore
  BNE ConvDoSub
  LDA sub_lo
  CMP place_lo
  BCC ConvStore
ConvDoSub:
  SEC
  LDA sub_lo
  SBC place_lo
  STA sub_lo
  LDA sub_hi
  SBC place_hi
  STA sub_hi
  INC tmp2
  JMP ConvSub
ConvStore:
  LDA tmp2
  STA score_d0,X
  INX
  CPX #$05
  BNE ConvPlace
  RTS

WriteHud:
  LDA #$20
  STA $2006
  LDA #$02
  STA $2006
  LDA level_idx
  CLC
  ADC #$1C
  STA $2007
  LDA #$20
  STA $2006
  LDA #$06
  STA $2006
  LDA cycle_num
  CLC
  ADC #$1B
  STA $2007
  LDA #$20
  STA $2006
  LDA #$0E
  STA $2006
  LDX #$00
HudScoreLoop:
  LDA score_d0,X
  CLC
  ADC #$1B
  STA $2007
  INX
  CPX #$05
  BNE HudScoreLoop
  LDA #$20
  STA $2006
  LDA #$25
  STA $2006
  LDA lives
  CLC
  ADC #$1B
  STA $2007
  LDA #$20
  STA $2006
  LDA #$2B
  STA $2006
  LDA letters_col
  CLC
  ADC #$1B
  STA $2007
  LDA #$20
  STA $2006
  LDA #$2D
  STA $2006
  LDA letters_total
  CLC
  ADC #$1B
  STA $2007
  LDA #$20
  STA $2006
  LDA #$34
  STA $2006
  LDA door_open
  BEQ HudDoorShut
  LDA #<door_open_str
  STA ptr_lo
  LDA #>door_open_str
  STA ptr_hi
  JMP HudDoorWrite
HudDoorShut:
  LDA #<door_shut_str
  STA ptr_lo
  LDA #>door_shut_str
  STA ptr_hi
HudDoorWrite:
  LDY #$00
HudDoorLoop:
  LDA (ptr_lo),Y
  STA $2007
  INY
  CPY #$04
  BNE HudDoorLoop
  JSR ResetScroll
  RTS
'''

# Note: HUD addresses above are for the templates defined earlier.
# Row0: level at col 2 ($2002), cycle at col 6 ($2006), score at
# col 14-18 ($200E-$2012). Row1: lives col 5 ($2025), collected
# col 11 ($202B), total col 13 ($202D), door col 20-23 ($2034-$2037).

ASM_TEMPLATE += r'''
LoadLevel:
  LDA #$00
  STA $2000
  STA $2001
  JSR CopyLevelMap
  JSR LoadEnemies
  JSR LoadColls
  LDA #$08
  STA start_x
  LDA #$D8
  STA start_y
  LDA #$E8
  STA door_x
  LDA #$D8
  STA door_y
  LDA start_x
  STA player_x
  LDA start_y
  STA player_y
  LDA #$00
  STA player_vy
  LDA #$01
  STA player_ground
  STA player_dir
  STA letters_col
  STA door_open
  STA door_cool
  STA invuln
  LDA coll_count
  STA letters_total
  JSR ClearNametable
@@HUD_CODE@@
  LDA #$20
  STA $2006
  LDA #$40
  STA $2006
  LDA #<level_map
  STA ptr_lo
  LDA #>level_map
  STA ptr_hi
  LDA #$80
  STA idx_lo
  LDA #$03
  STA idx_hi
  LDY #$00
LoadMapLoop:
  LDA idx_lo
  ORA idx_hi
  BEQ LoadMapDone
  LDA (ptr_lo),Y
  STA $2007
  INC ptr_lo
  BNE LoadMapNoHi
  INC ptr_hi
LoadMapNoHi:
  LDA idx_lo
  SEC
  SBC #$01
  STA idx_lo
  LDA idx_hi
  SBC #$00
  STA idx_hi
  JMP LoadMapLoop
LoadMapDone:
  LDA #$23
  STA $2006
  LDA #$C0
  STA $2006
  LDX #$40
  LDA #$00
LoadAttrLoop:
  STA $2007
  DEX
  BNE LoadAttrLoop
  JSR ConvertScore
  LDA #$01
  STA hud_dirty
  JSR ResetScroll
  LDA #$80
  STA $2000
  LDA #$1E
  STA $2001
  RTS

CopyLevelMap:
  LDA #<level_maps
  STA ptr_lo
  LDA #>level_maps
  STA ptr_hi
  LDX level_idx
  BEQ CopyMapSrcDone
CopyMapSrcLoop:
  CLC
  LDA ptr_lo
  ADC #$80
  STA ptr_lo
  LDA ptr_hi
  ADC #$03
  STA ptr_hi
  DEX
  BNE CopyMapSrcLoop
CopyMapSrcDone:
  LDA #<level_map
  STA tmp_lo
  LDA #>level_map
  STA tmp_hi
  LDA #$80
  STA idx_lo
  LDA #$03
  STA idx_hi
  LDY #$00
CopyMapLoop:
  LDA idx_lo
  ORA idx_hi
  BEQ CopyMapDone
  LDA (ptr_lo),Y
  STA (tmp_lo),Y
  INC ptr_lo
  BNE CopyMapNoHi
  INC ptr_hi
CopyMapNoHi:
  INC tmp_lo
  BNE CopyMapNoHi2
  INC tmp_hi
CopyMapNoHi2:
  LDA idx_lo
  SEC
  SBC #$01
  STA idx_lo
  LDA idx_hi
  SBC #$00
  STA idx_hi
  JMP CopyMapLoop
CopyMapDone:
  RTS

LoadEnemies:
  LDA #<enemy_data
  STA ptr_lo
  LDA #>enemy_data
  STA ptr_hi
  LDX level_idx
  BEQ LoadEnSrcDone
LoadEnSrcLoop:
  CLC
  LDA ptr_lo
  ADC #$0A
  STA ptr_lo
  LDA ptr_hi
  ADC #$00
  STA ptr_hi
  DEX
  BNE LoadEnSrcLoop
LoadEnSrcDone:
  LDY #$00
  LDA (ptr_lo),Y
  STA enemy_count
  LDX #$00
LoadEnLoop:
  CPX enemy_count
  BNE LoadEnGo
  JMP LoadEnDone
LoadEnGo:
  TXA
  STA tmp2
  ASL
  CLC
  ADC tmp2
  CLC
  ADC #$01
  TAY
  LDA (ptr_lo),Y
  ASL
  ASL
  ASL
  STA enemy_x,X
  LDA #$D8
  STA enemy_y,X
  LDA #$01
  STA enemy_dir,X
  STA enemy_alive,X
  INY
  LDA (ptr_lo),Y
  ASL
  ASL
  ASL
  STA enemy_min,X
  INY
  LDA (ptr_lo),Y
  ASL
  ASL
  ASL
  STA enemy_max,X
  INX
  JMP LoadEnLoop
LoadEnDone:
  RTS

LoadColls:
  LDA #<coll_data
  STA ptr_lo
  LDA #>coll_data
  STA ptr_hi
  LDX level_idx
  BEQ LoadCoSrcDone
LoadCoSrcLoop:
  CLC
  LDA ptr_lo
  ADC #$09
  STA ptr_lo
  LDA ptr_hi
  ADC #$00
  STA ptr_hi
  DEX
  BNE LoadCoSrcLoop
LoadCoSrcDone:
  LDY #$00
  LDA (ptr_lo),Y
  STA coll_count
  LDX #$00
LoadCoLoop:
  CPX coll_count
  BNE LoadCoGo
  JMP LoadCoDone
LoadCoGo:
  TXA
  ASL
  CLC
  ADC #$01
  TAY
  LDA (ptr_lo),Y
  ASL
  ASL
  ASL
  STA coll_x,X
  INY
  LDA (ptr_lo),Y
  CLC
  ADC #$02
  ASL
  ASL
  ASL
  STA coll_y,X
  LDA #$01
  STA coll_alive,X
  INX
  JMP LoadCoLoop
LoadCoDone:
  RTS

Respawn:
  LDA start_x
  STA player_x
  LDA start_y
  STA player_y
  LDA #$00
  STA player_vy
  LDA #$01
  STA player_ground
  LDA #$5A
  STA invuln
  JSR LoadEnemies
  RTS

Die:
  LDA lives
  BEQ DieGameOver
  DEC lives
  LDA #$01
  STA hud_dirty
  JSR PlayDeath
  LDA lives
  BEQ DieGameOver
  JSR Respawn
  RTS
DieGameOver:
  JSR DrawGameOver
  LDA #$03
  STA state
  RTS

AddScore100:
  CLC
  LDA score_lo
  ADC #$64
  STA score_lo
  LDA score_hi
  ADC #$00
  STA score_hi
  RTS

AddScore200:
  CLC
  LDA score_lo
  ADC #$C8
  STA score_lo
  LDA score_hi
  ADC #$00
  STA score_hi
  RTS

AddScore500:
  CLC
  LDA score_lo
  ADC #$F4
  STA score_lo
  LDA score_hi
  ADC #$01
  STA score_hi
  RTS
'''

# GetTile: check_x/check_y in, tile_val/tile_col/tile_row out.
# tile_row is the screen row (0-29), tile_val 0 when outside the map.
ASM_TEMPLATE += r'''
GetTile:
  LDA check_x
  LSR
  LSR
  LSR
  STA tile_col
  LDA check_y
  LSR
  LSR
  LSR
  STA tile_row
  LDA check_y
  CMP #$F0
  BCS GetTileEmpty
  LDA tile_row
  CMP #$02
  BCC GetTileEmpty
  CMP #$1E
  BCS GetTileEmpty
  SEC
  SBC #$02
  STA tmp2
  LDA #$00
  STA tmp3
  LDX #$05
GetTileMul:
  ASL tmp2
  ROL tmp3
  DEX
  BNE GetTileMul
  CLC
  LDA tmp2
  ADC tile_col
  STA tmp2
  LDA tmp3
  ADC #$00
  STA tmp3
  CLC
  LDA tmp2
  ADC #<level_map
  STA ptr_lo
  LDA tmp3
  ADC #>level_map
  STA ptr_hi
  LDY #$00
  LDA (ptr_lo),Y
  STA tile_val
  RTS
GetTileEmpty:
  LDA #$00
  STA tile_val
  RTS

IsSolid:
  LDA tile_val
  CMP #46
  BEQ IsSolidYes
  CMP #47
  BEQ IsSolidYes
  LDA #$00
  RTS
IsSolidYes:
  LDA #$01
  RTS

IsHazard:
  LDA tile_val
  CMP #48
  BEQ IsHazardYes
  CMP #49
  BEQ IsHazardYes
  LDA #$00
  RTS
IsHazardYes:
  LDA #$01
  RTS

HandlePlayInput:
  LDA btn_cur
  AND #$02
  BEQ InputRight
  LDA #$01
  STA player_dir
  LDA player_x
  CMP #$02
  BCC InputRight
  SEC
  SBC #$02
  STA player_x
  JSR CollideLeft
InputRight:
  LDA btn_cur
  AND #$01
  BEQ InputJump
  LDA #$00
  STA player_dir
  LDA player_x
  CMP #$EE
  BCS InputJump
  CLC
  ADC #$02
  STA player_x
  JSR CollideRight
InputJump:
  LDA btn_press
  AND #$80
  BEQ InputDone
  LDA player_ground
  BEQ InputDone
  LDA #$F7
  STA player_vy
  LDA #$00
  STA player_ground
  JSR PlayJump
InputDone:
  RTS

CollideLeft:
  LDA player_x
  STA check_x
  LDA player_y
  CLC
  ADC #$02
  STA check_y
  JSR GetTile
  JSR IsSolid
  BEQ CollideLeftLow
  LDA tile_col
  CLC
  ADC #$01
  ASL
  ASL
  ASL
  STA player_x
  RTS
CollideLeftLow:
  LDA player_x
  STA check_x
  LDA player_y
  CLC
  ADC #$0D
  STA check_y
  JSR GetTile
  JSR IsSolid
  BEQ CollideLeftDone
  LDA tile_col
  CLC
  ADC #$01
  ASL
  ASL
  ASL
  STA player_x
CollideLeftDone:
  RTS

CollideRight:
  LDA player_x
  CLC
  ADC #$0F
  STA check_x
  LDA player_y
  CLC
  ADC #$02
  STA check_y
  JSR GetTile
  JSR IsSolid
  BEQ CollideRightLow
  LDA tile_col
  ASL
  ASL
  ASL
  SEC
  SBC #$10
  STA player_x
  RTS
CollideRightLow:
  LDA player_x
  CLC
  ADC #$0F
  STA check_x
  LDA player_y
  CLC
  ADC #$0D
  STA check_y
  JSR GetTile
  JSR IsSolid
  BEQ CollideRightDone
  LDA tile_col
  ASL
  ASL
  ASL
  SEC
  SBC #$10
  STA player_x
CollideRightDone:
  RTS

UpdatePhysics:
  LDA player_ground
  BEQ PhysAir
  LDA player_x
  CLC
  ADC #$02
  STA check_x
  LDA player_y
  CLC
  ADC #$10
  STA check_y
  JSR GetTile
  JSR IsSolid
  BNE PhysGrounded
  LDA player_x
  CLC
  ADC #$0D
  STA check_x
  LDA player_y
  CLC
  ADC #$10
  STA check_y
  JSR GetTile
  JSR IsSolid
  BNE PhysGrounded
  LDA #$00
  STA player_ground
  STA player_vy
  RTS
PhysGrounded:
  RTS
PhysAir:
  LDA player_vy
  BMI PhysGrav
  CMP #$08
  BCS PhysMoveY
PhysGrav:
  INC player_vy
PhysMoveY:
  LDA player_y
  CLC
  ADC player_vy
  STA player_y
  LDA player_vy
  BMI PhysRise
  LDA player_x
  CLC
  ADC #$02
  STA check_x
  LDA player_y
  CLC
  ADC #$10
  STA check_y
  JSR GetTile
  JSR IsSolid
  BNE PhysLand
  LDA player_x
  CLC
  ADC #$0D
  STA check_x
  LDA player_y
  CLC
  ADC #$10
  STA check_y
  JSR GetTile
  JSR IsSolid
  BEQ PhysAirDone
PhysLand:
  LDA tile_row
  ASL
  ASL
  ASL
  SEC
  SBC #$10
  STA player_y
  LDA #$00
  STA player_vy
  LDA #$01
  STA player_ground
PhysAirDone:
  RTS
PhysRise:
  LDA player_x
  CLC
  ADC #$02
  STA check_x
  LDA player_y
  STA check_y
  JSR GetTile
  JSR IsSolid
  BNE PhysHead
  LDA player_x
  CLC
  ADC #$0D
  STA check_x
  LDA player_y
  STA check_y
  JSR GetTile
  JSR IsSolid
  BEQ PhysAirDone
PhysHead:
  LDA tile_row
  CLC
  ADC #$01
  ASL
  ASL
  ASL
  STA player_y
  LDA #$00
  STA player_vy
  RTS
'''

ASM_TEMPLATE += r'''
UpdateEnemies:
  LDA cycle_num
  CMP #$01
  BEQ EnSpeed1
  LDA #$02
  STA move_speed
  JMP EnLoopInit
EnSpeed1:
  LDA #$01
  STA move_speed
EnLoopInit:
  LDA #$00
  STA enemy_idx
EnLoop:
  LDA enemy_idx
  CMP enemy_count
  BCC EnLoopGo
  JMP EnDone
EnLoopGo:
  LDX enemy_idx
  LDA enemy_alive,X
  BEQ EnNext
  LDA enemy_dir,X
  BEQ EnMoveLeft
  LDA enemy_x,X
  CLC
  ADC move_speed
  STA enemy_x,X
  LDA enemy_x,X
  CMP enemy_max,X
  BCC EnNext
  LDA #$00
  STA enemy_dir,X
  JMP EnNext
EnMoveLeft:
  LDA enemy_x,X
  SEC
  SBC move_speed
  STA enemy_x,X
  LDA enemy_x,X
  CMP enemy_min,X
  BCS EnNext
  LDA #$01
  STA enemy_dir,X
EnNext:
  INC enemy_idx
  JMP EnLoop
EnDone:
  RTS

CheckHazards:
  LDA invuln
  BNE HazDone
  LDA player_x
  CLC
  ADC #$02
  STA check_x
  LDA player_y
  CLC
  ADC #$0F
  STA check_y
  JSR GetTile
  JSR IsHazard
  BNE HazDie
  LDA player_x
  CLC
  ADC #$0D
  STA check_x
  LDA player_y
  CLC
  ADC #$0F
  STA check_y
  JSR GetTile
  JSR IsHazard
  BEQ HazDone
HazDie:
  JSR Die
HazDone:
  RTS

CheckColls:
  LDA #$00
  STA coll_idx
CollLoop:
  LDA coll_idx
  CMP coll_count
  BCC CollGo
  JMP CollDone
CollGo:
  LDX coll_idx
  LDA coll_alive,X
  BEQ CollNext
  LDA coll_x,X
  CLC
  ADC #$08
  STA tmp4
  LDA player_x
  CMP tmp4
  BCS CollNext
  LDA player_x
  CLC
  ADC #$10
  STA tmp4
  LDA coll_x,X
  CMP tmp4
  BCS CollNext
  LDA coll_y,X
  CLC
  ADC #$08
  STA tmp4
  LDA player_y
  CMP tmp4
  BCS CollNext
  LDA player_y
  CLC
  ADC #$10
  STA tmp4
  LDA coll_y,X
  CMP tmp4
  BCS CollNext
  LDA #$00
  STA coll_alive,X
  INC letters_col
  JSR AddScore100
  JSR ConvertScore
  LDA #$01
  STA hud_dirty
  JSR PlayPickup
  LDA letters_col
  CMP letters_total
  BNE CollNext
  LDA #$01
  STA door_open
  JSR PlayDoor
CollNext:
  INC coll_idx
  JMP CollLoop
CollDone:
  RTS

CheckEnemies:
  LDA invuln
  BEQ EnCheckStart
  JMP EnCheckDone
EnCheckStart:
  LDA #$00
  STA enemy_idx
EnCheckLoop:
  LDA enemy_idx
  CMP enemy_count
  BCC EnCheckGo
  JMP EnCheckDone
EnCheckGo:
  LDX enemy_idx
  LDA enemy_alive,X
  BEQ EnCheckNext
  LDA enemy_x,X
  CLC
  ADC #$10
  STA tmp4
  LDA player_x
  CMP tmp4
  BCS EnCheckNext
  LDA player_x
  CLC
  ADC #$10
  STA tmp4
  LDA enemy_x,X
  CMP tmp4
  BCS EnCheckNext
  LDA enemy_y,X
  CLC
  ADC #$10
  STA tmp4
  LDA player_y
  CMP tmp4
  BCS EnCheckNext
  LDA player_y
  CLC
  ADC #$10
  STA tmp4
  LDA enemy_y,X
  CMP tmp4
  BCS EnCheckNext
  LDA player_vy
  BMI EnCheckDie
  LDA player_y
  CLC
  ADC #$10
  SEC
  SBC enemy_y,X
  CMP #$0A
  BCS EnCheckDie
  LDA #$00
  STA enemy_alive,X
  JSR AddScore200
  JSR ConvertScore
  LDA #$01
  STA hud_dirty
  JSR PlayStomp
  LDA #$FB
  STA player_vy
  LDA #$00
  STA player_ground
  JMP EnCheckDone
EnCheckDie:
  JSR Die
  JMP EnCheckDone
EnCheckNext:
  INC enemy_idx
  JMP EnCheckLoop
EnCheckDone:
  RTS

CheckDoor:
  LDA door_cool
  BNE DoorDone
  LDA player_x
  CLC
  ADC #$10
  STA tmp4
  LDA door_x
  CMP tmp4
  BCS DoorDone
  LDA door_x
  CLC
  ADC #$10
  STA tmp4
  LDA player_x
  CMP tmp4
  BCS DoorDone
  LDA player_y
  CLC
  ADC #$10
  STA tmp4
  LDA door_y
  CMP tmp4
  BCS DoorDone
  LDA door_y
  CLC
  ADC #$10
  STA tmp4
  LDA player_y
  CMP tmp4
  BCS DoorDone
  LDA door_open
  BEQ DoorLocked
  JSR AddScore500
  JSR ConvertScore
  LDA level_idx
  CMP #$03
  BNE DoorNextLevel
  INC cycle_num
  LDA #$00
  STA level_idx
  JSR DrawCycleCard
  LDA #$04
  STA state
  LDA #$B4
  STA card_timer
  RTS
DoorNextLevel:
  INC level_idx
  JSR DrawCard
  LDA #$02
  STA state
  LDA #$B4
  STA card_timer
  RTS
DoorLocked:
  LDA player_x
  SEC
  SBC #$10
  BCS DoorKnockOk
  LDA #$00
DoorKnockOk:
  STA player_x
  LDA #$1E
  STA door_cool
  JSR PlayBuzz
DoorDone:
  RTS

CheckFall:
  LDA player_y
  CMP #$F0
  BCC FallDone
  JSR Die
FallDone:
  RTS

WriteOneSprite:
  LDX spr_idx
  LDA spr_y
  STA $0200,X
  INX
  LDA spr_tile
  STA $0200,X
  INX
  LDA spr_attr
  STA $0200,X
  INX
  LDA spr_x
  STA $0200,X
  INX
  STX spr_idx
  RTS

BuildSprites:
  LDA #$FF
  LDX #$00
ClearOAM:
  STA $0200,X
  INX
  BNE ClearOAM
  LDA #$00
  STA spr_idx
  LDA invuln
  BEQ BuildPlayer
  LDA frame_cnt
  AND #$10
  BNE BuildEnemies
BuildPlayer:
  LDA player_dir
  BEQ SprFaceRight
  LDA #$40
  STA spr_attr
  JMP SprPlayerGo
SprFaceRight:
  LDA #$00
  STA spr_attr
SprPlayerGo:
  LDA player_y
  STA spr_y
  LDA player_x
  STA spr_x
  LDA #54
  STA spr_tile
  JSR WriteOneSprite
  LDA player_y
  STA spr_y
  LDA player_x
  CLC
  ADC #$08
  STA spr_x
  LDA #55
  STA spr_tile
  JSR WriteOneSprite
  LDA player_y
  CLC
  ADC #$08
  STA spr_y
  LDA player_x
  STA spr_x
  LDA #56
  STA spr_tile
  JSR WriteOneSprite
  LDA player_y
  CLC
  ADC #$08
  STA spr_y
  LDA player_x
  CLC
  ADC #$08
  STA spr_x
  LDA #57
  STA spr_tile
  JSR WriteOneSprite
BuildEnemies:
  LDA #$01
  STA spr_attr
  LDA #$00
  STA enemy_idx
BuildEnLoop:
  LDA enemy_idx
  CMP enemy_count
  BCC BuildEnGo
  JMP BuildColls
BuildEnGo:
  LDX enemy_idx
  LDA enemy_alive,X
  BEQ BuildEnNext
  LDA enemy_y,X
  STA spr_y
  LDA enemy_x,X
  STA spr_x
  LDA #58
  STA spr_tile
  JSR WriteOneSprite
  LDA enemy_y,X
  STA spr_y
  LDA enemy_x,X
  CLC
  ADC #$08
  STA spr_x
  LDA #58
  STA spr_tile
  JSR WriteOneSprite
  LDA enemy_y,X
  CLC
  ADC #$08
  STA spr_y
  LDA enemy_x,X
  STA spr_x
  LDA #58
  STA spr_tile
  JSR WriteOneSprite
  LDA enemy_y,X
  CLC
  ADC #$08
  STA spr_y
  LDA enemy_x,X
  CLC
  ADC #$08
  STA spr_x
  LDA #58
  STA spr_tile
  JSR WriteOneSprite
BuildEnNext:
  INC enemy_idx
  JMP BuildEnLoop
BuildColls:
  LDA #$02
  STA spr_attr
  LDA #$00
  STA coll_idx
BuildCoLoop:
  LDA coll_idx
  CMP coll_count
  BCC BuildCoGo
  JMP BuildDone
BuildCoGo:
  LDX coll_idx
  LDA coll_alive,X
  BEQ BuildCoNext
  LDA coll_y,X
  STA spr_y
  LDA coll_x,X
  STA spr_x
  LDA #59
  STA spr_tile
  JSR WriteOneSprite
BuildCoNext:
  INC coll_idx
  JMP BuildCoLoop
BuildDone:
  RTS

PlayJump:
  LDA #$9C
  STA $4000
  LDA #$00
  STA $4001
  LDA #$DE
  STA $4002
  LDA #$18
  STA $4003
  RTS

PlayPickup:
  LDA #$5C
  STA $4004
  LDA #$00
  STA $4005
  LDA #$8A
  STA $4006
  LDA #$20
  STA $4007
  RTS

PlayStomp:
  LDA #$1C
  STA $400C
  LDA #$04
  STA $400E
  LDA #$20
  STA $400F
  RTS

PlayDeath:
  LDA #$9C
  STA $4000
  LDA #$00
  STA $4001
  LDA #$E8
  STA $4002
  LDA #$2A
  STA $4003
  RTS

PlayDoor:
  LDA #$9C
  STA $4000
  LDA #$00
  STA $4001
  LDA #$6E
  STA $4002
  LDA #$30
  STA $4003
  RTS

PlayBuzz:
  LDA #$9C
  STA $4000
  LDA #$00
  STA $4001
  LDA #$5D
  STA $4002
  LDA #$1C
  STA $4003
  RTS

NMI:
  PHA
  TXA
  PHA
  TYA
  PHA
  LDA ptr_lo
  PHA
  LDA ptr_hi
  PHA
  LDA $2002
  INC frame_cnt
  LDA state
  CMP #$01
  BNE NmiNoHud
  LDA hud_dirty
  BEQ NmiNoHud
  JSR WriteHud
  LDA #$00
  STA hud_dirty
NmiNoHud:
  LDA #$00
  STA $2003
  LDA #$02
  STA $4014
  LDA #$01
  STA vblank_flag
  PLA
  STA ptr_hi
  PLA
  STA ptr_lo
  PLA
  TAY
  PLA
  TAX
  PLA
  RTI

IRQ:
  RTI

chr_tiles:
@@CHR@@
palette_data:
@@PALETTE@@
score_place_lo:
  .byte $10, $E8, $64, $0A, $01
score_place_hi:
  .byte $27, $03, $00, $00, $00
door_open_str:
@@DOOROPEN@@
door_shut_str:
@@DOORSHUT@@
level_maps:
@@LEVELMAPS@@
enemy_data:
@@ENEMYDATA@@
coll_data:
@@COLLDATA@@
@@STRINGS@@

  .org $FFFA
  .word NMI
  .word Reset
  .word IRQ
'''


def build_source():
    src = ASM_TEMPLATE
    src = src.replace("@@TITLE_CODE@@", TITLE_CODE)
    src = src.replace("@@GAMEOVER_CODE@@", GAMEOVER_CODE)
    src = src.replace("@@CYCLE_CODE@@", CYCLE_CODE)
    src = src.replace("@@CARD_BLOCKS@@", CARD_BLOCKS)
    src = src.replace("@@CARD_COMMON@@", CARD_COMMON)
    src = src.replace("@@HUD_CODE@@", HUD_CODE)
    src = src.replace("@@CHR@@", fmt_bytes(CHR_BYTES))
    src = src.replace("@@PALETTE@@", fmt_bytes(PALETTE))
    src = src.replace("@@DOOROPEN@@", fmt_bytes(tiles_for("OPEN")))
    src = src.replace("@@DOORSHUT@@", fmt_bytes(tiles_for("SHUT")))
    src = src.replace("@@LEVELMAPS@@", fmt_bytes(LEVEL_MAP_BYTES))
    src = src.replace("@@ENEMYDATA@@", fmt_bytes(ENEMY_BYTES))
    src = src.replace("@@COLLDATA@@", fmt_bytes(COLL_BYTES))
    str_lines = []
    for label, text in STRINGS:
        str_lines.append("%s:\n%s\n  .byte $FF" % (label, fmt_bytes(tiles_for(text))))
    src = src.replace("@@STRINGS@@", "\n".join(str_lines))
    return src


def main():
    try:
        prg, symbols = assemble(build_source())
    except AsmError as exc:
        print("ASSEMBLY FAILED: %s" % exc, file=sys.stderr)
        return 1
    header = bytearray(16)
    header[0:4] = b"NES\x1a"
    header[4] = 2
    header[5] = 0
    header[6] = 0x00
    header[7] = 0x00
    rom = bytes(header) + prg
    with open(OUT_PATH, "wb") as f:
        f.write(rom)
    with open(OUT_PATH, "rb") as f:
        data = f.read()
    assert data[0:4] == b"NES\x1a"
    assert data[4] == 2 and data[5] == 0
    assert ((data[6] >> 4) | (data[7] & 0xF0)) == 0
    assert len(data) == 16 + 2 * 16384
    vec_off = 16 + 0x7FFA
    nmi = data[vec_off] | (data[vec_off + 1] << 8)
    reset = data[vec_off + 2] | (data[vec_off + 3] << 8)
    irq = data[vec_off + 4] | (data[vec_off + 5] << 8)
    for name, v in (("NMI", nmi), ("Reset", reset), ("IRQ", irq)):
        assert 0x8000 <= v <= 0xFFFF, "%s vector out of range" % name
    assert symbols["Reset"] == reset
    assert symbols["NMI"] == nmi
    assert symbols["IRQ"] == irq
    print("Built %s" % OUT_PATH)
    print("Size: %d bytes" % len(data))
    print("Vectors: NMI=$%04X Reset=$%04X IRQ=$%04X" % (nmi, reset, irq))
    print("ZP last var enemy_idx=$%02X" % symbols["enemy_idx"])
    print("Levels: %d, map bytes %d, enemy bytes %d, coll bytes %d"
          % (len(LEVELS), len(LEVEL_MAP_BYTES), len(ENEMY_BYTES), len(COLL_BYTES)))
    print("Unresolved labels: none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
