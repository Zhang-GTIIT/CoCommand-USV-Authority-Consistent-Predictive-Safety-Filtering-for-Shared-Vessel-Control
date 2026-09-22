# Performance evidence

Only short desktop software-smoke latency is currently recorded. Each run stores p50/p95/p99,
maximum observed end-to-end latency, planning latency per cycle, evaluated candidates/branches,
and integration steps. This is ordinary desktop wall-clock measurement, not hard real-time
evidence and not Orange Pi performance.

Use:

```sh
python3 -m cocommand benchmark --profile configs/hardware/arm64_generic.yaml --dry-run
```

The command intentionally refuses to invent board measurements. Run the native diagnostics,
replay, and a bounded target-board benchmark on the selected board, then record CPU/memory,
kernel/compiler, frequency/thermal/throttling, logging setting, and p50/p95/p99/max separately.

