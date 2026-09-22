# Focused CoCommand-USV evaluation — 17 September 2026

This is a controlled **synthetic** simulation and desktop replay study. It uses engineering-assumption vessel parameters and scripted human commands. No real boat, Orange Pi, participant, CBF, or continuous-time safety theorem is involved.

## R01: align backup predictions with executable authority

90 distinct paired cases, three encounter families, 20 seconds maximum per rollout: **180 rollouts**. Both variants preserve human throttle at output. Only the permitted throttle in predicted backup maneuvers changes. All sampled conditions, noise, perception, horizon, candidate ordering and scoring are matched. Wall-clock cutoffs are disabled; a deterministic integration budget remains in force.

| Encounter | Hypothetical-throttle baseline collisions | Steering-only backup collisions |
|---|---:|---:|
| static | 5/30 | 0/30 |
| crossing | 9/30 | 0/30 |
| late_high_throttle | 12/30 | 0/30 |
| Total | 26/90 | 0/90 |

Observed collision fractions: **28.9% vs 0.0%**. The Wilson 95% upper bound for the zero-event constrained result is **4.09%**. This is not a zero-risk guarantee. The paired bootstrap change was -28.9 percentage points (95% interval -38.9 to -20.0).

The baseline selected throttle-dependent witnesses in **5219/12330 accepted cycles (42.3%)**; the constrained library selected zero. This diagnoses the selected witness, not impossibility of every alternative authorized continuation. Both variants had zero applied-throttle violations and zero search-budget unknown trials.

Mean minimum physical clearance: 1.112 vs 1.816 m. Mean northward progress: **4.698 vs 2.257 m**. The progress cost is material: this safety filter is not a route planner, and reduced collisions cannot be called improved overall navigation performance.

## Human intent / equal exposure analysis

Collision terminates a rollout, so full-run averages have unequal exposure. As a supplemental analysis, each pair is compared only up to its earlier stopping time, yielding 14607 matched cycles across 90 cases. Case means are weighted equally; confidence intervals resample cases within encounter families.

- Exact human-command pass-through: **74.67% vs 87.19%**.
- Paired change: 12.52 percentage points; stratified bootstrap 95% interval [9.14, 16.05].
- Mean absolute steering correction: **4.210 vs 3.094 degrees**; change interval [-1.822, -0.425] degrees.

These are scripted-input simulation results, not human trust, workload, or user-study findings. They do not remove the northward-progress tradeoff.

## R02: branch deduplication, including the negative result

On 630 replayed snapshots, exact deduplication produced zero command/outcome/clearance mismatches and reduced integration steps from 445,353 to 437,784 (1.70%). Mean case latency reduction was 1.06%, with a 95% interval [-0.50%, 2.52%]. The interval spans zero; **a latency improvement is not established**.

## R03: stop after the first complete safety witness

The added optional optimization exploits existential candidate acceptance: one complete positive-clearance backup is enough. Unsafe candidates still exhaust the full declared library. Exact human priority, candidate order, horizon and clearance tests stay fixed. It is enabled only for steering-only minimum-modification search, not emergency commitment or largest-clearance selection.

- **18,000 recorded control states** replayed with zero command/outcome mismatches and zero disagreement with the original R01 trace.
- 17,084 accepted states all retained a complete 52-point / 10.1-second witness with positive clearance; 916 exhaustive-no-witness states remained explicit. No unknown states were promoted to safe.
- Integration steps: **14,221,230 → 6,572,286 (53.8% reduction)**.
- 1,800 timed states, five measurements per variant after one warm-up, alternating order: mean case filter-call latency reduction **57.5%** (case-bootstrap 95% interval 53.7–61.3%).
- P95 of per-state median filter-call latency: **0.9043 → 0.9260 ms**; the tail did not improve. The mean/median benefit must not be called a worst-case or P95 speedup. This measures the filter call including Python/C-ABI overhead, not scan-to-actuator latency.

CPU: Intel Core i7-12700H, Windows 11, Release build, CPU only. Timings are desktop observations, not ARM64 or hard-real-time claims. The optimization may select a lower-clearance backup than exhaustive best-backup selection; minimum accepted sampled margin was 0.000004 m. Command equivalence under this exhaustive-budget study is not a theorem about bounded-time search or emergency recovery.

## R04: halve the independent physics/scoring step

Repeated all 180 rollouts at 10 ms rather than 20 ms, without changing the 100 ms control interval. Collision counts were 26/90 vs 0/90. Changed trial classifications: 0 baseline, 0 constrained. This is a sensitivity check on the same cases, not 90 additional independent paired cases. Maximum change in a trial's minimum clearance was 0.218414 m.

## Reproduction and evidence

Run from the repository root with `PYTHONPATH=python` and the built native library available:

```sh
python -m cocommand.focused_study --phase pilot --run-dir runs/new_study/pilot --stage all
python -m cocommand.focused_study --phase evaluation --run-dir runs/new_study/evaluation --stage all
python -m cocommand.optimization_study --source runs/new_study/evaluation --run-dir runs/new_study/followup --stage all
python tools/report_resume_study.py --root runs/new_study --output artifacts/research/new_study
```

Frozen R01 code and DLL are archived under `runs/resume_evidence_v1/`; R03 replay verified baseline parity after the optional optimization was added. Manifests lock source/configuration/native hashes; resume refuses a mismatch. Raw scans, controls, physical scoring, failures and per-case timing samples are retained under `runs/resume_evidence_v1/` (Git-ignored). Public-safe aggregates and figures are in this directory. Matplotlib is an optional reporting dependency only.

Limitations: synthetic parameters, scripted operator inputs, only three circle-obstacle families, synchronous plant without injected computation/network delay, finite-horizon sampled safety, no independent real-vessel validation, no navigation goal completion criterion. The evaluation distribution was fixed before results; R03/R04 are explicitly post-R01 follow-ups.
