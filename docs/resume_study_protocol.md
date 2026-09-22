# Focused synthetic evidence study (2026-09-17)

The user authorized controlled experiments beyond the original software-smoke gate.
This protocol is frozen before inspecting evaluation results. Pilot cases use separate
seeds and are retained but excluded from evaluation statistics. This is a synthetic
engineering study, not the complete E01-E11 matrix, a human study, or field validation.

## Questions and planned comparisons

1. **Authority consistency (R01):** compare the paper-style hypothetical-throttle backup
   library with a steering-only backup library. Both apply the human throttle unchanged.
   All other settings, observations, perturbations, dynamics, and candidate ordering are
   matched. Three encounter types, 30 distinct cases each, two controllers, 20 seconds
   maximum: 90 paired cases / 180 rollouts. Trials terminate at the first scored collision.
   The hypothetical baseline is an audit comparator, not a strawman autonomous controller:
   it may legitimately choose a throttle-dependent witness even if an alternative exists.
   A selected throttle-dependent witness is therefore **not proof that no authorized safe
   continuation exists**, and is not by itself proof of a collision.
2. **Exact branch deduplication (R02):** replay the same recorded sensor/state history from
   each R01 steering-only rollout into two controllers. At every 30th recorded cycle,
   compare the original backup library with its exact deduplicated version. Match commands,
   outcome, minimum clearance, and completeness before making a performance claim. Repeat
   timings five times in alternating variant order. Aggregate timing effects by case,
   never treat repeated timings or control cycles as independent trials.

## Fixed conditions and endpoints

`configs/studies/resume_evidence_v1.yaml` records distributions and seeds. Cases vary initial
distance, lateral offset, heading, velocity, circle radius, crossing timing, requested
throttle, and mild plant mismatch. Independent beam noise is keyed by case/time/beam.
The controller receives only scans and ego state. Geometry uses circles, for which the
fine-step rectangle-circle scorer is implemented; unvalidated wall/polygon cases are excluded.

Safety endpoints: per-trial collision count, minimum physical clearance, selected witness
throttle dependence, and actual unauthorized throttle outputs. Human-agency endpoints:
command pass-through and steering deviation. Progress is reported to expose stopping or
diversion effects. Trial means with paired bootstrap intervals and collision Wilson
intervals are reported; zero observed events is not a universal safety guarantee.

The control interval is 100 ms and the independent physics/scoring step is 20 ms.
Controller compute time is measured but not injected into the synchronous plant. Wall-clock
deadlines are disabled in R01/R02 to isolate algorithm effects; a very high deterministic
integration budget remains active and every unknown/failed outcome is reported. Consequently
these results cannot establish hard real-time or hardware safety. Measured native-filter
time and scan-to-command pipeline time are reported separately.

## Corrections before freezing the evaluation

- Timeout/numerical/stale fallback had set throttle to zero under steering-only authority.
  It now preserves admissible human throttle; regression tests cover those authority paths.
- Witness throttle dependence now checks all witness samples, not only the last recorded
  throttle override.
- Pipeline timing includes perception and C-ABI overhead, rather than relabeling filter-only
  time as end-to-end latency. State timestamps and idealized application timestamps are distinct.
- Source fingerprints exclude generated Python bytecode, avoiding interpreter-dependent hashes.

No favorable result is required. Pilot outcomes, failed trials, mismatches, and negative
results remain part of the report. Any protocol change must be versioned and explained.

## Follow-up R03/R04, registered after R01/R02

R01 observed 26/90 versus 0/90 collisions, with lower northward progress in the constrained
variant. R02's timing interval included zero. Neither is suppressed. Original source and
native DLL were archived in `runs/resume_evidence_v1/` before this follow-up implementation.

R03 tests a new optional short-circuit: once one **complete** positive-clearance backup
exists for a candidate, stop evaluating other backups of that candidate. The candidate
order, exact human-command priority, horizon, geometry, and margin stay fixed. All backups
must still be checked to reject a candidate. In a fully evaluated steering-only search this
preserves the selected immediate command, but can choose a different backup with less
clearance. It is disabled for emergency authority and largest-clearance selection. It is
not a new safety theorem. The option defaults to off.

Replay all 18,000 recorded constrained-controller states from R01, using sensor histories
only. Check immediate command/outcome equivalence on every state and require all accepted
witnesses to have the full 52-point horizon and positive clearance. Benchmark every tenth
cycle with five repeated timings after one warm-up, alternating variant order; bootstrap
over the 90 case blocks. Failure or incomplete-witness counts must be reported.

R04 reuses all 90 paired cases at 10 ms physics/scoring resolution (180 further rollouts).
No scene or controller parameter is adjusted after the R01 results. This is a numerical
sensitivity check, not a new independent sample or a doubling of the effective sample size.
