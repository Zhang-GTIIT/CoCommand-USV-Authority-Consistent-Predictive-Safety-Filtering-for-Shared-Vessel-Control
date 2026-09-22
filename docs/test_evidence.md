# Test and build evidence

## 2026-09-22 repository sharing review

The working folder had moved after the original build. Its old CMake/CTest cache still
referenced the former location, so verification used a fresh `build-release-review`
directory without overwriting the historical build or research data. No controller
implementation or experiment statistics changed during the documentation review.

| Current check | Actual result |
|---|---|
| Fresh desktop Release configuration | exit 0 |
| Native C++/C ABI/runner build | exit 0 |
| CTest | exit 0; 1/1 native executable passed |
| Python unittest discovery | exit 0; 29 tests passed |
| Diagnostic/native-library load | exit 0 |
| Authority configuration validation | exit 0 |
| Candidate-budget study expansion | exit 0; dry-run only |
| Four 0.5 s headless smoke tasks | exit 0 |
| Documentation/evidence/publication-set checks | exit 0; 70 local links, eight figure hashes, headline statistics, and selected path/token patterns checked |

Environment: Windows 11, Python 3.12.14, local Clang 21.1.0 through the Zig wrapper,
Release build. The following PowerShell commands used the pre-existing local build-tool
cache; these ignored tools are not distributed as part of the repository. On a fresh
Linux/ARM64 installation, use the prerequisite-based commands in README instead.

```powershell
& .tools/python/cmake/data/bin/cmake.exe -S . -B build-release-review -G Ninja `
  -DCMAKE_BUILD_TYPE=Release -DCOCOMMAND_BUILD_TESTS=ON -DCOCOMMAND_BUILD_PYBIND=OFF `
  "-DCMAKE_CXX_COMPILER=$((Resolve-Path scripts/zig-cxx.cmd).Path)" `
  "-DCMAKE_MAKE_PROGRAM=$((Resolve-Path .tools/python/bin/ninja.exe).Path)"
