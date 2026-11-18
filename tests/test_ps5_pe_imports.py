"""Import-census tests use only hand-built public PE bytes."""
from pathlib import Path
import struct
import tempfile
import unittest

from scripts.ps5.pe_probe import inspect_pe, PEFormatError


def pe64_with_imports() -> bytes:
    image = bytearray(0x600)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x80)
    pe = 0x80
    image[pe:pe + 4] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", image, pe + 4, 0x8664, 2, 0, 0, 0, 0xF0, 0x22)
    opt = pe + 24
    struct.pack_into("<H", image, opt, 0x20B)
    struct.pack_into("<I", image, opt + 4, 0x200)
    struct.pack_into("<I", image, opt + 16, 0x1000)
    struct.pack_into("<I", image, opt + 20, 0x1000)
    struct.pack_into("<Q", image, opt + 24, 0x140000000)
    struct.pack_into("<II", image, opt + 32, 0x1000, 0x200)
    struct.pack_into("<II", image, opt + 56, 0x3000, 0x200)
    struct.pack_into("<H", image, opt + 68, 3)
    struct.pack_into("<I", image, opt + 108, 16)
    # IMAGE_DIRECTORY_ENTRY_IMPORT
    struct.pack_into("<II", image, opt + 112 + 8, 0x2000, 0x100)

    table = opt + 0xF0
    sections = (
        (b".text", 6, 0x1000, 0x200, 0x200, 0x60000020),
        (b".idata", 0x200, 0x2000, 0x200, 0x400, 0xC0000040),
    )
    for i, (name, vsize, rva, raw_size, raw_offset, flags) in enumerate(sections):
        off = table + i * 40
        image[off:off + len(name)] = name
        struct.pack_into("<IIIIIIHHI", image, off + 8,
                         vsize, rva, raw_size, raw_offset, 0, 0, 0, 0, flags)

    image[0x200:0x206] = b"\xB8\x2A\x00\x00\x00\xC3"
    idata = 0x400
    # OriginalFirstThunk, TimeDateStamp, ForwarderChain, Name, FirstThunk
    struct.pack_into("<IIIII", image, idata, 0x2040, 0, 0, 0x2080, 0x2060)
    # Null descriptor follows at +20.
    ordinal = (1 << 63) | 17
    struct.pack_into("<QQQ", image, idata + 0x40, 0x2090, ordinal, 0)
    struct.pack_into("<QQQ", image, idata + 0x60, 0x2090, ordinal, 0)
    image[idata + 0x80:idata + 0x80 + len(b"KERNEL32.dll\0")] = b"KERNEL32.dll\0"
    struct.pack_into("<H", image, idata + 0x90, 0)
    image[idata + 0x92:idata + 0x92 + len(b"VirtualAlloc\0")] = b"VirtualAlloc\0"
    return bytes(image)


class PEImportProbeTest(unittest.TestCase):
    def test_named_and_ordinal_imports(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "imports.exe"
            p.write_bytes(pe64_with_imports())
            info = inspect_pe(p)
            self.assertEqual(info["import_dll_count"], 1)
            self.assertEqual(info["import_symbol_count"], 2)
            self.assertEqual(info["imports"], [{
                "dll": "KERNEL32.dll",
                "dll_normalized": "kernel32.dll",
                "runtime_area": "core",
                "count": 2,
                "symbols": ["VirtualAlloc", "#17"],
            }])

    def test_import_rva_outside_sections_fails_closed(self):
        data = bytearray(pe64_with_imports())
        opt = 0x80 + 24
        struct.pack_into("<II", data, opt + 112 + 8, 0x90000000, 0x100)
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "bad-import.exe"
            p.write_bytes(data)
            with self.assertRaises(PEFormatError):
                inspect_pe(p)

    def test_missing_import_directory_is_empty(self):
        data = bytearray(pe64_with_imports())
        opt = 0x80 + 24
        struct.pack_into("<II", data, opt + 112 + 8, 0, 0)
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "no-imports.exe"
            p.write_bytes(data)
            info = inspect_pe(p)
            self.assertEqual(info["imports"], [])
            self.assertEqual(info["import_symbol_count"], 0)


if __name__ == "__main__":
    unittest.main()
