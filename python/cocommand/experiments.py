from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Iterable

from .config import REPO_ROOT
from .reporting import generate_report
from .simulation import run_trial


def code_fingerprint() -> str:
    digest = hashlib.sha256()
    roots = [REPO_ROOT / "include", REPO_ROOT / "cpp", REPO_ROOT / "python", REPO_ROOT / "configs"]
    for root in roots:
        for path in sorted(file for file in root.rglob("*") if file.is_file()
                           and "__pycache__" not in file.parts
                           and file.suffix not in {".pyc", ".pyo"}):
            digest.update(path.relative_to(REPO_ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def _completed_cache(run_root: Path, task_hash: str, fingerprint: str) -> Path | None:
    for manifest_path in run_root.glob("*/tasks/*/manifest.json"):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        task = data.get("task", {})
        task_dir = manifest_path.parent
        if (task.get("task_hash") == task_hash
                and task.get("code_fingerprint") == fingerprint
                and (task_dir / "metrics.json").is_file()):
            return task_dir
    return None


def execute_tasks(tasks: Iterable[dict[str, Any]], *, run_root: Path, resume: bool,
                  duration_s: float) -> Path:
    fingerprint = code_fingerprint()
    run_id = time.strftime("%Y%m%dT%H%M%S") + f"_{fingerprint[:8]}"
    run_dir = run_root / run_id
    suffix = 1
    while run_dir.exists():
        run_dir = run_root / f"{run_id}_{suffix}"
        suffix += 1
    (run_dir / "tasks").mkdir(parents=True)
    index: list[dict[str, Any]] = []
    for original in tasks:
        task = dict(original)
        task["code_fingerprint"] = fingerprint
        cached = _completed_cache(run_root, task["task_hash"], fingerprint) if resume else None
        if cached:
            try:
                cached_label = cached.resolve().relative_to(REPO_ROOT).as_posix()
            except ValueError:
                cached_label = cached.name
            index.append({"task_hash": task["task_hash"], "status": "resumed", "path": cached_label})
            continue
        destination = run_dir / "tasks" / task["task_hash"]
        try:
            run_trial(task, destination, duration_s)
            status = "completed"
        except Exception as exc:  # failures are material experiment records, not skipped tasks
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "failure.json").write_text(json.dumps({
                "type": type(exc).__name__, "message": str(exc), "task": task,
            }, indent=2), encoding="utf-8")
            status = "failed"
        try:
            destination_label = destination.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            destination_label = destination.name
        index.append({"task_hash": task["task_hash"], "status": status, "path": destination_label})
    (run_dir / "run_index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    completed = [item for item in index if item["status"] == "completed"]
    if completed:
        generate_report(run_dir)
    return run_dir
