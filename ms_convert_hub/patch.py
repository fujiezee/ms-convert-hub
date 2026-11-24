"""Header fixes so common readers accept the mzML."""
from __future__ import annotations

# Instrument CV terms newer than the CV inside mzR / older ProteoWizard builds (which XCMS and many R tools read
# mzML with) make them refuse the file ("Invalid cvParam accession"). They are mapped to a generic term of the
# same length, so the byte offsets of an indexed mzML stay valid. Header metadata only.
NEW_MODELS = {
    b'accession="MS:1003378"': b'accession="MS:1000483"',  # Orbitrap Astral -> Thermo instrument model
    b'accession="MS:1003379"': b'accession="MS:1000084"',  # Astral analyzer -> time-of-flight
}


def patch_models(path: str, head: int = 1 << 20) -> int:
    """Replace NEW_MODELS in the first `head` bytes of `path` in place; returns the number of replacements."""
    with open(path, "r+b") as fh:
        buf = fh.read(head)
        out, n = buf, 0
        for old, new in NEW_MODELS.items():
            assert len(old) == len(new)
            n += out.count(old)
            out = out.replace(old, new)
        if n:
            fh.seek(0)
            fh.write(out)
    return n
