# Manuscript-to-code traceability

Status vocabulary: `manuscript_specified`, `legacy_observed`, `engineering_assumption`,
`new_extension`, `hardware_pending`.

| Manuscript item | Code | Configuration | Verification | Status |
|---|---|---|---|---|
| Eq. (1)-(3), admissible human-first contract | `SafetyFilter::filter` in `cpp/core.cpp` | controller authority/selection fields | exact 3.7 deg pass C++/Python tests | manuscript_specified |
| Eq. (4)-(6), state, rotation, 3-DOF dynamics | `VesselState`, `vessel_derivative` | `synthetic_vessel_v1.yaml` | Coriolis power, damping, coordinates | manuscript_specified + engineering_assumption parameters |
| Eq. (7)-(8), actuators | `vessel_derivative`, `rk4_step` | vessel actuator fields | thrust response, steering-rate and reverse tests | manuscript_specified + engineering_assumption parameters |
| Eq. (9), RK4 grid | `paper_time_grid`, `rk4_step` | paper horizon mode | 52 points; 10.1 s; first-segment test | manuscript_specified |
| Eq. (10), local scan reconstruction | `simulate_radar`, `reconstruct_detections` | `radar_360.yaml` | first hit, exact range boundary, no-hit distinction | manuscript_specified |
| Circle-fit/fallback rules | `cluster_to_detection` in `cpp/perception.cpp` | sensor fit thresholds | seam, low-point fallback, rank rejection paths | manuscript_specified |
| Eq. (11)-(13), track and association | `Tracker::update` | predictor and memory switches | duplicate time, CV Kalman/shared-estimate hypotheses, expiry | manuscript_specified + engineering_assumption sigma update |
| Eq. (14)-(16), CV and inflation | `predicted_centers`, `track_radius` | predictor/margin modes | future radius/covariance tests | manuscript_specified |
| Eq. (17)-(20), oriented hull gap | `rectangle_circle_signed_distance`, `clearance_at` | base/sweep margin | touch/intersection/rotation and strict boundary tests | manuscript_specified; speed allowance engineering_assumption |
| Eq. (21)-(22), candidate then backup | `evaluate_candidate`, `policies_for` | backup library mode | full-branch witness, partial timeout rejection | manuscript_specified |
| Table 1, 24 backup branches | `policies_for` | paper24/deduplicated | nominal/unique/evaluated counts | manuscript_specified |
| Eq. (23)-(25), exact input/minimum correction | `steering_candidates`, `SafetyFilter::filter` | sampling mode | exact input, stable nested grids | manuscript_specified |
| Eq. (26)-(27), no-witness score | branch/candidate fallback in `cpp/core.cpp` | controller config | strict G=0 exhaustive fallback test | manuscript_specified |
| Eq. (28), authority caveat | authority modes and `RecoveryCommitment` | C1/C2/C6 | deadline-not-postponed and revalidation tests | manuscript_specified requirement + new_extension implementation |
| Eq. (29)-(30), full-command distance | full-command candidate ordering | C7 weights/authority | finite candidate execution and reverse legality | manuscript_specified extension |
| Eq. (31)-(33), nested/multi-hypothesis search | nested grids, three shared-estimate motion hypotheses, shared backup min | sampling/predictor modes | subset coverage and three-hypothesis tests | manuscript_specified proposition + new_extension |
| Eq. (34)-(37), reporting metrics | `simulation.py`, `reporting.py` | experiment tiers | integration output/schema tests | manuscript_specified |
| Table 2 settings | vessel/sensor/controller configs | configs tree | catalog/schema tests | manuscript_specified |
| Figures 1-6 / Table 3 plan | report generator and manifest mapping | E01-E10 | smoke SVG only; formal outputs absent | manuscript_specified plan, not completed result |
| Legacy 2-D constants/flow | ignored `legacy/source_snapshot` audit | none | static line audit only | legacy_observed |
| Synthetic plant parameters and independent finer plant | `VesselParams`, `simulation.py` | vessel YAML | native and integration smoke | engineering_assumption |
| Adaptive candidate/horizon, covariance, Kalman/motion hypotheses, action library, deadline | `core.cpp` switches | C5-C9/E04-E10 | C++/Python tests and smoke | new_extension |
| Joystick/LiDAR/state/actuator/health interfaces | `runtime.hpp`; bridge/replay tools | hardware YAML | Mock/loopback/default-refusal tests | new_extension + hardware_pending |

Prediction terminology: the acceleration option adds smoothed acceleration to a four-state
Kalman estimate. The internally named IMM option produces three motion hypotheses from
that shared estimate, not a mixing bank of separate model-conditioned Kalman filters.
Completed comparative studies use the original smoothed constant-velocity predictor;
prediction-extension performance effects have not been isolated.
