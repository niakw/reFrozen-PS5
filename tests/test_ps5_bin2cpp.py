"""Tests for the public synthetic binary embedding helper."""
import unittest

from scripts.ps5.bin2cpp import emit_cpp


class Bin2CppTest(unittest.TestCase):
    def test_deterministic_bytes_and_size_symbol(self):
        result = emit_cpp(b"\x00\x7f\xff", "g_fixture")
        self.assertIn("0x00, 0x7f, 0xff,", result)
        self.assertIn('extern "C" const unsigned char g_fixture[]', result)
        self.assertIn('extern "C" const std::size_t g_fixture_size = sizeof(g_fixture);', result)
        self.assertEqual(result, emit_cpp(b"\x00\x7f\xff", "g_fixture"))

    def test_rejects_invalid_symbol(self):
        for name in ("", "1bad", "bad-name", "bad name"):
            with self.assertRaises(ValueError):
                emit_cpp(b"x", name)


if __name__ == "__main__":
    unittest.main()
