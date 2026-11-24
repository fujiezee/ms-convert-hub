import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from ms_convert_hub.cli import main
from ms_convert_hub.convert import convert_one, output_name
from ms_convert_hub.engines import Settings
from tests.fixtures import fake_parser, make


class Convert(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.out = os.path.join(self.dir, "out")

    def test_thermo_end_to_end(self):
        raw = make(self.dir, "S01.raw", "thermo")
        r = convert_one(raw, self.out, Settings(thermo_parser=fake_parser(self.dir)))
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["format"], r["engine"], r["engine_version"]), ("thermo-raw", "thermo", "9.9.9"))
        self.assertEqual(r["patched_terms"], 1, "Orbitrap Astral term mapped")
        self.assertEqual(r["check"]["ms_levels"], {"1": 2, "2": 1})
        self.assertEqual(sorted(os.listdir(self.out)), ["S01.conversion.json", "S01.mzML"], "no scratch folders left")
        with open(os.path.join(self.out, "S01.conversion.json")) as fh:
            self.assertEqual(json.load(fh)["sha256"], r["sha256"])
        again = convert_one(raw, self.out, Settings(thermo_parser="/nonexistent"), skip_existing=True)
        self.assertTrue(again.get("skipped"))

    def test_failures_are_recorded(self):
        raw = make(self.dir, "S02.raw", "thermo")
        r = convert_one(raw, self.out, Settings(thermo_parser=fake_parser(self.dir, fail=True)))
        self.assertFalse(r["ok"])
        self.assertRegex(r["errors"][0], "failed \\(3\\).*corrupt")
        self.assertFalse(os.path.exists(os.path.join(self.out, "S02.mzML")))
        missing = convert_one(raw, self.out, Settings(thermo_parser="/nonexistent", msconvert="/nonexistent"))
        self.assertRegex(missing["errors"][0], "no engine for Thermo .raw here")
        waters = convert_one(make(self.dir, "W.raw", "waters"), self.out, Settings(thermo_parser=fake_parser(self.dir)), engine="thermo")
        self.assertRegex(waters["errors"][0], "cannot be converted with thermo")

    def test_names(self):
        self.assertEqual([output_name(x) for x in ["a.raw", "b.d/", "c.wiff", "d.wiff2", "e.mzML"]], ["a.mzML", "b.mzML", "c.mzML", "d.mzML", "e.mzML"])

    def test_cli(self):
        raw = make(self.dir, "S03.raw", "thermo")
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["convert", raw, "-o", self.out, "--thermo-parser", fake_parser(self.dir)])
        self.assertEqual(code, 0, buf.getvalue())
        self.assertIn("ok      ", buf.getvalue())
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["convert", raw, "-o", self.out, "--thermo-parser", fake_parser(self.dir), "--strict"]), 0)
            self.assertEqual(main(["detect", make(self.dir, "x.bin", "text")]), 1)
            self.assertEqual(main(["check", os.path.join(self.out, "S03.mzML")]), 0)


if __name__ == "__main__":
    unittest.main()
