"""Generate auditable publication-style figures and a scoped CV evidence report."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from pathlib import Path

from cocommand.focused_study import write_json
from cocommand.optimization_study import read_controls


def stratified_interval(rows, key, resamples=4000):
    groups = [[row[key] for row in rows if row["scenario"] == scene]
              for scene in ["static", "crossing", "late_high_throttle"]]
    rng = random.Random(917263)
    values = sorted(statistics.fmean(rng.choice(group) for group in groups for _ in group)
                    for _ in range(resamples))
    return values[int(0.025 * (resamples - 1))], values[int(0.975 * (resamples - 1))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("runs/resume_evidence_v1"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/research/2026-09-17"))
    args = parser.parse_args()
    root, output = args.root, args.output
    output.mkdir(parents=True, exist_ok=True)
    primary = json.loads((root / "evaluation/aggregate.json").read_text())
    followup = json.loads((root / "followup/aggregate.json").read_text())
    cases = json.loads((root / "evaluation/cases.json").read_text())
    names = ["paper_hypothetical", "steering_hold_contract"]
    paired = []
    for case in cases:
        all_controls = [read_controls(root / "evaluation/authority" / case["case_id"] / name / "control.csv") for name in names]
        metrics = [json.loads((root / "evaluation/authority" / case["case_id"] / name / "metrics.json").read_text()) for name in names]
        n = min(map(len, all_controls))
        changes = [[abs(math.degrees(float(row["applied_steering_rad"]) - float(row["requested_steering_rad"])))
                    for row in controls[:n]] for controls in all_controls]
        passes = [statistics.fmean(value <= 1e-10 for value in group) for group in changes]
        deviations = list(map(statistics.fmean, changes))
        paired.append({
            "case_id": case["case_id"], "scenario": case["scenario"], "matched_cycles": n,
            "baseline_collision": int(metrics[0]["collision"]), "constrained_collision": int(metrics[1]["collision"]),
            "baseline_pass": passes[0], "constrained_pass": passes[1], "pass_difference": passes[1] - passes[0],
            "baseline_deviation_deg": deviations[0], "constrained_deviation_deg": deviations[1],
            "deviation_difference_deg": deviations[1] - deviations[0],
            "baseline_progress_m": metrics[0]["north_progress_m"], "constrained_progress_m": metrics[1]["north_progress_m"],
            "baseline_min_gap_m": metrics[0]["minimum_true_hull_clearance_m"],
            "constrained_min_gap_m": metrics[1]["minimum_true_hull_clearance_m"],
        })
    matched = {"case_count": len(paired), "total_matched_cycles": sum(row["matched_cycles"] for row in paired),
               "baseline_pass": statistics.fmean(row["baseline_pass"] for row in paired),
               "constrained_pass": statistics.fmean(row["constrained_pass"] for row in paired),
               "pass_difference_95": stratified_interval(paired, "pass_difference"),
               "baseline_deviation_deg": statistics.fmean(row["baseline_deviation_deg"] for row in paired),
               "constrained_deviation_deg": statistics.fmean(row["constrained_deviation_deg"] for row in paired),
               "deviation_difference_deg_95": stratified_interval(paired, "deviation_difference_deg")}
    by_scene = {}
    for scene in ["static", "crossing", "late_high_throttle"]:
        subset = [row for row in paired if row["scenario"] == scene]
        by_scene[scene] = {"cases": len(subset), "baseline_collisions": sum(row["baseline_collision"] for row in subset),
                           "constrained_collisions": sum(row["constrained_collision"] for row in subset)}
    a, b = [primary["authority"][name] for name in names]
    speed = followup["short_circuit"]
    proof_checks = {
        "primary_cases_90": primary["paired_cases"] == 90,
        "primary_rollouts_180": primary["rollouts"] == 180,
        "zero_authority_output_violations": a["applied_throttle_violations"] == b["applied_throttle_violations"] == 0,
        "zero_unknown_trials": a["trials_with_unknown"] == b["trials_with_unknown"] == 0,
        "all_replay_commands_match": speed["action_mismatches"] == 0,
        "original_replay_matches_r01": speed["reference_mismatches"] == 0,
        "all_accepted_witnesses_complete": speed["incomplete_accepted_witnesses"] == 0,
        "timing_repeats_consistent": speed["repeat_inconsistencies"] == 0,
        "physics_refinement_complete": all(followup["physics_refinement"][name]["trials"] == 90 for name in names),
    }
    if not all(proof_checks.values()):
        raise RuntimeError(f"evidence audit failed: {proof_checks}")
    write_json(output / "evidence_audit.json", proof_checks)
    write_json(output / "statistics.json", {"primary": primary, "followup": followup,
                                            "matched_exposure": matched, "by_scenario": by_scene})
    with (output / "paired_case_summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(paired[0]))
        writer.writeheader()
        writer.writerows(paired)
    provenance = {str(path.as_posix()): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in [root / "evaluation/study_manifest.json", root / "followup/study_manifest.json",
                               root / "evaluation/aggregate.json", root / "followup/aggregate.json",
                               Path("configs/studies/resume_evidence_v1.yaml"), Path("configs/studies/search_short_circuit_v1.yaml")]}
    provenance["tools/report_resume_study.py"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    write_json(output / "provenance.json", provenance)
    dedup = primary["dedup"]
    short_pct = 100 * speed["integration_reduction_fraction"]
    latency_pct = 100 * speed["mean_case_latency_reduction"]
    latency_ci = [100 * x for x in speed["case_bootstrap_95_latency_reduction"]]
    baseline_p95, optimized_p95 = [speed[f"{name}_filter_call_ms"]["p95"] for name in ["baseline", "optimized"]]
    table_rows = "\n".join(f"| {scene} | {data['baseline_collisions']}/{data['cases']} | {data['constrained_collisions']}/{data['cases']} |"
                           for scene, data in by_scene.items())
    fine = followup["physics_refinement"]
    report = f"""# Focused CoCommand-USV evaluation — 17 September 2026

