from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .io import write_json


STAGE_DIR_NAMES = {
    "prepare-dev-env": "00-prepare-dev-env",
    "dev-env": "00-prepare-dev-env",
    "environment": "00-prepare-dev-env",
    "implementation": "01-implementation",
    "coding": "01-implementation",
    "final-evaluator": "02-final-evaluator",
    "evaluator-final": "02-final-evaluator",
    "final-evaluation": "02-final-evaluator",
}


def stage_dir_name(stage: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", stage.strip().lower()).strip("-")
    if not normalized:
        raise ValueError("Task artifact stage must not be empty.")
    return STAGE_DIR_NAMES.get(normalized, f"99-{normalized}")


def task_dir(tasks_root: Path, stage: str) -> Path:
    return tasks_root / stage_dir_name(stage)


def rel(root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def write_stage_result(
    *,
    run_root: Path,
    stage_dir: Path,
    stage: str,
    role: str,
    status: str,
    completed: bool,
    result: dict[str, Any] | None = None,
) -> Path:
    payload: dict[str, Any] = {
        "stage": stage_dir.name,
        "role": role,
        "status": status,
        "completed": completed,
    }
    if result:
        payload.update(result)
    path = stage_dir / "result.json"
    write_json(path, _jsonable_paths(payload, run_root))
    return path


def _jsonable_paths(value: Any, root: Path) -> Any:
    if isinstance(value, Path):
        return rel(root, value)
    if isinstance(value, dict):
        return {key: _jsonable_paths(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable_paths(item, root) for item in value]
    return value
