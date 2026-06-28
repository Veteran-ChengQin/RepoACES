from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StageDefinition:
    key: str
    directory: str
    role: str
    display_name: str
    read_only: bool
    required_outputs: tuple[str, ...]


STAGES: dict[str, StageDefinition] = {
    "scope": StageDefinition(
        key="scope",
        directory="01-scope-explorer",
        role="scope_explorer",
        display_name="Scope Explorer",
        read_only=True,
        required_outputs=("scope.json", "scope.md"),
    ),
    "plan": StageDefinition(
        key="plan",
        directory="02-patch-planner",
        role="patch_planner",
        display_name="Patch Planner",
        read_only=True,
        required_outputs=("patch_plan.json", "patch_plan.md"),
    ),
    "implement": StageDefinition(
        key="implement",
        directory="03-patch-implementer",
        role="patch_implementer",
        display_name="Patch Implementer",
        read_only=False,
        required_outputs=("implementation_summary.md", "modified_files.json"),
    ),
    "validate": StageDefinition(
        key="validate",
        directory="04-developer-validator",
        role="developer_validator",
        display_name="Developer Validator",
        read_only=False,
        required_outputs=("validation_report.json", "validation_summary.md"),
    ),
}

STAGE_ORDER = ("scope", "plan", "implement", "validate")
TERMINAL_OPENHANDS_STATUSES = {
    "openhands_finished",
    "openhands_error",
    "openhands_failed",
    "openhands_stopped",
    "openhands_stuck",
}


def normalize_stage(stage: str) -> str:
    normalized = stage.strip().lower().replace("_", "-")
    aliases = {
        "scope-explorer": "scope",
        "explore": "scope",
        "planner": "plan",
        "patch-planner": "plan",
        "implementation": "implement",
        "patch-implementer": "implement",
        "validator": "validate",
        "developer-validator": "validate",
    }
    key = aliases.get(normalized, normalized)
    if key not in STAGES:
        raise ValueError(f"Unknown multi-agent stage: {stage}")
    return key


def stage_definition(stage: str) -> StageDefinition:
    return STAGES[normalize_stage(stage)]


def stage_dir(tasks_root: Path, stage: str) -> Path:
    path = tasks_root / stage_definition(stage).directory
    path.mkdir(parents=True, exist_ok=True)
    return path


def stage_key_from_directory(directory_name: str) -> str | None:
    for key, definition in STAGES.items():
        if definition.directory == directory_name:
            return key
    return None
