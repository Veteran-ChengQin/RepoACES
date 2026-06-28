from __future__ import annotations

import json
import time
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any

from repoaces.artifacts import write_stage_result
from repoaces.io import read_json, write_json, write_patch_text, write_text
from repoaces.openhands_client import OpenHandsConfig, OpenHandsRuntime
from repoaces.shell import run_cmd

from .stages import TERMINAL_OPENHANDS_STATUSES, StageDefinition


@dataclass(frozen=True)
class StageRunRequest:
    run_id: str
    stage: StageDefinition
    workspace: Path
    instruction: str
    task_dir: Path
    sandbox_repo_path: str
    model: str | None = None
    auto_run: bool = True
    wait_start_seconds: int = 180
    wait_completion_seconds: int = 0
    repo_mount_path: str | None = None
    repo_git_path: str | None = None
    docker_backend: str = "windows"


@dataclass(frozen=True)
class StageRunResult:
    status: str
    task_dir: Path
    runtime_state_path: Path
    patch_path: Path
    trajectory_path: Path | None
    output_status: dict[str, Any]


class OpenHandsStageAgent:
    """OpenHands-backed agent for one explicit MultiAgent stage."""

    def __init__(self, *, project_root: Path, run_root: Path | None = None, config: OpenHandsConfig | None = None) -> None:
        self.project_root = project_root
        self.run_root = run_root or project_root / "runs" / "repoaces-multiagent-openhands"
        self.config = config or OpenHandsConfig.from_env(project_root)
        self.runtime = OpenHandsRuntime(self.config, self.run_root)

    def start(self, request: StageRunRequest) -> StageRunResult:
        request.task_dir.mkdir(parents=True, exist_ok=True)
        instruction_path = request.task_dir / "instruction.md"
        write_text(instruction_path, request.instruction)

        server = self.runtime.start_server(
            run_id=f"{request.run_id}-{request.stage.key}",
            repo_dir=request.workspace,
            sandbox_repo_path=request.sandbox_repo_path,
            repo_mount_path=request.repo_mount_path,
            extra_sandbox_volumes=[(request.task_dir, "/repoaces_stage", "rw")],
        )
        conversation = self.runtime.start_conversation(
            base_url=server["base_url"],
            run_id=f"{request.run_id}-{request.stage.key}",
            instruction=request.instruction,
            model=request.model,
            auto_run=request.auto_run,
            wait_start_seconds=request.wait_start_seconds,
        )
        runtime_state = {
            "run_id": request.run_id,
            "stage": request.stage.key,
            "stage_dir": request.task_dir.name,
            "role": request.stage.role,
            "workspace": str(request.workspace),
            "sandbox_repo_path": request.sandbox_repo_path,
            "repo_mount_path": request.repo_mount_path,
            "repo_git_path": request.repo_git_path,
            "docker_backend": request.docker_backend,
            "instruction": str(instruction_path),
            "read_only": request.stage.read_only,
            "required_outputs": list(request.stage.required_outputs),
            "openhands": server,
            "conversation": conversation,
            "auto_run": request.auto_run,
            "model": request.model,
            "status": _status_from_start_task(conversation.get("start_task_status")),
        }
        runtime_state_path = request.task_dir / "openhands_runtime_state.json"
        write_json(runtime_state_path, runtime_state)

        if request.wait_completion_seconds > 0:
            return self.wait_until_terminal(
                workspace=request.workspace,
                task_dir=request.task_dir,
                timeout_seconds=request.wait_completion_seconds,
                poll_interval_seconds=10,
            )
        return self.refresh(workspace=request.workspace, task_dir=request.task_dir)

    def wait_until_terminal(
        self,
        *,
        workspace: Path,
        task_dir: Path,
        timeout_seconds: int,
        poll_interval_seconds: int,
    ) -> StageRunResult:
        deadline = time.time() + timeout_seconds
        result = self.refresh(workspace=workspace, task_dir=task_dir)
        while result.status not in TERMINAL_OPENHANDS_STATUSES and time.time() < deadline:
            time.sleep(poll_interval_seconds)
            result = self.refresh(workspace=workspace, task_dir=task_dir)
        return result

    def refresh(self, *, workspace: Path, task_dir: Path) -> StageRunResult:
        runtime_state_path = task_dir / "openhands_runtime_state.json"
        if not runtime_state_path.exists():
            raise FileNotFoundError(f"OpenHands runtime state not found: {runtime_state_path}")
        runtime_state = read_json(runtime_state_path)
        server = runtime_state.get("openhands") if isinstance(runtime_state.get("openhands"), dict) else {}
        conversation = runtime_state.get("conversation") if isinstance(runtime_state.get("conversation"), dict) else {}
        conversation_id = conversation.get("conversation_id")
        base_url = server.get("base_url")

        if not conversation_id:
            runtime_state["status"] = _status_from_start_task(
                conversation.get("start_task_status"),
                default=str(runtime_state.get("status", "openhands_unknown")),
            )
        elif base_url and not _cleanup_already_completed(runtime_state):
            try:
                latest = self.runtime.get_conversation(base_url=str(base_url), conversation_id=str(conversation_id))
            except Exception as exc:  # noqa: BLE001
                latest = None
                runtime_state["refresh_warning"] = f"Unable to query OpenHands API: {exc}"
            if latest:
                runtime_state["conversation_detail"] = latest
                execution_status = latest.get("execution_status")
                if execution_status:
                    runtime_state["status"] = f"openhands_{execution_status}"

        stage_key = str(runtime_state.get("stage") or "")
        patch_path = task_dir / ("patch.diff" if stage_key == "implement" else "workspace.diff")
        patch_info = self.runtime.export_patch(
            repo_dir=workspace,
            patch_path=patch_path,
            repo_git_path=runtime_state.get("repo_git_path"),
        )
        runtime_state["workspace_diff"] = patch_info
        if runtime_state.get("read_only") and patch_info.get("patch_diff_chars", 0):
            violation_patch = task_dir / "read_only_violation.patch"
            write_patch_text(violation_patch, patch_path.read_text(encoding="utf-8", errors="replace"))
            runtime_state["read_only_violation"] = {
                "detected": True,
                "patch": str(violation_patch),
                "cleaned": self._clean_read_only_workspace(
                    workspace=workspace,
                    repo_git_path=runtime_state.get("repo_git_path"),
                ),
            }
            patch_info = self.runtime.export_patch(
                repo_dir=workspace,
                patch_path=patch_path,
                repo_git_path=runtime_state.get("repo_git_path"),
            )
            runtime_state["workspace_diff_after_read_only_cleanup"] = patch_info

        trajectory_info = None
        openhands_home = server.get("openhands_home")
        if openhands_home:
            trajectory_info = self.runtime.export_conversation_artifacts(
                openhands_home=Path(str(openhands_home)),
                conversation_id=str(conversation_id) if conversation_id else None,
                artifact_dir=task_dir,
            )
            runtime_state["trajectory"] = trajectory_info

        sandbox_id = conversation.get("sandbox_id")
        if sandbox_id and not _cleanup_already_completed(runtime_state):
            runtime_state["stage_output_copy"] = self.runtime.copy_from_container(
                container=str(sandbox_id),
                source_path="/repoaces_stage",
                destination=task_dir,
            )

        output_status = self._collect_output_status(task_dir, runtime_state.get("required_outputs") or [])
        runtime_state["output_status"] = output_status

        if str(runtime_state.get("status")) in TERMINAL_OPENHANDS_STATUSES and not _cleanup_already_completed(runtime_state):
            cleanup = self.runtime.cleanup_runtime_containers(runtime_state)
            cleanup["stage"] = runtime_state.get("stage")
            runtime_state["container_cleanup"] = cleanup
            write_json(task_dir / "openhands_container_cleanup.json", cleanup)

        write_json(runtime_state_path, runtime_state)
        trajectory_path = (
            Path(str(trajectory_info["trajectory_path"]))
            if trajectory_info and trajectory_info.get("trajectory_path")
            else None
        )
        write_stage_result(
            run_root=_run_root(task_dir),
            stage_dir=task_dir,
            stage=str(runtime_state.get("stage", task_dir.name)),
            role=str(runtime_state.get("role", "multiagent_stage")),
            status=str(runtime_state.get("status", "openhands_unknown")),
            completed=bool(output_status.get("all_required_present")),
            result={
                "instruction": Path(str(runtime_state.get("instruction"))),
                "trajectory": trajectory_path,
                "conversation": Path(str(trajectory_info["conversation_dir"]))
                if trajectory_info and trajectory_info.get("conversation_dir")
                else None,
                "conversation_event_count": trajectory_info.get("event_count") if trajectory_info else None,
                "workspace_diff": patch_path,
                "runtime_state": runtime_state_path,
                "outputs": output_status,
                "summary": f"OpenHands {runtime_state.get('stage')} stage refreshed.",
            },
        )
        return StageRunResult(
            status=str(runtime_state.get("status", "openhands_unknown")),
            task_dir=task_dir,
            runtime_state_path=runtime_state_path,
            patch_path=patch_path,
            trajectory_path=trajectory_path,
            output_status=output_status,
        )

    def _collect_output_status(self, task_dir: Path, required_outputs: list[str]) -> dict[str, Any]:
        files = []
        for name in required_outputs:
            path = task_dir / name
            files.append(
                {
                    "name": name,
                    "path": str(path),
                    "present": path.exists(),
                    "size": path.stat().st_size if path.exists() else 0,
                }
            )
        return {
            "required": files,
            "all_required_present": all(item["present"] and item["size"] > 0 for item in files),
        }

    def _clean_read_only_workspace(self, *, workspace: Path, repo_git_path: str | None) -> dict[str, Any]:
        if self.config.docker_backend == "wsl" and repo_git_path:
            proc = self.runtime._run_git_in_agent_container(  # noqa: SLF001
                repo_git_path,
                "git reset --hard HEAD && git clean -fd",
                timeout=300,
            )
        else:
            proc = run_cmd(
                [
                    "git",
                    "-C",
                    str(workspace),
                    "reset",
                    "--hard",
                    "HEAD",
                ],
                timeout=300,
            )
            if proc.returncode == 0:
                clean_proc = run_cmd(["git", "-C", str(workspace), "clean", "-fd"], timeout=300)
                return {
                    "returncode": clean_proc.returncode,
                    "stdout": f"{proc.stdout}\n{clean_proc.stdout}",
                    "stderr": f"{proc.stderr}\n{clean_proc.stderr}",
                }
            return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
        return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def config_for_dev_environment(project_root: Path, dev_env: dict[str, Any]) -> tuple[OpenHandsConfig, str | None, str | None]:
    config = OpenHandsConfig.from_env(project_root)
    repo_mount_path = None
    repo_git_path = None
    if dev_env.get("docker_backend") == "wsl" and dev_env.get("workspace_wsl_path"):
        image_repo, image_tag = _split_docker_image(
            str(dev_env.get("image") or ""),
            config.agent_server_image_repository,
            config.agent_server_image_tag,
        )
        config = replace(
            config,
            docker_backend="wsl",
            wsl_distro=str(dev_env.get("wsl_distro") or config.wsl_distro),
            agent_server_image_repository=image_repo,
            agent_server_image_tag=image_tag,
        )
        repo_mount_path = str(dev_env["workspace_wsl_path"])
        repo_git_path = str(dev_env["workspace_wsl_path"])
    return config, repo_mount_path, repo_git_path


def _status_from_start_task(start_task_status: object, *, default: str = "openhands_started") -> str:
    status = str(start_task_status or "").strip().upper()
    if status == "ERROR":
        return "openhands_error"
    if status == "FAILED":
        return "openhands_failed"
    if status == "STOPPED":
        return "openhands_stopped"
    return default


def _cleanup_already_completed(runtime_state: dict[str, Any]) -> bool:
    cleanup = runtime_state.get("container_cleanup")
    return isinstance(cleanup, dict) and cleanup.get("attempted") and cleanup.get("all_removed")


def _split_docker_image(image: str, default_repository: str, default_tag: str) -> tuple[str, str]:
    image = image.strip()
    if not image or "@" in image:
        return default_repository, default_tag
    slash_index = image.rfind("/")
    colon_index = image.rfind(":")
    if colon_index > slash_index:
        return image[:colon_index], image[colon_index + 1 :]
    return image, default_tag


def _run_root(stage_dir: Path) -> Path:
    return stage_dir.parent.parent if stage_dir.parent.name == "tasks" else stage_dir.parent
