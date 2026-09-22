from __future__ import annotations

import csv
import json
import math
import random
from pathlib import Path
from typing import Any


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
    if trials <= 0:
        return None
    proportion = successes / trials
    denominator = 1.0 + z * z / trials
    center = (proportion + z * z / (2.0 * trials)) / denominator
    half = z * math.sqrt(proportion * (1.0 - proportion) / trials + z * z / (4.0 * trials * trials)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def bootstrap_mean_interval(values: list[float], *, resamples: int = 2000,
                            seed: int = 9173) -> tuple[float, float] | None:
    if not values:
        return None
    generator = random.Random(seed)
    means = []
    for _ in range(resamples):
        means.append(sum(generator.choice(values) for _ in values) / len(values))
    means.sort()
    return means[int(0.025 * (resamples - 1))], means[int(0.975 * (resamples - 1))]


def _task_directories(run_dir: Path) -> list[Path]:
    if (run_dir / "metrics.json").is_file():
        return [run_dir]
    tasks = run_dir / "tasks"
    return sorted(path for path in tasks.iterdir() if (path / "metrics.json").is_file()) if tasks.is_dir() else []


def _trajectory_svg(task_dir: Path) -> Path | None:
    control = task_dir / "control.csv"
    if not control.is_file():
        return None
    with control.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        return None
    points = [(float(row["n"]), float(row["e"])) for row in rows]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if abs(x1 - x0) < 1e-9:
        x1 = x0 + 1.0
    if abs(y1 - y0) < 1e-9:
        y1 = y0 + 1.0
    mapped = [f"{40 + 720 * (x - x0) / (x1 - x0):.2f},{360 - 320 * (y - y0) / (y1 - y0):.2f}"
              for x, y in points]
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400" viewBox="0 0 800 400">
<rect width="800" height="400" fill="white"/>
<text x="40" y="24" font-family="sans-serif" font-size="16">Software smoke / synthetic simulation - executed path</text>
<line x1="40" y1="360" x2="760" y2="360" stroke="#555"/><line x1="40" y1="40" x2="40" y2="360" stroke="#555"/>
<polyline points="{' '.join(mapped)}" fill="none" stroke="#1565c0" stroke-width="3"/>
<circle cx="{mapped[0].split(',')[0]}" cy="{mapped[0].split(',')[1]}" r="5" fill="#2e7d32"/>
<circle cx="{mapped[-1].split(',')[0]}" cy="{mapped[-1].split(',')[1]}" r="5" fill="#c62828"/>
<text x="360" y="392" font-family="sans-serif" font-size="13">x = north n (m)</text>
<text x="12" y="220" transform="rotate(-90 12 220)" font-family="sans-serif" font-size="13">y = east e (m)</text>
</svg>"""
    destination = task_dir / "trajectory_smoke.svg"
    destination.write_text(svg, encoding="utf-8")
    return destination


def generate_report(run_dir: str | Path) -> Path:
    run_path = Path(run_dir).resolve()
    task_dirs = _task_directories(run_path)
    if not task_dirs:
        raise FileNotFoundError(f"no completed task metrics under {run_path}")
    rows: list[dict[str, Any]] = []
    for task_dir in task_dirs:
        metrics = json.loads((task_dir / "metrics.json").read_text(encoding="utf-8"))
        manifest = json.loads((task_dir / "manifest.json").read_text(encoding="utf-8"))
        task = manifest["task"]
        rows.append({
            "task_hash": task["task_hash"], "experiment": task["experiment_id"],
            "tier": task["tier"], "controller": task["controller"],
            "scenario": task["scenario"], "seed": task["seed"],
            "collision": metrics["collision"],
            "minimum_true_hull_clearance_m": metrics["minimum_true_hull_clearance_m"],
            "pass_through_rate": metrics["pass_through_rate"],
            "budget_unknown_fraction": metrics["budget_unknown_fraction"],
            "latency_p95_ms": metrics["latency_ms"]["p95"],
            "formal_evidence": False,
        })
        _trajectory_svg(task_dir)
    summary = run_path / "summary.csv"
    with summary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    collision_count = sum(bool(row["collision"]) for row in rows)
    collision_interval = wilson_interval(collision_count, len(rows))
    pass_interval = bootstrap_mean_interval([float(row["pass_through_rate"]) for row in rows])
    report = run_path / "report.md"
    report.write_text(
        "# CoCommand software-smoke report\n\n"
        "> This report contains synthetic, short software checks. It is not a formal experiment, "
        "real-board benchmark, bench test, or real-vessel validation.\n\n"
        f"- Completed task records: {len(rows)}\n"
        f"- Collision-marked task records: {collision_count}\n"
        f"- Collision fraction Wilson 95% interval: {collision_interval}\n"
        f"- Trial-level bootstrap 95% interval for mean pass-through: {pass_interval}\n"
        "- Failed/timeout outcomes remain in each task's metrics and control log.\n"
        "- Physical clearance uses the independent fine-step scorer; planning clearance is logged separately.\n"
        "- See `summary.csv` and each task directory for resolved configuration, raw controls, observations, events, and preview SVG.\n",
        encoding="utf-8",
    )
    figure_status = {
        "Figure1": {"experiments": ["E01/S02", "E01/S03"], "status": "pending_formal_data"},
        "Figure2": {"experiments": ["E03", "E06", "E07"], "status": "pending_formal_data"},
        "Figure3": {"experiments": ["E02"], "status": "pending_formal_data"},
        "Figure4": {"experiments": ["E03-E08", "E10"], "status": "pending_formal_data"},
        "Figure5": {"experiments": ["E01", "E02", "E06"], "status": "pending_formal_data"},
        "Figure6A": {"experiments": ["E09"], "status": "pending_formal_data"},
        "Figure6B": {"experiments": ["E10", "H01"], "status": "pending_formal_data"},
        "Table3": {"experiments": ["E01", "E02", "E10"], "status": "pending_formal_data"},
        "smoke_preview": {"artifact": "tasks/*/trajectory_smoke.svg",
                          "status": "software_smoke_synthetic_simulation"},
    }
    (run_path / "figure_table_status.json").write_text(
        json.dumps(figure_status, indent=2), encoding="utf-8"
    )
    return report
