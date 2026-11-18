#!/usr/bin/env python3
"""Synthetic Win64 PE exercising a five-argument imported call.

Entry passes four register arguments plus one stack argument to
KERNEL32.dll!WriteFile, stores native handler RAX to .data, then returns.
No proprietary bytes are used.
"""
from pathlib import Path
import argparse
import struct


def make_pe64_abi5_import() -> bytes:
    image = bytearray(0xE00)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x80)
    pe = 0x80
    image[pe:pe + 4] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", image, pe + 4,
                     0x8664, 5, 0, 0, 0, 0xF0, 0x0022)
    opt = pe + 24
    struct.pack_into("<H", image, opt, 0x20B)
    struct.pack_into("<III", image, opt + 4, 0x200, 0x800, 0)
    struct.pack_into("<II", image, opt + 16, 0x1000, 0x1000)
    struct.pack_into("<Q", image, opt + 24, 0x140000000)
    struct.pack_into("<II", image, opt + 32, 0x1000, 0x200)
    struct.pack_into("<HH", image, opt + 40, 6, 0)
    struct.pack_into("<HH", image, opt + 48, 6, 0)
    struct.pack_into("<II", image, opt + 56, 0x6000, 0x400)
    struct.pack_into("<HH", image, opt + 68, 3, 0)
    struct.pack_into("<QQQQ", image, opt + 72,
                     0x100000, 0x1000, 0x100000, 0x1000)
    struct.pack_into("<I", image, opt + 108, 16)
    struct.pack_into("<II", image, opt + 112 + 1 * 8, 0x3000, 40)
    struct.pack_into("<II", image, opt + 112 + 3 * 8, 0x4000, 12)
    struct.pack_into("<II", image, opt + 112 + 12 * 8, 0x3050, 16)

    table = opt + 0xF0
    sections = (
        (b".text", 0x35, 0x1000, 0x200, 0x400, 0x60000020),
        (b".data", 0x08, 0x2000, 0x200, 0x600, 0xC0000040),
        (b".idata", 0xB0, 0x3000, 0x200, 0x800, 0xC0000040),
        (b".pdata", 12, 0x4000, 0x200, 0xA00, 0x40000040),
        (b".xdata", 4, 0x5000, 0x200, 0xC00, 0x40000040),
    )
    for i, (name, vsize, rva, raw_size, raw_offset, flags) in enumerate(sections):
        off = table + i * 40
        image[off:off + len(name)] = name
        struct.pack_into("<IIIIIIHHI", image, off + 8,
                         vsize, rva, raw_size, raw_offset, 0, 0, 0, 0, flags)

    code = (
        b"\x48\x83\xEC\x38"              # sub rsp,0x38
        b"\xB9\x11\x11\x00\x00"          # mov ecx,0x1111
        b"\xBA\x22\x22\x00\x00"          # mov edx,0x2222
        b"\x41\xB8\x33\x33\x00\x00"      # mov r8d,0x3333
        b"\x41\xB9\x44\x44\x00\x00"      # mov r9d,0x4444
        b"\x48\xC7\x44\x24\x20\x55\x55\x00\x00"  # [rsp+0x20]=0x5555
        b"\xFF\x15\x27\x20\x00\x00"      # call [rip+0x2027] -> IAT
        b"\x48\x89\x05\xD0\x0F\x00\x00"  # mov [rip+0xfd0],rax
        b"\x48\x83\xC4\x38"              # add rsp,0x38
        b"\xC3"
    )
    assert len(code) == 0x35
    image[0x400:0x435] = code

    struct.pack_into("<IIIII", image, 0x800,
                     0x3040, 0, 0, 0x3080, 0x3050)
    struct.pack_into("<QQ", image, 0x840, 0x3090, 0)
    struct.pack_into("<QQ", image, 0x850, 0x3090, 0)
    image[0x880:0x880 + len(b"KERNEL32.dll\0")] = b"KERNEL32.dll\0"
    struct.pack_into("<H", image, 0x890, 0)
    image[0x892:0x892 + len(b"WriteFile\0")] = b"WriteFile\0"

    struct.pack_into("<III", image, 0xA00, 0x1000, 0x1035, 0x5000)
    image[0xC00:0xC04] = b"\x01\x00\x00\x00"
    return bytes(image)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(make_pe64_abi5_import())
    print(f"Synthetic Win64 ABI5 import PE written: {args.output.name}")


if __name__ == "__main__":
    main()
