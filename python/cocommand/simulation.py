from __future__ import annotations

import csv
import copy
import hashlib
import json
import math
import platform
import random
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .config import REPO_ROOT, load_json_yaml
from .native import NativeController


@dataclass
class MovingObstacle:
    shape: str
    center: list[float]
    velocity: list[float]
    radius_m: float = 0.0
    a: list[float] | None = None
    b: list[float] | None = None


def _resolve_scenario(scenario_id: str, catalog: dict[str, Any]) -> dict[str, Any]:
    raw = dict(catalog["scenarios"][scenario_id])
    if "base" in raw:
        base_id = raw.pop("base")
        merged = _resolve_scenario(base_id, catalog)
        merged.update(raw)
        raw = merged
    return raw


def _derivative(state: Sequence[float], command: Sequence[float], mismatch: float = 1.0) -> list[float]:
    n, e, psi, u, v, r, thrust, delta = state
    throttle = max(-1.0, min(1.0, command[0]))
    steering = max(-math.radians(30), min(math.radians(30), command[1]))
    mass = [30.0 * mismatch, 37.0 * mismatch, 5.0 * mismatch]
    cnu = [-mass[1] * v * r, mass[0] * u * r, (mass[1] - mass[0]) * u * v]
    cross_y = cross_n = 0.0
    strips = 41  # deliberately different plant discretization from the predictor
    dx = 1.2 / strips
    for index in range(strips):
        x = -0.6 + (index + 0.5) * dx
        local = v + x * r
        force = 0.5 * 1000.0 * 1.0 * 0.07 * local * abs(local) * dx
        cross_y += force
        cross_n += x * force
    damping = [(4.0 * u + 6.0 * abs(u) * u) * mismatch,
               (12.0 * v + cross_y) * mismatch,
               (3.0 * r + cross_n) * mismatch]
    tau = [thrust * math.cos(delta), -thrust * math.sin(delta), 0.5 * thrust * math.sin(delta)]
    thrust_command = 20.0 * throttle if throttle >= 0.0 else 12.0 * throttle
    delta_dot = max(-math.radians(60), min(math.radians(60), (steering - delta) / 0.25))
    return [
        math.cos(psi) * u - math.sin(psi) * v,
        math.sin(psi) * u + math.cos(psi) * v,
        r,
        (tau[0] - cnu[0] - damping[0]) / mass[0],
        (tau[1] - cnu[1] - damping[1]) / mass[1],
        (tau[2] - cnu[2] - damping[2]) / mass[2],
        (thrust_command - thrust) / 0.35,
        delta_dot,
    ]


def _add(state: Sequence[float], derivative: Sequence[float], scale: float) -> list[float]:
    return [value + scale * slope for value, slope in zip(state, derivative)]


def plant_step(state: Sequence[float], command: Sequence[float], dt: float,
               mismatch: float = 1.0) -> list[float]:
    """Independent plant RK4 with finer integration and its own implementation."""
    k1 = _derivative(state, command, mismatch)
    k2 = _derivative(_add(state, k1, dt * 0.5), command, mismatch)
    k3 = _derivative(_add(state, k2, dt * 0.5), command, mismatch)
    k4 = _derivative(_add(state, k3, dt), command, mismatch)
    result = [value + dt * (a + 2 * b + 2 * c + d) / 6.0
              for value, a, b, c, d in zip(state, k1, k2, k3, k4)]
    result[7] = max(-math.radians(30), min(math.radians(30), result[7]))
    return result


def _ray_circle(origin: Sequence[float], direction: Sequence[float], center: Sequence[float],
                radius: float) -> float | None:
    qx, qy = origin[0] - center[0], origin[1] - center[1]
    b = 2.0 * (qx * direction[0] + qy * direction[1])
    c = qx * qx + qy * qy - radius * radius
    disc = b * b - 4.0 * c
    if disc < 0:
        return None
    root = math.sqrt(disc)
    roots = [value for value in ((-b - root) / 2.0, (-b + root) / 2.0) if value >= 0]
    return min(roots) if roots else None


