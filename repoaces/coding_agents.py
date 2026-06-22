from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .artifacts import write_stage_result
from .io import write_text
from .openhands_client import OpenHandsConfig, OpenHandsRuntime


@dataclass(frozen=True)
class CodingTask:
    run_id: str
    workspace: Path
    instruction_path: Path
    artifact_dir: Path
    mode: str = "implementation"
    sandbox_repo_path: str = "/workspace"
    model: str | None = None
    auto_run: bool = True
    wait_start_seconds: int = 180
    wait_completion_seconds: int = 0
    repo_mount_path: str | None = None
    repo_git_path: str | None = None


@dataclass(frozen=True)
class CodingResult:
    status: str
    summary: str
    patch_path: Path | None = None
    trajectory_path: Path | None = None


class CodingAgent(Protocol):
    def run(self, task: CodingTask) -> CodingResult:
        ...


class DryRunCodingAgent:
    """No-op agent used for pipeline smoke tests."""

    def run(self, task: CodingTask) -> CodingResult:
        task.artifact_dir.mkdir(parents=True, exist_ok=True)
        copied_instruction = task.artifact_dir / "instruction.md"
        write_text(copied_instruction, task.instruction_path.read_text(encoding="utf-8", errors="replace"))
        write_stage_result(
            run_root=_run_root(task.artifact_dir),
            stage_dir=task.artifact_dir,
            stage=task.mode,
            role=_role_for_mode(task.mode),
            status="dry_run",
            completed=True,
            result={
                "instruction": copied_instruction,
                "trajectory": None,
                "patch": None,
                "summary": "Instruction captured. No repository changes were made.",
            },
        )
        return CodingResult(
            status="dry_run",
            summary="Instruction captured. No repository changes were made.",
            patch_path=None,
            trajectory_path=None,
        )


