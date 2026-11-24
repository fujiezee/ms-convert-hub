"""Synthetic inputs: vendor files and folders by their structure, small mzML documents, a fake converter."""
from __future__ import annotations

import os
import stat
import sys
import textwrap

THERMO = b"\x01\xa1" + "Finnigan".encode("utf-16-le") + b"\x00" * 64
OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64


def spectrum(i, level=1, polarity="positive", rt=None, centroid=True, unit="minute"):
    pol = {"positive": '<cvParam cvRef="MS" accession="MS:1000130" name="positive scan" value=""/>',
           "negative": '<cvParam cvRef="MS" accession="MS:1000129" name="negative scan" value=""/>', None: ""}[polarity]
    mode = ('<cvParam cvRef="MS" accession="MS:1000127" name="centroid spectrum" value=""/>' if centroid
            else '<cvParam cvRef="MS" accession="MS:1000128" name="profile spectrum" value=""/>')
    rt = i * 0.5 if rt is None else rt
    # level 0: a UV/DAD spectrum (no MS level, no polarity)
    lvl = f'<cvParam cvRef="MS" accession="MS:1000511" name="ms level" value="{level}"/>' if level else ""
    return (f'<spectrum index="{i}" id="scan={i + 1}" defaultArrayLength="0">'
            f'{lvl}{pol}{mode}'
            f'<scanList count="1"><scan><cvParam cvRef="MS" accession="MS:1000016" name="scan start time" value="{rt}" unitName="{unit}"/></scan></scanList>'
            f'</spectrum>')


def mzml(spectra, model="MS:1000483", chromatograms=0):
    chrom = "".join(f'<chromatogram index="{i}" id="SRM {i}" defaultArrayLength="0"/>' for i in range(chromatograms))
    return ('<?xml version="1.0" encoding="utf-8"?>\n<indexedmzML xmlns="http://psi.hupo.org/ms/mzml"><mzML>'
            f'<instrumentConfigurationList count="1"><instrumentConfiguration id="IC1"><cvParam cvRef="MS" accession="{model}" name="model" value=""/></instrumentConfiguration></instrumentConfigurationList>'
            f'<run id="r"><spectrumList count="{len(spectra)}">{"".join(spectra)}</spectrumList>'
            f'<chromatogramList count="{chromatograms}">{chrom}</chromatogramList></run></mzML></indexedmzML>\n')


def fake_parser(folder, fail=False, model="MS:1003378"):
    """A ThermoRawFileParser stand-in: -i X.raw -o DIR writes DIR/X.mzML (Orbitrap Astral model term)."""
    doc = mzml([spectrum(0), spectrum(1), spectrum(2, level=2)], model=model)
    path = os.path.join(folder, "FakeParser")
    with open(path, "w") as fh:
        fh.write(textwrap.dedent(f"""\
            #!{sys.executable}
            import os, sys
            a = sys.argv[1:]
            if a == ["--version"]:
                print("9.9.9"); sys.exit(0)
            if {fail!r}:
                print("RawFileReader: file is corrupt"); sys.exit(3)
            src, out = a[a.index("-i") + 1], a[a.index("-o") + 1]
            open(os.path.join(out, os.path.basename(src)[:-4] + ".mzML"), "w").write({doc!r})
            """))
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


def make(root, name, kind):
    """Creates a synthetic input of `kind` named `name` under root; returns its path."""
    p = os.path.join(root, name)
    if kind == "thermo":
        open(p, "wb").write(THERMO)
    elif kind in ("tdf", "tsf", "baf", "agilent", "dfolder"):
        os.makedirs(p)
        f = {"tdf": "analysis.tdf", "tsf": "analysis.tsf", "baf": "analysis.baf", "agilent": "AcqData", "dfolder": "other.txt"}[kind]
        (os.makedirs if kind == "agilent" else lambda x: open(x, "w").close())(os.path.join(p, f))
    elif kind == "waters":
        os.makedirs(p)
        open(os.path.join(p, "_FUNC001.DAT"), "w").close()
        open(os.path.join(p, "_extern.inf"), "w").close()
    elif kind == "wiff":
        open(p, "wb").write(OLE2)
        open(p + ".scan", "wb").write(b"\x00")
    elif kind == "mzml":
        open(p, "w").write(mzml([spectrum(0)]))
    else:
        open(p, "wb").write(b"plain text")
    return p


def fake_msconvert(folder, samples=1, fail_vendor=False):
    """An msconvert stand-in: SRC -o DIR --mzML --filter ... writes one mzML per sample (<name>-<n>.mzML when
    several); with fail_vendor the vendor peak picking fails and cwt works."""
    doc = mzml([spectrum(0), spectrum(1), spectrum(2, level=2)])
    path = os.path.join(folder, "FakeMsconvert")
    with open(path, "w") as fh:
        fh.write(textwrap.dedent(f"""\
            #!{sys.executable}
            import os, sys
            a = sys.argv[1:]
            if "--help" in a:
                print("ProteoWizard release: 9.0.1"); sys.exit(0)
            if {fail_vendor!r} and "peakPicking vendor msLevel=1-" in a:
                print("Fatal error. 0xC0000005 at centroidScan"); sys.exit(5)
            src, out = a[0], a[a.index("-o") + 1]
            open(os.path.join(out, "input.txt"), "w").write(src)
            stem = os.path.basename(os.path.normpath(src)).rsplit(".", 1)[0]
            names = [stem + ".mzML"] if {samples} == 1 else [f"{{stem}}-{{i + 1}}.mzML" for i in range({samples})]
            for n in names:
                open(os.path.join(out, n), "w").write({doc!r})
            """))
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path
