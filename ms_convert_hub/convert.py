"""detect -> engine (the next one when it fails) -> mzML per sample -> header fixes -> check -> record."""
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


def candidates(fmt, engine: str | None, s: Settings) -> list:
    """Engines to try in order: the one asked for, else every engine of the format that can run here."""
    if engine:
        if engine not in fmt.engines:
            raise EngineError(f"{fmt.vendor} cannot be converted with {engine} (use {', '.join(fmt.engines)})")
        reason = ENGINES[engine].available(s)
        if reason:
            raise EngineError(reason)
        return [ENGINES[engine]]
    ready, reasons = [], []
    for name in fmt.engines:
        reason = ENGINES[name].available(s)
        (reasons.append(reason) if reason else ready.append(ENGINES[name]))
    if not ready:
        raise EngineError(f"no engine for {fmt.vendor} here: " + "; ".join(reasons))
    return ready


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _finish(produced: str, out: str, patch: bool) -> dict:
    """Header fixes and check of one produced mzML; moved to `out` when the check finds no errors."""
    entry = {"patched_terms": patch_models(produced) if patch else 0}
    summary = summarize(produced)
    errors, warnings = problems(summary)
    entry.update(check=summary, errors=errors, warnings=warnings)
    if not errors:
        shutil.move(produced, out)
        entry.update(output=os.path.abspath(out), sha256=sha256(out))
    return entry


def convert_one(src: str, outdir: str, s: Settings, engine: str | None = None, patch: bool = True,
                skip_existing: bool = False) -> dict:
    """Converts one input into outdir/<name>.mzML (or one mzML per sample, named by the engine, when the input
    holds several) with outdir/<name>.conversion.json; returns the record."""
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, output_name(src))
    record_file = out[:-len(".mzML")] + ".conversion.json"
    if skip_existing and os.path.exists(record_file):
        with open(record_file) as fh:
            old = json.load(fh)
        if old.get("ok") and all(os.path.exists(p) for p in ([old["output"]] if old.get("output") else old.get("outputs", []))):
            return {**old, "skipped": True}
    started = time.time()
    record = {"tool": f"ms-convert-hub {__version__}", "input": os.path.abspath(src)}
    s.log.clear()
    try:
        fmt = detect(src)
        record.update(format=fmt.kind, vendor=fmt.vendor)
        attempts = []
        with tempfile.TemporaryDirectory(prefix=".ms-convert-hub-", dir=outdir) as work:
            for e in candidates(fmt, engine, s):
                try:
                    produced, cmd, notes = e.convert(src, work, s)
                except EngineError as err:
                    attempts.append(f"{e.name}: {str(err).splitlines()[0][:300]}")
                    continue
                record.update(engine=e.name, engine_version=e.version(s), command=cmd, **notes)
                break
            else:
                raise EngineError("every engine failed: " + " | ".join(attempts))
            if attempts:
                record["failed_engines"] = attempts
            if len(produced) == 1:
                record.update(_finish(produced[0], out, patch))
            else:
                # one input, several samples (a Sciex .wiff of a batch): each sample checked on its own
                samples = [{"name": os.path.basename(p), **_finish(p, os.path.join(outdir, os.path.basename(p)), patch)} for p in produced]
                record["samples"] = samples
                record["outputs"] = [x["output"] for x in samples if x.get("output")]
                record["errors"] = [f"{x['name']}: {m}" for x in samples for m in x["errors"]]
                record["warnings"] = [f"{x['name']}: {m}" for x in samples for m in x["warnings"]]
    except Exception as err:  # noqa: BLE001 - every failure becomes the record's error
        record.setdefault("errors", []).append(str(err))
        record["log"] = s.log[-6:]
    record["seconds"] = round(time.time() - started, 1)
    record["ok"] = not record.get("errors")
    with open(record_file, "w") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
    return record
