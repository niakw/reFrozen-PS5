"""Export/ordinal census tests use only hand-built synthetic PE bytes."""
from pathlib import Path
import struct
import tempfile
import unittest

from scripts.ps5.pe_probe import inspect_pe, PEFormatError


def pe64_with_exports() -> bytes:
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
    # IMAGE_DIRECTORY_ENTRY_EXPORT.
    struct.pack_into("<II", image, opt + 112, 0x2000, 0x100)

    table = opt + 0xF0
    for i, (name, vsize, rva, raw_size, raw_offset, flags) in enumerate((
        (b".text", 6, 0x1000, 0x200, 0x200, 0x60000020),
        (b".edata", 0x200, 0x2000, 0x200, 0x400, 0x40000040),
    )):
        off = table + i * 40
        image[off:off + len(name)] = name
        struct.pack_into("<IIIIIIHHI", image, off + 8,
                         vsize, rva, raw_size, raw_offset, 0, 0, 0, 0, flags)

    image[0x200:0x206] = b"\xB8\x2A\x00\x00\x00\xC3"
    edata = 0x400
    # IMAGE_EXPORT_DIRECTORY.
    struct.pack_into("<IIHHIIIIIII", image, edata,
                     0, 0, 0, 0, 0x2080, 10, 2, 1, 0x2040, 0x2050, 0x2058)
    struct.pack_into("<II", image, edata + 0x40, 0x1000, 0x2090)
    struct.pack_into("<I", image, edata + 0x50, 0x2070)
    struct.pack_into("<H", image, edata + 0x58, 0)
    image[edata + 0x70:edata + 0x70 + len(b"Answer\0")] = b"Answer\0"
    image[edata + 0x80:edata + 0x80 + len(b"synthetic.dll\0")] = b"synthetic.dll\0"
    image[edata + 0x90:edata + 0x90 + len(b"KERNEL32.Sleep\0")] = b"KERNEL32.Sleep\0"
    return bytes(image)


class PEExportProbeTest(unittest.TestCase):
    def test_named_ordinal_and_forwarded_exports(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "exports.dll"
            p.write_bytes(pe64_with_exports())
            info = inspect_pe(p)
            self.assertEqual(info["export_symbol_count"], 2)
            self.assertEqual(info["exports"], [
                {"name": "Answer", "ordinal": 10, "rva": "0x1000", "forwarder": None},
                {"name": None, "ordinal": 11, "rva": "0x2090",
                 "forwarder": "KERNEL32.Sleep"},
            ])

    def test_bad_export_name_ordinal_fails_closed(self):
        data = bytearray(pe64_with_exports())
        # .edata raw + AddressOfNameOrdinals offset.
        struct.pack_into("<H", data, 0x400 + 0x58, 9)
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "bad-exports.dll"
            p.write_bytes(data)
            with self.assertRaises(PEFormatError):
                inspect_pe(p)


if __name__ == "__main__":
    unittest.main()
