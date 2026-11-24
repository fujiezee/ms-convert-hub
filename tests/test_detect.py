import os
import tempfile
import unittest

from ms_convert_hub.detect import UnknownFormat, detect
from tests.fixtures import make


class Detect(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_formats_by_content_and_structure(self):
        cases = [("a.raw", "thermo", "thermo-raw"), ("b.RAW", "thermo", "thermo-raw"), ("c.d", "tdf", "bruker-tdf"),
                 ("d.d", "tsf", "bruker-tsf"), ("e.d", "baf", "bruker-baf"), ("f.d", "agilent", "agilent-d"),
                 ("g.raw", "waters", "waters-raw"), ("h.wiff", "wiff", "sciex-wiff"), ("i.mzML", "mzml", "mzml"),
                 ("named.txt", "thermo", "thermo-raw")]
        for name, kind, expect in cases:
            with self.subTest(name=name):
                self.assertEqual(detect(make(self.dir, name, kind)).kind, expect)

    def test_engines_best_first(self):
        self.assertEqual(detect(make(self.dir, "a.raw", "thermo")).engines, ("thermo", "msconvert"))
        self.assertEqual(detect(make(self.dir, "c.d", "tdf")).engines, ("timsconvert", "msconvert"))
        self.assertEqual(detect(make(self.dir, "g.raw", "waters")).engines, ("msconvert",))

    def test_refused_with_the_reason(self):
        cases = [("x.raw", "text", "not Thermo"), ("y.d", "dfolder", "without analysis"), ("z.bin", "text", "unknown format"),
                 ("missing.raw", None, "not found")]
        for name, kind, reason in cases:
            with self.subTest(name=name):
                path = make(self.dir, name, kind) if kind else os.path.join(self.dir, name)
                with self.assertRaisesRegex(UnknownFormat, reason):
                    detect(path)
        w = make(self.dir, "lone.wiff", "wiff")
        os.remove(w + ".scan")
        with self.assertRaisesRegex(UnknownFormat, r"lone\.wiff\.scan is missing"):
            detect(w)


if __name__ == "__main__":
    unittest.main()