This is a controlled **synthetic** simulation and desktop replay study. It uses engineering-assumption vessel parameters and scripted human commands. No real boat, Orange Pi, participant, CBF, or continuous-time safety theorem is involved.

## R01: align backup predictions with executable authority

90 distinct paired cases, three encounter families, 20 seconds maximum per rollout: **180 rollouts**. Both variants preserve human throttle at output. Only the permitted throttle in predicted backup maneuvers changes. All sampled conditions, noise, perception, horizon, candidate ordering and scoring are matched. Wall-clock cutoffs are disabled; a deterministic integration budget remains in force.

| Encounter | Hypothetical-throttle baseline collisions | Steering-only backup collisions |
|---|---:|---:|
{table_rows}
| Total | {a['collisions']}/90 | {b['collisions']}/90 |

Observed collision fractions: **{100*a['collisions']/90:.1f}% vs {100*b['collisions']/90:.1f}%**. The Wilson 95% upper bound for the zero-event constrained result is **{100*b['collision_wilson_95'][1]:.2f}%**. This is not a zero-risk guarantee. The paired bootstrap change was {100*primary['paired_differences']['collision']['mean']:.1f} percentage points (95% interval {100*primary['paired_differences']['collision']['bootstrap_95'][0]:.1f} to {100*primary['paired_differences']['collision']['bootstrap_95'][1]:.1f}).

The baseline selected throttle-dependent witnesses in **{a['throttle_dependent_witness_cycles']}/{a['accepted_cycles']} accepted cycles ({100*a['dependent_selected_witness_fraction']:.1f}%)**; the constrained library selected zero. This diagnoses the selected witness, not impossibility of every alternative authorized continuation. Both variants had zero applied-throttle violations and zero search-budget unknown trials.

