# Implementation status

This file is evidence-oriented. `implemented_and_tested` means a listed command completed in the recorded environment; it does not mean real-vessel validation.

## 2026-09-19 update - concise English research report

- Created `output/pdf/CoCommand_USV_IEEE_Report.pdf`: six-page IEEE-style English report,
  author Zhang YUE, date Sep, 2026, three experiment figures and five tables.
- The three main contributions match the existing CV evidence: authority-consistent
  prediction, complete-witness early termination, and fixed-budget candidate resolution.
- Packaged original statistics, case summaries, provenance and audits; preserved original
  figures and generated print-sized redraws for the supplemental/budget figures.
- Report build, PDF rendering and report verification exited 0. All 17 headline/structure
  assertions and 22 source SHA-256 comparisons passed; six pages visually reviewed.
- Editable manuscript/layout source and captured build/render output are in `output/pdf/`.
  Detailed evidence: `output/pdf/QA_LOG.md` and `output/pdf/verification_logs/`.
- Report-only change: no controller modifications, new experiments, hardware activity,
  GitHub push, or change to the previously recorded board/field validation status.

## 2026-09-17 update — R08 budget/resolution study and fresh-seed confirmation

- Status: `implemented_and_tested` for scoped desktop synthetic experiments, no new C++ logic.
- Added configurable R08 runner, recorded-failure replay, frozen discovery and confirmation
  protocols, paired/family-stratified statistics, audits, figures and four tests (29 Python total).
- Completed 840 discovery rollouts on 60 fresh paired initial conditions and 120 confirmation
  rollouts on another 60 fresh paired initial conditions. No runtime failure records.
- Diagnostic replay reproduced all 3,341 R05 limited-short decisions exactly. Of 947 original
  unknown returns, a generous-budget same-state reference found 48 complete witnesses and
  exhaustively rejected 899. This is not a counterfactual closed-loop collision-prevention proof.
- Discovery primary 512-step goal comparison was negative: 4/60 goals for both 2° and 4°
  grids. Secondary 2048-step goals were 9/60 versus 47/60. All tested budgets remain reported.
- Fixed 2048-step follow-up before new outcomes: 60 disjoint-seed pairs at 10 ms physics
  again gave 9/60 versus 47/60 goals, collisions 51/60 versus 13/60. Goal-rate gain 63.33 pp,
  family-stratified case-bootstrap 95% [53.33,73.33] pp. This is a selected-setting validation,
  not evidence that 2048 was the original primary endpoint or that coarse grids always win.
- Intervention cost in confirmation: matched-exposure mean steering correction 5.043°→13.229°,
  paired increase 8.186° [6.805,9.514]. The candidate set changes; no equal minimum-modification
  claim across grids and no online adaptive resolution policy has been implemented.
- Across all 131,115 new cycles: zero invalid/incomplete accepted witnesses, throttle-authority
  violations, step-cap violations, exact-input acceptance violations or alignment errors.
  Generous-budget early-stop/exhaustive variants also matched over 12,000 new cycles.
- CTest and all 29 Python tests passed (exit 0). Discovery, confirmation and both report
  commands completed with exit 0. Native SHA-256 remains
  `135977e324509ad3b32360ddf4015ad4b041e10176788651edc9556e58e56073`.
- Source/config fingerprint `dd7f17fad0198b2b`; discovery source snapshot SHA-256:
  `d610e75d06c6333db82a7b5df9bc4c24eefc0a3d6af6d0a80ce86c72b92a9d56`.
- Raw records: `runs/budget_allocation_v1/`, `runs/budget_confirmation_v1/`.
  Public-safe report, separate confirmation, audits, bilingual explanation and three CV bullets:
  `artifacts/research/2026-09-17-budget/`. Logs: `artifacts/test-logs/budget-*.log`.
- No physical hardware, human subjects, full formal matrix, safety theorem or GitHub push.

## 2026-09-17 update — deeper validation R05–R07

- Status: `implemented_and_tested` for the new desktop synthetic study and numerical follow-up.
- Added a frozen finite-budget/stress/operator-model protocol, configurable stage runner,
  ego-only goal-feedback script, physics-substep goal termination, case-level reports,
  independent record audits, and six Python tests (25 total now).
- Completed 600 primary rollouts: 60 finite-budget, 300 held-out stress, 240 two-by-two
  operator/filter runs. Completed another 120 goal-feedback rollouts at 10 ms physics.
  Repeated configurations/refinement are not additional independent initial conditions.
