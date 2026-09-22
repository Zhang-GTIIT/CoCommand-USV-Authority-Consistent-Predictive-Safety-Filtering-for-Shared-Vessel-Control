# R05-R07: failure boundaries and shared-control tradeoffs

This is a new, user-authorized extension after R01-R04. Freeze this protocol before
examining its results. Original studies remain immutable. No favorable result is required.

## R05: finite computation

Replay every recorded state from the 90 R01 steering-only cases (18,000 states) into
exhaustive-backup and first-complete-witness controllers. Give both identical deterministic
RK4-step budgets: 32, 64, 128, 256, 512, 1024, 4096. Compare with the recorded unlimited
reference. Log witness availability, timeout/unknown, exhaustive rejection, integration
counts, and command agreement. Every accepted result must contain all 52 witness samples
and strictly positive planning clearance. A limited result may differ from the unlimited
reference when no witness can be completed; never count unknown as safe.

Comparator semantics: the existing exhaustive implementation evaluates all backups for a
candidate and retains its highest-clearance witness. If this candidate-level enumeration
is interrupted, it returns unknown even if an earlier branch completed successfully.
The optional short-circuit implementation accepts the first full positive-clearance branch
for that candidate, retaining candidate ordering and exhaustive rejection. Thus the finite-
budget benefit includes avoiding this conservative wait for maximum backup clearance; it
is not a new CBF, a novel existence theorem, or an identical future-backup selection rule.

Also test desktop soft wall-clock budgets of 0.1, 0.25, 0.5, 1 and 2 ms at every 30th cycle
(630 snapshots), with three repeats in alternating order. Timing results are host/load
dependent and do not establish hardware real-time guarantees. Per-state repeated calls
are not independent trials; statistics use case blocks. Do not run another benchmark,
compiler, or package installation alongside the timed part.

Primary reporting budgets are fixed in advance at 512 integration steps and 0.25 ms;
all other budgets remain in the report. Additionally run the first 10 source cases per
family (30 paired cases / 60 rollouts) closed-loop at the 512-step budget, comparing
exhaustive and short-circuit constrained search for up to 20 seconds. This tests whether
the snapshot benefit survives state-distribution changes in a closed loop.

## R06: held-out stress families

Use disjoint seeds, 20 generated cases each for head-on, overtaking, three competing
obstacles, crossing with 0.15 m range noise and 15% frame dropout, and very late static
encounters (3.0-4.5 m approach distance; 1.5-2.0 m/s initial surge). Circle geometry only.
Run three variants: hypothetical-throttle backup baseline, authority-constrained exhaustive
search, and authority-constrained first-complete-witness search. Matched cases and common
parameters; 25 seconds maximum, terminate on collision: 300 rollouts. Report every family,
including failures and zero feasible-witness states. Source conditions span a wider range
than R01, with plant mismatch 0.75-1.25. No tuning follows these outcomes.

## R07: progress and the operator model

Use the first 20 pre-existing cases in each R01 family (selection by index, not outcome),
giving 60 paired initial conditions. Compare two scripted operators, each with both the
hypothetical and constrained controller: 240 rollouts, maximum 40 seconds. The original
operator is the small open-loop sine steering input. The feedback operator points toward
the goal at (8,0), using only ego pose/yaw rate and a fixed waypoint, never obstacle truth.
Its gains and the goal tolerance are fixed in configuration. This is a scripted operator
model, not human-participant evidence or a new obstacle-aware path planner.

Report collision, reaching the 1.5 m goal region before collision, timeout, time to goal,
distance-to-goal reduction, path length, command preservation, and correction magnitude.
Stop scoring at the first collision or goal arrival, whichever occurs first. Keep the
full two-by-two table, so an operator-model effect is not attributed solely to the filter.
The stronger simulation result does not supersede original R01's progress cost.

Source/native/config hashes, raw scans and controls, and all failure records are retained.
Units, pairing, and new operator/goal semantics must pass tests before executing the study.
# Pre-execution validation note

The disjoint-seed unit test caught overlap between the initial proposed stress seed range and R01's family offsets. Before any R05–R07 study outcomes were generated, the stress base seed was changed to 120260917. The failing test log is retained as `artifacts/test-logs/depth-validation-python-tests.log`; the passing rerun uses the `-verified` suffix. No controller or scenario parameter was tuned from study results.