Mean minimum physical clearance: {a['mean_minimum_true_hull_clearance_m']:.3f} vs {b['mean_minimum_true_hull_clearance_m']:.3f} m. Mean northward progress: **{a['mean_north_progress_m']:.3f} vs {b['mean_north_progress_m']:.3f} m**. The progress cost is material: this safety filter is not a route planner, and reduced collisions cannot be called improved overall navigation performance.

## Human intent / equal exposure analysis

Collision terminates a rollout, so full-run averages have unequal exposure. As a supplemental analysis, each pair is compared only up to its earlier stopping time, yielding {matched['total_matched_cycles']} matched cycles across 90 cases. Case means are weighted equally; confidence intervals resample cases within encounter families.

- Exact human-command pass-through: **{100*matched['baseline_pass']:.2f}% vs {100*matched['constrained_pass']:.2f}%**.
- Paired change: {(matched['constrained_pass']-matched['baseline_pass'])*100:.2f} percentage points; stratified bootstrap 95% interval [{100*matched['pass_difference_95'][0]:.2f}, {100*matched['pass_difference_95'][1]:.2f}].
- Mean absolute steering correction: **{matched['baseline_deviation_deg']:.3f} vs {matched['constrained_deviation_deg']:.3f} degrees**; change interval [{matched['deviation_difference_deg_95'][0]:.3f}, {matched['deviation_difference_deg_95'][1]:.3f}] degrees.

These are scripted-input simulation results, not human trust, workload, or user-study findings. They do not remove the northward-progress tradeoff.

## R02: branch deduplication, including the negative result

On {dedup['snapshots']} replayed snapshots, exact deduplication produced zero command/outcome/clearance mismatches and reduced integration steps from {dedup['original_steps']:,} to {dedup['dedup_steps']:,} ({100*(1-dedup['dedup_steps']/dedup['original_steps']):.2f}%). Mean case latency reduction was {100*dedup['mean_case_latency_reduction']:.2f}%, with a 95% interval [{100*dedup['case_bootstrap_95_latency_reduction'][0]:.2f}%, {100*dedup['case_bootstrap_95_latency_reduction'][1]:.2f}%]. The interval spans zero; **a latency improvement is not established**.

## R03: stop after the first complete safety witness

The added optional optimization exploits existential candidate acceptance: one complete positive-clearance backup is enough. Unsafe candidates still exhaust the full declared library. Exact human priority, candidate order, horizon and clearance tests stay fixed. It is enabled only for steering-only minimum-modification search, not emergency commitment or largest-clearance selection.

- **{speed['replayed_states']:,} recorded control states** replayed with zero command/outcome mismatches and zero disagreement with the original R01 trace.
- {speed['accepted_states']:,} accepted states all retained a complete 52-point / 10.1-second witness with positive clearance; {speed['exhausted_states']} exhaustive-no-witness states remained explicit. No unknown states were promoted to safe.
- Integration steps: **{speed['baseline_integration_steps']:,} → {speed['optimized_integration_steps']:,} ({short_pct:.1f}% reduction)**.
- {speed['timed_states']:,} timed states, five measurements per variant after one warm-up, alternating order: mean case filter-call latency reduction **{latency_pct:.1f}%** (case-bootstrap 95% interval {latency_ci[0]:.1f}–{latency_ci[1]:.1f}%).
- P95 of per-state median filter-call latency: **{baseline_p95:.4f} → {optimized_p95:.4f} ms**; the tail did not improve. The mean/median benefit must not be called a worst-case or P95 speedup. This measures the filter call including Python/C-ABI overhead, not scan-to-actuator latency.

CPU: Intel Core i7-12700H, Windows 11, Release build, CPU only. Timings are desktop observations, not ARM64 or hard-real-time claims. The optimization may select a lower-clearance backup than exhaustive best-backup selection; minimum accepted sampled margin was {speed['minimum_accepted_backup_margin_m']:.6f} m. Command equivalence under this exhaustive-budget study is not a theorem about bounded-time search or emergency recovery.

## R04: halve the independent physics/scoring step

