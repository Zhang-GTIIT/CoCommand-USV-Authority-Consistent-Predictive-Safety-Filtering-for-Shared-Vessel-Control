# R08: search budget, candidate resolution, and closed-loop failure

Protocol fixed before R08 outcomes. The question follows R05's negative result: faster
fixed-state replay did not demonstrate a useful closed-loop collision reduction at 512
integration steps. No positive result is required, and no new safety theorem is claimed.

## Diagnostic replay (existing data, not held-out evidence)

Replay all 30 `limited_short` R05 trajectories and raw observations in temporal order,
using the recorded ego state and identical controller parameters. Reproduce the 512-step
decision and compare with a 2,000,000-step reference at the same state/scan history.
For every original unknown, distinguish reference witness found, exhaustive rejection,
and still unknown. Record first budget miss that had a complete reference witness and
its interval before any physical collision. Validate reproduction of recorded commands.
This is a counterfactual single-decision diagnostic, not proof that following a different
command would have prevented the recorded collision. No obstacle truth goes to either filter.

## Fresh closed-loop draws

Generate 20 cases per original encounter family (static, crossing, late/high-throttle),
60 total, using base seed 220260917 and the original frozen parameter distributions.
Seeds must be disjoint from R01 and R06. No selection by outcome and no tuning after
outcomes. This is a new draw within the same family distributions, not new environment types.

R08_open: three policy choices × three work budgets × 60 cases = 540 rollouts, up to 20 s.
Policies: 2-degree candidates/exhaustive backups, 2-degree/first complete backup, and
4-degree/first complete backup. Budgets: 512, 2048, 2,000,000 RK4 steps. The large budget
is a practical reference, not mathematical infinity. Exact human input remains first,
before any grid; horizon 10.1 s/52 samples, authority, margins and backup library unchanged.
The 4-degree grid includes clamped endpoints ±30 degrees. It changes the candidate set
and its finite-set minimality; do not claim the same minimum intervention as the 2-degree set.

R08_feedback: same 60 cases with the previously fixed ego-only goal-feedback script.
Compare both candidate resolutions at 512 and 2048 steps, plus 2-degree first-complete
at 2,000,000 steps: 300 rollouts, up to 40 s or first collision/goal arrival.
Goal (8,0), radius 1.5 m; gains 1.6/1.8, steering clamp ±30 degrees, same throttle per
case. This is not a human-subject study. All 840 planned closed-loop records are retained.

## Hypothesis and reporting

The primary contrast is 4-degree versus 2-degree first-complete search at 512 steps,
separately for open-loop and feedback operators. Coarser resolution may leave budget to
check larger evasive corrections, but may miss feasible inputs or increase intervention.
Report collision, goal/timeout, unknown/exhausted fractions, integration work, real hull
gap, progress, and absolute steering correction. Compare correction over matched exposure
within each pair, not the entire unequal-length trajectories. Bootstrap uses cases, not
individual cycles. Report all tested budgets, including neutral or worse results.

Audit full 52-sample positive-clearance witnesses, exact-input preservation on accepted
human candidates, throttle authority, step budgets, observation alignment and task hashes.
Treat 2,000,000-step results as the same method with more computation, not an optimization
at equal cost. No new controller logic or actuation is introduced by this experiment.

Dense/nested sampling is intentionally not labeled an adaptive allocation comparator:
the existing implementation merges nested grids and globally sorts by intervention, so
it currently behaves as a dense candidate set rather than budget-aware coarse-first search.

Source/config/native snapshots and logs stay in the desktop repository. Formal E01–E11,
real devices, and GitHub publication are outside this run. Frozen older studies stay intact.
