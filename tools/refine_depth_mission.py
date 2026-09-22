"""Post-analysis numerical sensitivity check; repeat all R07 feedback cases, not new draws."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from cocommand.experiments import code_fingerprint
from cocommand.focused_study import digest_file, write_json
from cocommand.native import find_native_library
from cocommand.simulation import run_trial


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("runs/depth_validation_v1"))
    parser.add_argument("--run-dir", type=Path, default=Path("runs/depth_validation_refinement_v1"))
    parser.add_argument("--physics-step", type=float, default=0.01)
    args = parser.parse_args()
    record = {"protocol": "post-analysis numerical sensitivity; every R07 feedback case, both filters; no retuning",
              "physics_step_s": args.physics_step, "source_manifest_sha256": digest_file(args.source / "study_manifest.json"),
              "source_fingerprint": code_fingerprint(), "native_sha256": digest_file(find_native_library()),
              "runner_sha256": digest_file(Path(__file__))}
    source_manifest = json.loads((args.source / "study_manifest.json").read_text())
    if any(record[key] != source_manifest[key] for key in ["source_fingerprint", "native_sha256"]):
        raise RuntimeError("refinement requires the original study source and native library")
    manifest = args.run_dir / "study_manifest.json"
    if manifest.exists() and json.loads(manifest.read_text()) != record:
        raise RuntimeError("resume refused: changed refinement provenance")
    write_json(manifest, record)
    results = {variant: {"trials": 0, "goals": 0, "collisions": 0, "timeouts": 0,
               "goal_classification_changes": 0, "collision_classification_changes": 0,
               "max_absolute_minimum_clearance_change_m": 0.0, "max_goal_time_change_common_successes_s": 0.0}
               for variant in ["feedback_hypothetical", "feedback_constrained"]}
    records = []
    paths = sorted((args.source / "R07").glob("*/feedback_*/metrics.json"))
    if len(paths) != 120:
        raise RuntimeError("expected all 120 R07 feedback trials")
    for index, path in enumerate(paths):
        original = json.loads(path.read_text())
        resolved = json.loads((path.parent / "resolved_config.yaml").read_text())
        task = copy.deepcopy(resolved["task"])
        task.pop("task_hash")
        task.update({"physics_step_s": args.physics_step, "experiment_id": "R07_refinement"})
        task["task_hash"] = hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest()[:16]
        target = args.run_dir / task["case_id"] / task["variant"]
        if (target / "metrics.json").exists():
            refined = json.loads((target / "metrics.json").read_text())
        else:
            try:
                refined = run_trial(task, target, resolved["duration_s"])
            except Exception as exc:
                write_json(target / "failure.json", {"type": type(exc).__name__, "message": str(exc), "task": task})
                raise
        row = results[task["variant"]]
        row["trials"] += 1
        row["goals"] += refined["goal_reached"]
        row["collisions"] += refined["collision"]
        row["timeouts"] += refined["mission_outcome"] == "timeout"
        goal_changed = original["goal_reached"] != refined["goal_reached"]
        collision_changed = original["collision"] != refined["collision"]
        row["goal_classification_changes"] += goal_changed
        row["collision_classification_changes"] += collision_changed
        gap_change = abs(original["minimum_true_hull_clearance_m"] - refined["minimum_true_hull_clearance_m"])
        row["max_absolute_minimum_clearance_change_m"] = max(row["max_absolute_minimum_clearance_change_m"], gap_change)
        if original["goal_reached"] and refined["goal_reached"]:
            row["max_goal_time_change_common_successes_s"] = max(row["max_goal_time_change_common_successes_s"],
                                                                abs(original["goal_time_s"] - refined["goal_time_s"]))
        records.append({"case": task["case_id"], "variant": task["variant"], "goal_changed": goal_changed,
                        "collision_changed": collision_changed, "minimum_clearance_change_m": gap_change})
        print(json.dumps({"completed": index + 1, "total": 120, "case": task["case_id"], "variant": task["variant"],
                          "goal_changed": goal_changed, "collision_changed": collision_changed}), flush=True)
    write_json(args.run_dir / "aggregate.json", {"provenance": record, "summary": results, "paired_records": records})
    print(json.dumps(results, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
