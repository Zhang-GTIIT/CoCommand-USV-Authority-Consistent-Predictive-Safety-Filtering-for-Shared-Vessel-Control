from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import (ConfigError, REPO_ROOT, expand_experiment, experiment_ids,
                     load_json_yaml, parse_seed_expression, validate_catalogs,
                     validate_experiment_config)
from .experiments import execute_tasks
from .hardware import HardwareRefused, udp_loopback_check, validate_hardware_profile
from .native import NativeController, NativeUnavailable, find_native_library
from .reporting import generate_report


def _json_print(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def command_doctor(_: argparse.Namespace) -> int:
    checks: dict[str, Any] = {"python": sys.version.split()[0], "platform": platform.platform(),
                              "headless": True, "neural_dependencies": False}
    try:
        checks["catalogs"] = validate_catalogs()
        checks["configuration"] = "ok"
    except ConfigError as exc:
        checks["configuration"] = f"error: {exc}"
    try:
        checks["native_library"] = str(find_native_library())
        controller_spec = load_json_yaml("configs/controllers/catalog.yaml")["controllers"]["steering_hold_contract"]
        with NativeController(controller_spec) as controller:
            checks["native_smoke_loaded"] = bool(controller.handle)
    except NativeUnavailable as exc:
        checks["native_library"] = f"error: {exc}"
    try:
        validate_hardware_profile("configs/hardware/real_unknown_disabled.yaml", enable_real=True)
        checks["hardware_fail_closed"] = False
    except HardwareRefused:
        checks["hardware_fail_closed"] = True
    _json_print(checks)
    return 0 if checks.get("configuration") == "ok" and checks.get("native_smoke_loaded") \
        and checks.get("hardware_fail_closed") else 1


def command_list_experiments(_: argparse.Namespace) -> int:
    manifest = load_json_yaml("configs/experiment_manifest_v1.yaml")
    for experiment_id, spec in manifest["experiments"].items():
        print(f"{experiment_id}\t{spec['kind']}")
    return 0


def command_list_controllers(_: argparse.Namespace) -> int:
    catalog = load_json_yaml("configs/controllers/catalog.yaml")["controllers"]
    for name, spec in catalog.items():
        flags = []
        if spec.get("simulation_only"):
            flags.append("simulation_only")
        if spec.get("adapted_not_literature_replication"):
            flags.append("adapted")
        print(f"{spec['code']}\t{name}\t{','.join(flags)}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    data = validate_experiment_config(args.path)
    _json_print({"valid": True, "id": data["id"], "path": str(Path(args.path))})
    return 0


def _expand(ids: list[str], tier: str, seed_expression: str | None) -> list[dict[str, Any]]:
    seeds = parse_seed_expression(seed_expression) if seed_expression else None
    tasks: list[dict[str, Any]] = []
    for experiment_id in ids:
        tasks.extend(expand_experiment(experiment_id, tier, seeds))
    return tasks


def _run_or_expand(args: argparse.Namespace, ids: list[str]) -> int:
    tasks = _expand(ids, args.tier, args.seeds)
    if args.dry_run:
        preview_limit = 25
        _json_print({"dry_run": True, "task_count": len(tasks),
                     "tasks_preview": tasks[:preview_limit],
                     "preview_truncated": len(tasks) > preview_limit,
                     "estimated_wall_time": "unmeasured_until_pilot",
                     "estimated_data_volume": "unmeasured_until_pilot",
                     "cache_scan": "performed only with --resume during execution",
                     "formal_experiments_started": False})
        return 0
    if args.tier in {"main", "pilot", "calibration", "stress"} and not args.confirm_formal:
        print("refusing non-smoke tier without --confirm-formal", file=sys.stderr)
        return 2
    duration = args.duration if args.duration is not None else (1.0 if args.tier == "smoke" else 30.0)
    run_dir = execute_tasks(tasks, run_root=Path(args.run_root), resume=args.resume, duration_s=duration)
    print(run_dir.resolve())
    return 0 if not any(run_dir.glob("tasks/*/failure.json")) else 1


def command_experiment(args: argparse.Namespace) -> int:
    return _run_or_expand(args, [args.id])


def command_batch(args: argparse.Namespace) -> int:
    return _run_or_expand(args, experiment_ids(args.ids))


def command_report(args: argparse.Namespace) -> int:
    print(generate_report(args.run_dir))
    return 0


def command_replay(args: argparse.Namespace) -> int:
    controller_spec = load_json_yaml("configs/controllers/catalog.yaml")["controllers"][args.controller]
    output: list[dict[str, Any]] = []
    with NativeController(controller_spec) as controller:
        for line_number, line in enumerate(Path(args.input).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            record = json.loads(line)
            tracks = controller.process_scan(record["state"], record["ranges_m"], record["hits"],
                                             record.get("max_range_m", 65.0), record["sensor_time_s"],
                                             record["receive_time_s"])
            decision = controller.filter(record["state"], record["human_command"], True,
                                         record["sensor_time_s"], record["receive_time_s"],
                                         record["receive_time_s"], record["receive_time_s"] + 0.1,
                                         record["receive_time_s"])
            output.append({"line": line_number, "tracks": tracks, "decision": decision})
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(json.dumps(row) for row in output) + "\n", encoding="utf-8")
    print(destination.resolve())
    return 0


def command_benchmark(args: argparse.Namespace) -> int:
    profile = validate_hardware_profile(args.profile)
    if args.dry_run:
        _json_print({"dry_run": True, "profile": profile["id"],
                     "measurements": ["wall_latency", "rss", "temperature_if_available", "frequency_if_available"],
                     "board_performance_claim": False})
        return 0
    print("benchmark execution requires an explicit target-board session; use --dry-run here", file=sys.stderr)
    return 2


def command_runtime(args: argparse.Namespace) -> int:
    if args.mode != "mock":
        print("only mock runtime is enabled; real hardware is fail-closed", file=sys.stderr)
        return 2
    runner_candidates = [REPO_ROOT / "build" / "cocommand_runner.exe",
                         REPO_ROOT / "build" / "cocommand_runner",
                         REPO_ROOT / "build" / "Release" / "cocommand_runner.exe"]
    runner = next((path for path in runner_candidates if path.is_file()), None)
    if runner is None:
        print("native runner not found", file=sys.stderr)
        return 1
    return subprocess.run([str(runner), "mock", str(args.cycles)], check=False).returncode


def command_hardware_check(args: argparse.Namespace) -> int:
    try:
        profile = validate_hardware_profile(args.profile, enable_real=args.enable_real)
    except HardwareRefused as exc:
        _json_print({"enabled": False, "refused": True, "reason": str(exc)})
        return 2 if args.enable_real else 1
    _json_print({"enabled": bool(args.enable_real), "profile": profile})
    return 0


def command_loopback(_: argparse.Namespace) -> int:
    result = udp_loopback_check()
    _json_print(result)
    return 0 if all(result[key] for key in ("accepted_valid", "rejected_duplicate", "rejected_corruption")) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cocommand")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor").set_defaults(func=command_doctor)
    sub.add_parser("list-experiments").set_defaults(func=command_list_experiments)
    sub.add_parser("list-controllers").set_defaults(func=command_list_controllers)
    validate = sub.add_parser("validate-config")
    validate.add_argument("path")
    validate.set_defaults(func=command_validate)
    for name, function in (("experiment", command_experiment), ("batch", command_batch)):
        command = sub.add_parser(name)
        command.add_argument("--id" if name == "experiment" else "--ids", required=True)
        command.add_argument("--tier", choices=["smoke", "pilot", "calibration", "main", "stress"], default="smoke")
        command.add_argument("--seeds")
        command.add_argument("--dry-run", action="store_true")
        command.add_argument("--resume", action="store_true")
        command.add_argument("--confirm-formal", action="store_true")
        command.add_argument("--duration", type=float)
        command.add_argument("--run-root", default=str(REPO_ROOT / "runs"))
        command.set_defaults(func=function)
    report = sub.add_parser("report")
    report.add_argument("--run-dir", required=True)
    report.set_defaults(func=command_report)
    replay = sub.add_parser("replay")
    replay.add_argument("--input", required=True)
    replay.add_argument("--controller", default="enhanced_steering")
    replay.add_argument("--output", default=str(REPO_ROOT / "runs" / "replay_output.jsonl"))
    replay.set_defaults(func=command_replay)
    benchmark = sub.add_parser("benchmark")
    benchmark.add_argument("--profile", required=True)
    benchmark.add_argument("--dry-run", action="store_true")
    benchmark.set_defaults(func=command_benchmark)
    runtime = sub.add_parser("runtime")
    runtime.add_argument("--mode", default="mock")
    runtime.add_argument("--config")
    runtime.add_argument("--cycles", type=int, default=3)
    runtime.set_defaults(func=command_runtime)
    hardware = sub.add_parser("hardware-check")
    hardware.add_argument("--profile", required=True)
    hardware.add_argument("--enable-real", action="store_true")
    hardware.set_defaults(func=command_hardware_check)
    sub.add_parser("loopback").set_defaults(func=command_loopback)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        return int(args.func(args))
    except (ConfigError, NativeUnavailable, HardwareRefused, FileNotFoundError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
