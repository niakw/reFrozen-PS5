"""Synthetic PE fixture tests; never use proprietary game bytes."""
from pathlib import Path
import hashlib
import struct
import tempfile
import unittest

from scripts.ps5.pe_probe import (inspect_pe, PEFormatError, _graphics_profile,
                                  _scan_com_guid_markers, _scan_fixed_file_info)


def synthetic_pe(machine: int, bits: int) -> bytes:
    dos = bytearray(128)
    dos[:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 128)
    optional = bytearray(240 if bits == 64 else 224)
    struct.pack_into("<H", optional, 0, 0x20B if bits == 64 else 0x10B)
    struct.pack_into("<I" if bits == 32 else "<Q", optional, 28 if bits == 32 else 24,
                     0x400000 if bits == 32 else 0x140000000)
    struct.pack_into("<I", optional, 56, 0x30000)
    struct.pack_into("<H", optional, 68, 2)
    coff = struct.pack("<HHIIIHH", machine, 1, 123456, 0, 0, len(optional), 0)
    section = bytearray(40)
    section[:5] = b".text"
    return bytes(dos) + b"PE\0\0" + coff + optional + bytes(section)


class PEProbeTest(unittest.TestCase):
    def test_x86_and_x86_64(self):
        with tempfile.TemporaryDirectory() as temp:
            for machine, bits in ((0x14C, 32), (0x8664, 64)):
                p = Path(temp) / ("guest%d.exe" % bits)
                data = synthetic_pe(machine, bits)
                p.write_bytes(data)
                result = inspect_pe(p)
                self.assertEqual(result["pe_bits"], bits)
                self.assertEqual(result["machine"], "x86" if bits == 32 else "x86_64")
                self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())
                self.assertEqual(result["image_size"], 0x30000)
                self.assertEqual(result["sections"], [".text"])
                self.assertIsNone(result["warcraft_version"])
                self.assertNotIn(str(Path(temp)), str(result))

    def test_graphics_profile_is_evidence_based(self):
        opengl = _graphics_profile([
            {"dll_normalized": "kernel32.dll"},
            {"dll_normalized": "opengl32.dll"},
            {"dll_normalized": "user32.dll"},
        ])
        self.assertEqual(opengl["static_backends"], [
            {"backend": "opengl", "dlls": ["opengl32.dll"]}
        ])
        self.assertEqual(opengl["ps5_initial_route"], "opengl_wgl_to_ps5_egl")
        self.assertEqual(opengl["confidence"], "imports_only")

        d3d11 = _graphics_profile([
            {"dll_normalized": "d3d11.dll"},
            {"dll_normalized": "dxgi.dll"},
        ])
        self.assertEqual(
            [item["backend"] for item in d3d11["static_backends"]],
            ["direct3d11"],
        )
        self.assertEqual(
            d3d11["static_backends"][0]["dlls"],
            ["d3d11.dll", "dxgi.dll"],
        )
        self.assertEqual(
            d3d11["ps5_initial_route"],
            "renderer_translation_or_runtime_forcing_required",
        )

        dynamic = _graphics_profile([{"dll_normalized": "kernel32.dll"}])
        self.assertEqual(dynamic["static_backends"], [])
        self.assertEqual(
            dynamic["ps5_initial_route"],
            "undetermined_dynamic_renderer_possible",
        )

    def test_fixed_file_info_is_advisory_and_rsrc_only(self):
        fixed = struct.pack(
            "<13I",
            0xFEEF04BD, 0x00010000,
            (1 << 16) | 31, (1 << 16) | 12164,
            (1 << 16) | 31, (1 << 16) | 12164,
            0x3F, 0, 0x00040004, 1, 0, 0, 0,
        )
        prefix = b"X" * 48
        raw = prefix + fixed + b"Y" * 32
        sections = [{
            "name": ".rsrc", "raw_offset": len(prefix),
            "raw_size": len(fixed) + 32,
        }]
        info = _scan_fixed_file_info(raw, sections)
        self.assertIsNotNone(info)
        self.assertEqual(info["file_version"], "1.31.1.12164")
        self.assertEqual(info["product_version"], "1.31.1.12164")
        self.assertEqual(
            info["trust"], "advisory_metadata_sha256_remains_authoritative")
        self.assertIsNone(_scan_fixed_file_info(
            raw, [{**sections[0], "name": ".data"}]))

        damaged = bytearray(fixed)
        struct.pack_into("<I", damaged, 4, 0x00020000)
        self.assertIsNone(_scan_fixed_file_info(
            prefix + damaged,
            [{"name": ".rsrc", "raw_offset": len(prefix),
              "raw_size": len(damaged)}],
        ))

    def test_com_guid_markers_report_only_counts_and_sections(self):
        wasapi = bytes.fromhex("9503debc2fe57c468e3dc4579291692e")
        xaudio = bytes.fromhex("8586505a54a2ba4f9b829a24b00306af")
        raw = b"X" * 64 + wasapi + b"Y" * 32 + xaudio + b"Z" * 32 + wasapi
        sections = [
            {
                "name": ".rdata", "raw_offset": 64,
                "raw_size": len(wasapi) + 32 + len(xaudio),
            },
            {
                "name": ".data",
                "raw_offset": 64 + len(wasapi) + 32 + len(xaudio),
                "raw_size": 32 + len(wasapi),
            },
        ]
        markers = _scan_com_guid_markers(raw, sections)
        by_name = {item["name"]: item for item in markers}
        self.assertEqual(by_name["wasapi_mmdevice_enumerator"]["count"], 2)
        self.assertEqual(
            by_name["wasapi_mmdevice_enumerator"]["sections"],
            [".data", ".rdata"],
        )
        self.assertEqual(by_name["xaudio2_27"]["count"], 1)
        self.assertEqual(by_name["xaudio2_27"]["sections"], [".rdata"])
        self.assertNotIn("offset", str(markers).lower())
        self.assertNotIn("raw", str(markers).lower())

    def test_bad_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "bad.dll"
            for data in (b"", b"MZ", b"X" * 512,
                         b"MZ" + b"\0" * 58 + struct.pack("<I", 0xFFFFFFFF),
                         synthetic_pe(0x14C, 32)[:-1]):
                p.write_bytes(data)
                with self.assertRaises(PEFormatError):
                    inspect_pe(p)
            data = bytearray(synthetic_pe(0x14C, 32))
            struct.pack_into("<H", data, 128 + 4 + 2, 0)
            p.write_bytes(data)
            with self.assertRaises(PEFormatError):
                inspect_pe(p)


if __name__ == "__main__":
    unittest.main()
