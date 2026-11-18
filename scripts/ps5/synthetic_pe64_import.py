#!/usr/bin/env python3
"""Build a wholly synthetic Win64 PE that calls one imported WinAPI.

Guest entry at 0x140001000:
    sub rsp, 0x28
    call qword ptr [rip + IAT]        ; kernel32.dll!GetTickCount64
    mov qword ptr [rip + global], rax
    add rsp, 0x28
    ret

The imported handler is supplied by the native PS5 probe. No proprietary code
or data is used.
"""
from pathlib import Path
import argparse
import struct


def make_pe64_import() -> bytes:
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
    # Data directory 1: imports.
    struct.pack_into("<II", image, opt + 112 + 1 * 8, 0x3000, 40)
    # Data directory 3: exception/unwind (.pdata).
    struct.pack_into("<II", image, opt + 112 + 3 * 8, 0x4000, 12)
    # Data directory 12: IAT.
    struct.pack_into("<II", image, opt + 112 + 12 * 8, 0x3050, 16)

    table = opt + 0xF0
    sections = (
        (b".text", 0x16, 0x1000, 0x200, 0x400, 0x60000020),
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

    # call IAT @ 0x140003050; store returned RAX to .data @ 0x140002000.
    code = (
        b"\x48\x83\xEC\x28"              # sub rsp,0x28
        b"\xFF\x15\x46\x20\x00\x00"      # call qword ptr [rip+0x2046]
        b"\x48\x89\x05\xEF\x0F\x00\x00"  # mov [rip+0xfef],rax
        b"\x48\x83\xC4\x28"              # add rsp,0x28
        b"\xC3"                          # ret
    )
    assert len(code) == 0x16
    image[0x400:0x416] = code
    struct.pack_into("<Q", image, 0x600, 0)

    # IMAGE_IMPORT_DESCRIPTOR: OriginalFirstThunk, TimeDateStamp,
    # ForwarderChain, Name, FirstThunk.
    struct.pack_into("<IIIII", image, 0x800,
                     0x3040, 0, 0, 0x3080, 0x3050)
    # Null descriptor at 0x814 is already zero.
    # Import lookup table and IAT: IMAGE_IMPORT_BY_NAME RVA 0x3090.
    struct.pack_into("<QQ", image, 0x840, 0x3090, 0)
    struct.pack_into("<QQ", image, 0x850, 0x3090, 0)
    image[0x880:0x880 + len(b"KERNEL32.dll\0")] = b"KERNEL32.dll\0"
    struct.pack_into("<H", image, 0x890, 0)
    image[0x892:0x892 + len(b"GetTickCount64\0")] = b"GetTickCount64\0"

    struct.pack_into("<III", image, 0xA00, 0x1000, 0x1016, 0x5000)
    image[0xC00:0xC04] = b"\x01\x00\x00\x00"
    return bytes(image)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(make_pe64_import())
    print(f"Synthetic Win64 import PE written: {args.output.name}")


if __name__ == "__main__":
    main()
