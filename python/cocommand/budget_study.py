"""R08: fixed candidate-resolution/work-budget ablation and recorded-failure diagnosis."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path

from .config import load_json_yaml
from .experiments import code_fingerprint
from .focused_study import cases, digest_file, write_json
from .native import NativeController, find_native_library
from .simulation import run_trial


def variants(protocol):
    return {f"{name}_b{budget}": {**definition, "max_integration_steps": budget}
            for name, definition in protocol["policies"].items() for budget in protocol["step_budgets"]}


def fresh_cases(protocol):
    source = load_json_yaml(protocol["source_protocol"])
    source.update({"generator_seed": protocol["generator_seed"],
                   "evaluation_cases_per_scenario": protocol["cases_per_family"]})
    return cases(source, "evaluation")


def make_task(case, name, protocol, stage, fingerprint):
    source = load_json_yaml(protocol["source_protocol"])
    task = copy.deepcopy(case)
    task.update({"study_id": protocol["study_id"], "experiment_id": stage, "tier": "evaluation",
                 "variant": name, "controller": "steering_hold_contract", "code_fingerprint": fingerprint,
                 "physics_step_s": protocol["physics_step_s"],
                 "overrides": {**source["common_overrides"], **variants(protocol)[name],
                               "mismatch_factor": case["mismatch_factor"]}})
    if stage == "R08_feedback":
        task["goal"] = copy.deepcopy(protocol["mission_goal"])
        task["command_profile"] = {"mode": "heading_feedback", "throttle": case["command_profile"]["throttle"],
                                   "goal_position": protocol["mission_goal"]["position"], **protocol["heading_feedback"]}
    task["task_hash"] = hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest()[:16]
    return task


def read_controls(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def diagnose_case(source, target):
    target.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((source / "manifest.json").read_text())
    task = manifest["task"]
    original = json.loads((source / "metrics.json").read_text())
    controls = read_controls(source / "control.csv")
    observations = [json.loads(line) for line in (source / "observations.jsonl").read_text().splitlines()]
    if len(controls) != len(observations):
        raise ValueError("diagnostic source is not time aligned")
    spec = load_json_yaml("configs/controllers/catalog.yaml")["controllers"][task["controller"]]
    reference_config = {**task["overrides"], "max_integration_steps": 2000000, "deadline_aware": False}
    counts = {"case_id": task["case_id"], "source_collision": original["collision"], "calls": 0,
              "reproduction_mismatches": 0, "unknown_calls": 0, "unknown_with_reference_witness": 0,
              "unknown_with_reference_rejection": 0, "unknown_with_reference_unknown": 0,
              "invalid_reference_witnesses": 0, "reference_command_changes_on_unknown": 0,
              "first_missed_witness_s": None, "seconds_from_first_miss_to_collision": None}
    state = list(task["scenario_config"]["initial_state"])
    with NativeController(spec, task["overrides"]) as limited, NativeController(spec, reference_config) as reference:
        with (target / "decisions.jsonl").open("w", encoding="utf-8") as stream:
            for row, obs in zip(controls, observations):
                now = float(row["sensor_timestamp_s"])
                human = [float(row["requested_throttle"]), float(row["requested_steering_rad"])]
                outputs = []
                for controller in [limited, reference]:
                    controller.process_scan(state, obs["ranges_m"], obs["hits"], 65, now, now)
                    outputs.append(controller.filter(state, human, obs["healthy"], now, now, now, now, now))
                limited_decision, ref = outputs
                mismatch = limited_decision["outcome"] != row["outcome"] or any(
                    abs(limited_decision[key] - float(row[key])) > 1e-12
                    for key in ["applied_throttle", "applied_steering_rad"])
                counts["calls"] += 1
                counts["reproduction_mismatches"] += mismatch
                unknown = row["outcome"] == "budget_exhausted_unknown"
                witness = ref["outcome"] == "witness_found"
                valid = not witness or (ref["complete_witness_samples"] == 52 and ref["predicted_minimum_clearance_m"] > 0)
                counts["invalid_reference_witnesses"] += not valid
                if unknown:
                    counts["unknown_calls"] += 1
                    counts["unknown_with_reference_witness"] += witness
                    counts["unknown_with_reference_rejection"] += ref["outcome"] == "exhausted_no_witness"
                    counts["unknown_with_reference_unknown"] += ref["outcome"] == "budget_exhausted_unknown"
                    counts["reference_command_changes_on_unknown"] += abs(ref["applied_steering_rad"] - float(row["applied_steering_rad"])) > 1e-12
                    if witness and counts["first_missed_witness_s"] is None:
                        counts["first_missed_witness_s"] = now
                gap = ref["predicted_minimum_clearance_m"]
                record = {"cycle": int(row["cycle"]), "time_s": now, "source_outcome": row["outcome"],
                          "reference_outcome": ref["outcome"], "reproduction_mismatch": mismatch,
                          "reference_witness_samples": ref["complete_witness_samples"], "valid_reference_witness": valid,
                          "reference_steering_rad": ref["applied_steering_rad"], "recorded_steering_rad": float(row["applied_steering_rad"]),
                          "reference_steps": ref["integration_steps"]}
                stream.write(json.dumps(record, allow_nan=False, separators=(",", ":")) + "\n")
                state = [float(row[key]) for key in ["n", "e", "psi_rad", "u_mps", "v_mps", "r_rad_s", "actual_thrust_n", "actual_delta_rad"]]
    if original["collision"] and counts["first_missed_witness_s"] is not None:
        counts["seconds_from_first_miss_to_collision"] = original["first_collision_time_s"] - counts["first_missed_witness_s"]
    write_json(target / "summary.json", counts)
    return counts


def run_stage(root, all_cases, protocol, stage, fingerprint):
    names = list(variants(protocol)) if stage == "R08_open" else protocol["feedback_variants"]
    duration = protocol["open_duration_s"] if stage == "R08_open" else protocol["feedback_duration_s"]
    for index, case in enumerate(all_cases):
        ordered = names[index % len(names):] + names[:index % len(names)]
        if index % 2:
            ordered = list(reversed(ordered))
        for name in ordered:
            target = root / stage / case["case_id"] / name
            if (target / "metrics.json").exists():
                continue
            task = make_task(case, name, protocol, stage, fingerprint)
            try:
                metrics = run_trial(task, target, duration)
            except Exception as exc:
                write_json(target / "failure.json", {"type": type(exc).__name__, "message": str(exc), "task": task})
                raise
            print(json.dumps({"stage": stage, "case": case["case_id"], "variant": name,
                              "case_index": index + 1, "total_cases": len(all_cases),
                              "collision": metrics["collision"], "goal": metrics["goal_reached"]}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/studies/budget_allocation_v1.yaml"))
    parser.add_argument("--run-dir", type=Path, default=Path("runs/budget_allocation_v1"))
    parser.add_argument("--stage", choices=["diagnose", "open", "feedback", "all", "dry-run"], default="all")
    args = parser.parse_args()
    protocol = load_json_yaml(args.config)
    all_cases = fresh_cases(protocol)
    if args.stage == "dry-run":
        print(json.dumps({"cases": len(all_cases), "open_rollouts": len(all_cases) * len(variants(protocol)),
                          "feedback_rollouts": len(all_cases) * len(protocol["feedback_variants"]),
                          "variants": variants(protocol)}, indent=2))
        return 0
    fingerprint = code_fingerprint()
    source = Path(protocol["diagnostic_source"])
    record = {"protocol": protocol, "source_fingerprint": fingerprint, "native_sha256": digest_file(find_native_library()),
              "diagnostic_parent_manifest_sha256": digest_file(source.parent / "study_manifest.json")}
    target = args.run_dir / "study_manifest.json"
    if target.exists() and json.loads(target.read_text()) != record:
        raise RuntimeError("resume refused: protocol/source/native changed")
    write_json(target, record)
    write_json(args.run_dir / "cases.json", all_cases)
    if args.stage in ["diagnose", "all"]:
        diagnostic = []
        for directory in sorted(source.glob("*/limited_short")):
            output = args.run_dir / "diagnosis" / directory.parent.name
            if (output / "summary.json").exists():
                result = json.loads((output / "summary.json").read_text())
            else:
                result = diagnose_case(directory, output)
            diagnostic.append(result)
            print(json.dumps({"diagnosed": directory.parent.name, "unknown_with_reference_witness": result["unknown_with_reference_witness"]}), flush=True)
        if len(diagnostic) != 30:
            raise RuntimeError("expected all 30 R05 limited-short cases")
        write_json(args.run_dir / "diagnosis.json", diagnostic)
    for stage, key in [("R08_open", "open"), ("R08_feedback", "feedback")]:
        if args.stage in [key, "all"]:
            run_stage(args.run_dir, all_cases, protocol, stage, fingerprint)
    print(json.dumps({"completed_requested_stage": args.stage, "run_dir": str(args.run_dir)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
