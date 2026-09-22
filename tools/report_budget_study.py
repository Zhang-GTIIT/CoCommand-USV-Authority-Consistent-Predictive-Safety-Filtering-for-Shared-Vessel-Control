"""Audit every R08 trial and report resolution/budget tradeoffs without selecting winners."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from cocommand.budget_study import read_controls, variants
from cocommand.focused_study import digest_file, write_json
from cocommand.reporting import wilson_interval


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def stratified_interval(by_family, resamples=4000):
    rng = random.Random(91708)
    samples = []
    size = sum(len(group) for group in by_family.values())
    for _ in range(resamples):
        samples.append(sum(sum(rng.choice(group) for _ in group) for group in by_family.values()) / size)
    samples.sort()
    return [samples[int(.025 * (resamples - 1))], samples[int(.975 * (resamples - 1))]]


def summarize(values):
    n = len(values)
    collisions = sum(item["metrics"]["collision"] for item in values)
    goals = sum(item["metrics"]["goal_reached"] is True for item in values)
    return {"cases": n, "collisions": collisions, "collision_wilson_95": wilson_interval(collisions, n),
            "goals": goals, "goal_wilson_95": wilson_interval(goals, n),
            "timeouts": sum(item["metrics"]["mission_outcome"] == "timeout" for item in values),
            "mean_unknown_fraction": statistics.fmean(item["metrics"]["budget_unknown_fraction"] for item in values),
            "mean_no_witness_fraction": statistics.fmean(item["metrics"]["no_witness_fraction"] for item in values),
            "mean_steps_per_cycle": statistics.fmean(item["metrics"]["mean_integration_steps"] for item in values),
            "mean_north_progress_m": statistics.fmean(item["metrics"]["north_progress_m"] for item in values),
            "mean_true_minimum_gap_m": statistics.fmean(item["metrics"]["minimum_true_hull_clearance_m"] for item in values)}


def primary_pairs(data, protocol):
    output = {}
    for stage in ["R08_open", "R08_feedback"]:
        for budget in [512, 2048]:
            left, right = f"u2_first_b{budget}", f"u4_first_b{budget}"
            selected = {}
            for metric in ["collision", "goal_reached", "matched_mean_correction_deg", "matched_pass_fraction",
                           "matched_mean_steps", "matched_unknown_fraction", "north_progress_m"]:
                groups = defaultdict(list)
                left_values, right_values = [], []
                matched_cycles = 0
                for case_id, a in data[stage][left].items():
                    b = data[stage][right][case_id]
                    count = min(len(a["controls"]), len(b["controls"]))
                    matched_cycles += count
                    if metric.startswith("matched_"):
                        def exposure(item):
                            controls = item["controls"][:count]
                            if metric == "matched_mean_correction_deg":
                                return math.degrees(statistics.fmean(abs(float(row["applied_steering_rad"]) - float(row["requested_steering_rad"])) for row in controls))
                            if metric == "matched_pass_fraction":
                                return statistics.fmean(abs(float(row["applied_steering_rad"]) - float(row["requested_steering_rad"])) <= 1e-12 for row in controls)
                            if metric == "matched_mean_steps":
                                return statistics.fmean(float(row["integration_steps"]) for row in controls)
                            return statistics.fmean(row["outcome"] == "budget_exhausted_unknown" for row in controls)
                        va, vb = exposure(a), exposure(b)
                    else:
                        va, vb = a["metrics"][metric], b["metrics"][metric]
                    if va is None or vb is None:
                        continue
                    left_values.append(float(va))
                    right_values.append(float(vb))
                    groups[a["task"]["scenario"]].append(float(vb) - float(va))
                if left_values:
                    selected[metric] = {"u2_mean": statistics.fmean(left_values), "u4_mean": statistics.fmean(right_values),
                        "paired_change_u4_minus_u2": statistics.fmean(b - a for a, b in zip(left_values, right_values)),
                        "family_stratified_case_bootstrap_95": stratified_interval(groups, protocol["bootstrap_resamples"]),
                        "paired_cases": len(left_values), "matched_cycles": matched_cycles}
            output[f"{stage}:budget{budget}"] = selected
    return output


def audit(root):
    evidence = {"trials": 0, "cycles": 0, "accepted_cycles": 0, "incomplete_or_nonpositive_witnesses": 0,
                "throttle_violations": 0, "exact_input_violations": 0, "step_budget_violations": 0,
                "time_alignment_violations": 0, "task_hash_violations": 0, "truth_access_manifest_violations": 0,
                "unexpected_outcomes": 0, "execution_failure_records": len(list(root.rglob("failure.json")))}
    data = defaultdict(lambda: defaultdict(dict))
    table, collision_rows = [], []
    for stage in ["R08_open", "R08_feedback"]:
        for path in sorted((root / stage).glob("*/*/metrics.json")):
            metrics, manifest = load(path), load(path.parent / "manifest.json")
            task = manifest["task"]
            controls = read_controls(path.parent / "control.csv")
            observations = [json.loads(line) for line in (path.parent / "observations.jsonl").read_text().splitlines()]
            evidence["trials"] += 1
            expected = hashlib.sha256(json.dumps({key: value for key, value in task.items() if key != "task_hash"}, sort_keys=True).encode()).hexdigest()[:16]
            evidence["task_hash_violations"] += expected != task["task_hash"]
            evidence["truth_access_manifest_violations"] += manifest["controller_truth_access"] is not False
            evidence["time_alignment_violations"] += len(controls) != len(observations)
            for row, obs in zip(controls, observations):
                evidence["cycles"] += 1
                evidence["time_alignment_violations"] += (int(row["cycle"]) != obs["cycle"] or abs(float(row["sensor_timestamp_s"]) - obs["sensor_timestamp_s"]) > 1e-12)
                evidence["throttle_violations"] += abs(float(row["applied_throttle"]) - float(row["requested_throttle"])) > 1e-12
                evidence["step_budget_violations"] += int(row["integration_steps"]) > task["overrides"]["max_integration_steps"]
                evidence["unexpected_outcomes"] += row["outcome"] not in {"witness_found", "exhausted_no_witness", "budget_exhausted_unknown"}
                if row["outcome"] == "witness_found":
                    evidence["accepted_cycles"] += 1
                    evidence["incomplete_or_nonpositive_witnesses"] += not (int(row["complete_witness_samples"]) == 52 and
                        float(row["predicted_minimum_clearance_m"]) > 0 and abs(float(row["actual_horizon_s"]) - 10.1) < 1e-12)
                    if int(row["paper_status"]) == 0:
                        evidence["exact_input_violations"] += abs(float(row["applied_steering_rad"]) - float(row["requested_steering_rad"])) > 1e-12
            data[stage][task["variant"]][task["case_id"]] = {"task": task, "controls": controls, "metrics": metrics}
            table.append({"stage": stage, "variant": task["variant"], "case": task["case_id"], "family": task["scenario"],
                          **{name: metrics[name] for name in ["collision", "goal_reached", "mission_outcome", "observed_duration_s",
                              "minimum_true_hull_clearance_m", "north_progress_m", "budget_unknown_fraction", "mean_integration_steps"]}})
            if metrics["collision"]:
                collision_rows.append({"stage": stage, "variant": task["variant"], "case": task["case_id"],
                    "collision_time_s": metrics["first_collision_time_s"], "terminal_outcome": controls[-1]["outcome"]})
    if evidence["trials"] != 840:
        raise RuntimeError(f"expected 840 complete trials, found {evidence['trials']}")
    expected_variants = {"R08_open": 9, "R08_feedback": 5}
    for stage in expected_variants:
        if len(data[stage]) != expected_variants[stage] or any(len(group) != 60 for group in data[stage].values()):
            raise RuntimeError("unbalanced/incomplete stage")
    evidence["generous_budget_short_circuit_compared_cycles"] = 0
    evidence["generous_budget_short_circuit_decision_mismatches"] = 0
    for case_id, a in data["R08_open"]["u2_exhaustive_b2000000"].items():
        b = data["R08_open"]["u2_first_b2000000"][case_id]
        evidence["generous_budget_short_circuit_decision_mismatches"] += abs(len(a["controls"]) - len(b["controls"]))
        for row_a, row_b in zip(a["controls"], b["controls"]):
            evidence["generous_budget_short_circuit_compared_cycles"] += 1
            evidence["generous_budget_short_circuit_decision_mismatches"] += (row_a["outcome"] != row_b["outcome"] or any(
                abs(float(row_a[key]) - float(row_b[key])) > 1e-12 for key in ["applied_throttle", "applied_steering_rad", "n", "e"]))
    return data, table, collision_rows, evidence


def plot(summary, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(15.2, 4.7), layout="constrained")
    budgets = [512, 2048, 2000000]
    for name, label, color in [("u2_exhaustive", "2° exhaustive", "#9d4d47"),
                                ("u2_first", "2° first witness", "#257c9c"),
                                ("u4_first", "4° first witness", "#54853d")]:
        values = [summary["R08_open"][f"{name}_b{b}"]["overall"]["collisions"] for b in budgets]
        axes[0].plot(range(3), values, "o-", label=label, color=color)
    axes[0].set(xticks=range(3), xticklabels=["512", "2048", "2,000,000"], xlabel="Integration-step budget",
                ylabel="Collisions / 60 cases", ylim=(-1, 60), title="Open-loop operator")
    axes[0].legend(fontsize=8)
    names = ["u2_first_b512", "u4_first_b512", "u2_first_b2048", "u4_first_b2048", "u2_first_b2000000"]
    bottom = [0] * 5
    for metric, label, color in [("goals", "Goal", "#257c9c"), ("collisions", "Collision", "#9d4d47"), ("timeouts", "Timeout", "#a4a9ae")]:
        vals = [summary["R08_feedback"][name]["overall"][metric] for name in names]
        axes[1].bar(range(5), vals, bottom=bottom, label=label, color=color)
        for i, value in enumerate(vals):
            if value:
                axes[1].text(i, bottom[i] + value / 2, str(value), ha="center", va="center", fontsize=9, color="white")
        bottom = [a + b for a, b in zip(bottom, vals)]
    axes[1].set(xticks=range(5), xticklabels=["2°\n512", "4°\n512", "2°\n2048", "4°\n2048", "2°\n2M"],
                xlabel="Candidate resolution / step budget", ylabel="Outcomes / 60 cases", ylim=(0, 72), title="Goal-feedback operator")
    axes[1].legend(ncol=3, loc="upper center", fontsize=8)
    for name, label, color in [("u2_first", "2° first witness", "#257c9c"), ("u4_first", "4° first witness", "#54853d")]:
        vals = [100 * summary["R08_open"][f"{name}_b{b}"]["overall"]["mean_unknown_fraction"] for b in budgets]
        axes[2].plot(range(3), vals, "o-", label=label, color=color)
    axes[2].set(xticks=range(3), xticklabels=["512", "2048", "2,000,000"], xlabel="Integration-step budget",
                ylabel="Mean per-case unknown fraction (%)", ylim=(-1, 100), title="Unknown is not exhaustive rejection")
    axes[2].legend(fontsize=8)
    for ax in [axes[0], axes[2]]:
        ax.grid(alpha=.2)
    fig.suptitle("R08 — fresh paired synthetic cases; no hardware or human participants", fontsize=13)
    fig.savefig(output / "budget_allocation.png", dpi=180)
    fig.savefig(output / "budget_allocation.svg")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, default=Path("runs/budget_allocation_v1"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/research/2026-09-17-budget"))
    args = parser.parse_args()
    root, output = args.run_dir, args.output
    manifest = load(root / "study_manifest.json")
    protocol = manifest["protocol"]
    data, table, collision_rows, evidence = audit(root)
    summary = {}
    for stage, groups in data.items():
        summary[stage] = {}
        for name, group in groups.items():
            summary[stage][name] = {"overall": summarize(list(group.values())),
                "by_family": {family: summarize([item for item in group.values() if item["task"]["scenario"] == family])
                              for family in sorted({item["task"]["scenario"] for item in group.values()})}}
    pairs = primary_pairs(data, protocol)
    diagnostic = load(root / "diagnosis.json")
    diag_totals = {key: sum(row[key] for row in diagnostic) for key in ["calls", "reproduction_mismatches", "unknown_calls",
        "unknown_with_reference_witness", "unknown_with_reference_rejection", "unknown_with_reference_unknown", "invalid_reference_witnesses"]}
    diag_totals.update({"cases": len(diagnostic), "collided_cases": sum(row["source_collision"] for row in diagnostic),
                       "collided_cases_with_prior_missed_reference_witness": sum(row["source_collision"] and row["unknown_with_reference_witness"] > 0 for row in diagnostic)})
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "statistics.json", {"groups": summary, "paired_contrasts": pairs, "diagnosis": diag_totals})
    write_json(output / "evidence_audit.json", evidence)
    write_json(output / "collision_records.json", collision_rows)
    write_json(output / "diagnosis_cases.json", diagnostic)
    write_json(output / "provenance.json", {"manifest": manifest, "files_sha256":
        {name: digest_file(root / name) for name in ["source_snapshot.zip", "native.dll", "cases.json", "diagnosis.json"]},
        "report_generator_sha256": digest_file(Path(__file__))})
    with (output / "trial_summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    lines = ["# R08: computation budget and candidate-resolution tradeoffs", "",
        "840 new closed-loop executions on 60 fresh paired synthetic initial conditions: 540 open-loop and 300 goal-feedback. "
        "The same 60 cases are repeated across configurations; this is not 840 independent scenarios. "
        "No C++ algorithm was changed; existing sampling/early-termination/work-budget configurations were ablated. "
        "Controller authority, the full 10.1 s prediction horizon and all 52 witness samples were retained.", "",
        "![Results](budget_allocation.png)", "", "## Recorded-failure diagnosis", "",
        f"Reproduced {diag_totals['calls']} decisions from all 30 original R05 limited-short trajectories with "
        f"{diag_totals['reproduction_mismatches']} command/outcome mismatches. Among {diag_totals['unknown_calls']} original unknowns, "
        f"a generous-budget reference found {diag_totals['unknown_with_reference_witness']} full witnesses, "
        f"exhaustively rejected {diag_totals['unknown_with_reference_rejection']}, and remained unknown for "
        f"{diag_totals['unknown_with_reference_unknown']}. "
        f"Of {diag_totals['collided_cases']} collided trajectories, {diag_totals['collided_cases_with_prior_missed_reference_witness']} "
        "had at least one earlier unknown with a reference witness.", "",
        "This single-decision counterfactual does not show that taking the alternative command would prevent collision. "
        "Exhaustive rejection refers only to the finite candidate/backup set under the prediction model, not physical impossibility. "
        "The replay uses observed scans and recorded ego state, never simulator obstacle truth.", ""]
    for stage, title in [("R08_open", "Open-loop operator, up to 20 s"), ("R08_feedback", "Goal-feedback operator, up to 40 s")]:
        lines.extend([f"## {title}", "", "| Policy / step budget | Collisions / 60 | Goals / 60 | Timeouts | Mean unknown % | Mean steps/cycle | Mean north progress, m |",
                      "|---|---:|---:|---:|---:|---:|---:|"])
        for name in (list(variants(protocol)) if stage == "R08_open" else protocol["feedback_variants"]):
            row = summary[stage][name]["overall"]
            goal_label = str(row["goals"]) if stage == "R08_feedback" else "not scored"
            timeout_label = str(row["timeouts"]) if stage == "R08_feedback" else "not scored"
            lines.append(f"| {name} | {row['collisions']} | {goal_label} | {timeout_label} | {100*row['mean_unknown_fraction']:.2f} | "
                         f"{row['mean_steps_per_cycle']:.1f} | {row['mean_north_progress_m']:.3f} |")
        lines.append("")
    lines.extend(["## Same-budget paired resolution contrasts", "",
        "Positive changes mean 4-degree minus 2-degree. Primary budget was fixed at 512 steps. "
        "Intervals resample paired cases within each of the three families (4,000 replicates), not cycles. "
        "Correction/pass-through/work/unknown metrics use matched exposure until the earlier endpoint of each pair. "
        "Secondary comparisons are exploratory; no multiple-testing-adjusted superiority claim is made.", "",
        "| Contrast | Outcome | Paired change [95% interval] |", "|---|---|---:|"])
    for contrast, metrics in pairs.items():
        for name in ["collision", "goal_reached", "matched_mean_correction_deg", "matched_unknown_fraction"]:
            if name not in metrics:
                continue
            row = metrics[name]
            lo, hi = row["family_stratified_case_bootstrap_95"]
            scale = 1 if name == "matched_mean_correction_deg" else 100
            unit = "degrees" if scale == 1 else "pp"
            lines.append(f"| {contrast} | {name} | {scale*row['paired_change_u4_minus_u2']:.3f} [{scale*lo:.3f}, {scale*hi:.3f}] {unit} |")
    lines.extend(["", "## Interpretation boundaries", "",
        "- More budget is not an equal-cost optimization; the 2,000,000-step reference is finite, not mathematical infinity.",
        "- A coarser grid changes admissible candidates and finite-set minimality. Even if it improves a budget-limited outcome, "
        "it cannot be called universally less intrusive or safer.",
        "- Exact operator input remains first and unquantized. Ego-only waypoint feedback is a script, not a human participant.",
        "- Unknown and no-witness fallback remain uncertified; a complete sampled witness is conditional on the prediction model.",
        "- New seeds test fresh draws from the original three scenario distributions, not arbitrary new environments.",
        "- Physics/scoring uses 20 ms and control 100 ms. This R08 study has not been numerically refined; earlier R07 showed "
        "that collision/timeout labels can change at 10 ms. Measured compute delay is not injected into dynamics.",
        "- Truth-isolation audit checks manifest declarations, with existing API/unit tests; it is not a formal information-flow proof.",
        "", "## Record audit", "", "```json", json.dumps(evidence, indent=2), "```", "",
        "Per-case/family statistics and collision records include all outcomes. See `docs/budget_allocation_protocol.md` "
        "and `docs/budget_allocation_reproduction.md`. Source/native snapshots and raw data remain in `runs/budget_allocation_v1/`. "
        "No hardware was used and nothing was pushed to GitHub.", ""])
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    plot(summary, output)
    print(json.dumps({"output": str(output), "diagnosis": diag_totals, "audit": evidence}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