Repeated all 180 rollouts at 10 ms rather than 20 ms, without changing the 100 ms control interval. Collision counts were {fine['paper_hypothetical']['collisions']}/90 vs {fine['steering_hold_contract']['collisions']}/90. Changed trial classifications: {fine['paper_hypothetical']['changed_collision_classification']} baseline, {fine['steering_hold_contract']['changed_collision_classification']} constrained. This is a sensitivity check on the same cases, not 90 additional independent paired cases. Maximum change in a trial's minimum clearance was {max(fine[name]['maximum_minimum_gap_change_m'] for name in names):.6f} m.

## Reproduction and evidence

Run from the repository root with `PYTHONPATH=python` and the built native library available:

```sh
python -m cocommand.focused_study --phase pilot --run-dir runs/new_study/pilot --stage all
python -m cocommand.focused_study --phase evaluation --run-dir runs/new_study/evaluation --stage all
python -m cocommand.optimization_study --source runs/new_study/evaluation --run-dir runs/new_study/followup --stage all
python tools/report_resume_study.py --root runs/new_study --output artifacts/research/new_study
```

Frozen R01 code and DLL are archived under `runs/resume_evidence_v1/`; R03 replay verified baseline parity after the optional optimization was added. Manifests lock source/configuration/native hashes; resume refuses a mismatch. Raw scans, controls, physical scoring, failures and per-case timing samples are retained under `runs/resume_evidence_v1/` (Git-ignored). Public-safe aggregates and figures are in this directory. Matplotlib is an optional reporting dependency only.

