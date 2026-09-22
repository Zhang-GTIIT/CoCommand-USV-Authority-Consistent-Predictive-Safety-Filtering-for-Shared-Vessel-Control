# Architecture and semantics

## One control core, separate responsibilities

The C++17 `cocommand_core` object library owns online semantics: vessel prediction,
perception reconstruction, tracking/prediction, uncertainty, geometry, backup policies,
candidate ordering, authority/recovery state, and deadline checks. The native runner, stable C
ABI shared library, and optional pybind11 module all link the same object files.

Python's default experiment path uses the C ABI because it keeps the runtime dependency-free
and is straightforward on ARM64. The pybind11 target is optional (`COCOMMAND_BUILD_PYBIND=ON`)
and exposes selected direct analysis functions; it is not a second algorithm. Python owns the
independently written finer-step plant, sensor truth, scenario timing/noise, physical scorer,
experiment matrix, statistics, SVG/report generation, replay, and HIL transport.

```text
human command + vessel estimate + range/hit scan
                        |
                        v
        C++ perception/tracker -> Snapshot (no world truth)
                        |
                        v
          C++ SafetyFilter -> FilterResult/witness
                        |
         +--------------+---------------+
         |                              |
 native mock/runtime              Python C ABI
                                        |
                       independent plant + truth scorer
```

## Coordinates and time

Internal position is `(x,y)=(n,e)` in metres. Heading is radians from +x/north toward
+y/east. Body velocity is `(u,v)` and yaw rate is `r`. State is
`[n,e,psi,u,v,r,T,delta]`; command is normalized throttle `h_T` and steering target
`delta_cmd`. Actual thrust/steering remain dynamic actuator states.

Within one process, freshness/deadlines use a monotonic clock. Logs retain sensor, receive,
alignment, decision-complete, expected-apply, and actual-apply timestamps. Monotonic epochs
are not subtracted across hosts; HIL uses local receive-monotonic time for freshness and keeps
the sender timestamp only for audit/alignment analysis.

## Search semantics

A branch first executes the current candidate for the complete 0.1 s RK4 interval, then uses
its backup policy. Every checked `G` must be strictly positive. Once a sample fails, that
branch is permanently rejected. A deadline is checked between short integration blocks; an
incomplete branch is never a witness. Exhaustive no-witness, budget-unknown, invalid, stale,
and numerical-failure outcomes are distinct.

Exact admissible human input is always candidate zero. Correction grids are finite and sorted
by deviation with deterministic tie order. Nested mode adds 4/2/1/0.5 degree lattices without
discarding old samples; it does not assume a connected or monotone safe set.

## Parameter source

All current numerical vessel values are the task brief's synthetic software-test assumptions.
The effective diagonal mass is used directly and is not added to a second added-mass matrix.
The Coriolis matrix is skew-symmetric for that effective mass. Cross-flow strip damping is
integrated once. The tail-vector thrust map is an engineering assumption. See the vessel YAML
and source traceability table for units/status.

