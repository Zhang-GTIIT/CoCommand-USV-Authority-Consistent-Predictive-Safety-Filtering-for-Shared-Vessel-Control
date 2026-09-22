# Deployment and ARM64 validation ladder

## Status vocabulary

1. `compiled`: application linked for the architecture.
2. `simulation_tested`: native unit/integration/mock checks ran on that host.
3. `board_replay_tested`: the same replay fixture ran on a physical board and parity/timing
   were recorded.
4. `bench_tested`: reviewed device protocols and independent safety measures were exercised
   without a water trial.
5. `field_tested`: separately authorized low-speed field validation completed.

This snapshot has desktop build/simulation evidence and an ARM64 cross-linked ELF. It does
not have stages 3-5.

## Native board build and replay

```sh
sh deploy/orangepi/install_deps.sh
sh deploy/orangepi/build_native.sh
sh deploy/orangepi/diagnose.sh > arm64_diagnostics.txt
sh deploy/orangepi/run_replay.sh
```

Compare the board's `runs/arm64_replay_output.jsonl` to the PC output using declared floating-
point tolerances; do not silently ignore boundary disagreements. Record CPU model, OS/kernel,
compiler, frequency, temperature/throttling, RSS, and latency percentiles.

## Cross-build used for this snapshot

The local ignored Zig tool cache was used as follows:

```powershell
.tools\python\cmake\data\bin\cmake.exe -S . -B build-arm64-cross -G Ninja `
  -DCMAKE_TOOLCHAIN_FILE=cmake/toolchains/zig-aarch64-linux.cmake `
  -DCMAKE_BUILD_TYPE=Release -DCOCOMMAND_BUILD_TESTS=ON -DCOCOMMAND_BUILD_PYBIND=OFF
.tools\python\cmake\data\bin\cmake.exe --build build-arm64-cross --parallel 2
```

The output header was checked as ELF64, `e_machine=183` (AArch64). It was not executed on a
board, so this is `implemented_not_tested_here`, not board validation.

## Real I/O refusal

`configs/hardware/real_unknown_disabled.yaml` is intentionally incomplete and disabled.
`UnknownHardwareActuatorSink` always refuses arming/sending. Hardware enable requires a
reviewed board/sensor/actuator profile, calibration, health/freshness, feedback, external
watchdog, independent stop, single-controller ownership, and a vessel-specific fail action.

The supplied systemd unit is mock-only and not automatically enabled. It runs as a non-root
user with filesystem/memory restrictions. There is no real-actuator systemd unit.

