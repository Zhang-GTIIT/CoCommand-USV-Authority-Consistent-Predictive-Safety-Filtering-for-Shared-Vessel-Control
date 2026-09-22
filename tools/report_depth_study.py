"""Audit and report the frozen R05-R07 study; no controller tuning or reruns."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

from cocommand.reporting import bootstrap_mean_interval


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def audit(root):
    result = {"trials": 0, "control_cycles": 0, "accepted_cycles": 0, "invalid_accepted_witnesses": 0,
              "throttle_violations": 0, "truth_access_violations": 0, "task_hash_mismatches": 0,
              "alignment_mismatches": 0, "stress_optimization_compared_cycles": 0,
              "stress_optimization_decision_mismatches": 0,
              "execution_failure_records": len(list(root.rglob("failure.json")))}
    rows, failures = [], []
    for stage in ["R05_closed", "R06", "R07"]:
        for path in sorted((root / stage).glob("*/*/metrics.json")):
            metrics = read_json(path)
            manifest = read_json(path.parent / "manifest.json")
            task = manifest["task"]
            controls = read_csv(path.parent / "control.csv")
            observations = [json.loads(line) for line in (path.parent / "observations.jsonl").read_text().splitlines()]
            result["trials"] += 1
            result["truth_access_violations"] += manifest["controller_truth_access"] is not False
            frozen = {key: value for key, value in task.items() if key != "task_hash"}
            expected_hash = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()[:16]
            result["task_hash_mismatches"] += expected_hash != task["task_hash"]
            result["alignment_mismatches"] += len(controls) != len(observations)
            for control, obs in zip(controls, observations):
                result["control_cycles"] += 1
                result["alignment_mismatches"] += (int(control["cycle"]) != obs["cycle"] or
                    abs(float(control["sensor_timestamp_s"]) - obs["sensor_timestamp_s"]) > 1e-12)
                result["throttle_violations"] += abs(float(control["requested_throttle"]) - float(control["applied_throttle"])) > 1e-12
                if control["outcome"] == "witness_found":
                    result["accepted_cycles"] += 1
                    result["invalid_accepted_witnesses"] += not (int(control["complete_witness_samples"]) == 52 and
                        float(control["predicted_minimum_clearance_m"]) > 0)
            row = {"stage": stage, "case_id": task["case_id"], "variant": task["variant"], "family": task["scenario"],
                   **{key: metrics[key] for key in ["collision", "goal_reached", "mission_outcome", "goal_time_s",
                       "north_progress_m", "goal_distance_reduction_m", "path_length_m", "pass_through_rate",
                       "mean_steering_modification_rad", "budget_unknown_fraction", "no_witness_fraction"]}}
            rows.append(row)
            if metrics["collision"]:
                failures.append({"stage": stage, "case_id": task["case_id"], "variant": task["variant"],
                    "collision_time_s": metrics["first_collision_time_s"], "terminal_outcome": controls[-1]["outcome"],
                    "terminal_clearance_m": float(controls[-1]["true_minimum_clearance_m"])})
    for case_dir in sorted((root / "R06").iterdir()):
        baseline = read_csv(case_dir / "constrained" / "control.csv")
        optimized = read_csv(case_dir / "constrained_short" / "control.csv")
        if len(baseline) != len(optimized):
            result["stress_optimization_decision_mismatches"] += abs(len(baseline) - len(optimized))
        for a, b in zip(baseline, optimized):
            result["stress_optimization_compared_cycles"] += 1
            mismatch = a["outcome"] != b["outcome"] or any(abs(float(a[key]) - float(b[key])) > 1e-12
                for key in ["applied_throttle", "applied_steering_rad", "n", "e", "psi_rad"])
            result["stress_optimization_decision_mismatches"] += mismatch
    result["replay_calls"] = 0
    result["replay_invalid_acceptances"] = 0
    result["soft_deadline_overruns_by_budget"] = {}
    for path in sorted((root / "R05_replay").glob("*.jsonl")):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                result["replay_calls"] += 1
                result["replay_invalid_acceptances"] += not row["valid_acceptance"]
                if row["kind"] == "deadline_ms":
                    key = f"{row['budget']}:{row['variant']}"
                    block = result["soft_deadline_overruns_by_budget"].setdefault(key,
                        {"calls": 0, "returned_after_soft_budget": 0, "accepted_after_soft_budget": 0})
                    block["calls"] += 1
                    overrun = row["native_ms"] > row["budget"]
                    block["returned_after_soft_budget"] += overrun
                    block["accepted_after_soft_budget"] += overrun and row["outcome"] == "witness_found"
    if result["trials"] != 600:
        raise RuntimeError(f"incomplete study: {result['trials']} / 600 trials")
    return result, rows, failures


def paired_statistics(rows):
    result = {}
    for stage, left, right in [
        ("R06", "hypothetical", "constrained"),
        ("R05_closed", "limited_exhaustive", "limited_short"),
        ("R07", "open_hypothetical", "open_constrained"),
        ("R07", "feedback_hypothetical", "feedback_constrained"),
        ("R07", "open_constrained", "feedback_constrained"),
    ]:
        a = {r["case_id"]: r for r in rows if r["stage"] == stage and r["variant"] == left}
        b = {r["case_id"]: r for r in rows if r["stage"] == stage and r["variant"] == right}
        assert set(a) == set(b)
        outcomes = {}
        for metric in ["collision", "goal_reached", "north_progress_m", "goal_distance_reduction_m", "path_length_m"]:
            if any(a[key][metric] is None or b[key][metric] is None for key in a):
                continue
            differences = [float(b[key][metric]) - float(a[key][metric]) for key in sorted(a)]
            outcomes[metric] = {"mean_paired_difference": statistics.fmean(differences),
                                "case_bootstrap_95": bootstrap_mean_interval(differences, resamples=4000)}
        result[f"{stage}:{left}->{right}"] = {"paired_cases": len(a), "outcomes": outcomes}
    return result


def figures(summary, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.8), layout="constrained")
    totals = summary["budget_replay"]["totals"]
    budgets = [32, 64, 128, 256, 512, 1024, 4096]
    for variant, label, color in [("exhaustive", "Exhaustive backups", "#a44742"),
                                   ("short_circuit", "First complete witness", "#167a8a")]:
        axes[0].plot(budgets, [100 * totals[f"steps:{n}:{variant}"]["witness_fraction"] for n in budgets],
                     marker="o", label=label, color=color)
    axes[0].set(xscale="log", ylim=(0, 101), xlabel="Integration-step budget per decision",
                ylabel="Calls returning a complete witness (%)", title="R05: bounded computation")
    axes[0].legend(loc="lower right", fontsize=8)
    axes[0].grid(alpha=0.2)
    families = ["head_on", "overtaking", "multi_obstacle", "noisy_dropout_crossing", "late_static"]
    for offset, variant, label, color in [(-0.18, "hypothetical", "Hypothetical throttle", "#a44742"),
                                          (0.18, "constrained", "Authority constrained", "#167a8a")]:
        values = [summary["stress"][variant]["by_family"][name]["collisions"] for name in families]
        bars = axes[1].bar([i + offset for i in range(5)], values, width=0.35, color=color, label=label)
        axes[1].bar_label(bars, padding=2)
    axes[1].set(xticks=range(5), xticklabels=["Head-on", "Overtake", "Multiple", "Noise +\ndropout", "Late"],
                ylim=(0, 23), ylabel="Collisions / 20 cases", title="R06: held-out stress cases")
    axes[1].tick_params(axis="x", labelsize=8)
    axes[1].legend(fontsize=8, loc="upper left")
    variants = ["open_hypothetical", "open_constrained", "feedback_hypothetical", "feedback_constrained"]
    bottom = [0] * 4
    for metric, label, color in [("goals", "Goal reached", "#167a8a"), ("collisions", "Collision", "#a44742"),
                                 ("timeouts", "Timeout", "#a9adb3")]:
        values = [summary["mission"][v]["overall"][metric] for v in variants]
        bars = axes[2].bar(range(4), values, bottom=bottom, color=color, label=label)
        for i, value in enumerate(values):
            if value:
                axes[2].text(i, bottom[i] + value / 2, str(value), ha="center", va="center", color="white", fontsize=9)
        bottom = [a + b for a, b in zip(bottom, values)]
    axes[2].set(xticks=range(4), xticklabels=["Open\nHypoth.", "Open\nConstr.", "Feedback\nHypoth.", "Feedback\nConstr."],
                ylim=(0, 75), ylabel="Outcomes / 60 cases", title="R07: operator-model sensitivity")
    axes[2].legend(fontsize=8, ncol=3, loc="upper center")
    fig.suptitle("Synthetic USV evaluation — desktop CPU, no hardware or human participants", fontsize=13)
    fig.savefig(output / "depth_validation.png", dpi=180)
    fig.savefig(output / "depth_validation.svg")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, default=Path("runs/depth_validation_v1"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/research/2026-09-17-depth"))
    parser.add_argument("--refinement-dir", type=Path, default=Path("runs/depth_validation_refinement_v1"))
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    summary = read_json(args.run_dir / "aggregate.json")
    if any(summary.get(key) is None for key in ["budget_replay", "budget_closed", "stress", "mission"]):
        raise RuntimeError("cannot report an incomplete study")
    evidence, rows, collisions = audit(args.run_dir)
    paired = paired_statistics(rows)
    write_json(output / "statistics.json", summary)
    write_json(output / "evidence_audit.json", evidence)
    write_json(output / "paired_statistics.json", paired)
    write_json(output / "collision_records.json", collisions)
    with (output / "trial_summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    provenance = {"manifest": read_json(args.run_dir / "study_manifest.json"), "file_sha256": {}}
    for relative in ["source_snapshot.zip", "native.dll", "stress_cases.json", "aggregate.json"]:
        provenance["file_sha256"][relative] = hashlib.sha256((args.run_dir / relative).read_bytes()).hexdigest()
    write_json(output / "provenance.json", provenance)
    totals = summary["budget_replay"]["totals"]
    lines = ["# R05–R07: deeper validation and failure boundaries", "",
        "600 new closed-loop rollouts: 60 bounded-computation, 300 held-out stress, and 240 operator-model/mission sensitivity runs. "
        "The 90 original trajectories used for replay and the 60 reused mission initial conditions are NOT additional independent draws. "
        "Parameters were frozen before outcomes; failures are retained. Synthetic vessel; desktop CPU; no hardware or participant data.", "",
        "![Evaluation](depth_validation.png)", "", "## R05: complete-witness availability", "",
        "Fractions below use all evaluated calls, not only favorable reference states. Repeated wall-clock calls share states and are not independent samples. "
        "Primary budgets were fixed at 512 integration steps and 0.25 ms. Wall-clock deadlines are soft, host/load dependent, and not injected into plant dynamics.", "",
        "| Budget | Calls/variant | Exhaustive witness % | Optimized witness % | Paired gain, pp [case-bootstrap 95%] |",
        "|---|---:|---:|---:|---:|"]
    for key, a in totals.items():
        if a["variant"] != "exhaustive":
            continue
        prefix = key.rsplit(":", 1)[0]
        b = totals[prefix + ":short_circuit"]
        diff = summary["budget_replay"]["paired_differences"][prefix]
        lo, hi = diff["case_bootstrap_95"]
        lines.append(f"| {prefix} | {a['calls']} | {100*a['witness_fraction']:.2f} | {100*b['witness_fraction']:.2f} | "
                     f"{100*diff['mean_witness_fraction_gain']:.2f} [{100*lo:.2f}, {100*hi:.2f}] |")
    for key in ["invalid_accepts", "accepted_reference_disagreements", "step_overshoots"]:
        lines.extend(["", f"Replay `{key}` across all budgets/variants: {sum(v[key] for v in totals.values())}."])
    lines.extend(["", "The optimized search may choose a different future backup than the exhaustive maximum-clearance witness. "
                  "Equivalence applies to the immediate command/outcome when a complete witness is found; it is not equality of backup clearance or a recursive-safety proof.", "",
                  "### Closed loop, 512 steps", "", "| Search | Collisions / 30 | Mean unknown fraction | Mean north progress, m |", "|---|---:|---:|---:|"])
    for name, group in summary["budget_closed"].items():
        row = group["overall"]
        lines.append(f"| {name} | {row['collisions']}/30 | {row['mean_unknown_fraction']:.3f} | {row['mean_progress_m']:.3f} |")
    lines.extend(["", "## R06: new stress cases", "", "| Family | Hypothetical collisions | Constrained collisions | Optimized constrained collisions |", "|---|---:|---:|---:|"])
    for family in summary["stress"]["hypothetical"]["by_family"]:
        counts = [summary["stress"][v]["by_family"][family]["collisions"] for v in ["hypothetical", "constrained", "constrained_short"]]
        lines.append(f"| {family} | {counts[0]}/20 | {counts[1]}/20 | {counts[2]}/20 |")
    lines.extend(["", "These deliberately difficult families mix geometry, speed, noise/dropout and model mismatch. "
                  "This is not a factorial noise ablation, and failures cannot be causally attributed to any one component from this table alone. "
                  "A finite-horizon witness is conditional on the prediction model; no-witness fallback is not a certified safe controller.", "",
                  "## R07: operator model × controller", "",
                  "Each row has the same 60 selected initial conditions; goal (8,0), radius 1.5 m, 40 s limit. "
                  "Feedback uses ego pose/yaw rate and waypoint only, not obstacle truth. It is not a human-subject experiment. "
                  "Do not interpret arrival rates as filter-only effects across different operator rows.", "",
                  "| Operator / filter | Goal | Collision | Timeout | Mean north progress, m | Mean arrival time among successes, s |", "|---|---:|---:|---:|---:|---:|"])
    for name, group in summary["mission"].items():
        row = group["overall"]
        time_label = f"{row['mean_goal_time_successes_only_s']:.2f}" if row["mean_goal_time_successes_only_s"] is not None else "n/a"
        lines.append(f"| {name} | {row['goals']}/60 | {row['collisions']}/60 | {row['timeouts']}/60 | {row['mean_progress_m']:.3f} | {time_label} |")
    lines.extend(["", "Unequal stopping times make unpaired per-cycle command-preservation rates and successful-only travel times unsuitable as headline comparative claims. "
                  "`trial_summary.csv` retains path length, goal-distance reduction, intervention and outcomes. "
                  "`paired_statistics.json` includes case-level paired differences and bootstrap intervals.", "",
                  "## Audit and limits", "", "```json", json.dumps(evidence, indent=2), "```", "",
                  "All 52 discrete witness samples must pass positive clearance. This is not continuous-time verification. "
                  "The independent plant checks real hull separation at 20 ms, but does not model waves, currents, real sensor faults, or actual actuator protocols. "
                  "Compute latency is measured but not injected into the synchronous plant. Prior 10 ms refinement covered R01, not this entire new suite. "
                  "Original R01 zero observed collisions remain true only for its original 90 cases; use new stress failures when discussing generalization.", "",
                  "Reproduce with the commands in `docs/depth_validation_reproduction.md`. "
                  "Raw local scans/control logs and frozen source/native snapshots are under `runs/depth_validation_v1/`; "
                  "private absolute-path test logs remain ignored by Git.", ""])
    refinement_path = args.refinement_dir / "aggregate.json"
    if refinement_path.exists():
        refinement = read_json(refinement_path)
        check = {"trials": 0, "cycles": 0, "invalid_accepted_witnesses": 0, "throttle_violations": 0,
                 "execution_failures": len(list(args.refinement_dir.rglob("failure.json")))}
        for path in args.refinement_dir.glob("*/*/metrics.json"):
            check["trials"] += 1
            for row in read_csv(path.parent / "control.csv"):
                check["cycles"] += 1
                check["throttle_violations"] += abs(float(row["requested_throttle"]) - float(row["applied_throttle"])) > 1e-12
                if row["outcome"] == "witness_found":
                    check["invalid_accepted_witnesses"] += not (int(row["complete_witness_samples"]) == 52 and
                                                               float(row["predicted_minimum_clearance_m"]) > 0)
        if check["trials"] != 120:
            raise RuntimeError("incomplete numerical refinement")
        refinement["record_audit"] = check
        write_json(output / "physics_refinement.json", refinement)
        lines.extend(["", "## Post-analysis R07 numerical sensitivity", "",
            "Repeat all 120 feedback-operator rollouts at 10 ms physics/scoring instead of 20 ms; same cases, "
            "100 ms control, fixed policy and controller. These are NOT new independent trials. This follow-up "
            "was specified after the primary outcomes, before its own execution, without retuning.", "",
            "| Filter | Goals, 20→10 ms | Collisions, 20→10 ms | Changed goal / collision labels | Max absolute gap change, m |",
            "|---|---:|---:|---:|---:|"])
        for variant, row in refinement["summary"].items():
            original = summary["mission"][variant]["overall"]
            lines.append(f"| {variant} | {original['goals']}→{row['goals']}/60 | {original['collisions']}→{row['collisions']}/60 | "
                         f"{row['goal_classification_changes']} / {row['collision_classification_changes']} | "
                         f"{row['max_absolute_minimum_clearance_change_m']:.4f} |")
        lines.extend(["", "Discrete tracking/search can change closed-loop trajectories after small plant differences. "
                      "Even unchanged goal counts do not establish numerical convergence or continuous-time safety. "
                      "Every paired label/gap discrepancy is retained in `physics_refinement.json`.", "",
                      "Refinement record audit: `" + json.dumps(check) + "`.", ""])
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    figures(summary, output)
    print(json.dumps({"output": str(output), "audit": evidence}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
