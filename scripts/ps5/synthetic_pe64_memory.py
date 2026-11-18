#!/usr/bin/env python3
"""Build a synthetic Win64 PE whose one function reads/writes a RIP-relative global.

Guest function at 0x140001000:
    mov eax, dword ptr [rip + 0xffa]   ; [0x140002000]
    add eax, 1
    mov dword ptr [rip + 0xff1], eax   ; [0x140002000]
    ret
No proprietary code or data is used.
"""
from pathlib import Path
import argparse
import struct


def make_pe64_memory() -> bytes:
    image = bytearray(0xC00)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x80)
    pe = 0x80
    image[pe:pe + 4] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", image, pe + 4,
                     0x8664, 4, 0, 0, 0, 0xF0, 0x0022)
    opt = pe + 24
    struct.pack_into("<H", image, opt, 0x20B)
    struct.pack_into("<III", image, opt + 4, 0x200, 0x400, 0)
    struct.pack_into("<II", image, opt + 16, 0x1000, 0x1000)
    struct.pack_into("<Q", image, opt + 24, 0x140000000)
    struct.pack_into("<II", image, opt + 32, 0x1000, 0x200)
    struct.pack_into("<HH", image, opt + 40, 6, 0)
    struct.pack_into("<HH", image, opt + 48, 6, 0)
    struct.pack_into("<II", image, opt + 56, 0x5000, 0x400)
    struct.pack_into("<HH", image, opt + 68, 3, 0)
    struct.pack_into("<QQQQ", image, opt + 72,
                     0x100000, 0x1000, 0x100000, 0x1000)
    struct.pack_into("<I", image, opt + 108, 16)
    # IMAGE_DIRECTORY_ENTRY_EXCEPTION (.pdata)
    struct.pack_into("<II", image, opt + 112 + 3 * 8, 0x3000, 12)

    table = opt + 0xF0
    sections = (
        (b".text", 0x10, 0x1000, 0x200, 0x400, 0x60000020),
        (b".data", 4, 0x2000, 0x200, 0x600, 0xC0000040),
        (b".pdata", 12, 0x3000, 0x200, 0x800, 0x40000040),
        (b".xdata", 4, 0x4000, 0x200, 0xA00, 0x40000040),
    )
    for i, (name, vsize, rva, raw_size, raw_offset, flags) in enumerate(sections):
        off = table + i * 40
        image[off:off + len(name)] = name
        struct.pack_into("<IIIIIIHHI", image, off + 8,
                         vsize, rva, raw_size, raw_offset, 0, 0, 0, 0, flags)

    code = (
        b"\x8B\x05\xFA\x0F\x00\x00"  # mov eax,[rip+0xffa]
        b"\x83\xC0\x01"              # add eax,1
        b"\x89\x05\xF1\x0F\x00\x00"  # mov [rip+0xff1],eax
        b"\xC3"
    )
    assert len(code) == 0x10
    image[0x400:0x410] = code
    struct.pack_into("<I", image, 0x600, 41)
    struct.pack_into("<III", image, 0x800, 0x1000, 0x1010, 0x4000)
    image[0xA00:0xA04] = b"\x01\x00\x00\x00"
    return bytes(image)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(make_pe64_memory())
    print(f"Synthetic Win64 identity-memory PE written: {args.output.name}")


if __name__ == "__main__":
    main()
