# Reproducing the focused studies

## Run current code on Linux

Build using the main README, then from the repository root:

```sh
export PYTHONPATH="$PWD/python"
export COCOMMAND_NATIVE_LIB="$PWD/build/libcocommand_c.so"
python3 -m cocommand.focused_study --phase pilot --run-dir runs/reproduction/pilot --stage all
python3 -m cocommand.focused_study --phase evaluation --run-dir runs/reproduction/evaluation --stage all
python3 -m cocommand.optimization_study --source runs/reproduction/evaluation --run-dir runs/reproduction/followup --stage all
python3 -m pip install matplotlib==3.11.2
python3 tools/report_resume_study.py --root runs/reproduction --output artifacts/research/reproduction
```

The optional reporting package is not imported in the control path. Configuration and
source/native fingerprints prevent silent reuse after changes. A fresh run directory is
required if the source or binary differs. These commands are explicitly scoped studies;
they do not run the E01-E11 full matrix or connect any device.

## Exact local Windows commands used

In PowerShell, with the repository as the working directory and a Python 3.12 executable:

```powershell
$env:PYTHONPATH = (Resolve-Path 'python').Path
.tools\python\cmake\data\bin\cmake.exe --build build --parallel 2
.tools\python\cmake\data\bin\ctest.exe --test-dir build --output-on-failure
python -m unittest discover -s tests/python -v
python -m cocommand.focused_study --phase pilot --run-dir runs\resume_evidence_v1\pilot --stage all
python -m cocommand.focused_study --phase evaluation --run-dir runs\resume_evidence_v1\evaluation --stage all
python -m cocommand.optimization_study --stage all
$env:PYTHONPATH = (Resolve-Path 'python').Path + ';' + (Resolve-Path '.tools\analysis').Path
python tools\report_resume_study.py
```

The original study directories contain frozen manifests. Do not overwrite them with
new-source results; use the `runs/reproduction` commands above for a new execution.
The study-specific runners resume completed case directories only after validating their
run-level source, native binary, phase and configuration identities.

## Local immutable checkpoints

- `runs/resume_evidence_v1/r01_source_snapshot.zip`: original R01/R02 algorithm, Python,
  configuration and tests. `r01_build_support.zip` contains unchanged app/binding/toolchain
  sources needed alongside it for an isolated rebuild.
- `r01_native.dll`: exact R01/R02 desktop binary.
- `r03_source_snapshot.zip` and `r03_native.dll`: follow-up source and desktop binary.
- `evaluation/study_manifest.json` and `followup/study_manifest.json`: identities and
  protocol definitions; report-level hashes are in
  `artifacts/research/2026-09-17/provenance.json`.

R04 preserves the parent task hash for case/variant pairing. Its full identity is the
follow-up manifest plus `refinement/<case>/<controller>` and the logged 10 ms physics step;
do not use the inherited task hash alone as a cross-study cache key.

Original raw records are Git-ignored. Public-safe statistics and the claim ledger remain
under `artifacts/research/2026-09-17/`. Timing varies with machine load and compiler; command
equivalence and integration counts are the deterministic checks in this dataset.