def _cross(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _ray_segment(origin: Sequence[float], direction: Sequence[float],
                 a: Sequence[float], b: Sequence[float]) -> float | None:
    edge = [b[0] - a[0], b[1] - a[1]]
    denominator = _cross(direction, edge)
    if abs(denominator) < 1e-12:
        return None
    offset = [a[0] - origin[0], a[1] - origin[1]]
    ray_t = _cross(offset, edge) / denominator
    segment_t = _cross(offset, direction) / denominator
    return ray_t if ray_t >= 0 and 0 <= segment_t <= 1 else None


def _stable_random(seed: int, time_index: int, beam: int, channel: str) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{time_index}:{beam}:{channel}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def simulate_scan(state: Sequence[float], obstacles: Sequence[MovingObstacle], *, seed: int,
                  time_index: int, time_s: float, scenario: dict[str, Any],
                  beams: int = 360, max_range: float = 65.0) -> tuple[list[float], list[bool], bool]:
    frame_dropout = float(scenario.get("frame_dropout_probability", 0.0))
    if _stable_random(seed, time_index, -1, "frame").random() < frame_dropout:
        return [max_range] * beams, [False] * beams, False
    ranges, hits = [], []
    noise_std = float(scenario.get("range_noise_std_m", 0.0))
    hidden = False
    if "occlusion_window_s" in scenario:
        hidden = scenario["occlusion_window_s"][0] <= time_s < scenario["occlusion_window_s"][1]
    if "visibility_after_s" in scenario:
        hidden = time_s < scenario["visibility_after_s"]
    for beam in range(beams):
        bearing = -math.pi + 2 * math.pi * beam / beams
        angle = state[2] + bearing
        direction = [math.cos(angle), math.sin(angle)]
        closest = max_range
        hit = False
        if not hidden:
            for obstacle in obstacles:
                distance = None
                if obstacle.shape == "circle":
                    distance = _ray_circle(state[:2], direction, obstacle.center, obstacle.radius_m)
                elif obstacle.shape == "wall" and obstacle.a and obstacle.b:
                    distance = _ray_segment(state[:2], direction, obstacle.a, obstacle.b)
                if distance is not None and distance <= closest and distance <= max_range:
                    closest, hit = distance, True
        if hit and noise_std:
            closest = max(0.0, min(max_range, closest + _stable_random(
                seed, time_index, beam, "range").gauss(0.0, noise_std)))
        ranges.append(closest)
        hits.append(hit)
    return ranges, hits, True


def _rectangle_circle_gap(state: Sequence[float], obstacle: MovingObstacle) -> float:
    dx, dy = obstacle.center[0] - state[0], obstacle.center[1] - state[1]
    c, s = math.cos(state[2]), math.sin(state[2])
    qx, qy = c * dx + s * dy, -s * dx + c * dy
    ox, oy = abs(qx) - 0.6, abs(qy) - 0.225
    return math.hypot(max(ox, 0.0), max(oy, 0.0)) + min(max(ox, oy), 0.0) - obstacle.radius_m


def physical_minimum_gap(state: Sequence[float], obstacles: Sequence[MovingObstacle]) -> float:
    gaps = []
    for obstacle in obstacles:
        if obstacle.shape == "circle":
            gaps.append(_rectangle_circle_gap(state, obstacle))
        elif obstacle.shape == "wall" and obstacle.a and obstacle.b:
            # Fine-step scorer uses a conservative hull-circumcircle-to-segment gap for walls.
            ax, ay = obstacle.a
            bx, by = obstacle.b
            ex, ey = bx - ax, by - ay
            denominator = ex * ex + ey * ey
            t = 0.0 if denominator == 0 else max(0.0, min(1.0,
                ((state[0] - ax) * ex + (state[1] - ay) * ey) / denominator))
            distance = math.hypot(state[0] - (ax + t * ex), state[1] - (ay + t * ey))
            gaps.append(distance - math.hypot(0.6, 0.225))
    return min(gaps, default=math.inf)


def human_command(script: str, time_s: float) -> list[float]:
    if script == "gentle_sine":
        return [0.5, math.radians(5.0) * math.sin(0.4 * time_s)]
    if script == "sustained_high_throttle":
        return [1.0, 0.0]
    if script == "throttle_change":
        return [0.8 if time_s < 1.0 else -0.5, 0.0]
    return [0.5, 0.0]


def profile_command(profile: dict[str, Any], time_s: float, state: Sequence[float]) -> list[float]:
    """Scripted operator; consumes only ego state and a declared waypoint, no obstacles."""
    mode = profile.get("mode", "open_loop_sine")
    throttle = float(profile["throttle"])
    if mode == "open_loop_sine":
        steering = math.radians(float(profile.get("steering_bias_deg", 0.0)) +
                                float(profile.get("steering_amplitude_deg", 0.0)) *
                                math.sin(float(profile.get("frequency_rad_s", 0.3)) * time_s))
    elif mode == "heading_feedback":
        goal = profile["goal_position"]
        desired = math.atan2(float(goal[1]) - state[1], float(goal[0]) - state[0])
        error = math.atan2(math.sin(desired - state[2]), math.cos(desired - state[2]))
        limit = math.radians(float(profile["max_steering_deg"]))
        steering = max(-limit, min(limit, float(profile["heading_gain"]) * error -
                                  float(profile["yaw_rate_gain"]) * state[5]))
    else:
        raise ValueError(f"unknown scripted-operator mode: {mode}")
    return [throttle, steering]


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _safe_number(value: float) -> float | None:
    return value if math.isfinite(value) else None


def run_trial(task: dict[str, Any], output_dir: Path, duration_s: float) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    controller_catalog = load_json_yaml("configs/controllers/catalog.yaml")["controllers"]
    scenario_catalog = load_json_yaml("configs/scenarios/catalog.yaml")
    controller_spec = controller_catalog[task["controller"]]
    scenario = copy.deepcopy(task.get("scenario_config") or
                             _resolve_scenario(task["scenario"], scenario_catalog))
    default = scenario_catalog["default_vessel"]
    state = list(scenario.get("initial_state", default["state"]))
    obstacles = [MovingObstacle(
        shape=item["shape"], center=list(item.get("center", [0.0, 0.0])),
        velocity=list(item.get("velocity", [0.0, 0.0])), radius_m=float(item.get("radius_m", 0.0)),
        a=list(item["a"]) if "a" in item else None, b=list(item["b"]) if "b" in item else None,
    ) for item in scenario.get("obstacles", [])]
    seed = int(task["seed"])
    overrides = dict(task.get("overrides", {}))
    script = str(overrides.get("human_script", scenario.get("human_script", "straight")))
    mismatch = float(overrides.get("mismatch_factor", 1.0))
    physics_dt = float(task.get("physics_step_s", 0.02))
    if not math.isfinite(physics_dt) or physics_dt <= 0.0:
        raise ValueError("physics_step_s must be finite and positive")
    substeps = round(0.1 / physics_dt)
    if substeps < 1 or not math.isclose(substeps * physics_dt, 0.1, abs_tol=1e-12):
        raise ValueError("physics_step_s must divide the 0.1 s control interval")
    control_rows: list[dict[str, Any]] = []
    observation_rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    physical_minimum = physical_minimum_gap(state, obstacles)
    collision = False
    first_collision_time: float | None = None
    goal = task.get("goal")
    goal_reached = False
    goal_time: float | None = None
    path_length = 0.0
    initial_goal_distance = math.dist(state[:2], goal["position"]) if goal else None
    if goal and float(goal["radius_m"]) <= 0:
        raise ValueError("goal radius must be positive")
    native = None if controller_spec.get("bypass_filter") else NativeController(controller_spec, overrides)
    wall_start = time.perf_counter()
    try:
        steps = max(1, int(math.ceil(duration_s / 0.1)))
        for index in range(steps):
            now = index * 0.1
            requested = human_command(script, now)
            if "command_profile" in task:
                requested = profile_command(task["command_profile"], now, state)
            sensor_time = now
            receive_time = now + float(overrides.get("delay_ms", 0)) / 1000.0
            ranges, hits, sensor_healthy = simulate_scan(
                state, obstacles, seed=seed, time_index=index, time_s=now, scenario=scenario
            )
            track_count = 0
            controller_start = time.perf_counter()
            if native:
                track_count = native.process_scan(state, ranges, hits, 65.0, sensor_time, receive_time)
                decision = native.filter(state, requested, sensor_healthy, sensor_time,
                                         receive_time, receive_time, receive_time,
                                         receive_time)
                applied = [decision["applied_throttle"], decision["applied_steering_rad"]]
            else:
                applied = list(requested)
                decision = {
                    "outcome": "unfiltered", "paper_status": -1,
                    "predicted_minimum_clearance_m": math.nan,
                    "requested_horizon_s": 0.0, "actual_horizon_s": 0.0,
                    "latency_ms": 0.0, "evaluated_candidates": 0,
                    "evaluated_branches": 0, "integration_steps": 0,
                    "search_complete": True, "minimality_established": False,
                    "recovery_active": False, "used_hypothetical_throttle": False,
                    "witness_required_throttle": requested[0],
                }
            controller_pipeline_ms = (time.perf_counter() - controller_start) * 1000.0
            cycle_minimum = math.inf
            state_time = now
            for substep in range(substeps):
                previous_position = state[:2]
                state = plant_step(state, applied, physics_dt, mismatch)
                path_length += math.dist(previous_position, state[:2])
                state_time = now + (substep + 1) * physics_dt
                for obstacle in obstacles:
                    obstacle.center[0] += obstacle.velocity[0] * physics_dt
                    obstacle.center[1] += obstacle.velocity[1] * physics_dt
                    if obstacle.a and obstacle.b:
                        for point in (obstacle.a, obstacle.b):
                            point[0] += obstacle.velocity[0] * physics_dt
                            point[1] += obstacle.velocity[1] * physics_dt
                substep_gap = physical_minimum_gap(state, obstacles)
                cycle_minimum = min(cycle_minimum, substep_gap)
                if substep_gap <= 0.0 and first_collision_time is None:
                    first_collision_time = state_time
                if goal:
                    if substep_gap <= 0.0:
                        break
                    if math.dist(state[:2], goal["position"]) <= float(goal["radius_m"]):
                        goal_reached = True
                        goal_time = state_time
                        break
            physical_minimum = min(physical_minimum, cycle_minimum)
            apply_time = now
            row = {
                "cycle": index, "sensor_timestamp_s": sensor_time,
                "receive_timestamp_s": receive_time, "aligned_timestamp_s": receive_time,
                "decision_complete_timestamp_s": receive_time + decision["latency_ms"] / 1000.0,
                "apply_timestamp_s": apply_time, "n": state[0], "e": state[1],
                "state_timestamp_s": state_time,
                "psi_rad": state[2], "u_mps": state[3], "v_mps": state[4],
                "r_rad_s": state[5], "actual_thrust_n": state[6], "actual_delta_rad": state[7],
                "requested_throttle": requested[0], "requested_steering_rad": requested[1],
                "applied_throttle": applied[0], "applied_steering_rad": applied[1],
                "outcome": decision["outcome"], "paper_status": decision["paper_status"],
                "witness_required_throttle": decision["witness_required_throttle"],
                "used_hypothetical_throttle": decision["used_hypothetical_throttle"],
                "recovery_active": decision["recovery_active"],
                "predicted_minimum_clearance_m": decision["predicted_minimum_clearance_m"],
                "true_minimum_clearance_m": cycle_minimum,
                "requested_horizon_s": decision["requested_horizon_s"],
                "actual_horizon_s": decision["actual_horizon_s"],
                "end_to_end_latency_ms": controller_pipeline_ms + max(0.0, (receive_time - sensor_time) * 1000),
                "planning_latency_ms": decision["latency_ms"],
                "track_count": track_count, "evaluated_candidates": decision["evaluated_candidates"],
                "evaluated_branches": decision["evaluated_branches"],
                "integration_steps": decision["integration_steps"],
                "search_complete": decision["search_complete"],
                "minimality_established": decision["minimality_established"],
                "complete_witness_samples": decision.get("complete_witness_samples"),
            }
            control_rows.append(row)
            observation_rows.append({
                "cycle": index, "sensor_timestamp_s": sensor_time,
                "receive_timestamp_s": receive_time, "healthy": sensor_healthy,
                "beam_count": len(ranges), "hit_count": sum(hits),
                "ranges_m": ranges, "hits": hits,
            })
            if cycle_minimum <= 0.0:
                collision = True
                events.append({"time_s": first_collision_time, "type": "physical_collision",
                               "true_clearance_m": cycle_minimum})
                break
            if goal_reached:
                events.append({"time_s": goal_time, "type": "goal_reached"})
                break
    finally:
        if native:
            native.close()

    fieldnames = list(control_rows[0]) if control_rows else []
    with (output_dir / "control.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(control_rows)
    with (output_dir / "observations.jsonl").open("w", encoding="utf-8") as stream:
        for row in observation_rows:
            stream.write(json.dumps(row, separators=(",", ":")) + "\n")
    with (output_dir / "events.jsonl").open("w", encoding="utf-8") as stream:
        for event in events:
            stream.write(json.dumps(event, separators=(",", ":")) + "\n")

    latencies = [float(row["end_to_end_latency_ms"]) for row in control_rows]
    modified = [row for row in control_rows if
                abs(float(row["applied_throttle"]) - float(row["requested_throttle"])) > 1e-12 or
                abs(float(row["applied_steering_rad"]) - float(row["requested_steering_rad"])) > 1e-12]
    steering_changes = [abs(float(row["applied_steering_rad"]) - float(row["requested_steering_rad"]))
                        for row in control_rows]
    no_witness = sum(row["outcome"] == "exhausted_no_witness" for row in control_rows)
    unknown = sum(row["outcome"] == "budget_exhausted_unknown" for row in control_rows)
    observed_duration = float(control_rows[-1]["state_timestamp_s"]) if control_rows else 0.0
    metrics = {
        "label": ("synthetic_controlled_evaluation" if task.get("study_id") else
                  "software_smoke_synthetic_simulation"),
        "sample_count_cycles": len(control_rows), "observed_duration_s": observed_duration,
        "collision": collision, "first_collision_time_s": first_collision_time,
        "minimum_true_hull_clearance_m": _safe_number(physical_minimum),
        "minimum_planning_clearance_m": _safe_number(min(
            (float(row["predicted_minimum_clearance_m"]) for row in control_rows
             if math.isfinite(float(row["predicted_minimum_clearance_m"]))), default=math.inf)),
        "pass_through_rate": 1.0 - len(modified) / max(1, len(control_rows)),
        "modification_rate": len(modified) / max(1, len(control_rows)),
        "mean_steering_modification_rad": statistics.fmean(steering_changes) if steering_changes else 0.0,
        "peak_steering_modification_rad": max(steering_changes, default=0.0),
        "no_witness_fraction": no_witness / max(1, len(control_rows)),
        "budget_unknown_fraction": unknown / max(1, len(control_rows)),
        "accepted_cycles": sum(row["outcome"] == "witness_found" for row in control_rows),
        "throttle_dependent_witness_cycles": sum(
            row["outcome"] == "witness_found" and row["used_hypothetical_throttle"]
            for row in control_rows),
        "applied_throttle_violation_cycles": sum(
            abs(row["applied_throttle"] - row["requested_throttle"]) > 1e-12
            for row in control_rows) if int(controller_spec.get("authority_mode", 1)) in (0, 1) else None,
        "mean_evaluated_branches": statistics.fmean(row["evaluated_branches"] for row in control_rows),
        "mean_integration_steps": statistics.fmean(row["integration_steps"] for row in control_rows),
        "north_progress_m": state[0] - float(scenario.get("initial_state", default["state"])[0]),
        "latency_ms": {"p50": _percentile(latencies, 0.50), "p95": _percentile(latencies, 0.95),
                       "p99": _percentile(latencies, 0.99), "max": max(latencies, default=None)},
        "wall_time_s": time.perf_counter() - wall_start,
        "formal_evidence": False,
        "physics_step_s": physics_dt,
        "goal_reached": goal_reached if goal else None,
        "goal_time_s": goal_time,
        "mission_outcome": ("collision" if collision else "goal" if goal_reached else "timeout") if goal else None,
        "path_length_m": path_length,
        "goal_distance_reduction_m": initial_goal_distance - math.dist(state[:2], goal["position"]) if goal else None,
    }
    native_path = getattr(native, "path", None)
    if native_path:
        try:
            native_label = str(Path(native_path).resolve().relative_to(REPO_ROOT).as_posix())
        except ValueError:
            native_label = Path(native_path).name
    else:
        native_label = "bypassed"
    manifest = {
        "schema_version": 1, "software_version": __version__, "task": task,
        "data_classification": ("synthetic_controlled_evaluation" if task.get("study_id") else
                                "synthetic_software_smoke"),
        "timing_model": "synchronous zero-order-hold; measured compute delay is not injected into plant",
        "vessel_parameter_source": "engineering_assumption:synthetic_vessel_v1",
        "controller_truth_access": False,
        "physical_scorer_truth_access": True,
        "native_library": native_label,
        "python": sys.version, "platform": platform.platform(),
        "clock": "time.perf_counter/experiment timestamps",
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    resolved = {"controller": controller_spec, "scenario": scenario, "task": task,
                "duration_s": duration_s, "vessel": "synthetic_vessel_v1"}
    (output_dir / "resolved_config.yaml").write_text(json.dumps(resolved, indent=2), encoding="utf-8")
    return metrics
