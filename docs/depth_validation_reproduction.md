# Reproducing R05–R07

Run from the repository root, after the native build and Python setup in README.md.
This is an additional, explicitly authorized synthetic evaluation, not the full E01–E11 suite.
No real devices are connected, armed, or needed.

```powershell
$env:PYTHONPATH = (Resolve-Path python).Path
python -m unittest discover -s tests/python -v
ctest --test-dir build --output-on-failure
python -u -m cocommand.depth_study --stage all --run-dir runs/depth_validation_v1
```

Stages can be run individually: `replay`, `budget_closed`, `stress`, `mission`, `report`.
The same run directory resumes completed cases only when source/native/protocol hashes
match. With modified code, choose a **new** run directory. Do not delete old failures or
overwrite old source/native snapshots to force a resume. Timing results will vary by host.

The original R01 inputs must exist at `runs/resume_evidence_v1/evaluation/`:
study manifest, cases, and all 90 constrained-controller control/scan logs. These raw
synthetic logs are local and ignored by Git. See `focused_study_reproduction.md` for
the original frozen source and binary; do not rerun R01 using new source into its old directory.

Before a new data collection, archive `python/`, `cpp/`, `include/`, `configs/`, `tests/`,
`apps/`, `bindings/`, `cmake/`, `CMakeLists.txt` and `pyproject.toml` into the chosen run's
`source_snapshot.zip`, and copy the used native library to `native.dll` (Windows).
The checked-in protocol is `configs/studies/depth_validation_v1.yaml`.
Details and pre-execution corrections are in `depth_validation_protocol.md`.

## Audit and figures

After all stages finish, with matplotlib available:

```powershell
python tools/report_depth_study.py --run-dir runs/depth_validation_v1 --output artifacts/research/2026-09-17-depth
```

Use the same Python environment for simulation and reporting. Install the optional
plotting dependency in that environment if needed:

```powershell
python -m pip install matplotlib
$env:PYTHONPATH = (Resolve-Path python).Path
python tools/report_depth_study.py
```

Public-safe reports, trial-level summaries, collision records, audit counts and provenance
are in `artifacts/research/2026-09-17-depth/`. Private-path execution/test logs are under
ignored `artifacts/test-logs/depth-validation-*.log`. Archive this document and the report
generator with the study if moving it to another machine.

No stage constitutes a CBF implementation, continuous-time safety proof, hardware
real-time guarantee, field test, or human-participant experiment. The fixed feedback
operator is a sensitivity analysis, not a fitted model of human behavior.

## Post-analysis numerical refinement

After the primary study, run the frozen follow-up in `depth_refinement_protocol.md`:

```powershell
python -u tools/refine_depth_mission.py --physics-step 0.01
python tools/report_depth_study.py
```

The default separate output is `runs/depth_validation_refinement_v1/`. The report tool
automatically includes its completed aggregate if present. The initial report preceded
this follow-up; the final report includes all label changes. The archived source/native
are the same as R05–R07, with the refinement runner's own SHA-256 recorded separately.
