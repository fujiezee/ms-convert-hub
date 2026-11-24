# ms-convert-hub

One command to turn LC-MS vendor raw data into checked mzML.

```bash
ms-convert-hub convert data/*.raw data/*.d -o mzml/ -j 4
```

Vendor formats are closed; readers that work exist, each for some formats and some systems. ms-convert-hub
does not decode vendor files itself. It recognises the format from the file or folder, runs the best reader
available on this machine, and makes every output the same: centroided mzML, instrument terms that older
readers refuse mapped to generic ones, a check of what downstream tools rely on, and a record of how the file
was made.

## Formats and engines

| Format | Recognised by | Engines, best first |
|---|---|---|
| Thermo `.raw` | file header (`Finnigan`) | `thermo` (ThermoRawFileParser), `msconvert` |
| Bruker `.d` (TDF, TSF, BAF) | `analysis.tdf` / `.tsf` / `.baf` in the folder | `msconvert`, `timsconvert` |
| Agilent `.d` | `AcqData` in the folder | `msconvert` |
| Waters `.raw` (folder) | `_FUNC*.DAT` in the folder | `msconvert` |
| Sciex `.wiff` / `.wiff2` | compound-document header (`.wiff.scan` next to it when there is one) | `msconvert` |
| mzXML | XML root | `msconvert` |
| mzML | XML root | `copy` (fixed and checked) |

| Engine | Reader | Runs on |
|---|---|---|
| `thermo` | [ThermoRawFileParser](https://github.com/compomics/ThermoRawFileParser) (Thermo RawFileReader) | macOS, Linux, Windows |
| `timsconvert` | [TIMSCONVERT](https://github.com/gtluu/timsconvert) (Bruker TDF-SDK) | Linux, Windows; used for Bruker when msconvert cannot run (TIMSCONVERT 2.0.0 leaves out each spectrum's polarity and fails on diaPASEF data) |
| `msconvert` | [ProteoWizard](https://proteowizard.sourceforge.io) msconvert with the vendor readers | Windows; Linux with `--msconvert docker` (ProteoWizard's Wine image) |

`ms-convert-hub engines` shows which engines can run here and what is missing. `--engine` forces one; otherwise
the engines are tried in order until one succeeds (the record lists the ones that failed). msconvert uses the
vendor's centroiding and, when that fails (Waters' native centroider crashes under Wine on some files),
ProteoWizard's CWT peak picking; it keeps mass spectra only (UV/DAD spectra in the same file are dropped).
A Sciex `.wiff` holding several samples gives one mzML per sample, each checked. For timsTOF data with ion mobility
(TDF), msconvert combines the mobility scans of each frame into one spectrum (`--combineIonMobilitySpectra`):
one spectrum per mobility scan made a 15 min run of 400 MB into more than 10 GB of mzML; combined it takes
45 s and 0.7 GB, and XCMS finds peaks as in other LC-MS data.

When a conversion is stopped (Ctrl-C, or a workflow manager cancelling the task), the Docker containers it
started are killed with it; stopping the docker client alone leaves them running.

The engines are not bundled. Each reader comes under its own licence, and the vendor libraries under the
vendors' terms (the Docker image's name says you accept them); read them before using an engine.

## Output

For `<name>.raw`, `<name>.d`, `<name>.wiff`, ... the output folder gets:

- `<name>.mzML`: centroided (vendor peak picking), the instrument model and analyzer terms of newer
  instruments (Orbitrap Astral) mapped to generic terms of the same length so readers built on an older CV
  (mzR, used by XCMS) accept the file; the byte offsets of an indexed mzML stay valid.
- `<name>.conversion.json`: input, format, engine and its version, the command, the check, warnings or
  errors, the output's SHA-256 and the time taken.

An output is written only when the check finds no errors: no spectra, no MS1 (SRM/MRM data with chromatograms
only, or MS2-only targeted data, are named as such: they are not for untargeted feature detection). Warnings are listed and fail
the run with `--strict`: profile spectra, spectra without polarity, both polarities in one file (polarity
switching: select one downstream), decreasing retention times, unmapped instrument terms.

```bash
ms-convert-hub detect data/*                 # name the format of each input
ms-convert-hub check mzml/*.mzML [--json]    # the same check for any mzML
ms-convert-hub convert ... --skip-existing   # keep outputs that already have a record
```

## Install

```bash
pip install .            # Python 3.9+, no dependencies
pip install .[bruker]    # with TIMSCONVERT (Linux, Windows)
```

Then install the readers you need: ThermoRawFileParser (release archive, or `conda install -c bioconda
thermorawfileparser`), and for the other vendors msconvert on Windows or Docker with
`proteowizard/pwiz-skyline-i-agree-to-the-vendor-licenses` on Linux.

On macOS (Apple silicon) a downloaded ThermoRawFileParser that is not signed is stopped by the system; sign it
yourself (`codesign --force --sign - ThermoRawFileParser`) or use the conda package.

## Checked against

- Thermo (Orbitrap, polarity switching): 36 injections of one order converted byte-identical to
  ThermoRawFileParser 2.0.0.0 run by hand (`-f 1`).
- ProteoWizard's vendor reader test files (Bruker, Agilent, Waters, Sciex; 25 inputs) with msconvert 4.0.26299
  in Docker: every full-scan file converted; where ProteoWizard ships the reference conversion of the whole
  file (16 files), the spectra per MS level and polarity are the same; the 7 SRM/MRM and MS2-only files are
  refused with that reason; a Sciex .wiff holding several samples gives one mzML per sample.
- Real data from public repositories through an untargeted pipeline (XCMS): Bruker timsTOF PASEF (TDF, MetaboBank
  MTBKS220), negative mode, 15 min runs: 1011 MS1 spectra, polarity recorded, 935 chromatographic peaks with
  default centWave settings.

## Tests

```bash
python -m unittest discover -s tests -t .
```

## Licence

Apache License 2.0.
