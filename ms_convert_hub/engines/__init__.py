"""Conversion engines: each wraps an existing, licensed reader; ms-convert-hub adds detection, a uniform output,
header fixes and checks."""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field

MSCONVERT_IMAGE = "proteowizard/pwiz-skyline-i-agree-to-the-vendor-licenses"


@dataclass
class Settings:
    """Where the engines are: commands on PATH by default."""
    thermo_parser: str = "ThermoRawFileParser"
    timsconvert: str = "timsconvert"
    # 'msconvert' (a native ProteoWizard install) or 'docker' (ProteoWizard's Wine image)
    msconvert: str = "msconvert"
    docker_image: str = MSCONVERT_IMAGE
    log: list[str] = field(default_factory=list)


class EngineError(RuntimeError):
    pass


def _which(cmd: str) -> str | None:
    return cmd if os.path.isfile(cmd) and os.access(cmd, os.X_OK) else shutil.which(cmd)


def _run(cmd: list[str], settings: Settings, timeout: int | None = None) -> str:
    settings.log.append("$ " + " ".join(cmd))
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout,
                           env={**os.environ, "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8")})
    except FileNotFoundError as e:
        raise EngineError(f"{cmd[0]}: not found") from e
    except subprocess.TimeoutExpired as e:
        raise EngineError(f"{cmd[0]}: no answer within {timeout} s") from e
    settings.log.append(r.stdout[-4000:])
    if r.returncode:
        tail = "\n".join(r.stdout.strip().splitlines()[-5:])
        raise EngineError(f"{os.path.basename(cmd[0])} failed ({r.returncode}): {tail}")
    return r.stdout


def _single_mzml(folder: str) -> str:
    found = glob.glob(os.path.join(folder, "**", "*.mzML"), recursive=True)
    if len(found) != 1:
        raise EngineError(f"expected one mzML from the engine, found {len(found)}")
    return found[0]


class Engine:
    name = ""
    description = ""

    def available(self, s: Settings) -> str | None:
        """None when it can run here, else the reason."""
        raise NotImplementedError

    def version(self, s: Settings) -> str:
        return ""

    def convert(self, src: str, work: str, s: Settings) -> tuple[str, list[str]]:
        """Converts `src` into the folder `work`; returns the mzML path and the command."""
        raise NotImplementedError


class Copy(Engine):
    name = "copy"
    description = "mzML input: copied, then fixed and checked"

    def available(self, s):
        return None

    def convert(self, src, work, s):
        out = os.path.join(work, "copy.mzML")
        shutil.copyfile(src, out)
        return out, ["copy", src]


class Thermo(Engine):
    name = "thermo"
    description = "Thermo .raw with ThermoRawFileParser (Thermo RawFileReader; macOS, Linux, Windows)"

    def available(self, s):
        return None if _which(s.thermo_parser) else f"ThermoRawFileParser not found ({s.thermo_parser}); --thermo-parser PATH"

    def version(self, s):
        return _run([_which(s.thermo_parser), "--version"], s, timeout=60).strip().splitlines()[-1].strip()

    def convert(self, src, work, s):
        # -f 1: mzML (not indexed); vendor centroiding is on by default
        cmd = [_which(s.thermo_parser), "-i", src, "-o", work, "-f", "1"]
        _run(cmd, s)
        return _single_mzml(work), cmd


class TimsConvert(Engine):
    name = "timsconvert"
    description = "Bruker .d (TDF, TSF, BAF) with TIMSCONVERT (Bruker TDF-SDK; Linux, Windows)"

    def available(self, s):
        return None if _which(s.timsconvert) else f"timsconvert not found ({s.timsconvert}); pip install timsconvert (not on macOS)"

    def version(self, s):
        try:
            from importlib.metadata import version
            return version("timsconvert")
        except Exception:
            return ""

    def convert(self, src, work, s):
        # centroided MS1/MS2 without the ion mobility arrays: what LC-MS feature detection reads
        cmd = [_which(s.timsconvert), "--input", src, "--outdir", work, "--mode", "centroid", "--exclude_mobility"]
        _run(cmd, s)
        return _single_mzml(work), cmd


class MsConvert(Engine):
    name = "msconvert"
    description = "ProteoWizard msconvert with the vendor readers (Windows, or its Wine image under Docker on Linux)"
    FILTER = "peakPicking vendor msLevel=1-"

    def _docker(self, s):
        return s.msconvert == "docker"

    def available(self, s):
        if self._docker(s):
            if not shutil.which("docker"):
                return "docker not found (--msconvert docker uses ProteoWizard's image)"
            return None
        return None if _which(s.msconvert) else f"msconvert not found ({s.msconvert}); --msconvert PATH or --msconvert docker"

    def version(self, s):
        cmd = (["docker", "run", "--rm", s.docker_image, "wine", "msconvert", "--help"] if self._docker(s)
               else [_which(s.msconvert), "--help"])
        try:
            text = _run(cmd, s, timeout=600)
        except EngineError:
            return ""
        m = re.search(r"ProteoWizard release:\s*(\S+)", text)
        return m.group(1) if m else ""

    def convert(self, src, work, s):
        src = os.path.abspath(src)
        folder, base = os.path.split(os.path.normpath(src))
        if self._docker(s):
            # the input's folder read-only (a .wiff needs its .wiff.scan next to it), the work folder for the output
            cmd = ["docker", "run", "--rm", "-e", "WINEDEBUG=-all", "-v", f"{folder}:/in:ro", "-v", f"{os.path.abspath(work)}:/out",
                   s.docker_image, "wine", "msconvert", f"/in/{base}", "-o", "/out", "--mzML", "--filter", self.FILTER]
        else:
            cmd = [_which(s.msconvert), src, "-o", work, "--mzML", "--filter", self.FILTER]
        _run(cmd, s)
        return _single_mzml(work), cmd


ENGINES = {e.name: e for e in (Copy(), Thermo(), TimsConvert(), MsConvert())}