class OpenHandsCodingAgent:
    """OpenHands-backed coding agent."""

    def __init__(self, *, project_root: Path, run_root: Path | None = None, config: OpenHandsConfig | None = None) -> None:
        self.project_root = project_root
        self.run_root = run_root or project_root / "runs" / "repoaces-openhands"
        self.runtime = OpenHandsRuntime(config or OpenHandsConfig.from_env(project_root), self.run_root)

    def run(self, task: CodingTask) -> CodingResult:
        task.artifact_dir.mkdir(parents=True, exist_ok=True)
        instruction = task.instruction_path.read_text(encoding="utf-8", errors="replace")
        instruction_artifact = task.artifact_dir / "instruction.md"
        write_text(instruction_artifact, instruction)
        server = self.runtime.start_server(
            run_id=task.run_id,
            repo_dir=task.workspace,
            sandbox_repo_path=task.sandbox_repo_path,
            repo_mount_path=task.repo_mount_path,
        )
        conversation = self.runtime.start_conversation(
            base_url=server["base_url"],
            run_id=task.run_id,
            instruction=instruction,
            model=task.model,
            auto_run=task.auto_run,
            wait_start_seconds=task.wait_start_seconds,
        )
        runtime_state = {
            "run_id": task.run_id,
            "mode": task.mode,
            "workspace": str(task.workspace),
            "instruction_path": str(task.instruction_path),
            "instruction_artifact": str(instruction_artifact),
            "sandbox_repo_path": task.sandbox_repo_path,
            "repo_mount_path": task.repo_mount_path,
            "repo_git_path": task.repo_git_path,
            "openhands": server,
            "conversation": conversation,
            "auto_run": task.auto_run,
            "model": task.model,
            "status": "openhands_started",
        }

        if conversation.get("conversation_id"):
            latest = self.runtime.get_conversation(
                base_url=server["base_url"],
                conversation_id=str(conversation["conversation_id"]),
            )
            if latest:
                runtime_state["conversation_detail"] = latest
                if latest.get("execution_status"):
                    runtime_state["status"] = f"openhands_{latest['execution_status']}"

        if task.wait_completion_seconds > 0 and conversation.get("conversation_id"):
            deadline = time.time() + task.wait_completion_seconds
            while time.time() < deadline:
                latest = self.runtime.get_conversation(
                    base_url=server["base_url"],
                    conversation_id=str(conversation["conversation_id"]),
                )
                if latest:
                    runtime_state["conversation_detail"] = latest
                    execution_status = latest.get("execution_status")
                    if execution_status:
                        runtime_state["status"] = f"openhands_{execution_status}"
                    if execution_status in {"finished", "error", "stuck"}:
                        break
                time.sleep(10)

        patch_path = task.artifact_dir / "patch.diff"
        patch_info = self.runtime.export_patch(repo_dir=task.workspace, patch_path=patch_path, repo_git_path=task.repo_git_path)
        runtime_state["patch"] = patch_info
        trajectory_info = self.runtime.export_conversation_artifacts(
            openhands_home=Path(str(server["openhands_home"])),
            conversation_id=str(conversation["conversation_id"]) if conversation.get("conversation_id") else None,
            artifact_dir=task.artifact_dir,
        )
        runtime_state["trajectory"] = trajectory_info
        runtime_state_path = task.artifact_dir / "openhands_runtime_state.json"
        self.runtime.write_runtime_state(runtime_state_path, runtime_state)
        trajectory_path = Path(str(trajectory_info["trajectory_path"])) if trajectory_info.get("trajectory_path") else None
        result_path = write_stage_result(
            run_root=_run_root(task.artifact_dir),
            stage_dir=task.artifact_dir,
            stage=task.mode,
            role=_role_for_mode(task.mode),
            status=str(runtime_state["status"]),
            completed=bool(patch_path.exists()),
            result={
                "instruction": instruction_artifact,
                "trajectory": trajectory_path,
                "conversation": Path(str(trajectory_info["conversation_dir"]))
                if trajectory_info.get("conversation_dir")
                else None,
                "conversation_event_count": trajectory_info.get("event_count"),
                "patch": patch_path,
                "runtime_state": runtime_state_path,
                "summary": "OpenHands run started through app-server REST API.",
            },
        )
        runtime_state["result"] = str(result_path)
        self.runtime.write_runtime_state(runtime_state_path, runtime_state)

        return CodingResult(
            status=str(runtime_state["status"]),
            summary="OpenHands run started through app-server REST API.",
            patch_path=patch_path,
            trajectory_path=trajectory_path,
        )

    def refresh(self, *, workspace: Path, artifact_dir: Path, mode: str = "implementation") -> CodingResult:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        runtime_state_path = artifact_dir / "openhands_runtime_state.json"
        if not runtime_state_path.exists():
            raise FileNotFoundError(f"OpenHands runtime state not found: {runtime_state_path}")

        runtime_state = json.loads(runtime_state_path.read_text(encoding="utf-8", errors="replace"))
        server = runtime_state.get("openhands") or {}
        conversation = runtime_state.get("conversation") or {}
        base_url = server.get("base_url")
        conversation_id = conversation.get("conversation_id")
        if base_url and conversation_id and not _cleanup_already_completed(runtime_state):
            try:
                latest = self.runtime.get_conversation(base_url=str(base_url), conversation_id=str(conversation_id))
            except Exception as exc:  # noqa: BLE001
                runtime_state["refresh_warning"] = f"Unable to query OpenHands API: {exc}"
                latest = None
            if latest:
                runtime_state["conversation_detail"] = latest
                if latest.get("execution_status"):
                    runtime_state["status"] = f"openhands_{latest['execution_status']}"
        patch_path = artifact_dir / "patch.diff"
        patch_info = self.runtime.export_patch(
            repo_dir=workspace,
            patch_path=patch_path,
            repo_git_path=runtime_state.get("repo_git_path"),
        )
        runtime_state["patch"] = patch_info
        trajectory_info = None
        openhands_home = (runtime_state.get("openhands") or {}).get("openhands_home")
        if openhands_home:
            trajectory_info = self.runtime.export_conversation_artifacts(
                openhands_home=Path(str(openhands_home)),
                conversation_id=str(conversation_id) if conversation_id else None,
                artifact_dir=artifact_dir,
            )
            runtime_state["trajectory"] = trajectory_info
        self.runtime.write_runtime_state(runtime_state_path, runtime_state)
        trajectory_path = (
            Path(str(trajectory_info["trajectory_path"]))
            if trajectory_info and trajectory_info.get("trajectory_path")
            else None
        )
        write_stage_result(
            run_root=_run_root(artifact_dir),
            stage_dir=artifact_dir,
            stage=mode,
            role=_role_for_mode(mode),
            status=str(runtime_state.get("status", "openhands_unknown")),
            completed=bool(patch_path.exists()),
            result={
                "instruction": Path(str(runtime_state.get("instruction_artifact")))
                if runtime_state.get("instruction_artifact")
                else None,
                "trajectory": trajectory_path,
                "conversation": Path(str(trajectory_info["conversation_dir"]))
                if trajectory_info and trajectory_info.get("conversation_dir")
                else None,
                "conversation_event_count": trajectory_info.get("event_count") if trajectory_info else None,
                "patch": patch_path,
                "runtime_state": runtime_state_path,
                "summary": "OpenHands runtime state refreshed.",
            },
        )
        return CodingResult(
            status=str(runtime_state.get("status", "openhands_unknown")),
            summary="OpenHands runtime state refreshed.",
            patch_path=patch_path,
            trajectory_path=trajectory_path,
        )


def _role_for_mode(mode: str) -> str:
    return "repairer" if "repair" in mode.lower() else "coding_agent"


def _run_root(stage_dir: Path) -> Path:
    return stage_dir.parent.parent if stage_dir.parent.name == "tasks" else stage_dir.parent


def _cleanup_already_completed(runtime_state: dict) -> bool:
    cleanup = runtime_state.get("container_cleanup")
    return isinstance(cleanup, dict) and cleanup.get("attempted") and cleanup.get("all_removed")