- R05 replay: 270,900 calls across deterministic/soft-time budgets and repeats. At the
  preregistered 512-step budget, full witnesses increased from 4,655/18,000 (25.86%) to
  16,862/18,000 (93.68%); no invalid accepted witnesses, accepted/reference command
  mismatches, or integration-budget overshoots. The exhaustive comparator waits for its
  maximum-clearance backup; short-circuit accepts existence and can choose another backup.
- Closed-loop 512-step collisions were 20/30 versus 19/30. This does NOT establish a
  meaningful collision reduction from faster search. Soft deadlines can overrun and
  are not hard real-time guarantees; all overrun records are retained.
- New stress collisions: 35/100 hypothetical versus 25/100 constrained; both variants
  collided in all 20 very-late static encounters. Optimized/unoptimized constrained
  controls and states matched across 19,314 corresponding cycles.
- R07 with the same ego-only goal-feedback policy: goals 29/60 versus 52/60; collisions
  31/60 versus 5/60; timeouts 0 versus 3. With the original open-loop input, both methods
  reached zero goals (collisions 15 versus 0). These are scripted operators, not people.
- Refinement 20→10 ms retained every goal classification but changed three constrained
  collision/timeout labels (total collisions 5→4). Maximum per-case minimum-gap difference
  was 1.314 m. Numerical convergence is NOT established; all discrepancies remain public.
- All 720 executions completed without runtime failures. The primary 123,593 control
  records contain zero throttle violations, invalid accepted witnesses, or observation
  sequence alignment errors. A pre-run seed-overlap test initially failed and was fixed
  before outcomes; both the failed log and passing rerun remain saved.
- Native CTest and all 25 Python tests passed (exit 0). Study, refinement, and report
  commands completed with exit 0. No C++ controller behavior was changed in this extension.
- Raw data: `runs/depth_validation_v1/`, `runs/depth_validation_refinement_v1/`.
  Source fingerprint: `42881402c170e6b0`; frozen native SHA-256:
  `135977e324509ad3b32360ddf4015ad4b041e10176788651edc9556e58e56073`.
- Reports, audits, bilingual CV text and limitations:
  `artifacts/research/2026-09-17-depth/`. Reproduction:
  `docs/depth_validation_reproduction.md`, `docs/depth_refinement_protocol.md`.
- Full formal matrix, hardware, field and participant studies remain unrun. No GitHub push.

## 2026-09-17 update — authorized focused evaluation

- Status: `implemented_and_tested` for scoped desktop synthetic studies R01-R04.
- After user authorization, completed 12 disjoint pilot rollouts, 180 primary rollouts
  (90 paired cases), and 180 physics-refinement rollouts on the same cases. The full formal
  E01-E11 matrix remains unrun. Refinement trials are not additional independent samples.
- Authority-constrained backups: 0/90 observed collisions versus 26/90 for the hypothetical
  throttle-backup comparator. Mean northward progress decreased from 4.70 to 2.26 m.
  All values are synthetic; neither universal safety nor overall navigation improvement is claimed.
- At equal exposure, exact-input pass-through was 74.67% versus 87.19%; mean steering
  correction was 4.210 versus 3.094 degrees. Trial-level uncertainty intervals are in the report.
- Exact branch deduplication: 630 snapshots, no decision differences, but its latency
  interval spans zero. The negative result is retained.
- New optional complete-witness short-circuit: 18,000 replayed states with zero immediate
  decision differences, 53.8% fewer integration steps, and 57.5% lower mean case filter-call
  latency on this desktop. P95 did not improve. Selected backup clearance can differ.
- Fixed steering-only failure-path throttle violations, checked all witness samples for
  throttle dependence, corrected pipeline timing labels and simulation state timestamps,
  and excluded Python bytecode from source fingerprints.
- Current native regression suite and 19 Python tests pass. Raw logs are under
  `artifacts/test-logs/`; raw observations, commands, timings, archived source/native binaries,
  and manifests are under `runs/resume_evidence_v1/` (Git-ignored).
- The current source also cross-links for ARM64 and builds/imports the optional pybind11
  module. Physical ARM64 execution remains untested. Final record audit: 372 completed
  trials and zero execution failures; collision outcomes remain explicit.
- Public-safe report, statistics, figure, and English CV bullets:
  `artifacts/research/2026-09-17/`.
- The dated stages below describe the original 2026-09-16 delivery. They are historical
  evidence, not a claim that only smoke tests remain available today.

## Stage 1 - source audit and frozen specification