& .tools/python/cmake/data/bin/cmake.exe --build build-release-review --parallel 2
& .tools/python/cmake/data/bin/ctest.exe --test-dir build-release-review --output-on-failure
$env:PYTHONPATH = (Resolve-Path python).Path
$env:COCOMMAND_NATIVE_LIB = (Resolve-Path build-release-review/libcocommand_c.dll).Path
python -m unittest discover -s tests/python -v
python -m cocommand doctor
python -m cocommand validate-config configs/experiments/E02_authority.yaml
python -m cocommand.budget_study --stage dry-run
python -m cocommand experiment --id E00 --tier smoke --seeds 0:1 --duration 0.5 --run-root runs/readme-smoke-20260922
```

Actual command output is retained under `artifacts/test-logs/release-review-20260922-*.log`.
The Python executable's machine-specific path is retained only in local execution context.
The smoke run is `runs/readme-smoke-20260922/20260922T163332_dd7f17fa/`, including its
generated report. No formal studies, hardware connections, ARM64 execution, or remote
publication were performed in this review.

## 2026-09-17 focused-study verification

The original 2026-09-16 evidence below is retained. After user authorization, the scoped
R01-R04 synthetic study ran with these additional actual outcomes:

| Check | Result |
|---|---|
| Authority fallback / timing corrections build and CTest | exit 0 / 0 |
| Pre-study Python suite | exit 0; 17 tests |
| Disjoint pilot, 12 rollouts plus 42 replay snapshots | exit 0 |
| R01/R02 evaluation, 180 rollouts plus 630 snapshots | exit 0 |
| Complete-witness short-circuit build and CTest | exit 0 / 0 |
| Updated Python suite | exit 0; 19 tests |
| R03/R04, 18,000 replayed states plus 180 refined-step rollouts | exit 0 |
| Automated evidence audit and report/figure generation | exit 0; all audit checks passed |
| Current ARM64 cross-build / ELF64 AArch64 header check | exit 0 / 0; not run on a board |
| Current optional pybind11 build / import | exit 0 / 0 |

Logs: `artifacts/test-logs/focused-study-*.log`, `short-circuit-*.log`.
Source/configuration/native hashes, raw per-cycle records, repeated timings, and all
collisions are retained under `runs/resume_evidence_v1/`. The public-safe report is
`artifacts/research/2026-09-17/report.md`. `docs/resume_study_protocol.md` distinguishes
the frozen primary protocol from the later optimization/refinement follow-up.

R01-R04 do not constitute the complete E01-E11 formal matrix, board replay, or field validation.
The final raw-record audit counted 372 completed trial records (12 pilot + 180 primary +
180 refinement), zero execution-failure files, and 18,000 R03 replay states. Collision
records are retained and are separate from execution failures. Public report path/secret
pattern scan passed. Binary-check logs are `focused-study-arm64-build.log`,
`focused-study-pybind-build.log`, and `focused-study-binary-check.log`.

Environment: Windows 11 desktop, Python 3.12.14. The repository-local ignored tool cache used
CMake 4.4.3, Ninja 1.13.2, Zig 0.16.0/Clang 21.1.0, and pybind11 3.1.0. These tools are build
inputs, not runtime dependencies.

## Final commands and outcomes

| Check | Result |
|---|---|
| Fresh desktop CMake configure | exit 0 |
| Desktop native build | exit 0 |
| `ctest --test-dir build --output-on-failure` | exit 0; 1/1 executable passed; native executable contains multiple unit/property/regression checks |
| `build/cocommand_runner.exe selftest` | exit 0; 52 time points and exact 3.7 deg pass verified |
| `python -m unittest discover -s tests/python -v` | exit 0; 13/13 tests passed |
| Optional pybind11 configure/build/import | exit 0/0/0; Python 3.12 module returned 52-point grid |
| Clean generic AArch64 Linux cross-configure/build | exit 0/0 |
| ARM64 output header | ELF64, `e_machine=183`; check exit 0 |
| `cocommand doctor` | exit 0 |
| E02 config validation | exit 0 |
| JSONL replay | exit 0 |
| UDP loopback integrity/freshness | exit 0 |
| Native mock runtime, 3 cycles | exit 0 |
| Two-process PC-board bridge, 3 cycles | PC exit 0, board exit 0 |
| ARM64 benchmark dry-run | exit 0; no board number invented |
| Unknown real hardware enable attempt | expected refusal exit 2 |
| E01:E11 main dry-run | exit 0; 50,300 tasks expanded, zero started |
| Current E00 synthetic smoke | exit 0; four 0.5 s task records completed |

Local raw logs: `artifacts/test-logs/final-build-and-tests.log`,
`final-pybind.log`, `final-arm64-clean.log`, `final-cli.log`,
`final-bridge-summary.log`, `final-main-dry-run.log`, `final-smoke.log`,
`post-latency-fix-regression.log`, `post-fix-smoke.log`, `post-fix-pybind.log`,
and `post-fix-arm64.log`.
They are Git-ignored because tool output contains personal absolute paths. Bridge stdout/stderr
and the public-safe smoke/replay records remain under `artifacts/`.

## Failures encountered and fixed

- The first Zig/CMake build reached compilation but failed archiving because CMake could not
  infer `CMAKE_AR` for the wrapper compiler. The core target was changed to a CMake object
  library shared by all front ends, and later clean builds passed.
- The first Python test discovery found a real unmatched parenthesis in the resume cache
  condition. The syntax was corrected, compile/import checks were added, and all 13 tests pass.
- An early pybind configure selected the Windows Store Python 3.11 cache. A clean build using
  `PYBIND11_FINDPYTHON` and explicit Python 3.12 produced/imported the correct `cp312` module.
- A superseded smoke artifact contained a personal absolute library path. Manifest path
  serialization was changed to repository-relative form; the old run was moved into ignored
  `tmp/superseded-smoke/`, and the public-artifact path scan is clean.

## Interpretation of the original 2026-09-16 verification

Desktop exit 0 does not imply hard real-time safety. ARM64 cross-link does not imply board
execution. Four short synthetic trials do not support a performance claim. No formal study,
board replay, bench test, field test, or human study was run.
