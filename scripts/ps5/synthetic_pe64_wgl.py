#!/usr/bin/env python3
"""Synthetic Win64 PE exercising the Warcraft-style WGL import path.

Entry:
  wglCreateContext(hdc)
  wglMakeCurrent(hdc, hglrc)
  wglGetProcAddress("glGetString")
  wglSwapBuffers(hdc)
and stores context/proc/swap results in .data.

No Blizzard bytes or assets are used.
"""
from pathlib import Path
import argparse
import struct

BASE = 0x140000000
TEXT_RVA = 0x1000
DATA_RVA = 0x2000
RDATA_RVA = 0x3000
IDATA_RVA = 0x4000
PDATA_RVA = 0x5000
XDATA_RVA = 0x6000

IMPORTS = (
    "wglCreateContext",
    "wglMakeCurrent",
    "wglGetProcAddress",
    "wglSwapBuffers",
)


def _rel32(code_rva: int, insn_size: int, target_rva: int) -> bytes:
    disp = target_rva - (code_rva + insn_size)
    return struct.pack("<i", disp)


def make_pe64_wgl() -> bytes:
    image = bytearray(0x1000)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x80)
    pe = 0x80
    image[pe:pe + 4] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", image, pe + 4,
                     0x8664, 6, 0, 0, 0, 0xF0, 0x0022)
    opt = pe + 24
    struct.pack_into("<H", image, opt, 0x20B)
    struct.pack_into("<III", image, opt + 4, 0x200, 0xA00, 0)
    struct.pack_into("<II", image, opt + 16, TEXT_RVA, TEXT_RVA)
    struct.pack_into("<Q", image, opt + 24, BASE)
    struct.pack_into("<II", image, opt + 32, 0x1000, 0x200)
    struct.pack_into("<HH", image, opt + 40, 6, 0)
    struct.pack_into("<HH", image, opt + 48, 6, 0)
    struct.pack_into("<II", image, opt + 56, 0x7000, 0x400)
    struct.pack_into("<HH", image, opt + 68, 3, 0)
    struct.pack_into("<QQQQ", image, opt + 72,
                     0x100000, 0x1000, 0x100000, 0x1000)
    struct.pack_into("<I", image, opt + 108, 16)

    # import, exception, and IAT directories
    struct.pack_into("<II", image, opt + 112 + 1 * 8, IDATA_RVA, 40)
    struct.pack_into("<II", image, opt + 112 + 3 * 8, PDATA_RVA, 12)
    struct.pack_into("<II", image, opt + 112 + 12 * 8, IDATA_RVA + 0x70, 40)

    table = opt + 0xF0
    sections = (
        (b".text", 0x80, TEXT_RVA, 0x200, 0x400, 0x60000020),
        (b".data", 0x18, DATA_RVA, 0x200, 0x600, 0xC0000040),
        (b".rdata", 0x20, RDATA_RVA, 0x200, 0x800, 0x40000040),
        (b".idata", 0x200, IDATA_RVA, 0x200, 0xA00, 0xC0000040),
        (b".pdata", 12, PDATA_RVA, 0x200, 0xC00, 0x40000040),
        (b".xdata", 4, XDATA_RVA, 0x200, 0xE00, 0x40000040),
    )
    for i, (name, vsize, rva, raw_size, raw_offset, flags) in enumerate(sections):
        off = table + i * 40
        image[off:off + len(name)] = name
        struct.pack_into("<IIIIIIHHI", image, off + 8,
                         vsize, rva, raw_size, raw_offset, 0, 0, 0, 0, flags)

    ilt_rva = IDATA_RVA + 0x40
    iat_rva = IDATA_RVA + 0x70
    dll_name_rva = IDATA_RVA + 0xA0
    ibn_rvas = []
    cursor = IDATA_RVA + 0xC0
    for name in IMPORTS:
        ibn_rvas.append(cursor)
        size = 2 + len(name.encode("ascii")) + 1
        cursor += (size + 1) & ~1

    # Code. RIP-relative displacements are computed from RVAs.
    code = bytearray()
    def emit(raw: bytes) -> None:
        code.extend(raw)
    def call_iat(index: int) -> None:
        rva = TEXT_RVA + len(code)
        emit(b"\xff\x15" + _rel32(rva, 6, iat_rva + index * 8))
    def store_rax(target_rva: int) -> None:
        rva = TEXT_RVA + len(code)
        emit(b"\x48\x89\x05" + _rel32(rva, 7, target_rva))
    def lea_rcx(target_rva: int) -> None:
        rva = TEXT_RVA + len(code)
        emit(b"\x48\x8d\x0d" + _rel32(rva, 7, target_rva))

    emit(b"\x48\x83\xec\x28")          # sub rsp,0x28
    emit(b"\xb9\x11\x11\x00\x00")      # mov ecx,0x1111
    call_iat(0)
    store_rax(DATA_RVA)
    emit(b"\xb9\x11\x11\x00\x00")      # mov ecx,0x1111
    emit(b"\x48\x89\xc2")                 # mov rdx,rax
    call_iat(1)
    lea_rcx(RDATA_RVA)
    call_iat(2)
    store_rax(DATA_RVA + 8)
    emit(b"\xb9\x11\x11\x00\x00")
    call_iat(3)
    store_rax(DATA_RVA + 16)
    emit(b"\x48\x83\xc4\x28")
    emit(b"\xc3")
    assert len(code) <= 0x80
    image[0x400:0x400 + len(code)] = code

    image[0x800:0x800 + len(b"glGetString\0")] = b"glGetString\0"

    # Single OPengl32 import descriptor with four entries.
    struct.pack_into("<IIIII", image, 0xA00,
                     ilt_rva, 0, 0, dll_name_rva, iat_rva)
    for i, ibn_rva in enumerate(ibn_rvas):
        struct.pack_into("<Q", image, 0xA40 + i * 8, ibn_rva)
        struct.pack_into("<Q", image, 0xA70 + i * 8, ibn_rva)
    image[0xAA0:0xAA0 + len(b"OPENGL32.dll\0")] = b"OPENGL32.dll\0"
    for rva, name in zip(ibn_rvas, IMPORTS):
        raw = 0xA00 + (rva - IDATA_RVA)
        struct.pack_into("<H", image, raw, 0)
        encoded = name.encode("ascii") + b"\0"
        image[raw + 2:raw + 2 + len(encoded)] = encoded

    struct.pack_into("<III", image, 0xC00,
                     TEXT_RVA, TEXT_RVA + len(code), XDATA_RVA)
    image[0xE00:0xE04] = b"\x01\x00\x00\x00"
    return bytes(image)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(make_pe64_wgl())
    print(f"Synthetic Win64 WGL PE written: {args.output.name}")


if __name__ == "__main__":
    main()
