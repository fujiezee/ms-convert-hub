"""Check an mzML after conversion: what downstream tools (XCMS, MZmine, OpenMS) rely on."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from .patch import NEW_MODELS

MS_LEVEL = "MS:1000511"
POSITIVE = "MS:1000130"
NEGATIVE = "MS:1000129"
CENTROID = "MS:1000127"
PROFILE = "MS:1000128"
SCAN_START = "MS:1000016"
UNPATCHED = {old.decode().split('"')[1] for old in NEW_MODELS}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def summarize(path: str) -> dict:
    """Counts per MS level and polarity, centroid/profile, retention time range (minutes), instrument terms."""
    levels: dict[int, int] = {}
    polarity = {"positive": 0, "negative": 0, "none": 0}
    centroid = profile = 0
    rt_min = rt_max = None
    rt_decreasing = 0
    last_rt = None
    instrument: list[str] = []
    in_instrument = False
    spectra = 0
    chromatograms = 0
    for event, el in ET.iterparse(path, events=("start", "end")):
        tag = _local(el.tag)
        if tag == "instrumentConfigurationList":
            in_instrument = event == "start"
        if event != "end":
            continue
        if tag == "cvParam" and in_instrument:
            instrument.append(el.get("accession", ""))
        if tag == "chromatogram":
            chromatograms += 1
            el.clear()
            continue
        if tag != "spectrum":
            continue
        spectra += 1
        level = None
        pol = "none"
        rt = None
        mode = None
        for p in el.iter():
            if _local(p.tag) != "cvParam":
                continue
            acc = p.get("accession")
            if acc == MS_LEVEL:
                level = int(p.get("value", "0") or 0)
            elif acc == POSITIVE:
                pol = "positive"
            elif acc == NEGATIVE:
                pol = "negative"
            elif acc == CENTROID:
                mode = "centroid"
            elif acc == PROFILE:
                mode = "profile"
            elif acc == SCAN_START and rt is None:
                value = float(p.get("value"))
                rt = value / 60 if p.get("unitName", "minute") == "second" else value
        levels[level or 0] = levels.get(level or 0, 0) + 1
        # polarity and centroiding of mass spectra only (UV/DAD spectra have neither MS level nor polarity)
        if level:
            polarity[pol] += 1
            centroid += mode == "centroid"
            profile += mode == "profile"
        if rt is not None:
            rt_min = rt if rt_min is None else min(rt_min, rt)
            rt_max = rt if rt_max is None else max(rt_max, rt)
            if last_rt is not None and rt < last_rt - 1e-9:
                rt_decreasing += 1
            last_rt = rt
        el.clear()
    return {
        "spectra": spectra,
        "chromatograms": chromatograms,
        "ms_levels": {str(k): v for k, v in sorted(levels.items())},
        "polarity": polarity,
        "centroid": centroid,
        "profile": profile,
        "rt_min": None if rt_min is None else round(rt_min, 4),
        "rt_max": None if rt_max is None else round(rt_max, 4),
        "rt_decreasing": rt_decreasing,
        "instrument_terms": sorted(set(a for a in instrument if a)),
    }


def problems(summary: dict) -> tuple[list[str], list[str]]:
    """(errors, warnings) for a summary: errors make the output unusable, warnings need a look."""
    errors, warnings = [], []
    srm = f" and {summary.get('chromatograms', 0)} chromatograms: SRM/MRM data, not for untargeted analysis" if summary.get("chromatograms") else ""
    if not summary["spectra"]:
        errors.append("no spectra" + srm)
        return errors, warnings
    if not summary["ms_levels"].get("1"):
        if summary["ms_levels"].get("2"):
            errors.append("no MS1 spectra, only MS2: targeted MS/MS data (product ion scans, MRM-HR), not for untargeted analysis")
        else:
            errors.append("no MS1 spectra" + srm)
    if summary["ms_levels"].get("0"):
        warnings.append(f"{summary['ms_levels']['0']} spectra without MS level (UV/DAD or other detectors)")
    if summary["profile"]:
        warnings.append(f"{summary['profile']} profile spectra (peak pickers such as XCMS centWave expect centroided data)")
    if summary["polarity"]["none"]:
        warnings.append(f"{summary['polarity']['none']} spectra without polarity")
    if summary["polarity"]["positive"] and summary["polarity"]["negative"]:
        warnings.append("positive and negative scans in one file (polarity switching): select one polarity downstream")
    if summary["rt_min"] is None:
        warnings.append("no retention times")
    elif summary["rt_decreasing"]:
        warnings.append(f"retention time decreases {summary['rt_decreasing']} times")
    unpatched = UNPATCHED & set(summary["instrument_terms"])
    if unpatched:
        warnings.append(f"instrument terms older readers refuse: {', '.join(sorted(unpatched))} (convert without --no-patch)")
    return errors, warnings
