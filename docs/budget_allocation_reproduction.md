# Reproduce R08 budget/candidate-resolution experiments

The study uses the existing C++ core, not a new actuator or safety policy. All work is
headless, CPU-only and synthetic. It does not run the full formal E01–E11 matrix.

From the repository root, after the build/install in README:

```powershell
$env:PYTHONPATH = (Resolve-Path python).Path
ctest --test-dir build --output-on-failure
python -m unittest discover -s tests/python -v
python -m cocommand.budget_study --stage dry-run
python -u -m cocommand.budget_study --stage all --run-dir runs/budget_allocation_v1
python tools/report_budget_study.py --run-dir runs/budget_allocation_v1 --output artifacts/research/2026-09-17-budget
```

The dry run expands 540 open-loop and 300 goal-feedback tasks on 60 fresh paired cases.
The `diagnose` stage additionally replays the 30 recorded R05 limited-short trajectories.
Individual stages: `diagnose`, `open`, `feedback`, `all`, `dry-run`.
All choices are in `configs/studies/budget_allocation_v1.yaml`; use `--config` for a new
protocol file and a new `--run-dir` for changed source/config/native identities.

The same manifest-matching directory resumes completed cases. Never replace old manifests
or delete unfavorable results to force a resume. The new source fingerprint differs from
R01–R07 because of the R08 module/config, although the native controller binary is unchanged.
Use the original source snapshots to resume older study directories; do not rewrite them.

The default diagnostic source is `runs/depth_validation_v1/R05_closed/`. The local raw
records are ignored by Git. `open` and `feedback` still require the parent study manifest
under the current provenance implementation; `diagnose` requires all raw scan/control
files. See `depth_validation_reproduction.md` for generating/restoring that source.

## Windows environment setup

```powershell
$env:PYTHONPATH = (Resolve-Path python).Path
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
python -m unittest discover -s tests/python -v
python -u -m cocommand.budget_study --stage all
python -m pip install matplotlib
python tools/report_budget_study.py
```

Before the original collection, source/config/tests/build files and the protocol were
archived as `runs/budget_allocation_v1/source_snapshot.zip`; the used native library is
`native.dll`. The public provenance file records their SHA-256 hashes and the report
generator identity. For new reproductions, archive the corresponding source and native
library under these names before invoking the report generator.

Full logs: `artifacts/test-logs/budget-study-*.log` (ignored, may contain private paths).
Raw results: `runs/budget_allocation_v1/` (ignored).
Public-safe report, case summaries, collision ledger, audits and plots:
`artifacts/research/2026-09-17-budget/`.

No numerical-convergence, real-time, hardware, human-participant, or formal-safety claim
follows from these software experiments. More computation is not an equal-cost algorithmic
improvement. Matched-exposure correction statistics compare equal elapsed time within
pairs; after trajectories diverge, they are not identical-state/identical-request comparisons.

## Separate selected-setting confirmation

The 2048-step condition was selected after exploratory discovery and frozen before the
new cohort. Preserve that distinction; do not merge discovery/confirmation into one
unqualified primary experiment. The new protocol is in `budget_confirmation_protocol.md`.

```powershell
python -u -m cocommand.budget_study --config docs/budget_allocation_confirmation_v1.yaml --stage feedback --run-dir runs/budget_confirmation_v1
python tools/report_budget_confirmation.py
```

This adds exactly 120 rollouts on 60 fresh paired initial conditions with 10 ms physics.
The native/source identity must match discovery when generating the confirmation report.
Existing matching manifests resume without new rollouts; changing the confirmation
protocol requires a new output directory.
