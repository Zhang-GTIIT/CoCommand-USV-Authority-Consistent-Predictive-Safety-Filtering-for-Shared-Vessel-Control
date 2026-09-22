"""Reproducible paired synthetic studies; no physical I/O or fabricated results."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from .config import REPO_ROOT, load_json_yaml
from .experiments import code_fingerprint
from .native import NativeController, find_native_library
from .reporting import bootstrap_mean_interval, wilson_interval
from .simulation import run_trial


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")


def cases(config: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    count = int(config[f"{phase}_cases_per_scenario"])
    p = config["perturbations"]
    result = []
    for scene_index, scene in enumerate(config["scenarios"]):
        for index in range(count):
            seed = int(config["generator_seed"]) + scene_index * 10000 + index
            if phase == "pilot":
                seed += 1000000
            rng = random.Random(seed)
            prefix = "late" if scene == "late_high_throttle" else scene
            distance = rng.uniform(*p[f"{prefix}_distance_m"])
            speed = rng.uniform(*p[f"{prefix}_speed_mps"])
            y = rng.uniform(*p["lateral_offset_m"])
            heading = math.radians(rng.uniform(*p["heading_deg"]))
            radius = rng.uniform(*p["obstacle_radius_m"])
            throttle = 1.0 if prefix == "late" else rng.uniform(*p["normal_throttle"])
            obstacle_speed = rng.uniform(*p["obstacle_speed_mps"]) if scene == "crossing" else 0.0
            arrival = distance / speed * rng.uniform(*p["crossing_arrival_factor"])
            scenario = {
                "name": scene,
                "initial_state": [-distance, y, heading, speed, 0.0, 0.0, 20.0 * throttle, 0.0],
                "range_noise_std_m": p["range_noise_std_m"],
                "obstacles": [{"shape": "circle", "center": [0.0, -obstacle_speed * arrival],
                               "velocity": [0.0, obstacle_speed], "radius_m": radius}],
            }
            result.append({
                "case_id": f"{scene}_{index:03d}", "seed": seed, "scenario": scene,
                "scenario_config": scenario,
                "command_profile": {"throttle": throttle, "steering_bias_deg": 0.0,
                                    "steering_amplitude_deg": p["steering_amplitude_deg"],
                                    "frequency_rad_s": 0.3},
                "mismatch_factor": rng.uniform(*p["plant_mismatch_factor"]),
            })
    return result


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_task(case: dict[str, Any], controller: str, config: dict[str, Any], phase: str) -> dict[str, Any]:
    task = {**case, "study_id": config["study_id"], "experiment_id": "R01",
            "tier": phase, "controller": controller,
            "overrides": {**config["common_overrides"], "mismatch_factor": case["mismatch_factor"]}}
    task["task_hash"] = hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest()[:16]
    return task


def initialize(root: Path, config: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    fingerprint = code_fingerprint()
    native_hash = digest_file(find_native_library())
    record = {"protocol": config, "phase": phase, "source_fingerprint": fingerprint,
              "native_sha256": native_hash}
    manifest_path = root / "study_manifest.json"
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        if any(old[key] != value for key, value in record.items()):
            raise RuntimeError("resume refused: protocol, phase, source, or native binary changed")
    else:
        write_json(manifest_path, {**record, "started_local": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                  "python": sys.version, "system": platform.platform(),
                                  "processor": platform.processor(), "formal_E_matrix": False,
                                  "physical_hardware_used": False})
    all_cases = cases(config, phase)
    write_json(root / "cases.json", all_cases)
    return all_cases


def run_authority(root: Path, config: dict[str, Any], phase: str, all_cases: list[dict[str, Any]]) -> None:
    count = len(all_cases) * len(config["controllers"])
    done = 0
    start = time.perf_counter()
    for case_index, case in enumerate(all_cases):
        variants = list(config["controllers"])
        if case_index % 2:
            variants.reverse()
        for controller in variants:
            target = root / "authority" / case["case_id"] / controller
            if (target / "metrics.json").is_file():
                done += 1
                continue
            task = make_task(case, controller, config, phase)
            task["code_fingerprint"] = code_fingerprint()
            try:
                metrics = run_trial(task, target, float(config["duration_s"]))
            except Exception as exc:
                write_json(target / "failure.json", {"type": type(exc).__name__, "message": str(exc), "task": task})
                raise
            done += 1
            print(json.dumps({"stage": "authority", "done": done, "total": count,
                              "case": case["case_id"], "controller": controller,
                              "collision": metrics["collision"], "cycles": metrics["sample_count_cycles"],
                              "throttle_witness_cycles": metrics["throttle_dependent_witness_cycles"],
                              "unknown": metrics["budget_unknown_fraction"],
                              "elapsed_s": round(time.perf_counter() - start, 1)}), flush=True)


def same_decision(left: dict[str, Any], right: dict[str, Any]) -> bool:
    fields = ["outcome", "search_complete", "minimality_established", "used_hypothetical_throttle"]
    if any(left[field] != right[field] for field in fields):
        return False
    for field in ["applied_throttle", "applied_steering_rad", "predicted_minimum_clearance_m"]:
        a, b = left[field], right[field]
        if a != b and not math.isclose(a, b, abs_tol=1e-10, rel_tol=1e-10):
            return False
    return True


def run_dedup(root: Path, config: dict[str, Any], all_cases: list[dict[str, Any]]) -> None:
    catalog = load_json_yaml("configs/controllers/catalog.yaml")["controllers"]
    for case_index, case in enumerate(all_cases):
        target = root / "dedup" / f"{case['case_id']}.json"
        if target.exists():
            continue
        source = root / "authority" / case["case_id"] / "steering_hold_contract"
        with (source / "control.csv").open(encoding="utf-8", newline="") as stream:
            controls = list(csv.DictReader(stream))
        observations = [json.loads(line) for line in (source / "observations.jsonl").read_text(encoding="utf-8").splitlines()]
        state = list(case["scenario_config"]["initial_state"])
        rows = []
        with NativeController(catalog["steering_hold_contract"], config["common_overrides"]) as original, \
             NativeController(catalog["steering_hold_contract"], {**config["common_overrides"], "backup_library_mode": 1}) as dedup:
            for index, (control, observation) in enumerate(zip(controls, observations)):
                now = float(control["sensor_timestamp_s"])
                for controller in (original, dedup):
                    controller.process_scan(state, observation["ranges_m"], observation["hits"], 65.0, now, now)
                if index % int(config["snapshot_stride_cycles"]) == 0:
                    command = [float(control["requested_throttle"]), float(control["requested_steering_rad"])]
                    timings: dict[str, list[float]] = {"original": [], "dedup": []}
                    outputs = {}
                    consistent_repeats = True
                    for repeat in range(int(config["benchmark_repeats"]) + 1):
                        order = [("original", original), ("dedup", dedup)]
                        if (repeat + index + case_index) % 2:
                            order.reverse()
                        for name, controller in order:
                            start = time.perf_counter()
                            output = controller.filter(state, command, bool(observation["healthy"]), now, now, now, now, now)
                            elapsed = (time.perf_counter() - start) * 1000.0
                            if name in outputs:
                                consistent_repeats = consistent_repeats and same_decision(outputs[name], output)
                            outputs[name] = output
                            if repeat:  # warm-up is not a timing observation
                                timings[name].append(elapsed)
                    equal = same_decision(outputs["original"], outputs["dedup"])
                    rows.append({"cycle": index, "same_decision": equal,
                                 "repeat_consistency": consistent_repeats,
                                 "original_steps": outputs["original"]["integration_steps"],
                                 "dedup_steps": outputs["dedup"]["integration_steps"],
                                 "original_branches": outputs["original"]["evaluated_branches"],
                                 "dedup_branches": outputs["dedup"]["evaluated_branches"],
                                 "original_ms": timings["original"], "dedup_ms": timings["dedup"],
                                 "outcome": outputs["original"]["outcome"]})
                state = [float(control[key]) for key in ["n", "e", "psi_rad", "u_mps", "v_mps", "r_rad_s", "actual_thrust_n", "actual_delta_rad"]]
        write_json(target, {"case_id": case["case_id"], "source": source.relative_to(root).as_posix(), "snapshots": rows})
        print(json.dumps({"stage": "dedup", "done": case_index + 1, "total": len(all_cases),
                          "snapshots": len(rows), "mismatches": sum(not row["same_decision"] for row in rows)}), flush=True)


def summarize(root: Path, config: dict[str, Any], all_cases: list[dict[str, Any]]) -> dict[str, Any]:
    records = []
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in config["controllers"]}
    for case in all_cases:
        for name in config["controllers"]:
            path = root / "authority" / case["case_id"] / name / "metrics.json"
            if not path.exists():
                raise RuntimeError(f"missing result: {case['case_id']} / {name}")
            metrics = json.loads(path.read_text(encoding="utf-8"))
            grouped[name].append(metrics)
            records.append({"case_id": case["case_id"], "scenario": case["scenario"], "controller": name, **metrics})
    metrics_to_compare = ["pass_through_rate", "mean_steering_modification_rad", "minimum_true_hull_clearance_m", "north_progress_m"]
    result: dict[str, Any] = {"scope": "synthetic paired evaluation", "paired_cases": len(all_cases),
                             "rollouts": len(records), "authority": {}, "paired_differences": {}}
    for name, data in grouped.items():
        n = len(data)
        collisions = sum(row["collision"] for row in data)
        accepted = sum(row["accepted_cycles"] for row in data)
        dependent = sum(row["throttle_dependent_witness_cycles"] for row in data)
        result["authority"][name] = {
            "trials": n, "collisions": collisions, "collision_wilson_95": wilson_interval(collisions, n),
            "cycles": sum(row["sample_count_cycles"] for row in data),
            "accepted_cycles": accepted, "throttle_dependent_witness_cycles": dependent,
            "dependent_selected_witness_fraction": dependent / max(1, accepted),
            "trials_with_dependent_selected_witness": sum(row["throttle_dependent_witness_cycles"] > 0 for row in data),
            "applied_throttle_violations": sum(row["applied_throttle_violation_cycles"] for row in data),
            "trials_with_unknown": sum(row["budget_unknown_fraction"] > 0 for row in data),
            **{f"mean_{key}": statistics.fmean(row[key] for row in data) for key in metrics_to_compare},
        }
    before, after = [grouped[name] for name in config["controllers"]]
    for key in metrics_to_compare + ["collision"]:
        differences = [float(b[key]) - float(a[key]) for a, b in zip(before, after)]
        result["paired_differences"][key] = {
            "direction": "steering_hold_contract minus paper_hypothetical",
            "mean": statistics.fmean(differences),
            "bootstrap_95": bootstrap_mean_interval(differences, resamples=config["bootstrap_resamples"])}
    dedup_paths = list((root / "dedup").glob("*.json"))
    if len(dedup_paths) == len(all_cases):
        blocks = [json.loads(path.read_text(encoding="utf-8"))["snapshots"] for path in sorted(dedup_paths)]
        rows = [row for block in blocks for row in block]
        block_savings = [1.0 - sum(statistics.median(row["dedup_ms"]) for row in block) /
                         sum(statistics.median(row["original_ms"]) for row in block) for block in blocks]
        result["dedup"] = {
            "cases": len(blocks), "snapshots": len(rows),
            "decision_mismatches": sum(not row["same_decision"] for row in rows),
            "inconsistent_repeats": sum(not row["repeat_consistency"] for row in rows),
            "unknown_snapshots": sum(row["outcome"] == "budget_exhausted_unknown" for row in rows),
            "original_steps": sum(row["original_steps"] for row in rows),
            "dedup_steps": sum(row["dedup_steps"] for row in rows),
            "original_branches": sum(row["original_branches"] for row in rows),
            "dedup_branches": sum(row["dedup_branches"] for row in rows),
            "mean_case_latency_reduction": statistics.fmean(block_savings),
            "case_bootstrap_95_latency_reduction": bootstrap_mean_interval(block_savings, resamples=config["bootstrap_resamples"]),
        }
    write_json(root / "aggregate.json", result)
    # Raw trial-level table remains available independently of rounded narrative claims.
    keys = ["case_id", "scenario", "controller", "sample_count_cycles", "collision", "minimum_true_hull_clearance_m",
            "accepted_cycles", "throttle_dependent_witness_cycles", "applied_throttle_violation_cycles",
            "pass_through_rate", "mean_steering_modification_rad", "budget_unknown_fraction", "north_progress_m", "wall_time_s"]
    with (root / "trial_summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/studies/resume_evidence_v1.yaml")
    parser.add_argument("--phase", choices=["pilot", "evaluation"], required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--stage", choices=["authority", "dedup", "all", "report"], default="all")
    args = parser.parse_args()
    config = load_json_yaml(args.config)
    root = args.run_dir.resolve()
    all_cases = initialize(root, config, args.phase)
    if args.stage in {"authority", "all"}:
        run_authority(root, config, args.phase, all_cases)
    if args.stage in {"dedup", "all"}:
        run_dedup(root, config, all_cases)
    result = summarize(root, config, all_cases)
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
