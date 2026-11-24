import os
import tempfile
import unittest

from ms_convert_hub.check import problems, summarize
from ms_convert_hub.patch import patch_models
from tests.fixtures import mzml, spectrum


def write(doc):
    fd, path = tempfile.mkstemp(suffix=".mzML")
    os.write(fd, doc.encode())
    os.close(fd)
    return path


class Check(unittest.TestCase):
    def test_summary(self):
        path = write(mzml([spectrum(0), spectrum(1, polarity="negative"), spectrum(2, level=2), spectrum(3, rt=90, unit="second")]))
        s = summarize(path)
        self.assertEqual(s["spectra"], 4)
        self.assertEqual(s["ms_levels"], {"1": 3, "2": 1})
        self.assertEqual(s["polarity"], {"positive": 3, "negative": 1, "none": 0})
        self.assertEqual((s["rt_min"], s["rt_max"]), (0.0, 1.5))
        self.assertEqual(s["instrument_terms"], ["MS:1000483"])
        errors, warnings = problems(s)
        self.assertEqual(errors, [])
        self.assertTrue(any("polarity switching" in w for w in warnings))

    def test_problems(self):
        self.assertEqual(problems(summarize(write(mzml([]))))[0], ["no spectra"])
        self.assertRegex(problems(summarize(write(mzml([spectrum(0, level=2)]))))[0][0], "^no MS1 spectra")
        _, w = problems(summarize(write(mzml([spectrum(0, centroid=False), spectrum(1, polarity=None), spectrum(2, rt=0)]))))
        self.assertTrue(any("profile" in x for x in w) and any("without polarity" in x for x in w) and any("decreases" in x for x in w))
        _, w = problems(summarize(write(mzml([spectrum(0)], model="MS:1003378"))))
        self.assertTrue(any("MS:1003378" in x for x in w))

    def test_srm_and_uv(self):
        # SRM/MRM: chromatograms only
        errors, _ = problems(summarize(write(mzml([], chromatograms=8))))
        self.assertEqual(errors, ["no spectra and 8 chromatograms: SRM/MRM data, not for untargeted analysis"])
        errors, _ = problems(summarize(write(mzml([spectrum(0, level=2), spectrum(1, level=2)], chromatograms=1))))
        self.assertRegex(errors[0], "only MS2: targeted MS/MS data")
        # UV/DAD spectra next to the mass spectra: counted apart, not as profile or polarity-less mass spectra
        s = summarize(write(mzml([spectrum(0), spectrum(1, level=0, polarity=None, centroid=False), spectrum(2)])))
        self.assertEqual((s["ms_levels"], s["polarity"]["none"], s["profile"]), ({"0": 1, "1": 2}, 0, 0))
        self.assertEqual(problems(s)[1], ["1 spectra without MS level (UV/DAD or other detectors)"])

    def test_patch_keeps_length_and_is_idempotent(self):
        path = write(mzml([spectrum(0)], model="MS:1003378"))
        size = os.path.getsize(path)
        self.assertEqual(patch_models(path), 1)
        self.assertEqual(os.path.getsize(path), size)
        self.assertEqual(summarize(path)["instrument_terms"], ["MS:1000483"])
        self.assertEqual(patch_models(path), 0)


if __name__ == "__main__":
    unittest.main()
