# R08-C: independent-seed follow-up at the selected 2048-step budget

This was specified AFTER exploratory R08, before these new outcomes. It validates a selected secondary setting without pretending 2048 was the original primary endpoint. The original 512-step goal result remained 4/60 versus 4/60.

60 fresh paired initial conditions, base seed 320260917, original three family distributions; 120 rollouts. Both filters use 2048 steps, first-complete-witness search, steering-only authority, 10.1 s prediction, identical ego-only goal-feedback policy, and 10 ms physical integration/scoring. No parameter retuning. The discovery cohort used 20 ms; these new seeds do not constitute paired numerical convergence testing.

| Candidate grid | Goals / 60 | Collisions / 60 | Timeouts | Mean unknown % |
|---|---:|---:|---:|---:|
| u2_first_b2048 | 9 | 51 | 0 | 31.72 |
| u4_first_b2048 | 47 | 13 | 0 | 11.89 |

## Paired tradeoffs

| Metric | 4° minus 2° [family-stratified case-bootstrap 95%] |
|---|---:|
| goal_reached | 63.333 [53.333, 73.333] pp |
| collision | -63.333 [-73.333, -53.333] pp |
| matched_mean_correction_deg | 8.186 [6.805, 9.514] degrees |
| matched_unknown_fraction | -12.861 [-14.017, -11.608] pp |

A coarser grid changes finite-set intervention optimality and can miss viable controls. The primary endpoint is goal completion at this fixed budget, not an unconditional safety guarantee. Correction comparisons use matched elapsed time, not identical state/request pairs after closed-loop divergence. Retain failed cases and the unfavorable 512-step result alongside any CV claim.

## Audit

```json
{
  "trials": 120,
  "cycles": 14482,
  "invalid_witnesses": 0,
  "throttle_violations": 0,
  "step_budget_violations": 0,
  "task_hash_violations": 0,
  "truth_manifest_violations": 0,
  "alignment_violations": 0,
  "exact_input_violations": 0,
  "execution_failures": 0
}
```

Raw data: `runs/budget_confirmation_v1/`; original study: `runs/budget_allocation_v1/`. The full manifest, per-family summaries and paired records are in `confirmation_statistics.json`. Protocol/command: `docs/budget_confirmation_protocol.md`. Neither cohort uses physical devices or human participants.