- Status: `implemented_and_tested`
- Current manuscript inspected: 22 pages; equations (1)-(37), Tables 1-2, and the planned Figures/Table 3 sections were checked from rendered pages.
- Current input SHA-256: `main.pdf = 8e6d5ffe81b18212b39fcdafca46a54615da2050a91a28a2182af39df7c784ca`; `CoCommand.zip = ac53bb7d713f8fa1b0a76b05158e6864a30d58016fd775f7a366921e72b58bcf`.
- The PDF hash differs from the value in `SOURCE_AUDIT_V1.md`; the ZIP hash matches. The current PDF is the implementation source of truth for this snapshot.
- `experiment_manifest_v1.yaml` was not present beside the supplied brief. A derived manifest is maintained in `configs/experiment_manifest_v1.yaml` and is explicitly marked as derived.
- Legacy Python source was inspected without execution; `.pt`, third-party PDFs, temporary Office files, and caches were not loaded or imported.

## Stage 2 - paper-reference core and independent smoke simulator

- Status: `implemented_and_tested`
- Nonlinear 3-DOF/actuator RK4 core, paper grid, radar reconstruction, tracking, inflation,
  oriented hull geometry, paper backup search, exact-human priority, finite correction, and
  no-witness/unknown separation are implemented.
- The Python plant/scorer is independently written, runs at 0.02 s inside the 0.1 s control
  period, and does not expose obstacle truth through the controller API.
- Native CTest and Python C-ABI integration tests pass; the current synthetic E00 smoke is
  under `artifacts/smoke/20260916T221511_dac5a31d/`.

## Stage 3 - seven switchable extensions

- Status: `implemented_and_tested`
- Authority consistency and committed recovery, nested sampling, guarded horizon, propagated
  covariance, CV/CA Kalman and CV/CA/CT IMM hypotheses, extended/adapted finite-segment
  libraries, and deadline-aware search have independent switches and automated checks.
- This status means functional/unit/integration validation, not measured performance benefit.
  Formal ablations remain intentionally unrun and may show neutral or worse results.

## Stage 4 - experiment orchestration and reports

- Status: `implemented_and_tested`
- E00, E01-E11, H01, and H02 are represented in the derived manifest and individual validated
  configs. List/validate/dry-run/smoke/batch/resume/replay/report entry points execute.
- Full E01:E11 `main` dry-run expanded 50,300 tasks and started none. No pilot, calibration,
  main, stress, board, bench, field, or participant dataset is claimed.

## Stage 5 - ARM64 runtime and hardware boundary

- Desktop Mock/replay/UDP loopback and a three-cycle two-process PC-board bridge test are
  `implemented_and_tested`.
- Generic AArch64 Linux cross-link and ELF header verification are
  `implemented_not_tested_here`; the binary was not executed on a physical ARM64 board.
- Real-board replay, board latency/thermal data, device drivers, bench operation, and field
  operation are `blocked_by_missing_hardware`. Unknown hardware arming is tested fail-closed.

## Stage 6 - clean verification

- Status: `implemented_and_tested` for the current desktop environment.
- A fresh native configure/build, CTest, runner selftest, 13 Python tests, pybind11 build/import,
  ARM64 clean cross-build/header check, CLI checks, HIL loopback, replay, and E00 smoke all
  completed with expected exit codes. See `docs/test_evidence.md`.

## Validation evidence

Local full logs are saved under ignored `artifacts/test-logs/` to avoid publishing personal
absolute paths. Public-safe synthetic example output is under
`artifacts/smoke/20260916T221511_dac5a31d/`.

| Item | State |
|---|---|
| Desktop C++ core/C ABI/native runner | `implemented_and_tested` |
| Optional pybind11 module | `implemented_and_tested` on Python 3.12 desktop |
| Python orchestration/independent smoke/report/replay | `implemented_and_tested` |
| Seven extension switches and functional tests | `implemented_and_tested` |
| Formal E01-E11 data and claims | `not_implemented` (configs/runner exist; studies intentionally not run) |
| Physical ARM64 execution/replay/timing | `blocked_by_missing_hardware` |
| Actual LiDAR/joystick/state/actuator drivers | `blocked_by_missing_hardware` |
| Bench/field/participant validation | `blocked_by_missing_hardware` |

## Academic report revision - 2026-09-21

- Replaced `output/pdf/CoCommand USV.pdf` in place with the 15-page English report,
  preserving Zhang YUE and Sep, 2026. The current source is
  `output/pdf/source/academic_report.py`; the existing build entry point delegates to it.
