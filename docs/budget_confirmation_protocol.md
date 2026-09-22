# R08-C: fresh-seed confirmation after exploratory R08

This follow-up is specified after R08's 840 outcomes and before its own execution.
R08's primary 512-step comparison did NOT improve goal completion (4/60 for either grid).
Its secondary 2048-step comparison had goals 9/60 versus 47/60. Therefore do not portray
2048 as the original primary endpoint. The new follow-up fixes that chosen budget before
collecting new outcomes, with no parameter tuning during/after this run.

Use 60 fresh initial conditions from the original three families, base seed 320260917,
20 per family, disjoint from prior studies. Run only the fixed ego-only goal-feedback
operator, both 2-degree and 4-degree first-complete-witness policies, both with 2048 steps,
unchanged authority/backups/margins/10.1 s horizon, 40 s limit and original waypoint/gains.
Independently integrate and check collision/goal at 10 ms instead of discovery's 20 ms.
Total 120 rollouts. The same conditions/generator remain synthetic; this is not a new
environment family, a human trial, or a numerical-convergence study.

Primary endpoint: paired goal-completion difference, with a family-stratified case-level
95% bootstrap interval. Also report collisions, timeouts, matched-exposure steering
correction and unknown frequency, and all safety/authority/witness/budget audit failures.
Retain unfavorable cases. No automatic choice of another budget, gain, grid or scenario
range is allowed in response to these new outcomes.

The JSON-compatible protocol is `docs/budget_allocation_confirmation_v1.yaml`. It is in
the documentation directory to preserve the discovery source fingerprint; its full content
is still frozen and compared by the normal per-run manifest, so changes cannot silently
resume a previous run. The same runner and native binary are used.

```powershell
$env:PYTHONPATH = (Resolve-Path python).Path
python -u -m cocommand.budget_study --config docs/budget_allocation_confirmation_v1.yaml --stage feedback --run-dir runs/budget_confirmation_v1
```