Limitations: synthetic parameters, scripted operator inputs, only three circle-obstacle families, synchronous plant without injected computation/network delay, finite-horizon sampled safety, no independent real-vessel validation, no navigation goal completion criterion. The evaluation distribution was fixed before results; R03/R04 are explicitly post-R01 follow-ups.
"""
    (output / "report.md").write_text(report, encoding="utf-8")
    # Keep all CV numbers derivable from named fields, not manually invented constants.
    bullets = [
        f"Implemented an authority-consistent predictive safety filter for USV shared control, restricting backup maneuvers to executable steering actions; observed {b['collisions']}/90 collisions versus {a['collisions']}/90 for a hypothetical-throttle baseline in paired synthetic trials, while quantifying the associated loss in forward progress.",
        f"Added complete-witness early termination to C++ backup search, cutting trajectory-integration steps by {short_pct:.1f}% and achieving a {latency_pct:.1f}% average per-case reduction in filter-call latency on desktop replay, with identical immediate control decisions across {speed['replayed_states']:,} recorded states."
    ]
    cv = "# CoCommand-USV: Predictive Safety Filtering for Shared Vessel Control\n\n" + "\n\n".join("- " + bullet for bullet in bullets)
    cv += f"\n\nOptional third bullet:\n\n- Built an independent sensor-driven simulation benchmark with paired perturbations and 20-ms collision scoring; reproduced collision classifications at 10-ms resolution across 180 rollouts and quantified the tradeoff between operator-command preservation and navigation progress.\n\n## Claim ledger\n\n- Collision counts: `statistics.json -> primary.authority.*.collisions`; scope is synthetic, paired cases, not real boats.\n- Integration reduction: `statistics.json -> followup.short_circuit.integration_reduction_fraction`.\n- Latency reduction: mean of 90 case-level relative reductions, each based on paired medians of repeated filter-call measurements; not whole-controller latency or ARM64 latency.\n- Identical decisions means immediate applied throttle/steering, acceptance outcome, completeness and finite-set minimality status; chosen backup margin may differ.\n- No zero-risk, novel CBF, global-optimality, field-validation, or overall-navigation-performance claim is supported.\n- Progress fell from {a['mean_north_progress_m']:.2f} m to {b['mean_north_progress_m']:.2f} m on average; keep this qualification when explaining the safety result.\n- Describe your own implementation, debugging, analysis, and technical decisions accurately; method ownership and authorship follow the underlying project.\n"
    (output / "resume_bullets_en.md").write_text(cv, encoding="utf-8")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = ["#b45309", "#0369a1"]
    fig, axes = plt.subplots(2, 2, figsize=(12.6, 8.1), layout="constrained")
    fig.suptitle("CoCommand-USV | Paired synthetic evaluation", fontsize=17, fontweight="bold")
    ax = axes[0, 0]
    scenes = list(by_scene)
    for j, label in enumerate(["Hypothetical-throttle baseline", "Authority-constrained"]):
        counts = [by_scene[scene]["baseline_collisions" if j == 0 else "constrained_collisions"] for scene in scenes]
        bars = ax.bar([i + (j - 0.5) * 0.36 for i in range(3)], [100*x/30 for x in counts], width=0.36, color=colors[j], label=label)
        ax.bar_label(bars, labels=[f"{x}/30" for x in counts], padding=3)
    ax.set(xticks=range(3), xticklabels=["Static", "Crossing", "Late/high throttle"], ylabel="Observed collision fraction (%)", ylim=(0, 70), title="A  Safety outcome (90 paired cases)")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax = axes[0, 1]
    ax.scatter([row["baseline_deviation_deg"] for row in paired], [row["constrained_deviation_deg"] for row in paired], s=23, alpha=0.7, color=colors[1])
    maximum = max(max(row["baseline_deviation_deg"], row["constrained_deviation_deg"]) for row in paired) * 1.05
    ax.plot([0, maximum], [0, maximum], "--", color="#94a3b8", linewidth=1)
    ax.set(xlabel="Baseline mean correction (deg)", ylabel="Constrained mean correction (deg)", title="B  Steering correction (equal exposure)", xlim=(0, maximum), ylim=(0, maximum))
    ax.text(0.03, 0.96, f"Means: {matched['baseline_deviation_deg']:.2f} → {matched['constrained_deviation_deg']:.2f} deg", transform=ax.transAxes, va="top")
    ax = axes[1, 0]
    for j, (name, label) in enumerate([("baseline", "Exhaustive backups"), ("optimized", "First complete witness")]):
        values = [speed[f"{name}_filter_call_ms"][stat] for stat in ["median", "p95"]]
        bars = ax.bar([i + (j - 0.5) * 0.34 for i in range(2)], values, width=0.34, color=colors[j], label=label)
        ax.bar_label(bars, fmt="%.3f", padding=3, fontsize=8)
    ax.set(xticks=[0, 1], xticklabels=["Median", "P95 (no improvement)"], ylabel="Filter-call time (ms)", ylim=(0, max(baseline_p95, optimized_p95)*1.45), title="C  Search optimization (desktop replay)")
    ax.legend(frameon=False, loc="upper left", fontsize=8)
    ax = axes[1, 1]
    for row in paired:
        ax.plot([0, 1], [row["baseline_progress_m"], row["constrained_progress_m"]], color="#94a3b8", alpha=0.18, linewidth=0.8)
    means = [a["mean_north_progress_m"], b["mean_north_progress_m"]]
    ax.plot([0, 1], means, color="#7c3aed", linewidth=2.5, marker="o", markersize=8)
    for i, value in enumerate(means):
        ax.annotate(f"Mean {value:.2f} m", (i, value), xytext=(7, 8), textcoords="offset points", fontsize=9)
    ax.set(xticks=[0, 1], xticklabels=["Hypothetical baseline", "Authority-constrained"], ylabel="Northward progress (m)", xlim=(-0.2, 1.5), title="D  Progress cost (not goal completion)")
    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.18)
        ax.set_axisbelow(True)
    fig.savefig(output / "evaluation_overview.png", dpi=180)
    fig.savefig(output / "evaluation_overview.svg")
    plt.close(fig)
    write_json(output / "plot_environment.json", {"matplotlib": matplotlib.__version__})
    print(json.dumps({"output": output.as_posix(), "matched_exposure": matched, "cv_bullets": bullets, "checks": proof_checks}, indent=2))


if __name__ == "__main__":
    main()
