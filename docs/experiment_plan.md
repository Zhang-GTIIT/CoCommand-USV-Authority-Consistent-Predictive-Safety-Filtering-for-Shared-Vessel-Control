# Executable experiment plan

`configs/experiment_manifest_v1.yaml` is the machine-readable source for E00, E01-E11,
H01, and H02. It was derived from the supplied `EXPERIMENT_PLAN_V1.md` because the separately
named manifest was absent. Individual files under `configs/experiments/` validate an exact ID
against that manifest.

Tiers and default seed intervals are: smoke `[0,2)`, pilot `[0,20)`, calibration `[100,120)`,
main `[1000,1100)`, and stress `[2000,2050)`. Smoke truncates each matrix to a bounded subset.
Dry-run expands combinations without constructing a controller, simulator, or hardware
endpoint. Non-smoke execution requires `--confirm-formal`.

All tasks record experiment, controller, scenario, seed, overrides, configuration hash/code
fingerprint, resolved config, system details, synthetic parameter source, control timestamps,
requested/applied commands, witness throttle requirement, authority/recovery state, actual
horizon, planning and end-to-end latency, candidate/branch/step counts, planning clearance,
and independent physical clearance.

Formal selection/calibration rules remain those in the supplied plan. No formal tier has
been run in this snapshot, and no result percentage is prefilled.

