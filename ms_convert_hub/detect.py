"""Recognise a vendor format from the file or folder itself, not from its name alone."""
from __future__ import annotations

import os
from dataclasses import dataclass

THERMO_MAGIC = b"\x01\xa1" + "Finnigan".encode("utf-16-le")


@dataclass(frozen=True)
class Format:
    """A recognised input: `kind` is the format id, `vendor` a display name, `engines` the engines that can
    convert it, best first."""
    kind: str
    vendor: str
    engines: tuple[str, ...]


FORMATS = {
    "mzml": Format("mzml", "mzML", ("copy",)),
    "thermo-raw": Format("thermo-raw", "Thermo .raw", ("thermo", "msconvert")),
    "bruker-tdf": Format("bruker-tdf", "Bruker timsTOF .d (TDF)", ("timsconvert", "msconvert")),
    "bruker-tsf": Format("bruker-tsf", "Bruker .d (TSF)", ("timsconvert", "msconvert")),
    "bruker-baf": Format("bruker-baf", "Bruker .d (BAF)", ("timsconvert", "msconvert")),
    "agilent-d": Format("agilent-d", "Agilent .d", ("msconvert",)),
    "waters-raw": Format("waters-raw", "Waters .raw", ("msconvert",)),
    "sciex-wiff": Format("sciex-wiff", "Sciex .wiff", ("msconvert",)),
    "sciex-wiff2": Format("sciex-wiff2", "Sciex .wiff2", ("msconvert",)),
    "mzxml": Format("mzxml", "mzXML", ("msconvert",)),
}


class UnknownFormat(ValueError):
    pass


def _head(path: str, n: int = 4096) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(n)


def detect(path: str) -> Format:
    """The format of `path` (a file or a vendor folder); UnknownFormat with the reason otherwise."""
    if not os.path.exists(path):
        raise UnknownFormat(f"{path}: not found")
    name = os.path.basename(os.path.normpath(path)).lower()
    if os.path.isdir(path):
        entries = {e.lower() for e in os.listdir(path)}
        if name.endswith(".d"):
            if "analysis.tdf" in entries:
                return FORMATS["bruker-tdf"]
            if "analysis.tsf" in entries:
                return FORMATS["bruker-tsf"]
            if "analysis.baf" in entries:
                return FORMATS["bruker-baf"]
            if "acqdata" in entries:
                return FORMATS["agilent-d"]
            raise UnknownFormat(f"{path}: a .d folder without analysis.tdf/tsf/baf (Bruker) or AcqData (Agilent)")
        if name.endswith(".raw"):
            if any(e.startswith("_func") and e.endswith(".dat") for e in entries):
                return FORMATS["waters-raw"]
            raise UnknownFormat(f"{path}: a .raw folder without _FUNC*.DAT (Waters)")
        raise UnknownFormat(f"{path}: a folder that is not a vendor data folder (.d or .raw)")
    head = _head(path)
    if head.startswith(THERMO_MAGIC):
        return FORMATS["thermo-raw"]
    text = head.decode("latin-1")
    if "<mzML" in text or "<indexedmzML" in text:
        return FORMATS["mzml"]
    if "<mzXML" in text:
        return FORMATS["mzxml"]
    if name.endswith(".wiff2"):
        return FORMATS["sciex-wiff2"]
    if name.endswith(".wiff"):
        # OLE2 compound document; the spectra are in <name>.wiff.scan next to it
        if not head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            raise UnknownFormat(f"{path}: not a Sciex .wiff (no compound-document header)")
        if not os.path.exists(path + ".scan"):
            raise UnknownFormat(f"{path}: the spectra file {os.path.basename(path)}.scan is missing next to it")
        return FORMATS["sciex-wiff"]
    if name.endswith(".raw"):
        raise UnknownFormat(f"{path}: a .raw file that is not Thermo (Waters .raw is a folder)")
    raise UnknownFormat(f"{path}: unknown format")
