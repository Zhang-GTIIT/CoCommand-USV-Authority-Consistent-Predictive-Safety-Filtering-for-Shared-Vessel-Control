# Known limitations and claim boundary

- R08's same-budget 4°/2° candidate comparison did not improve goal completion at the
  original primary 512-step budget. The favorable 2048-step setting was secondary, then
  frozen and validated with fresh seeds. It must not be retrospectively labeled the
  discovery primary endpoint or generalized to arbitrary computation limits.
- R08-C's goal improvement (9/60→47/60) came with 8.186° greater mean correction over
  matched exposure. Coarser candidates change finite-set minimality, and no online adaptive
  candidate-resolution policy was added. It is not evidence of lower intervention.
- Fresh-seed 10 ms confirmation is not a same-case numerical-convergence test; R08 remains
  synthetic, fixed-policy and model-dependent with substantial residual collisions.

- Follow-up R05–R07 adds five stress families and a two-by-two scripted-operator study.
  Constrained stress collisions are 25/100, so R01's 0/90 must not be generalized.
  All 20 very-late static stress encounters collided with either backup authority model.
- At 512 integration steps, better replay witness availability did not translate into a
  demonstrated closed-loop collision improvement (20/30 versus 19/30). Replay state
  distributions and live closed-loop trajectories differ.
- Goal-feedback script results (29/60 versus 52/60 arrivals) are conditional on a fixed
  synthetic operator and initial-condition subset, not human shared-control performance.
  The 10 ms refinement retained goal labels but changed three collision/timeout labels;
  minimum-gap changes reached 1.314 m. Numerical convergence is not established.
- No-witness fallback remains uncertified. Observing `exhausted_no_witness` at a collision
  does not prove collision was unavoidable under all possible authorized policies.

- Focused 2026-09-17 studies use three synthetic encounter families and scripted human
  commands. They are not a user study or a completed full E01-E11 evaluation. Their
  authority-constrained controller had less northward progress; no overall navigation
  improvement is established.
- Optional first-complete-witness search preserves the immediate decision under the
  tested exhaustive-budget steering-only conditions, but not the maximum-clearance
  choice of future backup. It is off by default and unavailable for emergency authority
  or largest-clearance selection. Its P95 runtime did not improve in the recorded replay.
- The simulation is synchronous: measured perception/filter computation time is recorded
  but not injected into physical actuation delay. Hardware real-time claims need separate tests.

- Synthetic parameters are for software behavior only. They are not real-vessel estimates.
- The sampled witness test is not a continuous-time collision-avoidance theorem, viability
  kernel, terminal invariant-set proof, or guarantee under arbitrary unmodeled motion.
- Sweep and obstacle-speed allowances are engineering bounds, not verified interval bounds.
- Circle patches bound observed points, not necessarily the complete hidden object.
- Nearest-neighbor association can switch identities. Kalman/acceleration/multi-hypothesis
  performance is not yet calibrated. Acceleration is auxiliary to a four-state Kalman
  estimate; the three motion hypotheses share that estimate and do not form a full IMM
  filter bank. A finite hypothesis set does not cover unknown maneuvers.
- The covariance margin is a per-time, per-obstacle Gaussian construction, not a joint
  trajectory collision probability.
- Obstacle and own-vessel estimation covariances are combined under an independence
  assumption. The current C ABI supplies zero own-vessel covariance unless a richer state
  adapter populates the C++ `Snapshot` interface; formal covariance studies must not leave it
  implicit.
- The adapted predictive/sampling comparators are project-specific finite-sequence methods,
  not reproductions of cited learning/MPC methods and do not inherit published guarantees.
- Deadline checks are cooperative software checks on ordinary Linux/Windows; they are not
  hard-real-time guarantees. The smoke latencies are desktop observations only.
- The wall scorer uses a conservative hull-circumcircle approximation; circle obstacles use
  oriented-rectangle truth geometry. Polygonal continuous collision checking needs further
  validation before formal S03/S12 runs.
- The PC-board bridge checksum/token prevents accidental corruption/replay in a controlled
  lab loop, but is not a production authenticated/encrypted actuator protocol.
- No real Orange Pi, LiDAR, positioning source, joystick, propulsion, rudder, watchdog,
  bench, water trial, or participant study has been tested.
