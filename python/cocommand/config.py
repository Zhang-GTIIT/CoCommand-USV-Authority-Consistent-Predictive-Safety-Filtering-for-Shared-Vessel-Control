from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(ValueError):
    pass


def load_json_yaml(path: str | Path) -> dict[str, Any]:
    """Load the project's JSON-compatible YAML subset without hidden defaults."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration not found: {candidate}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON-compatible YAML at {candidate}:{exc.lineno}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"top level must be a mapping: {candidate}")
    return data


def _require_keys(data: dict[str, Any], required: set[str], allowed: set[str], label: str) -> None:
    missing = required - data.keys()
    unknown = data.keys() - allowed
    if missing:
        raise ConfigError(f"{label}: missing fields {sorted(missing)}")
    if unknown:
        raise ConfigError(f"{label}: unknown fields {sorted(unknown)}")


def validate_experiment_config(path: str | Path) -> dict[str, Any]:
    data = load_json_yaml(path)
    allowed = {"schema_version", "id", "manifest", "formal_results", "ethics_approval_required"}
    _require_keys(data, {"schema_version", "id", "manifest", "formal_results"}, allowed, "experiment")
    if data["schema_version"] != 1:
        raise ConfigError("experiment: unsupported schema_version")
    manifest = validate_manifest(data["manifest"])
    if data["id"] not in manifest["experiments"]:
        raise ConfigError(f"experiment id {data['id']!r} is absent from manifest")
    return data


def validate_manifest(path: str | Path = "configs/experiment_manifest_v1.yaml") -> dict[str, Any]:
    data = load_json_yaml(path)
    allowed = {"schema_version", "id", "source_status", "seed_ranges", "experiments"}
    _require_keys(data, {"schema_version", "id", "source_status", "seed_ranges", "experiments"}, allowed, "manifest")
    if data["schema_version"] != 1 or not isinstance(data["experiments"], dict):
        raise ConfigError("manifest schema_version/experiments invalid")
    required_ids = {"E00", *(f"E{i:02d}" for i in range(1, 12)), "H01", "H02"}
    missing = required_ids - data["experiments"].keys()
    if missing:
        raise ConfigError(f"manifest missing experiment ids {sorted(missing)}")
    for experiment_id, spec in data["experiments"].items():
        _require_keys(spec, {"kind", "controllers", "scenarios", "axes"},
                      {"kind", "controllers", "scenarios", "axes"}, f"manifest.{experiment_id}")
        if not all(isinstance(value, list) for value in (spec["controllers"], spec["scenarios"])):
            raise ConfigError(f"manifest.{experiment_id}: controllers/scenarios must be lists")
        if not isinstance(spec["axes"], dict):
            raise ConfigError(f"manifest.{experiment_id}: axes must be a mapping")
    return data


def validate_catalogs() -> dict[str, int]:
    manifest = validate_manifest()
    controllers = load_json_yaml("configs/controllers/catalog.yaml")
    scenarios = load_json_yaml("configs/scenarios/catalog.yaml")
    if set(controllers) != {"schema_version", "controllers"}:
        raise ConfigError("controller catalog has unknown or missing top-level fields")
    if set(scenarios) != {"schema_version", "coordinate_frame", "default_duration_s", "default_vessel", "scenarios"}:
        raise ConfigError("scenario catalog has unknown or missing top-level fields")
    controller_ids = set(controllers["controllers"])
    scenario_ids = set(scenarios["scenarios"])
    for experiment_id, spec in manifest["experiments"].items():
        missing_controllers = set(spec["controllers"]) - controller_ids
        missing_scenarios = set(spec["scenarios"]) - scenario_ids
        if missing_controllers or missing_scenarios:
            raise ConfigError(
                f"{experiment_id}: missing controllers={sorted(missing_controllers)}, "
                f"scenarios={sorted(missing_scenarios)}"
            )
    return {"experiments": len(manifest["experiments"]),
            "controllers": len(controller_ids), "scenarios": len(scenario_ids)}


def parse_seed_expression(expression: str) -> list[int]:
    if ":" in expression:
        left, right = expression.split(":", 1)
        start, stop = int(left), int(right)
        if stop < start:
            raise ConfigError("seed range stop must be >= start")
        return list(range(start, stop))
    return [int(expression)]


def experiment_ids(expression: str) -> list[str]:
    if ":" not in expression:
        return [part.strip() for part in expression.split(",") if part.strip()]
    left, right = expression.split(":", 1)
    if not (left.startswith("E") and right.startswith("E")):
        raise ConfigError("experiment ranges must use E01:E11 form")
    start, stop = int(left[1:]), int(right[1:])
    return [f"E{value:02d}" for value in range(start, stop + 1)]


def _axis_product(axes: dict[str, list[Any]]) -> Iterable[dict[str, Any]]:
    if not axes:
        yield {}
        return
    keys = list(axes)
    for values in itertools.product(*(axes[key] for key in keys)):
        yield dict(zip(keys, values))


def expand_experiment(experiment_id: str, tier: str, seeds: list[int] | None = None) -> list[dict[str, Any]]:
    manifest = validate_manifest()
    if experiment_id not in manifest["experiments"]:
        raise ConfigError(f"unknown experiment {experiment_id}")
    if tier not in manifest["seed_ranges"]:
        raise ConfigError(f"unknown tier {tier}")
    spec = manifest["experiments"][experiment_id]
    seed_values = seeds if seeds is not None else list(range(*manifest["seed_ranges"][tier]))
    controllers = list(spec["controllers"])
    scenarios = list(spec["scenarios"])
    axes = {key: list(values) for key, values in spec["axes"].items()}
    if tier == "smoke":
        controllers = controllers[:2]
        scenarios = scenarios[:2]
        axes = {key: values[:1] for key, values in axes.items()}
    tasks: list[dict[str, Any]] = []
    for controller, scenario, seed, override in itertools.product(
        controllers, scenarios, seed_values, _axis_product(axes)
    ):
        task = {"experiment_id": experiment_id, "tier": tier, "controller": controller,
                "scenario": scenario, "seed": seed, "overrides": override}
        canonical = json.dumps(task, sort_keys=True, separators=(",", ":"))
        task["task_hash"] = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        tasks.append(task)
    return tasks

