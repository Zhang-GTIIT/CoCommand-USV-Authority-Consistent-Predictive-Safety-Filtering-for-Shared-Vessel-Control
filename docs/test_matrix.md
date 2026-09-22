# Verification matrix

| Required risk | Automated evidence |
|---|---|
| Units, rotation, thrust/rudder, energy/damping | `test_dynamics_energy_actuators_and_reverse` |
| 51 propagation intervals / 52 checks, RK4 first segment | `test_time_grids_and_rk4_switch_boundary` |
| Oriented rectangle-circle boundary/intersection/rotation | `test_geometry_strict_boundary` |
| Radar first return, exact range edge, no-hit, seam/fallback | `test_radar_first_hit_boundary_and_wrap_cluster` |
| Exact human command not quantized | native test and `test_exact_human_command_not_quantized_through_c_api` |
| Strict G=0 rejection and exhaustive status 2 | `test_geometry_strict_boundary` |
| Authority/reverse and recovery not postponed | dynamics, runtime, and recovery tests |
| Partial branch not a witness / timeout unknown != no-witness | `test_exact_human_pass_and_timeout_unknown` |
| Old witness must be revalidated | recovery revalidation test |
| Nested grids retain old points / interior islands sampled | candidate nested/disconnected coverage test |
| TCPA vs TTC/DCPA analytic cases | `test_tcpa_ttc_cases` |
| KF variable time, prediction-only memory, covariance growth, three shared-estimate motion hypotheses | tracker/covariance test |
| Truth isolation and fine scorer catches between-sample overlap | Python isolation/scorer tests |
| Schema typo rejection, switching, seed determinism, resume fingerprint | configuration/integration tests |
| Mock range/freshness/sequence, real hardware default refusal | runtime and hardware tests |
| Loopback duplicate/corruption/staleness | bridge tests |
| C++ runner/Python C ABI parity on exact command | runner selftest plus Python exact-command test |

Remaining before formal studies: denser analytic circle-fit fixtures, track-crossing identity
statistics, continuous polygon collision kernel, board parity/latency, target-device fault
injection, and any real I/O/bench/field validation.
