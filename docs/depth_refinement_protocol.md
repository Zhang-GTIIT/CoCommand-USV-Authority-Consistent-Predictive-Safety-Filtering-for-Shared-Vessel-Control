# R07 numerical sensitivity follow-up

This protocol is written after seeing R05–R07, but before running this follow-up.
It is explicitly a post-analysis numerical sensitivity check, not a new independent
confirmatory sample and not a revised controller.

Repeat every one of the 60 R07 feedback-operator initial conditions with both hypothetical
and constrained filters (120 rollouts). Change only the independent physical integration
and collision/goal checking step from 20 ms to 10 ms. Keep the 100 ms control interval,
10.1 s prediction horizon, original goal/operator policy, controller settings, initial
conditions, seeds and 40 s maximum duration. Do not tune any parameter after outcomes.

Save new data separately to `runs/depth_validation_refinement_v1/`. Check goal/collision
classification changes, minimum hull-gap changes, and goal-time changes among common
successes. Report all discrepancies, including whether they change a proposed CV number.
This does not refine all R05/R06 data or establish continuous-time safety.

```powershell
$env:PYTHONPATH = (Resolve-Path python).Path
python -u tools/refine_depth_mission.py --physics-step 0.01
```

The runner verifies the original study source and native fingerprints and locks its own
hash in the new manifest; completed cases resume only with identical provenance.
