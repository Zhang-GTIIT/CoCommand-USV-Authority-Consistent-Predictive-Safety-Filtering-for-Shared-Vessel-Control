"""R05-R07: bounded search, held-out stress, and scripted-operator sensitivity."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import random
import statistics
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from .config import load_json_yaml
from .experiments import code_fingerprint
from .focused_study import digest_file, write_json
from .native import NativeController, find_native_library
from .optimization_study import read_controls
from .reporting import bootstrap_mean_interval, wilson_interval
from .simulation import run_trial


def source_subset(source_cases, count):
    return [copy.deepcopy(case) for case in source_cases if int(case["case_id"].rsplit("_", 1)[1]) < count]


def stress_cases(config):
    result = []
    for family_index, family in enumerate(config["stress_families"]):
        for index in range(config["stress_cases_per_family"]):
            seed = config["generator_seed"] + family_index * 10000 + index
            rng = random.Random(seed)
            distance = rng.uniform(7.0, 13.0)
            speed = rng.uniform(0.9, 1.5)
            throttle = rng.uniform(0.5, 0.9)
            radius = rng.uniform(0.5, 1.0)
            noise, dropout = 0.03, 0.0
            if family == "head_on":
                obstacles = [{"shape": "circle", "center": [2.0, rng.uniform(-0.5, 0.5)],
                              "velocity": [-rng.uniform(0.6, 1.4), 0.0], "radius_m": radius}]
            elif family == "overtaking":
                speed, throttle = rng.uniform(1.4, 1.8), 1.0
                obstacles = [{"shape": "circle", "center": [-distance / 2, rng.uniform(-0.5, 0.5)],
                              "velocity": [rng.uniform(0.35, 0.75), 0.0], "radius_m": radius}]
            elif family == "multi_obstacle":
                obstacles = [
                    {"shape": "circle", "center": [0.0, rng.uniform(-0.5, 0.5)], "velocity": [0.0, 0.0], "radius_m": radius},
                    {"shape": "circle", "center": [3.0, -8.0], "velocity": [0.0, rng.uniform(0.6, 1.1)], "radius_m": rng.uniform(0.5, 0.9)},
                    {"shape": "circle", "center": [5.0, 8.0], "velocity": [0.0, -rng.uniform(0.6, 1.1)], "radius_m": rng.uniform(0.5, 0.9)},
                ]
            elif family == "noisy_dropout_crossing":
                velocity = rng.uniform(0.7, 1.3)
                obstacles = [{"shape": "circle", "center": [0.0, -velocity * distance / speed],
                              "velocity": [0.0, velocity], "radius_m": radius}]
                noise, dropout = 0.15, 0.15
            elif family == "late_static":
                distance, speed, throttle = rng.uniform(3.0, 4.5), rng.uniform(1.5, 2.0), 1.0
                obstacles = [{"shape": "circle", "center": [0.0, 0.0], "velocity": [0.0, 0.0], "radius_m": radius}]
            else:
                raise ValueError(f"unknown stress family {family}")
            result.append({
                "case_id": f"{family}_{index:03d}", "seed": seed, "scenario": family,
                "scenario_config": {"name": family, "initial_state": [-distance, rng.uniform(-0.5, 0.5),
                    math.radians(rng.uniform(-4.0, 4.0)), speed, 0.0, 0.0, 20.0 * throttle, 0.0],
                    "obstacles": obstacles, "range_noise_std_m": noise, "frame_dropout_probability": dropout},
                "command_profile": {"throttle": throttle, "steering_amplitude_deg": 0.7, "frequency_rad_s": 0.3},
                "mismatch_factor": rng.uniform(0.75, 1.25),
            })
    return result


def trial_task(case, variant, source_config, config, stage, fingerprint):
    task = copy.deepcopy(case)
    task.update({"study_id": config["study_id"], "experiment_id": stage,
                 "tier": "evaluation", "variant": variant, "controller": "steering_hold_contract",
                 "code_fingerprint": fingerprint,
                 "overrides": {**source_config["common_overrides"], "mismatch_factor": case["mismatch_factor"]}})
    if "hypothetical" in variant:
        task["controller"] = "paper_hypothetical"
    if "short" in variant:
        task["overrides"]["first_complete_witness"] = True
    if stage == "R05_closed":
        task["overrides"]["max_integration_steps"] = config["primary_step_budget"]
    if stage == "R07":
        task["goal"] = config["mission_goal"]
        if variant.startswith("feedback_"):
            task["command_profile"] = {"mode": "heading_feedback", "throttle": case["command_profile"]["throttle"],
                                       "goal_position": config["mission_goal"]["position"], **config["heading_feedback"]}
    task["task_hash"] = hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest()[:16]
    return task


def run_trials(root, all_cases, variants, source_config, config, stage, duration, fingerprint):
    for index, case in enumerate(all_cases):
        ordered = list(variants)
        if index % 2:
            ordered.reverse()
        for variant in ordered:
            target = root / stage / case["case_id"] / variant
            if (target / "metrics.json").exists():
                continue
            task = trial_task(case, variant, source_config, config, stage, fingerprint)
            try:
                metrics = run_trial(task, target, duration)
            except Exception as exc:
                write_json(target / "failure.json", {"type": type(exc).__name__, "message": str(exc), "task": task})
                raise
            print(json.dumps({"stage": stage, "case": case["case_id"], "done_case": index + 1,
                              "total_cases": len(all_cases), "variant": variant,
                              "collision": metrics["collision"], "goal": metrics["goal_reached"],
                              "unknown_fraction": round(metrics["budget_unknown_fraction"], 4)}), flush=True)


def replay_budget_case(source, case, config, source_config, target):
    directory = source / "authority" / case["case_id"] / "steering_hold_contract"
    controls = read_controls(directory / "control.csv")
    observations = [json.loads(line) for line in (directory / "observations.jsonl").read_text().splitlines()]
    if len(controls) != len(observations):
        raise ValueError("replay control/observation lengths differ")
    spec = load_json_yaml("configs/controllers/catalog.yaml")["controllers"]["steering_hold_contract"]
    definitions = [("steps", budget) for budget in config["step_budgets"]]
    definitions += [("deadline_ms", budget) for budget in config["deadline_budgets_ms"]]
    stats = {}
    target.parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack, target.with_suffix(".jsonl").open("w", encoding="utf-8") as stream:
        controllers = {}
        for kind, budget in definitions:
            for variant in ["exhaustive", "short_circuit"]:
                overrides = {**source_config["common_overrides"], "first_complete_witness": variant == "short_circuit"}
                if kind == "steps":
                    overrides["max_integration_steps"] = budget
                else:
                    overrides.update({"deadline_aware": True, "planning_budget_ms": budget})
                key = f"{kind}:{budget}:{variant}"
                controllers[key] = stack.enter_context(NativeController(spec, overrides))
                stats[key] = {"kind": kind, "budget": budget, "variant": variant, "calls": 0,
                              "reference_witness_calls": 0, "accepted": 0, "unknown": 0, "exhausted": 0,
                              "invalid_accepts": 0, "accepted_reference_disagreements": 0,
                              "step_overshoots": 0, "native_ms_sum": 0.0, "native_ms_max": 0.0}
        state = list(case["scenario_config"]["initial_state"])
        for index, (control, observation) in enumerate(zip(controls, observations)):
            now = float(control["sensor_timestamp_s"])
            requested = [float(control["requested_throttle"]), float(control["requested_steering_rad"])]
            for controller in controllers.values():
                controller.process_scan(state, observation["ranges_m"], observation["hits"], 65.0, now, now)
            for kind, budget in definitions:
                if kind == "deadline_ms" and index % config["deadline_stride_cycles"]:
                    continue
                repeats = config["deadline_repeats"] if kind == "deadline_ms" else 1
                for repeat in range(repeats):
                    variants = ["exhaustive", "short_circuit"]
                    if (case["seed"] + index + repeat) % 2:
                        variants.reverse()
                    for variant in variants:
                        key = f"{kind}:{budget}:{variant}"
                        decision = controllers[key].filter(state, requested, bool(observation["healthy"]), now, now, now, now, now)
                        accepted = decision["outcome"] == "witness_found"
                        valid = not accepted or (decision["complete_witness_samples"] == 52 and
                                                  decision["predicted_minimum_clearance_m"] > 0.0)
                        agrees = decision["outcome"] == control["outcome"] and all(
                            abs(decision[name] - float(control[name])) <= 1e-12
                            for name in ["applied_throttle", "applied_steering_rad"])
                        overshoot = kind == "steps" and decision["integration_steps"] > budget
                        stat = stats[key]
                        stat["calls"] += 1
                        stat["reference_witness_calls"] += control["outcome"] == "witness_found"
                        stat["accepted"] += accepted
                        stat["unknown"] += decision["outcome"] == "budget_exhausted_unknown"
                        stat["exhausted"] += decision["outcome"] == "exhausted_no_witness"
                        stat["invalid_accepts"] += not valid
                        stat["accepted_reference_disagreements"] += accepted and not agrees
                        stat["step_overshoots"] += overshoot
                        stat["native_ms_sum"] += decision["latency_ms"]
                        stat["native_ms_max"] = max(stat["native_ms_max"], decision["latency_ms"])
                        row = {"cycle": index, "kind": kind, "budget": budget, "variant": variant, "repeat": repeat,
                               "outcome": decision["outcome"], "steps": decision["integration_steps"],
                               "witness_samples": decision["complete_witness_samples"], "valid_acceptance": valid,
                               "reference_match": agrees, "reference_outcome": control["outcome"],
                               "applied_throttle": decision["applied_throttle"],
                               "applied_steering_rad": decision["applied_steering_rad"], "native_ms": decision["latency_ms"]}
                        stream.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
            state = [float(control[name]) for name in ["n", "e", "psi_rad", "u_mps", "v_mps", "r_rad_s", "actual_thrust_n", "actual_delta_rad"]]
    write_json(target, {"case_id": case["case_id"], "statistics": stats})


def summarize_trials(root, stage, all_cases, variants):
    output = {}
    for variant in variants:
        data = []
        for case in all_cases:
            path = root / stage / case["case_id"] / variant / "metrics.json"
            if not path.exists():
                return None
            data.append((case, json.loads(path.read_text())))
        def aggregate(group):
            n = len(group)
            values = [item[1] for item in group]
            collisions = sum(row["collision"] for row in values)
            return {"trials": n, "collisions": collisions, "collision_wilson_95": wilson_interval(collisions, n),
                    "goals": sum(row["goal_reached"] is True for row in values),
                    "timeouts": sum(row["mission_outcome"] == "timeout" for row in values),
                    "mean_pass_through": statistics.fmean(row["pass_through_rate"] for row in values),
                    "mean_steering_correction_deg": math.degrees(statistics.fmean(row["mean_steering_modification_rad"] for row in values)),
                    "mean_progress_m": statistics.fmean(row["north_progress_m"] for row in values),
                    "mean_unknown_fraction": statistics.fmean(row["budget_unknown_fraction"] for row in values),
                    "mean_no_witness_fraction": statistics.fmean(row["no_witness_fraction"] for row in values),
                    "applied_throttle_violations": sum(row["applied_throttle_violation_cycles"] for row in values),
                    "mean_goal_time_successes_only_s": (statistics.fmean(row["goal_time_s"] for row in values if row["goal_reached"])
                                                         if any(row["goal_reached"] for row in values) else None)}
        output[variant] = {"overall": aggregate(data), "by_family": {family: aggregate([item for item in data if item[0]["scenario"] == family])
                           for family in sorted({case["scenario"] for case in all_cases})}}
    return output


def summarize(root, source_cases, stress, config):
    result = {}
    paths = sorted((root / "R05_replay").glob("*.json"))
    if len(paths) == len(source_cases):
        blocks = [json.loads(path.read_text())["statistics"] for path in paths]
        totals = {}
        for key in blocks[0]:
            rows = [block[key] for block in blocks]
            first = rows[0]
            combined = {name: first[name] for name in ["kind", "budget", "variant"]}
            for field in ["calls", "reference_witness_calls", "accepted", "unknown", "exhausted", "invalid_accepts", "accepted_reference_disagreements", "step_overshoots"]:
                combined[field] = sum(row[field] for row in rows)
            combined["witness_fraction"] = combined["accepted"] / combined["calls"]
            combined["reference_witness_coverage"] = combined["accepted"] / combined["reference_witness_calls"]
            combined["unknown_fraction"] = combined["unknown"] / combined["calls"]
            combined["max_native_ms"] = max(row["native_ms_max"] for row in rows)
            combined["mean_native_ms"] = sum(row["native_ms_sum"] for row in rows) / combined["calls"]
            totals[key] = combined
        differences = {}
        for kind, budget in [("steps", value) for value in config["step_budgets"]] + [("deadline_ms", value) for value in config["deadline_budgets_ms"]]:
            values = [(block[f"{kind}:{budget}:short_circuit"]["accepted"] - block[f"{kind}:{budget}:exhaustive"]["accepted"]) /
                      block[f"{kind}:{budget}:exhaustive"]["calls"] for block in blocks]
            differences[f"{kind}:{budget}"] = {"mean_witness_fraction_gain": statistics.fmean(values),
                                               "case_bootstrap_95": bootstrap_mean_interval(values, resamples=config["bootstrap_resamples"])}
        result["budget_replay"] = {"case_count": len(blocks), "totals": totals, "paired_differences": differences}
    result["budget_closed"] = summarize_trials(root, "R05_closed", source_subset(source_cases, config["budget_closed_loop_cases_per_source_family"]),
                                                ["limited_exhaustive", "limited_short"])
    result["stress"] = summarize_trials(root, "R06", stress, ["hypothetical", "constrained", "constrained_short"])
    result["mission"] = summarize_trials(root, "R07", source_subset(source_cases, config["mission_cases_per_source_family"]),
                                        ["open_hypothetical", "open_constrained", "feedback_hypothetical", "feedback_constrained"])
    write_json(root / "aggregate.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, default=Path("runs/depth_validation_v1"))
    parser.add_argument("--stage", choices=["replay", "budget_closed", "stress", "mission", "all", "report"], default="all")
    args = parser.parse_args()
    config = load_json_yaml("configs/studies/depth_validation_v1.yaml")
    source = Path(config["source_run"])
    source_manifest = json.loads((source / "study_manifest.json").read_text())
    source_config = source_manifest["protocol"]
    source_cases = json.loads((source / "cases.json").read_text())
    fingerprint = code_fingerprint()
    record = {"protocol": config, "source_manifest_sha256": digest_file(source / "study_manifest.json"),
              "source_fingerprint": fingerprint, "native_sha256": digest_file(find_native_library())}
    root = args.run_dir
    manifest = root / "study_manifest.json"
    if manifest.exists() and json.loads(manifest.read_text()) != record:
        raise RuntimeError("resume refused: source/native/protocol changed")
    write_json(manifest, record)
    stress = stress_cases(config)
    write_json(root / "stress_cases.json", stress)
    if args.stage in {"replay", "all"}:
        for index, case in enumerate(source_cases):
            target = root / "R05_replay" / f"{case['case_id']}.json"
            if not target.exists():
                replay_budget_case(source, case, config, source_config, target)
                print(json.dumps({"stage": "R05_replay", "case": case["case_id"], "done": index + 1, "total": len(source_cases)}), flush=True)
    if args.stage in {"budget_closed", "all"}:
        run_trials(root, source_subset(source_cases, config["budget_closed_loop_cases_per_source_family"]),
                   ["limited_exhaustive", "limited_short"], source_config, config, "R05_closed", 20.0, fingerprint)
    if args.stage in {"stress", "all"}:
        run_trials(root, stress, ["hypothetical", "constrained", "constrained_short"], source_config, config,
                   "R06", config["stress_duration_s"], fingerprint)
    if args.stage in {"mission", "all"}:
        run_trials(root, source_subset(source_cases, config["mission_cases_per_source_family"]),
                   ["open_hypothetical", "open_constrained", "feedback_hypothetical", "feedback_constrained"],
                   source_config, config, "R07", config["mission_duration_s"], fingerprint)
    result = summarize(root, source_cases, stress, config)
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