- Organized every completed focused-study family: authority, exact deduplication,
  complete-witness search, work/deadline replay, bounded closed-loop evaluation,
  unknown diagnosis, held-out stress, operator feedback, grid discovery, fresh-seed
  confirmation, and same-case physics refinement. Preparatory smoke/pilot checks are
  explicitly separate from the statistical cohorts. This does not mark the full
  planned experiment matrix as executed.
- Defined preset versus goal-feedback operator input, finite-set intervention,
  complete witness, physical gap versus planning clearance, no-witness survival-score
  fallback, unknown hold-actual-steering action, per-cycle replanning, matched exposure,
  and filter-call versus end-to-end timing. No internal study codes, evidence filenames,
  or tool-generation declarations appear in the academic PDF.
- Added a full methods page on four-state obstacle Kalman estimation, Joseph covariance
  update, missing-observation prediction/expiry, acceleration-augmented prediction,
  three-motion-hypothesis clearance checking, and covariance-based margins.
- Naming correction from direct source inspection: the acceleration option uses a
  four-state Kalman estimate plus separately smoothed acceleration, not a six-state
  acceleration Kalman filter. The internally named IMM option generates three
  hypotheses from one shared estimate and heuristic motion scores; it is not a full
  interacting multiple-model filter bank. The reported comparative experiments retain
  the original smoothed constant-velocity predictor and inflation mode. No Kalman
  performance improvement or full IMM implementation is claimed.
- Report verification: build and Poppler rendering exited 0; 24 source-value/structure
  assertions, 19 source hashes, all eight figure-label scans, and all 15 page-boundary
  checks passed. All 15 rendered pages were visually reviewed, including equations,
  table wrapping, column heading placement, legend/data separation, and abstract spacing.
- Actual verification commands and outputs are retained in
  `output/pdf/verification_logs/`; current PDF hash is in `output/pdf/validation.json`.
  The former report and builders are preserved under
  `tmp/pdfs/before-academic-revision-20260921/`.
- Report-only revision: no controller source changes, new simulation experiments,
  controller test reruns, hardware connections, or remote publication were performed.

## Repository sharing review - 2026-09-22

- Rewrote English and Chinese README around the tested authority, complete-witness search,
  and candidate-budget questions. Added `docs/experimental_results.md`, covering every
  completed focused experiment, definitions, all 14 discovery configurations, negative
  outcomes, numerical sensitivity, and direct aggregate-evidence links.
- Copied eight existing academic-result figures to `docs/figures/` for portable publication
  links; no data or plots were recomputed. Corrected Kalman/shared-estimate multi-hypothesis
  terminology in introductory, source-mapping, limitation, and test-matrix documentation.
- Added `docs/release_review.md`; ignored report-authoring output and application-specific
  resume notes; removed personal interpreter paths from two reproduction guides. Existing
  local files were retained. License, authorship metadata, inherited-code redistribution,
  and result-disclosure approval remain owner/supervisor decisions.
- The relocated folder's historical CMake cache pointed at the old location. A separate
  fresh desktop Release configure/build completed with exit 0. CTest passed 1/1 executable;
  Python unittest discovery passed 29 tests. Diagnostic, configuration validation, budget
  dry-run, and four 0.5 s headless smoke tasks all exited 0. See `docs/test_evidence.md` and
  ignored `artifacts/test-logs/release-review-20260922-*.log` for actual outputs.
- Documentation checks exited 0: 70 local links resolved, all eight copied figure hashes
  matched the report originals, headline values matched frozen statistics, and selected
  personal-path/private-key/token patterns were absent from eligible text. The candidate
  publication set is 186 files, approximately 3.11 MiB; this is not legal clearance or
  a clean-checkout/hosted-CI test.
- No control-source changes, formal experiment reruns, changes to frozen statistics,
  physical hardware connections, license selection, commit, remote creation, or upload.

## Initial GitHub publication

- At the user's explicit request, published the inspected 186-file code/documentation/
  aggregate-evidence set to the user-specified repository on `main`. Initial source commit:
  `54fe15550371d1ed8fefe57878e7c9a45bd55f2c`.
- Local native tests and all 29 Python tests passed again before publication. The hosted
  Linux workflow for that commit completed successfully: configuration, build, native
  tests, Python tests, and short headless smoke. Evidence:
  https://github.com/Zhang-GTIIT/CoCommand-USV-Authority-Consistent-Predictive-Safety-Filtering-for-Shared-Vessel-Control/actions/runs/35708643425
- Publication did not include raw run archives, report-authoring output, private test logs,
  inherited source snapshots, tool caches, binaries, or application-specific resume notes.
  No license was selected, formal studies rerun, or physical hardware connected.
