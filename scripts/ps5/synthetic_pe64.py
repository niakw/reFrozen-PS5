#!/usr/bin/env python3
"""Build a tiny, wholly synthetic Win64 PE with valid .pdata for lifter tests.

The only instruction sequence is 'mov eax, 42; ret' (no game code).
"""
from pathlib import Path
import argparse
import struct


def make_pe64() -> bytes:
    image = bytearray(0x800)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x80)
    pe = 0x80
    image[pe:pe + 4] = b"PE\x00\x00"
    struct.pack_into("<HHIIIHH", image, pe + 4,
                     0x8664, 3, 0, 0, 0, 0xF0, 0x0022)
    opt = pe + 24
    struct.pack_into("<H", image, opt, 0x20B)
    struct.pack_into("<III", image, opt + 4, 0x200, 0x400, 0)
    struct.pack_into("<II", image, opt + 16, 0x1000, 0x1000)
    struct.pack_into("<Q", image, opt + 24, 0x140000000)
    struct.pack_into("<II", image, opt + 32, 0x1000, 0x200)
    struct.pack_into("<HH", image, opt + 40, 6, 0)
    struct.pack_into("<HH", image, opt + 48, 6, 0)
    struct.pack_into("<II", image, opt + 56, 0x4000, 0x200)
    struct.pack_into("<HH", image, opt + 68, 3, 0)
    struct.pack_into("<QQQQ", image, opt + 72, 0x100000, 0x1000, 0x100000, 0x1000)
    struct.pack_into("<I", image, opt + 108, 16)
    struct.pack_into("<II", image, opt + 112 + 3 * 8, 0x2000, 12)
    section_table = opt + 0xF0
    for i, (name, size, rva, raw_offset, characteristics) in enumerate((
        (b".text", 6, 0x1000, 0x200, 0x60000020),
        (b".pdata", 12, 0x2000, 0x400, 0x40000040),
        (b".xdata", 4, 0x3000, 0x600, 0x40000040),
    )):
        off = section_table + 40 * i
        image[off:off + len(name)] = name
        struct.pack_into("<IIIIIIHHI", image, off + 8,
                         size, rva, 0x200, raw_offset, 0, 0, 0, 0, characteristics)
    image[0x200:0x206] = b"\xB8\x2A\x00\x00\x00\xC3"
    struct.pack_into("<III", image, 0x400, 0x1000, 0x1006, 0x3000)
    image[0x600:0x604] = b"\x01\x00\x00\x00"
    return bytes(image)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(make_pe64())
    print(f"Synthetic Win64 PE fixture written: {args.output.name}")


if __name__ == "__main__":
    main()
