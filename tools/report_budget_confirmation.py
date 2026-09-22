"""Report the pre-frozen, post-discovery R08-C follow-up; do not pool it with discovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from cocommand.budget_study import read_controls
from cocommand.focused_study import digest_file, write_json
from report_budget_study import load, stratified_interval, summarize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, default=Path("runs/budget_confirmation_v1"))
    parser.add_argument("--discovery", type=Path, default=Path("runs/budget_allocation_v1"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/research/2026-09-17-budget"))
    args = parser.parse_args()
    manifest = load(args.run_dir / "study_manifest.json")
    original = load(args.discovery / "study_manifest.json")
    if any(manifest[key] != original[key] for key in ["source_fingerprint", "native_sha256"]):
        raise RuntimeError("confirmation changed controller source/native")
    names = manifest["protocol"]["primary_contrast"]
    data = {name: {} for name in names}
    audit = {"trials": 0, "cycles": 0, "invalid_witnesses": 0, "throttle_violations": 0,
             "step_budget_violations": 0, "task_hash_violations": 0, "truth_manifest_violations": 0,
             "alignment_violations": 0, "exact_input_violations": 0,
             "execution_failures": len(list(args.run_dir.rglob("failure.json")))}
    for name in names:
        for path in sorted((args.run_dir / "R08_feedback").glob(f"*/{name}/metrics.json")):
            metrics, trial_manifest = load(path), load(path.parent / "manifest.json")
            task = trial_manifest["task"]
            if task["physics_step_s"] != 0.01 or task["overrides"]["max_integration_steps"] != 2048:
                raise RuntimeError("confirmation protocol mismatch")
            expected = hashlib.sha256(json.dumps({key: value for key, value in task.items() if key != "task_hash"}, sort_keys=True).encode()).hexdigest()[:16]
            audit["task_hash_violations"] += expected != task["task_hash"]
            audit["truth_manifest_violations"] += trial_manifest["controller_truth_access"] is not False
            controls = read_controls(path.parent / "control.csv")
            observations = [json.loads(line) for line in (path.parent / "observations.jsonl").read_text().splitlines()]
            audit["alignment_violations"] += len(controls) != len(observations)
            audit["trials"] += 1
            for row, obs in zip(controls, observations):
                audit["cycles"] += 1
                audit["alignment_violations"] += int(row["cycle"]) != obs["cycle"] or abs(float(row["sensor_timestamp_s"]) - obs["sensor_timestamp_s"]) > 1e-12
                audit["throttle_violations"] += abs(float(row["applied_throttle"]) - float(row["requested_throttle"])) > 1e-12
                audit["step_budget_violations"] += int(row["integration_steps"]) > 2048
                if row["outcome"] == "witness_found":
                    audit["invalid_witnesses"] += not (int(row["complete_witness_samples"]) == 52 and
                        float(row["predicted_minimum_clearance_m"]) > 0 and abs(float(row["actual_horizon_s"]) - 10.1) < 1e-12)
                    if int(row["paper_status"]) == 0:
                        audit["exact_input_violations"] += abs(float(row["applied_steering_rad"]) - float(row["requested_steering_rad"])) > 1e-12
            data[name][task["case_id"]] = {"task": task, "metrics": metrics, "controls": controls}
    if any(len(group) != 60 for group in data.values()) or set(data[names[0]]) != set(data[names[1]]):
        raise RuntimeError("confirmation must have all 60 paired cases")
    totals = {name: summarize(list(group.values())) for name, group in data.items()}
    families = {name: {family: summarize([r for r in group.values() if r["task"]["scenario"] == family])
                for family in sorted({r["task"]["scenario"] for r in group.values()})} for name, group in data.items()}
    contrasts, records = {}, []
    for metric in ["goal_reached", "collision", "matched_mean_correction_deg", "matched_unknown_fraction"]:
        by_family = defaultdict(list)
        values = {name: [] for name in names}
        for case_id in sorted(data[names[0]]):
            pair = [data[name][case_id] for name in names]
            count = min(len(item["controls"]) for item in pair)
            outcomes = []
            for item in pair:
                if metric == "matched_mean_correction_deg":
                    value = math.degrees(statistics.fmean(abs(float(r["applied_steering_rad"]) - float(r["requested_steering_rad"])) for r in item["controls"][:count]))
                elif metric == "matched_unknown_fraction":
                    value = statistics.fmean(r["outcome"] == "budget_exhausted_unknown" for r in item["controls"][:count])
                else:
                    value = float(item["metrics"][metric])
                outcomes.append(value)
            for name, value in zip(names, outcomes):
                values[name].append(value)
            difference = outcomes[1] - outcomes[0]
            by_family[pair[0]["task"]["scenario"]].append(difference)
            records.append({"case": case_id, "metric": metric, "u2": outcomes[0], "u4": outcomes[1], "matched_cycles": count})
        contrasts[metric] = {"means": {name: statistics.fmean(value) for name, value in values.items()},
            "paired_change_u4_minus_u2": statistics.fmean(b - a for a, b in zip(values[names[0]], values[names[1]])),
            "family_stratified_case_bootstrap_95": stratified_interval(by_family, manifest["protocol"]["bootstrap_resamples"])}
    args.output.mkdir(parents=True, exist_ok=True)
    record = {"manifest": manifest, "discovery_manifest_sha256": digest_file(args.discovery / "study_manifest.json"),
              "report_generator_sha256": digest_file(Path(__file__)), "totals": totals, "by_family": families,
              "paired_contrasts": contrasts, "audit": audit, "case_records": records}
    write_json(args.output / "confirmation_statistics.json", record)
    lines = ["# R08-C: independent-seed follow-up at the selected 2048-step budget", "",
        "This was specified AFTER exploratory R08, before these new outcomes. It validates a selected secondary setting "
        "without pretending 2048 was the original primary endpoint. The original 512-step goal result remained 4/60 versus 4/60.", "",
        "60 fresh paired initial conditions, base seed 320260917, original three family distributions; 120 rollouts. "
        "Both filters use 2048 steps, first-complete-witness search, steering-only authority, 10.1 s prediction, "
        "identical ego-only goal-feedback policy, and 10 ms physical integration/scoring. No parameter retuning. "
        "The discovery cohort used 20 ms; these new seeds do not constitute paired numerical convergence testing.", "",
        "| Candidate grid | Goals / 60 | Collisions / 60 | Timeouts | Mean unknown % |", "|---|---:|---:|---:|---:|"]
    for name, row in totals.items():
        lines.append(f"| {name} | {row['goals']} | {row['collisions']} | {row['timeouts']} | {100*row['mean_unknown_fraction']:.2f} |")
    lines.extend(["", "## Paired tradeoffs", "", "| Metric | 4° minus 2° [family-stratified case-bootstrap 95%] |", "|---|---:|"])
    for metric, row in contrasts.items():
        scale = 1 if metric == "matched_mean_correction_deg" else 100
        lo, hi = row["family_stratified_case_bootstrap_95"]
        unit = "degrees" if scale == 1 else "pp"
        lines.append(f"| {metric} | {scale*row['paired_change_u4_minus_u2']:.3f} [{scale*lo:.3f}, {scale*hi:.3f}] {unit} |")
    lines.extend(["", "A coarser grid changes finite-set intervention optimality and can miss viable controls. "
        "The primary endpoint is goal completion at this fixed budget, not an unconditional safety guarantee. "
        "Correction comparisons use matched elapsed time, not identical state/request pairs after closed-loop divergence. "
        "Retain failed cases and the unfavorable 512-step result alongside any CV claim.", "", "## Audit", "", "```json",
        json.dumps(audit, indent=2), "```", "",
        "Raw data: `runs/budget_confirmation_v1/`; original study: `runs/budget_allocation_v1/`. "
        "The full manifest, per-family summaries and paired records are in `confirmation_statistics.json`. "
        "Protocol/command: `docs/budget_confirmation_protocol.md`. Neither cohort uses physical devices or human participants.", ""])
    (args.output / "confirmation_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"totals": totals, "contrasts": contrasts, "audit": audit}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
