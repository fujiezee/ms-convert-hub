"""Command line: convert, detect, check, engines."""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor

from . import __version__
from .check import problems, summarize
from .convert import convert_one
from .detect import FORMATS, UnknownFormat, detect
from .engines import ENGINES, MSCONVERT_IMAGE, Settings


def _settings(a) -> Settings:
    return Settings(thermo_parser=a.thermo_parser, timsconvert=a.timsconvert, msconvert=a.msconvert, docker_image=a.docker_image)


def _engine_args(p):
    p.add_argument("--thermo-parser", default="ThermoRawFileParser", help="ThermoRawFileParser command or path")
    p.add_argument("--timsconvert", default="timsconvert", help="timsconvert command or path")
    p.add_argument("--msconvert", default="msconvert", help="msconvert command or path, or 'docker' for ProteoWizard's image")
    p.add_argument("--docker-image", default=MSCONVERT_IMAGE, help="image for --msconvert docker")


def cmd_convert(a) -> int:
    def one(src):
        return convert_one(src, a.outdir, _settings(a), engine=a.engine, patch=not a.no_patch, skip_existing=a.skip_existing)
    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        records = list(pool.map(one, a.inputs))
    failed = 0
    for r in records:
        bad = (not r["ok"]) or bool(a.strict and r.get("warnings"))
        failed += bad
        status = "skipped" if r.get("skipped") else ("FAILED" if bad else "ok")
        detail = "; ".join(r.get("errors", []) + (r.get("warnings", []) if a.strict or not r["ok"] else []))
        line = f"{status:7} {r['input']}"
        if r.get("output"):
            line += f" -> {r['output']} ({r.get('engine')}, {r['check']['spectra']} spectra, {r['seconds']} s)"
        elif r.get("outputs"):
            line += f" -> {len(r['outputs'])} samples ({r.get('engine')}, {r['seconds']} s)"
        print(line + (f": {detail}" if detail else ""))
        for w in r.get("warnings", []) if r["ok"] and not a.strict else []:
            print(f"        warning: {w}")
    return 1 if failed else 0


def cmd_detect(a) -> int:
    bad = 0
    for path in a.inputs:
        try:
            f = detect(path)
            print(f"{path}\t{f.kind}\t{f.vendor}\t{', '.join(f.engines)}")
        except UnknownFormat as e:
            bad += 1
            print(f"{path}\t-\t{e}")
    return 1 if bad else 0


def cmd_check(a) -> int:
    bad = 0
    for path in a.inputs:
        s = summarize(path)
        errors, warnings = problems(s)
        bad += bool(errors) or (a.strict and bool(warnings))
        if a.json:
            print(json.dumps({"file": path, "check": s, "errors": errors, "warnings": warnings}, ensure_ascii=False))
        else:
            print(f"{path}: {s['spectra']} spectra, MS levels {s['ms_levels']}, polarity {s['polarity']}, "
                  f"RT {s['rt_min']}-{s['rt_max']} min, centroid {s['centroid']} / profile {s['profile']}")
            for e in errors:
                print(f"  error: {e}")
            for w in warnings:
                print(f"  warning: {w}")
    return 1 if bad else 0


def cmd_engines(a) -> int:
    s = _settings(a)
    for name, e in ENGINES.items():
        reason = e.available(s)
        formats = [f.vendor for f in FORMATS.values() if name in f.engines]
        print(f"{name:12} {'ready' if reason is None else 'missing'}  {e.description}")
        print(f"{'':12} formats: {', '.join(formats)}" + (f"\n{'':12} {reason}" if reason else ""))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ms-convert-hub", description="LC-MS vendor raw data to checked mzML")
    p.add_argument("--version", action="version", version=f"ms-convert-hub {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("convert", help="convert files or vendor folders to mzML")
    c.add_argument("inputs", nargs="+")
    c.add_argument("-o", "--outdir", required=True)
    c.add_argument("--engine", choices=sorted(ENGINES), help="force an engine (default: the best one available)")
    c.add_argument("--no-patch", action="store_true", help="keep instrument terms older readers refuse")
    c.add_argument("--strict", action="store_true", help="fail on warnings too")
    c.add_argument("--skip-existing", action="store_true", help="keep outputs that already have a record")
    c.add_argument("-j", "--jobs", type=int, default=1, help="files converted at once")
    _engine_args(c)
    c.set_defaults(func=cmd_convert)

    d = sub.add_parser("detect", help="name the format of files or folders")
    d.add_argument("inputs", nargs="+")
    d.set_defaults(func=cmd_detect)

    k = sub.add_parser("check", help="check mzML files")
    k.add_argument("inputs", nargs="+")
    k.add_argument("--strict", action="store_true")
    k.add_argument("--json", action="store_true")
    k.set_defaults(func=cmd_check)

    e = sub.add_parser("engines", help="which engines can run here")
    _engine_args(e)
    e.set_defaults(func=cmd_engines)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
