#!/usr/bin/env python3
"""Build a playable NES ROM port of the Roland drum machine series.

No cc65 is required: this file contains a minimal two-pass 6502 assembler
that assembles the ROM source below and writes roland-x0x.nes next to it.

All sound is synthesized live by the NES APU. No Roland samples, no original
Roland audio, and no copyrighted ROMs are used or downloaded.

ROM layout: iNES header, mapper 0 (NROM), 32 KiB PRG ($8000-$FFFF),
CHR RAM (CHR size 0 in the header, tiles uploaded by code at startup).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "roland-x0x.nes")

# ---------------------------------------------------------------- font
# 5x7 glyphs, '#' = pixel. Tile order (assembly constants must match):
#   0 blank, 1-26 A-Z, 27-36 0-9, 37 '-', 38 ':', 39 '.', 40 '>',
#   41 '^', 42 '*', 43 solid block, 44 '+', 45 '/'
FONT = {
    'A': [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    'B': ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    'C': [".####", "#....", "#....", "#....", "#....", "#....", ".####"],
    'D': ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    'E': ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    'F': ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    'G': [".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."],
    'H': ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    'I': [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    'J': ["..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."],
    'K': ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    'L': ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    'M': ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    'N': ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
    'O': [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    'P': ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    'Q': [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
    'R': ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    'S': [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    'T': ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    'U': ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    'V': ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    'W': ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
    'X': ["#...#", ".#.#.", "..#..", "..#..", "..#..", ".#.#.", "#...#"],
    'Y': ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    'Z': ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    '0': [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    '1': ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    '2': [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    '3': ["####.", "....#", "....#", ".###.", "....#", "....#", "####."],
    '4': ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    '5': ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    '6': [".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."],
    '7': ["#####", "....#", "...#.", "..#..", "..#..", "..#..", "..#.."],
    '8': [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    '9': [".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."],
    '-': [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    ':': [".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."],
    '.': [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
    '>': ["#....", ".#...", "..#..", "...#.", "..#..", ".#...", "#...."],
    '^': ["..#..", ".#.#.", "#...#", ".....", ".....", ".....", "....."],
    '*': [".....", ".#.#.", "..#..", "#####", "..#..", ".#.#.", "....."],
    '+': [".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."],
    '/': ["....#", "...#.", "...#.", "..#..", ".#...", ".#...", "#...."],
}
TILE_ORDER = ([' '] + [chr(ord('A') + i) for i in range(26)]
              + [chr(ord('0') + i) for i in range(10)]
              + ['-', ':', '.', '>', '^', '*'])
TILE_INDEX = {ch: i for i, ch in enumerate(TILE_ORDER)}
TILE_INDEX['+'] = 44
TILE_INDEX['/'] = 45


def tile_bytes_for(rows):
    out = []
    for r in range(8):
        row = rows[r] if r < len(rows) else "....."
        b = 0
        for i, ch in enumerate(row):
            if ch == '#':
                b |= 1 << (7 - i)
        out.append(b)
    return out


def font_tiles_bytes():
    data = []
    for ch in TILE_ORDER:
        if ch == ' ':
            data.extend([0] * 16)
        else:
            glyph = tile_bytes_for(FONT[ch])
            data.extend(glyph)   # plane 0
            data.extend([0] * 8)  # plane 1 (unused, monochrome)
    # solid block, tile 43
    data.extend([0xFF] * 8 + [0] * 8)
    # '+' tile 44 and '/' tile 45
    for ch in ('+', '/'):
        glyph = tile_bytes_for(FONT[ch])
        data.extend(glyph)
        data.extend([0] * 8)
    return data


def tiles_for(s):
    return [TILE_INDEX[ch] for ch in s]


def fmt_bytes(data, per_line=16):
    lines = []
    for i in range(0, len(data), per_line):
        chunk = data[i:i + per_line]
        lines.append("  .byte " + ", ".join("$%02X" % b for b in chunk))
    return "\n".join(lines)


# ---------------------------------------------------------------- data
MACHINES = ["808", "909", "606", "707", "727", "505", "626", "C78", "C80"]
VOICES = ["BD", "SD", "LT", "HT", "RS", "CB", "OH", "CH"]


def tri_timer(freq):
    return int(55930 / freq) - 1  # NES triangle: CPU/32/(timer+1)


def pulse_timer(freq):
    return int(111861 / freq) - 1  # NES pulse: CPU/16/(timer+1)


def lo_hi(v):
    return v & 0xFF, (v >> 8) & 0xFF


# (start_freq, end_freq, decay_frames) per machine, in MACHINES order
BD_DATA = [(160, 45, 18), (180, 40, 14), (140, 60, 10), (120, 55, 8),
           (110, 65, 7), (130, 50, 10), (125, 55, 9), (100, 60, 10),
           (110, 55, 11)]
TOM_DATA = [(160, 80, 12), (170, 85, 10), (150, 75, 8), (140, 70, 7),
            (130, 65, 7), (145, 72, 8), (140, 70, 8), (120, 60, 9),
            (125, 62, 9)]
# (noise period index, mode, volume, length code) per machine
SD_NOISE = [(7, 0, 13, 4), (6, 1, 14, 6), (8, 0, 11, 3), (5, 0, 12, 5),
            (7, 1, 11, 3), (6, 0, 12, 4), (6, 0, 12, 5), (9, 0, 9, 3),
            (8, 0, 10, 4)]
HAT_NOISE = [(3, 1, 11, 8), (2, 1, 12, 9), (4, 1, 10, 7), (3, 0, 11, 8),
             (3, 1, 10, 6), (3, 0, 11, 7), (3, 0, 11, 8), (5, 0, 9, 6),
             (4, 0, 10, 7)]
RS_FREQ = [1800, 1600, 1700, 1500, 1900, 1600, 1550, 1200, 1300]
RS_VOL = [11, 12, 10, 11, 11, 11, 11, 9, 10]
RS_LEN = [2, 3, 2, 3, 2, 3, 3, 2, 2]
CB_FREQ = [800, 850, 750, 900, 1000, 820, 840, 700, 720]
CB_VOL = [11, 12, 10, 11, 11, 11, 11, 9, 10]
CB_LEN = [6, 7, 5, 6, 5, 6, 6, 5, 5]
SD_BODY_FREQ = [180, 200, 170, 190, 210, 185, 190, 160, 170]


def tri_table(rows):
    out = []
    for start, end, decay in rows:
        s_lo, s_hi = lo_hi(tri_timer(start))
        e_lo, e_hi = lo_hi(tri_timer(end))
        # Precompute the pitch step so the NMI handler never divides:
        # a division loop in NMI pushed PPU updates past vblank.
        step = (tri_timer(end) - tri_timer(start)) // decay
        st_lo, st_hi = lo_hi(step)
        out.extend([s_lo, s_hi, e_lo, e_hi, decay, st_lo, st_hi])
    return out


def pulse_table(freqs, vols, lens):
    out = []
    for f, v, ln in zip(freqs, vols, lens):
        p_lo, p_hi = lo_hi(pulse_timer(f))
        out.extend([p_lo, p_hi, v, ln])
    return out


# Presets: 9 patterns, one per machine, 8 rows x 16 steps.
# Row order is VOICES. Steps are step numbers 0-15 (step 0 = beat 1).
PRESETS = [
    # 808
    [[0, 4, 8, 12], [4, 12], [14], [11], [2, 7, 10, 15], [2, 6, 10, 14],
     [2, 6, 10, 14], [0, 2, 4, 6, 8, 10, 12, 14]],
    # 909
    [[0, 4, 8, 12], [4, 12], [15], [7], [3, 11], [0, 4, 8, 12],
     [2, 6, 10, 14], [0, 2, 4, 6, 8, 10, 12, 14]],
    # 606
    [[0, 4, 8, 12], [4, 12], [7, 15], [3, 11], [10], [6, 14],
     [2, 6, 10, 14], [0, 4, 8, 12]],
    # 707
    [[0, 4, 8, 12], [4, 12], [15], [], [7], [2, 10],
     [14], [0, 2, 4, 6, 8, 10, 12, 14]],
    # 727 (Latin-leaning)
    [[0, 8], [4, 12], [7], [15], [3, 6, 11, 14], [0, 3, 6, 10, 12],
     [2, 10], [4, 12]],
    # 505
    [[0, 4, 8, 12], [4, 12], [12], [4], [2, 10], [0, 8],
     [6, 14], [0, 2, 4, 6, 8, 10, 12, 14]],
    # 626
    [[0, 4, 8, 12], [4, 12, 15], [14], [7], [3, 11], [6, 14],
     [2, 10], [0, 4, 8, 12]],
    # CR-78
    [[0, 8], [4, 12], [7], [15], [4, 12], [0, 10],
     [0, 8], [2, 6, 10, 14]],
    # CR-8000
    [[0, 4, 8, 12], [4, 12], [15], [3], [7], [3, 11],
     [2, 8], [0, 6, 10, 14]],
]


def preset_bytes():
    out = []
    for pat in PRESETS:
        for row in pat:
            b0 = sum(1 << s for s in row if s < 8)
            b1 = sum(1 << (s - 8) for s in row if s >= 8)
            out.extend([b0, b1])
    return out


FONT_BYTES = font_tiles_bytes()
PALETTE = [0x0F, 0x30, 0x00, 0x10, 0x0F, 0x30, 0x27, 0x10,
           0x0F, 0x30, 0x2A, 0x10, 0x0F, 0x30, 0x16, 0x10,
           0x0F, 0x30, 0x00, 0x10, 0x0F, 0x30, 0x27, 0x10,
           0x0F, 0x30, 0x2A, 0x10, 0x0F, 0x30, 0x16, 0x10]
MACHINE_NAME_BYTES = []
for m in MACHINES:
    MACHINE_NAME_BYTES.extend(tiles_for(m))
VOICE_LABEL_BYTES = []
for v in VOICES:
    VOICE_LABEL_BYTES.extend(tiles_for(v))

# ------------------------------------------------------- minimal assembler
OPCODES = {}


def _op(mn, mode, code):
    OPCODES[(mn, mode)] = code


for _mn, _modes in [
    ("LDA", {"imm": 0xA9, "zp": 0xA5, "zpx": 0xB5, "abs": 0xAD,
             "absx": 0xBD, "absy": 0xB9, "indx": 0xA1, "indy": 0xB1}),
    ("LDX", {"imm": 0xA2, "zp": 0xA6, "zpy": 0xB6, "abs": 0xAE,
             "absy": 0xBE}),
    ("LDY", {"imm": 0xA0, "zp": 0xA4, "zpx": 0xB4, "abs": 0xAC,
             "absx": 0xBC}),
    ("STA", {"zp": 0x85, "zpx": 0x95, "abs": 0x8D, "absx": 0x9D,
             "absy": 0x99, "indx": 0x81, "indy": 0x91}),
    ("STX", {"zp": 0x86, "zpy": 0x96, "abs": 0x8E}),
    ("STY", {"zp": 0x84, "zpx": 0x94, "abs": 0x8C}),
    ("INC", {"zp": 0xE6, "zpx": 0xF6, "abs": 0xEE, "absx": 0xFE}),
    ("DEC", {"zp": 0xC6, "zpx": 0xD6, "abs": 0xCE, "absx": 0xDE}),
    ("ASL", {"acc": 0x0A, "zp": 0x06, "zpx": 0x16, "abs": 0x0E,
             "absx": 0x1E}),
    ("LSR", {"acc": 0x4A, "zp": 0x46, "zpx": 0x56, "abs": 0x4E,
             "absx": 0x5E}),
    ("ROL", {"acc": 0x2A, "zp": 0x26, "zpx": 0x36, "abs": 0x2E,
             "absx": 0x3E}),
    ("ROR", {"acc": 0x6A, "zp": 0x66, "zpx": 0x76, "abs": 0x6E,
             "absx": 0x7E}),
    ("ADC", {"imm": 0x69, "zp": 0x65, "zpx": 0x75, "abs": 0x6D,
             "absx": 0x7D, "absy": 0x79, "indx": 0x61, "indy": 0x71}),
    ("SBC", {"imm": 0xE9, "zp": 0xE5, "zpx": 0xF5, "abs": 0xED,
             "absx": 0xFD, "absy": 0xF9, "indx": 0xE1, "indy": 0xF1}),
    ("AND", {"imm": 0x29, "zp": 0x25, "zpx": 0x35, "abs": 0x2D,
             "absx": 0x3D, "absy": 0x39, "indx": 0x21, "indy": 0x31}),
    ("ORA", {"imm": 0x09, "zp": 0x05, "zpx": 0x15, "abs": 0x0D,
             "absx": 0x1D, "absy": 0x19, "indx": 0x01, "indy": 0x11}),
    ("EOR", {"imm": 0x49, "zp": 0x45, "zpx": 0x55, "abs": 0x4D,
             "absx": 0x5D, "absy": 0x59, "indx": 0x41, "indy": 0x51}),
    ("CMP", {"imm": 0xC9, "zp": 0xC5, "zpx": 0xD5, "abs": 0xCD,
             "absx": 0xDD, "absy": 0xD9, "indx": 0xC1, "indy": 0xD1}),
    ("CPX", {"imm": 0xE0, "zp": 0xE4, "abs": 0xEC}),
    ("CPY", {"imm": 0xC0, "zp": 0xC4, "abs": 0xCC}),
    ("BIT", {"zp": 0x24, "abs": 0x2C}),
    ("JMP", {"abs": 0x4C, "ind": 0x6C}),
    ("JSR", {"abs": 0x20}),
]:
    for _mode, _code in _modes.items():
        _op(_mn, _mode, _code)
for _mn, _code in [("TAX", 0xAA), ("TAY", 0xA8), ("TXA", 0x8A),
                   ("TYA", 0x98), ("TSX", 0xBA), ("TXS", 0x9A),
                   ("INX", 0xE8), ("INY", 0xC8), ("DEX", 0xCA),
                   ("DEY", 0x88), ("RTS", 0x60), ("RTI", 0x40),
                   ("BRK", 0x00), ("CLC", 0x18), ("SEC", 0x38),
                   ("CLI", 0x58), ("SEI", 0x78), ("CLD", 0xD8),
                   ("SED", 0xF8), ("CLV", 0xB8), ("NOP", 0xEA),
                   ("PHA", 0x48), ("PLA", 0x68), ("PHP", 0x08),
                   ("PLP", 0x28)]:
    _op(_mn, "imp", _code)
for _mn, _code in [("BCC", 0x90), ("BCS", 0xB0), ("BEQ", 0xF0),
                   ("BNE", 0xD0), ("BMI", 0x30), ("BPL", 0x10),
                   ("BVC", 0x50), ("BVS", 0x70)]:
    _op(_mn, "rel", _code)

BRANCHES = {"BCC", "BCS", "BEQ", "BNE", "BMI", "BPL", "BVC", "BVS"}
IMPLIED = {"TAX", "TAY", "TXA", "TYA", "TSX", "TXS", "INX", "INY", "DEX",
           "DEY", "RTS", "RTI", "BRK", "CLC", "SEC", "CLI", "SEI", "CLD",
           "SED", "CLV", "NOP", "PHA", "PLA", "PHP", "PLP"}


def parse_number(s, symbols=None):
    s = s.strip()
    if s.startswith("$"):
        return int(s[1:], 16)
    if s.startswith("%"):
        return int(s[1:], 2)
    if s.lstrip("-").isdigit():
        return int(s, 10)
    if symbols is not None and s in symbols:
        return symbols[s]
    return None


class AsmError(Exception):
    pass


def split_lines(source):
    out = []
    for raw in source.splitlines():
        line = raw.split(";", 1)[0].rstrip()
        if not line.strip():
            continue
        out.append(line)
    return out


def parse_line(line):
    """Return (label_or_None, rest_or_None)."""
    s = line.strip()
    label = None
    if ":" in s:
        label, s = s.split(":", 1)
        label = label.strip()
        s = s.strip()
        if not s:
            return label, None
    return label, s


def instr_size(mn, operand, symbols):
    if mn in IMPLIED:
        return 1
    if mn in BRANCHES:
        return 2
    if operand is None:
        if mn in ("ASL", "LSR", "ROL", "ROR"):
            return 1  # accumulator mode
        raise AsmError("missing operand for %s" % mn)
    op = operand.strip()
    if op == "A":
        return 1
    if op.startswith("#"):
        return 2
    if op.startswith("("):
        return 2 if op.endswith(",X)") or op.endswith("),Y") else 3
    base = op
    mode_suffix = None
    if op.endswith(",X"):
        base, mode_suffix = op[:-2], "x"
    elif op.endswith(",Y"):
        base, mode_suffix = op[:-2], "y"
    val = parse_number(base.strip(), symbols)
    if val is not None and val < 0x100:
        return 2
    return 3


def assemble(source):
    lines = split_lines(source)
    # Pass 1: symbols
    symbols = {}
    pc = 0
    parsed = []  # (label, rest, pc_at_line)
    for line in lines:
        label, rest = parse_line(line)
        if label:
            if label in symbols:
                raise AsmError("duplicate label %s" % label)
            symbols[label] = pc
        if rest is None:
            parsed.append((label, None, pc))
            continue
        parts = rest.split(None, 1)
        head = parts[0]
        operand = parts[1].strip() if len(parts) > 1 else None
        if head == ".org":
            v = parse_number(operand, symbols)
            if v is None:
                raise AsmError(".org with unknown value %s" % operand)
            pc = v
            parsed.append((label, rest, pc))
            continue
        if head == ".res":
            n = parse_number(operand, symbols)
            parsed.append((label, rest, pc))
            pc += n
            continue
        if head == ".byte":
            n = len([x for x in operand.split(",") if x.strip()])
            parsed.append((label, rest, pc))
            pc += n
            continue
        if head == ".word":
            n = len([x for x in operand.split(",") if x.strip()])
            parsed.append((label, rest, pc))
            pc += 2 * n
            continue
        # instruction
        sz = instr_size(head, operand, symbols)
        parsed.append((label, rest, pc))
        pc += sz
    # Pass 2: emit into 32 KiB PRG buffer ($8000-$FFFF)
    rom = bytearray([0x00] * 0x8000)

    def emit(addr, b):
        if 0x8000 <= addr < 0x10000:
            rom[addr - 0x8000] = b & 0xFF

    pc = 0
    for label, rest, line_pc in parsed:
        if rest is None:
            continue
        parts = rest.split(None, 1)
        head = parts[0]
        operand = parts[1].strip() if len(parts) > 1 else None
        pc = line_pc
        if head == ".org":
            pc = parse_number(operand, symbols)
            continue
        if head == ".res":
            pc += parse_number(operand, symbols)
            continue
        if head == ".byte":
            for item in operand.split(","):
                item = item.strip()
                if not item:
                    continue
                if item.startswith("<"):
                    name = item[1:]
                    if name not in symbols:
                        raise AsmError("unresolved label %s" % name)
                    emit(pc, symbols[name] & 0xFF)
                elif item.startswith(">"):
                    name = item[1:]
                    if name not in symbols:
                        raise AsmError("unresolved label %s" % name)
                    emit(pc, symbols[name] >> 8)
                else:
                    v = parse_number(item, symbols)
                    if v is None:
                        raise AsmError("unresolved byte %s" % item)
                    emit(pc, v & 0xFF)
                pc += 1
            continue
        if head == ".word":
            for item in operand.split(","):
                item = item.strip()
                v = parse_number(item, symbols)
                if v is None:
                    raise AsmError("unresolved word %s" % item)
                emit(pc, v & 0xFF)
                emit(pc + 1, (v >> 8) & 0xFF)
                pc += 2
            continue
        # instruction
        mn = head
        if mn in IMPLIED:
            emit(pc, OPCODES[(mn, "imp")])
            pc += 1
            continue
        if operand is None and mn in ("ASL", "LSR", "ROL", "ROR"):
            emit(pc, OPCODES[(mn, "acc")])
            pc += 1
            continue
        if mn in BRANCHES:
            if operand not in symbols:
                raise AsmError("unresolved branch %s" % operand)
            target = symbols[operand]
            off = target - (pc + 2)
            if not -128 <= off <= 127:
                raise AsmError("branch out of range to %s" % operand)
            emit(pc, OPCODES[(mn, "rel")])
            emit(pc + 1, off & 0xFF)
            pc += 2
            continue
        op = operand.strip()
        if op == "A":
            emit(pc, OPCODES[(mn, "acc")])
            pc += 1
            continue
        if op.startswith("#"):
            body = op[1:].strip()
            if body.startswith("<"):
                name = body[1:]
                num = parse_number(name, symbols)
                if num is not None:
                    val = num & 0xFF
                elif name not in symbols:
                    raise AsmError("unresolved label %s" % name)
                else:
                    val = symbols[name] & 0xFF
            elif body.startswith(">"):
                name = body[1:]
                num = parse_number(name, symbols)
                if num is not None:
                    val = (num >> 8) & 0xFF
                elif name not in symbols:
                    raise AsmError("unresolved label %s" % name)
                else:
                    val = (symbols[name] >> 8) & 0xFF
            else:
                val = parse_number(body, symbols)
                if val is None:
                    raise AsmError("unresolved immediate %s" % body)
            emit(pc, OPCODES[(mn, "imm")])
            emit(pc + 1, val & 0xFF)
            pc += 2
            continue
        if op.startswith("("):
            if op.endswith(",X)"):
                base = op[1:-3].strip()
                mode = "indx"
                val = parse_number(base, symbols)
                if val is None:
                    raise AsmError("unresolved %s" % base)
                emit(pc, OPCODES[(mn, mode)])
                emit(pc + 1, val & 0xFF)
                pc += 2
                continue
            if op.endswith("),Y"):
                base = op[1:-3].strip()
                mode = "indy"
                val = parse_number(base, symbols)
                if val is None:
                    raise AsmError("unresolved %s" % base)
                emit(pc, OPCODES[(mn, mode)])
                emit(pc + 1, val & 0xFF)
                pc += 2
                continue
            base = op[1:-1].strip()
            val = parse_number(base, symbols)
            if val is None:
                raise AsmError("unresolved %s" % base)
            emit(pc, OPCODES[(mn, "ind")])
            emit(pc + 1, val & 0xFF)
            emit(pc + 2, (val >> 8) & 0xFF)
            pc += 3
            continue
        suffix = None
        base = op
        if op.endswith(",X"):
            base, suffix = op[:-2], "x"
        elif op.endswith(",Y"):
            base, suffix = op[:-2], "y"
        val = parse_number(base.strip(), symbols)
        if val is None:
            raise AsmError("unresolved operand %s" % base)
        if suffix == "x":
            mode = "zpx" if val < 0x100 else "absx"
        elif suffix == "y":
            mode = "zpy" if val < 0x100 else "absy"
        else:
            mode = "zp" if val < 0x100 else "abs"
        if (mn, mode) not in OPCODES:
            raise AsmError("unsupported %s %s" % (mn, mode))
        emit(pc, OPCODES[(mn, mode)])
        if mode in ("zp", "zpx", "zpy"):
            emit(pc + 1, val & 0xFF)
            pc += 2
        else:
            emit(pc + 1, val & 0xFF)
            emit(pc + 2, (val >> 8) & 0xFF)
            pc += 3
    return bytes(rom), symbols

