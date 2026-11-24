"""detect -> engine -> mzML -> header fixes -> check -> record."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time

from . import __version__
from .check import problems, summarize
from .detect import detect
from .engines import ENGINES, EngineError, Settings
from .patch import patch_models

STEM = re.compile(r"\.(raw|d|wiff2?|mzml|mzxml)$", re.I)


def output_name(src: str) -> str:
    """<name>.mzML for <name>.raw, <name>.d, <name>.wiff, ..."""
    return STEM.sub("", os.path.basename(os.path.normpath(src))) + ".mzML"


def choose(fmt, engine: str | None, s: Settings):
    """The engine to use: the one asked for, else the first of the format's engines that can run here."""
    if engine:
        if engine not in fmt.engines:
            raise EngineError(f"{fmt.vendor} cannot be converted with {engine} (use {', '.join(fmt.engines)})")
        e = ENGINES[engine]
        reason = e.available(s)
        if reason:
            raise EngineError(reason)
        return e
    reasons = []
    for name in fmt.engines:
        reason = ENGINES[name].available(s)
        if reason is None:
            return ENGINES[name]
        reasons.append(reason)
    raise EngineError(f"no engine for {fmt.vendor} here: " + "; ".join(reasons))


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_one(src: str, outdir: str, s: Settings, engine: str | None = None, patch: bool = True,
                skip_existing: bool = False) -> dict:
    """Converts one input into outdir/<name>.mzML with outdir/<name>.conversion.json; returns the record."""
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, output_name(src))
    record_file = out[:-len(".mzML")] + ".conversion.json"
    if skip_existing and os.path.exists(out) and os.path.exists(record_file):
        with open(record_file) as fh:
            return {**json.load(fh), "skipped": True}
    started = time.time()
    record = {"tool": f"ms-convert-hub {__version__}", "input": os.path.abspath(src)}
    s.log.clear()
    try:
        fmt = detect(src)
        e = choose(fmt, engine, s)
        record.update(format=fmt.kind, vendor=fmt.vendor, engine=e.name, engine_version=e.version(s))
        with tempfile.TemporaryDirectory(prefix=".ms-convert-hub-", dir=outdir) as work:
            produced, cmd = e.convert(src, work, s)
            record["command"] = cmd
            record["patched_terms"] = patch_models(produced) if patch else 0
            summary = summarize(produced)
            errors, warnings = problems(summary)
            record.update(check=summary, errors=errors, warnings=warnings)
            if not errors:
                shutil.move(produced, out)
                record.update(output=os.path.abspath(out), sha256=sha256(out))
    except Exception as err:  # noqa: BLE001 - every failure becomes the record's error
        record.setdefault("errors", []).append(str(err))
        record["log"] = s.log[-6:]
    record["seconds"] = round(time.time() - started, 1)
    record["ok"] = not record.get("errors")
    with open(record_file, "w") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
    return record
