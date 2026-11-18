from pathlib import Path
import tempfile
import unittest

from scripts.ps5.x86recomp_runtime_portability import census

class RuntimeCensusTest(unittest.TestCase):
    def test_classifies_apple_and_portable_sources_without_paths(self):
        with tempfile.TemporaryDirectory(prefix="private-runtime-") as d:
            root=Path(d)
            (root/"a.cpp").write_text('#include <mach/mach_time.h>\nauto x=mach_absolute_time();\n')
            (root/"b.cpp").write_text('void f(){ clock_gettime(CLOCK_MONOTONIC, 0); socket(0,0,0); }\n')
            (root/"c.cpp").write_text('void f(){ sceKernelGetDirectMemorySize(); }\n')
            r=census(root)
            self.assertEqual(r["source_files"],3)
            self.assertEqual(r["apple_blocker_count"],1)
            self.assertEqual(r["non_apple_candidate_count"],2)
            self.assertEqual(r["apple_blocker_files"],["a.cpp"])
            self.assertIsNone(r["runtime_root"])
            self.assertNotIn(d,str(r))

if __name__=="__main__":
    unittest.main()
