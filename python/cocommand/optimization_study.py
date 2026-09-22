"""Post-R01 full-witness short-circuit audit and physics-step sensitivity study."""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

from .config import load_json_yaml
from .experiments import code_fingerprint
from .focused_study import digest_file, make_task, write_json
from .native import NativeController, find_native_library
from .reporting import bootstrap_mean_interval, wilson_interval
from .simulation import _percentile, run_trial


def read_controls(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def same_action(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (a["outcome"] == b["outcome"] and a["search_complete"] == b["search_complete"]
            and a["minimality_established"] == b["minimality_established"]
            and abs(a["applied_throttle"] - b["applied_throttle"]) <= 1e-12
            and abs(a["applied_steering_rad"] - b["applied_steering_rad"]) <= 1e-12)


def replay_case(source: Path, case: dict[str, Any], common: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    directory = source / "authority" / case["case_id"] / "steering_hold_contract"
    controls = read_controls(directory / "control.csv")
    observations = [json.loads(line) for line in (directory / "observations.jsonl").read_text(encoding="utf-8").splitlines()]
    spec = load_json_yaml("configs/controllers/catalog.yaml")["controllers"]["steering_hold_contract"]
    state = list(case["scenario_config"]["initial_state"])
    rows = []
    with NativeController(spec, common) as baseline, \
         NativeController(spec, {**common, "first_complete_witness": True}) as optimized:
        for index, (control, observation) in enumerate(zip(controls, observations)):
            now = float(control["sensor_timestamp_s"])
            for controller in (baseline, optimized):
                controller.process_scan(state, observation["ranges_m"], observation["hits"], 65.0, now, now)
            requested = [float(control["requested_throttle"]), float(control["requested_steering_rad"])]
            benchmark = index % config["timing_stride_cycles"] == 0
            repetitions = config["timing_repeats"] + config["warmup_repeats"] if benchmark else 1
            timings: dict[str, list[float]] = {"baseline": [], "optimized": []}
            native_timings: dict[str, list[float]] = {"baseline": [], "optimized": []}
            outputs: dict[str, dict[str, Any]] = {}
            repeat_consistent = True
            for repeat in range(repetitions):
                order = [("baseline", baseline), ("optimized", optimized)]
                if (repeat + index + case["seed"]) % 2:
                    order.reverse()
                for name, controller in order:
                    start = time.perf_counter()
                    decision = controller.filter(state, requested, bool(observation["healthy"]), now, now, now, now, now)
                    latency = (time.perf_counter() - start) * 1000.0
                    if name in outputs:
                        repeat_consistent = repeat_consistent and same_action(outputs[name], decision)
                    outputs[name] = decision
                    if benchmark and repeat >= config["warmup_repeats"]:
                        timings[name].append(latency)
                        native_timings[name].append(decision["latency_ms"])
            a, b = outputs["baseline"], outputs["optimized"]
            row = {
                "cycle": index, "same_action": same_action(a, b), "repeat_consistent": repeat_consistent,
                "reference_match": a["outcome"] == control["outcome"] and all(
                    abs(a[key] - float(control[key])) <= 1e-12
                    for key in ("applied_throttle", "applied_steering_rad")),
                "baseline_steps": a["integration_steps"], "optimized_steps": b["integration_steps"],
                "baseline_branches": a["evaluated_branches"], "optimized_branches": b["evaluated_branches"],
                "outcome": b["outcome"], "complete_witness_samples": b["complete_witness_samples"],
                "accepted_complete": b["outcome"] != "witness_found" or (
                    b["complete_witness_samples"] == 52 and b["predicted_minimum_clearance_m"] > 0.0),
                "baseline_clearance": a["predicted_minimum_clearance_m"] if a["outcome"] == "witness_found" else None,
                "optimized_clearance": b["predicted_minimum_clearance_m"] if b["outcome"] == "witness_found" else None,
                "baseline_ms": timings["baseline"], "optimized_ms": timings["optimized"],
                "baseline_native_ms": native_timings["baseline"], "optimized_native_ms": native_timings["optimized"],
            }
            rows.append(row)
            state = [float(control[key]) for key in ["n", "e", "psi_rad", "u_mps", "v_mps", "r_rad_s", "actual_thrust_n", "actual_delta_rad"]]
    return {"case_id": case["case_id"], "rows": rows}


def summarize(source: Path, root: Path, cases: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    replay_paths = sorted((root / "replay").glob("*.json"))
    if len(replay_paths) == len(cases):
        blocks = [json.loads(path.read_text(encoding="utf-8"))["rows"] for path in replay_paths]
        rows = [row for block in blocks for row in block]
        samples = [row for row in rows if row["baseline_ms"]]
        case_reductions = []
        case_absolute_reductions = []
        for block in blocks:
            timed = [row for row in block if row["baseline_ms"]]
            a = statistics.fmean(statistics.median(row["baseline_ms"]) for row in timed)
            b = statistics.fmean(statistics.median(row["optimized_ms"]) for row in timed)
            case_reductions.append(1.0 - b / a)
            case_absolute_reductions.append(a - b)
        original_steps = sum(row["baseline_steps"] for row in rows)
        optimized_steps = sum(row["optimized_steps"] for row in rows)
        result["short_circuit"] = {
            "paired_cases": len(blocks), "replayed_states": len(rows), "timed_states": len(samples),
            "timings_per_variant": sum(len(row["baseline_ms"]) for row in samples),
            "action_mismatches": sum(not row["same_action"] for row in rows),
            "reference_mismatches": sum(not row["reference_match"] for row in rows),
            "repeat_inconsistencies": sum(not row["repeat_consistent"] for row in rows),
            "incomplete_accepted_witnesses": sum(not row["accepted_complete"] for row in rows),
            "accepted_states": sum(row["outcome"] == "witness_found" for row in rows),
            "exhausted_states": sum(row["outcome"] == "exhausted_no_witness" for row in rows),
            "unknown_states": sum(row["outcome"] == "budget_exhausted_unknown" for row in rows),
            "baseline_integration_steps": original_steps, "optimized_integration_steps": optimized_steps,
            "integration_reduction_fraction": 1.0 - optimized_steps / original_steps,
            "baseline_branches": sum(row["baseline_branches"] for row in rows),
            "optimized_branches": sum(row["optimized_branches"] for row in rows),
            "mean_case_latency_reduction": statistics.fmean(case_reductions),
            "case_bootstrap_95_latency_reduction": bootstrap_mean_interval(case_reductions, resamples=config["bootstrap_resamples"]),
            "mean_case_absolute_latency_reduction_ms": statistics.fmean(case_absolute_reductions),
            "selected_backup_margin_not_preserved": True,
            "minimum_accepted_backup_margin_m": min(row["optimized_clearance"] for row in rows if row["optimized_clearance"] is not None),
        }
        for name in ["baseline", "optimized"]:
            medians = [statistics.median(row[f"{name}_ms"]) for row in samples]
            native_medians = [statistics.median(row[f"{name}_native_ms"]) for row in samples]
            result["short_circuit"][f"{name}_filter_call_ms"] = {
                "median": statistics.median(medians), "p95": _percentile(medians, 0.95), "p99": _percentile(medians, 0.99)}
            result["short_circuit"][f"{name}_native_filter_ms"] = {
                "median": statistics.median(native_medians), "p95": _percentile(native_medians, 0.95)}
    refinement = {}
    for name in ["paper_hypothetical", "steering_hold_contract"]:
        metrics_paths = [root / "refinement" / case["case_id"] / name / "metrics.json" for case in cases]
        if all(path.exists() for path in metrics_paths):
            data = [json.loads(path.read_text(encoding="utf-8")) for path in metrics_paths]
            original = [json.loads((source / "authority" / case["case_id"] / name / "metrics.json").read_text(encoding="utf-8")) for case in cases]
            collisions = sum(row["collision"] for row in data)
            refinement[name] = {
                "trials": len(data), "physics_step_s": config["physics_refinement_s"],
                "collisions": collisions, "collision_wilson_95": wilson_interval(collisions, len(data)),
                "changed_collision_classification": sum(a["collision"] != b["collision"] for a, b in zip(original, data)),
                "maximum_minimum_gap_change_m": max(abs(a["minimum_true_hull_clearance_m"] - b["minimum_true_hull_clearance_m"]) for a, b in zip(original, data)),
                "applied_throttle_violations": sum(row["applied_throttle_violation_cycles"] for row in data),
                "trials_with_unknown": sum(row["budget_unknown_fraction"] > 0 for row in data),
            }
    result["physics_refinement"] = refinement
    write_json(root / "aggregate.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("runs/resume_evidence_v1/evaluation"))
    parser.add_argument("--run-dir", type=Path, default=Path("runs/resume_evidence_v1/followup"))
    parser.add_argument("--stage", choices=["replay", "refinement", "all", "report"], default="all")
    args = parser.parse_args()
    source, root = args.source.resolve(), args.run_dir.resolve()
    config = load_json_yaml("configs/studies/search_short_circuit_v1.yaml")
    source_manifest = json.loads((source / "study_manifest.json").read_text(encoding="utf-8"))
    source_config = source_manifest["protocol"]
    all_cases = json.loads((source / "cases.json").read_text(encoding="utf-8"))
    manifest = {"protocol": config, "source_manifest_sha256": digest_file(source / "study_manifest.json"),
                "source_fingerprint": code_fingerprint(), "native_sha256": digest_file(find_native_library())}
    path = root / "study_manifest.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != manifest:
        raise RuntimeError("follow-up resume refused: source/config/native changed")
    write_json(path, manifest)
    if args.stage in {"replay", "all"}:
        for index, case in enumerate(all_cases):
            target = root / "replay" / f"{case['case_id']}.json"
            if not target.exists():
                result = replay_case(source, case, source_config["common_overrides"], config)
                write_json(target, result)
                print(json.dumps({"stage": "short_circuit", "done": index + 1, "total": len(all_cases),
                                  "states": len(result["rows"]), "mismatches": sum(not row["same_action"] for row in result["rows"])}), flush=True)
    if args.stage in {"refinement", "all"}:
        for index, case in enumerate(all_cases):
            names = list(source_config["controllers"])
            if index % 2:
                names.reverse()
            for name in names:
                target = root / "refinement" / case["case_id"] / name
                if (target / "metrics.json").exists():
                    continue
                task = make_task(case, name, source_config, "evaluation")
                task["experiment_id"] = "R04"
                task["physics_step_s"] = config["physics_refinement_s"]
                task["code_fingerprint"] = code_fingerprint()
                try:
                    metrics = run_trial(task, target, source_config["duration_s"])
                except Exception as exc:
                    write_json(target / "failure.json", {"type": type(exc).__name__, "message": str(exc), "task": task})
                    raise
                print(json.dumps({"stage": "physics_refinement", "case": case["case_id"], "controller": name,
                                  "collision": metrics["collision"], "done_case": index + 1}), flush=True)
    result = summarize(source, root, all_cases, config)
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
