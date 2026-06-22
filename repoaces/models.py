from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .artifacts import task_dir


@dataclass(frozen=True)
class CaseInput:
    case_id: str
    repo: str
    repo_url: str
    base_branch: str
    base_commit: str
    pr_number: int
    pr_url: str
    pr_title_raw: str
    summary_source: str
    summary_raw_markdown: str


@dataclass(frozen=True)
class CaseValidation:
    head_commit: str
    merge_commit: str | None
    patch_source: str
    patch_file: str
    patch_sha256: str
    changed_files_file: str
    manual_functionality_description: str


@dataclass(frozen=True)
class FeatureCase:
    case_id: str
    input: CaseInput
    validation: CaseValidation
    case_path: Path


@dataclass(frozen=True)
class PublicCase:
    case_id: str
    repo: str
    repo_url: str
    base_branch: str
    base_commit: str
    pr_number: int
    pr_title: str
    feature_summary: str
    acceptance_criteria: list[str]
    constraints: list[str]
    hidden_fields: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ArtifactLayout:
    root: Path
    case_dir: Path
    tasks_dir: Path
    repo_intelligence_dir: Path
    report_dir: Path

    @classmethod
    def create(cls, root: Path) -> "ArtifactLayout":
        layout = cls(
            root=root,
            case_dir=root / "case",
            tasks_dir=root / "tasks",
            repo_intelligence_dir=root / "repo_intelligence",
            report_dir=root / "report",
        )
        for directory in [
            layout.case_dir,
            layout.tasks_dir,
            layout.repo_intelligence_dir,
            layout.report_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)
        return layout

    def task_dir(self, stage: str) -> Path:
        path = task_dir(self.tasks_dir, stage)
        path.mkdir(parents=True, exist_ok=True)
        return path


@dataclass
class RunState:
    run_id: str
    case_id: str
    status: str
    artifact_root: Path
    workspace: Path | None = None
    data: dict[str, Any] = field(default_factory=dict)
