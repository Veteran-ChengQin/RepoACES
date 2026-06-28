from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from repoaces.agent_orchestrator import RepoACESOrchestrator
from repoaces.case_builder import CaseBuilder
from repoaces.evaluator import FinalEvaluator
from repoaces.io import path_to_jsonable, read_json, write_json
from repoaces.models import ArtifactLayout, RunState
from repoaces.repo_intelligence import StaticRepoIntelligence

from .prompts import build_stage_instruction
from .stage_agent import OpenHandsStageAgent, StageRunRequest, config_for_dev_environment
from .stages import STAGE_ORDER, TERMINAL_OPENHANDS_STATUSES, normalize_stage, stage_definition, stage_dir


class MultiAgentRepoACESOrchestrator:
    """Workflow-oriented RepoACES variant with one OpenHands agent per stage."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.base = RepoACESOrchestrator(project_root)
        self.case_builder = CaseBuilder()
        self.repo_intelligence = StaticRepoIntelligence()
        self.final_evaluator = FinalEvaluator()

    def init_run(self, case_yaml: Path, artifact_root: Path | None = None, workspace_path: str = "/workspace/project") -> RunState:
        state = self.base.init_run(case_yaml, artifact_root=artifact_root, workspace_path=workspace_path)
        state.data.setdefault("modules", {})["multiagent"] = {
            "version": 1,
            "stage_order": list(STAGE_ORDER),
            "workspace_path": workspace_path,
            "stages": {},
        }
        state.status = "MULTIAGENT_INITIALIZED"
        self.write_state(state)
        self.write_manifest(state)
        return state

    def load_state(self, artifact_root: Path) -> RunState:
        return self.base.load_state(artifact_root)

    def prepare_workspace(self, artifact_root: Path, case_yaml: Path, *, force: bool = False) -> RunState:
        state = self.base.prepare_workspace(artifact_root=artifact_root, case_yaml=case_yaml, force=force)
        self._ensure_multiagent_module(state)
        self.write_state(state)
        self.write_manifest(state)
        return state

    def prepare_dev_environment(
        self,
        artifact_root: Path,
        case_yaml: Path,
        *,
        wsl_distro: str = "Ubuntu-22.04",
        wsl_root: str | None = None,
        image: str = "repoaces/openhands-agent-fastgpt:node20-pnpm10",
        seed_workspace_from_image: bool = False,
        seed_source_path: str = "/workspace",
        container_uid: int = 10001,
        container_gid: int = 10001,
        force: bool = False,
        run_install: bool = True,
        run_smoke_tests: bool = True,
        extra_commands: list[str] | None = None,
        timeout: int = 3600,
    ) -> RunState:
        state = self.base.prepare_dev_environment(
            artifact_root=artifact_root,
            case_yaml=case_yaml,
            wsl_distro=wsl_distro,
            wsl_root=wsl_root,
            image=image,
            seed_workspace_from_image=seed_workspace_from_image,
            seed_source_path=seed_source_path,
            container_uid=container_uid,
            container_gid=container_gid,
            force=force,
            run_install=run_install,
            run_smoke_tests=run_smoke_tests,
            extra_commands=extra_commands or [],
            timeout=timeout,
        )
        self._ensure_multiagent_module(state)
        self.write_state(state)
        self.write_manifest(state)
        return state

    def build_static_intelligence(self, artifact_root: Path, *, focus_terms: list[str] | None = None) -> RunState:
        state = self.load_state(artifact_root)
        if not state.workspace:
            raise ValueError("Workspace is not ready. Run prepare-workspace or prepare-dev-env first.")
        layout = ArtifactLayout.create(state.artifact_root)
        artifacts = self.repo_intelligence.build(
            state.workspace,
            layout.repo_intelligence_dir,
            focus_terms=focus_terms or [],
        )
        state.data.setdefault("modules", {})["repo_intelligence"] = path_to_jsonable(artifacts)
        self.write_state(state)
        self.write_manifest(state)
        return state

    def start_stage(
        self,
        artifact_root: Path,
        *,
        stage: str,
        sandbox_repo_path: str = "/workspace/project",
        model: str | None = None,
        auto_run: bool = True,
        wait_start_seconds: int = 180,
        wait_completion_seconds: int = 0,
    ) -> RunState:
        state = self.load_state(artifact_root)
        if not state.workspace:
            raise ValueError("Workspace is not ready. Run prepare-dev-env first.")
        key = normalize_stage(stage)
        definition = stage_definition(key)
        layout = ArtifactLayout.create(state.artifact_root)
        task = stage_dir(layout.tasks_dir, key)
        repo_context = layout.repo_intelligence_dir / "repo_context.json"
        instruction = build_stage_instruction(
            stage=key,
            run_root=state.artifact_root,
            workspace_path=sandbox_repo_path,
            case_instruction_path=layout.case_dir / "instruction.md",
            repo_context_path=repo_context if repo_context.exists() else None,
        )
        dev_env = state.data.get("modules", {}).get("dev_environment", {})
        config, repo_mount_path, repo_git_path = config_for_dev_environment(self.project_root, dev_env)
        agent = OpenHandsStageAgent(project_root=self.project_root, config=config)
        result = agent.start(
            StageRunRequest(
                run_id=state.run_id,
                stage=definition,
                workspace=state.workspace,
                instruction=instruction,
                task_dir=task,
                sandbox_repo_path=sandbox_repo_path,
                model=model,
                auto_run=auto_run,
                wait_start_seconds=wait_start_seconds,
                wait_completion_seconds=wait_completion_seconds,
                repo_mount_path=repo_mount_path,
                repo_git_path=repo_git_path,
                docker_backend=str(dev_env.get("docker_backend") or "windows"),
            )
        )
        self._record_stage_result(state, key, result.status, result)
        state.status = f"MULTIAGENT_{key.upper()}_{_status_suffix(result.status)}"
        self.write_state(state)
        self.write_manifest(state)
        return state

    def poll_stage(self, artifact_root: Path, *, stage: str) -> RunState:
        state = self.load_state(artifact_root)
        if not state.workspace:
            raise ValueError("Workspace is not recorded in run state.")
        key = normalize_stage(stage)
        layout = ArtifactLayout.create(state.artifact_root)
        task = stage_dir(layout.tasks_dir, key)
        dev_env = state.data.get("modules", {}).get("dev_environment", {})
        config, _, _ = config_for_dev_environment(self.project_root, dev_env)
        agent = OpenHandsStageAgent(project_root=self.project_root, config=config)
        result = agent.refresh(workspace=state.workspace, task_dir=task)
        self._record_stage_result(state, key, result.status, result)
        if not state.status.startswith("EVALUATION_"):
            state.status = f"MULTIAGENT_{key.upper()}_{_status_suffix(result.status)}"
        self.write_state(state)
        self.write_manifest(state)
        return state

    def run_stage_until_terminal(
        self,
        artifact_root: Path,
        *,
        stage: str,
        sandbox_repo_path: str = "/workspace/project",
        model: str | None = None,
        wait_start_seconds: int = 180,
        timeout_seconds: int = 3600,
        poll_interval_seconds: int = 60,
        start_retries: int = 2,
        progress: Callable[[str], None] | None = None,
    ) -> RunState:
        key = normalize_stage(stage)
        last_state: RunState | None = None
        for attempt in range(start_retries + 1):
            if progress:
                progress(f"start stage={key} attempt={attempt + 1}/{start_retries + 1}")
            state = self.start_stage(
                artifact_root,
                stage=key,
                sandbox_repo_path=sandbox_repo_path,
                model=model,
                auto_run=True,
                wait_start_seconds=wait_start_seconds,
                wait_completion_seconds=0,
            )
            deadline = time.time() + timeout_seconds
            while True:
                stage_status = _stage_status(state, key)
                if progress:
                    progress(f"stage={key} status={_display_status(stage_status)}")
                if stage_status in TERMINAL_OPENHANDS_STATUSES:
                    break
                if time.time() >= deadline:
                    raise TimeoutError(f"Stage {key} did not finish within {timeout_seconds} seconds.")
                time.sleep(poll_interval_seconds)
                state = self.poll_stage(artifact_root, stage=key)

            last_state = state
            if _stage_completed_successfully(state, key):
                return state
            if not _is_transient_openhands_start_error(state, key) or attempt >= start_retries:
                break
            time.sleep(min(10 + attempt * 10, 30))

        if last_state is None:
            raise RuntimeError(f"Stage {key} did not start.")
        raise RuntimeError(_stage_failure_message(last_state, key))

    def run_final_evaluation(
        self,
        artifact_root: Path,
        case_yaml: Path,
        *,
        command_timeout: int = 1800,
        run_install: bool = False,
    ) -> RunState:
        state = self.load_state(artifact_root)
        if not state.workspace:
            raise ValueError("Workspace is not ready. Run prepare-dev-env first.")
        case = self.case_builder.load_case(case_yaml)
        output_dir = state.artifact_root / "tasks" / "05-final-evaluator"
        output_dir.mkdir(parents=True, exist_ok=True)
        candidate_patch = state.artifact_root / "tasks" / "03-patch-implementer" / "patch.diff"
        dev_env = state.data.get("modules", {}).get("dev_environment", {})
        execution_backend = None
        if dev_env.get("docker_backend") == "wsl" and dev_env.get("workspace_wsl_path"):
            execution_backend = {
                "docker_backend": "wsl",
                "wsl_distro": str(dev_env.get("wsl_distro") or "Ubuntu-22.04"),
                "workspace_wsl_path": str(dev_env["workspace_wsl_path"]),
                "image": str(dev_env.get("image") or "repoaces/openhands-agent-fastgpt:node20-pnpm10"),
            }
        artifacts = self.final_evaluator.evaluate(
            case=case,
            repo_dir=state.workspace,
            candidate_patch=candidate_patch,
            output_dir=output_dir,
            command_timeout=command_timeout,
            run_install=run_install,
            execution_backend=execution_backend,
        )
        report = read_json(artifacts["final_evaluation_report"])
        state.status = "EVALUATION_PASSED" if report.get("passed") else "EVALUATION_FAILED"
        self._ensure_multiagent_module(state)
        state.data["modules"]["multiagent"]["final_evaluator"] = {
            "task_dir": str(output_dir),
            "passed": bool(report.get("passed")),
            "candidate_patch": str(artifacts["candidate_patch"]),
            "baseline_patch": str(artifacts["baseline_patch"]),
            "eval_script": str(artifacts["eval_script"]),
            "test_output": str(artifacts["test_output"]),
            "final_evaluation_report": str(artifacts["final_evaluation_report"]),
            "result": str(artifacts["result"]),
        }
        self.write_state(state)
        self.write_manifest(state)
        return state

    def write_state(self, state: RunState) -> Path:
        path = state.artifact_root / "report" / "run_state.json"
        write_json(path, path_to_jsonable(asdict(state)))
        return path

    def write_manifest(self, state: RunState) -> Path:
        self.base.write_manifest(state)
        manifest_path = state.artifact_root / "report" / "multiagent-manifest.json"
        write_json(
            manifest_path,
            {
                "run_id": state.run_id,
                "case_id": state.case_id,
                "status": state.status,
                "artifact_root": str(state.artifact_root),
                "workspace": str(state.workspace) if state.workspace else None,
                "stages": state.data.get("modules", {}).get("multiagent", {}).get("stages", {}),
                "final_evaluator": state.data.get("modules", {}).get("multiagent", {}).get("final_evaluator"),
            },
        )
        return manifest_path

    def _record_stage_result(self, state: RunState, key: str, status: str, result: Any) -> None:
        self._ensure_multiagent_module(state)
        state.data["modules"]["multiagent"]["stages"][key] = {
            "status": status,
            "task_dir": str(result.task_dir),
            "runtime_state": str(result.runtime_state_path),
            "patch_path": str(result.patch_path),
            "trajectory_path": str(result.trajectory_path) if result.trajectory_path else None,
            "outputs": result.output_status,
            "result": str(result.task_dir / "result.json"),
        }

    def _ensure_multiagent_module(self, state: RunState) -> None:
        state.data.setdefault("modules", {}).setdefault(
            "multiagent",
            {
                "version": 1,
                "stage_order": list(STAGE_ORDER),
                "workspace_path": "/workspace/project",
                "stages": {},
            },
        )
        state.data["modules"]["multiagent"].setdefault("stages", {})


def _status_suffix(openhands_status: str) -> str:
    if openhands_status.startswith("openhands_"):
        return openhands_status.removeprefix("openhands_").upper()
    return openhands_status.upper()


def _stage_status(state: RunState, key: str) -> str | None:
    raw = (
        state.data.get("modules", {})
        .get("multiagent", {})
        .get("stages", {})
        .get(key, {})
        .get("status")
    )
    return str(raw) if raw else None


def _display_status(status: object) -> str:
    text = str(status or "unknown")
    if text.startswith("openhands_"):
        return "RepoACES_" + text.removeprefix("openhands_")
    return text


def _stage_record(state: RunState, key: str) -> dict[str, Any]:
    raw = (
        state.data.get("modules", {})
        .get("multiagent", {})
        .get("stages", {})
        .get(key, {})
    )
    return raw if isinstance(raw, dict) else {}


def _stage_completed_successfully(state: RunState, key: str) -> bool:
    record = _stage_record(state, key)
    outputs = record.get("outputs")
    return (
        record.get("status") == "openhands_finished"
        and isinstance(outputs, dict)
        and bool(outputs.get("all_required_present"))
    )


def _is_transient_openhands_start_error(state: RunState, key: str) -> bool:
    record = _stage_record(state, key)
    if record.get("status") != "openhands_error":
        return False
    runtime_state_path = record.get("runtime_state")
    if not runtime_state_path:
        return False
    try:
        runtime_state = read_json(Path(str(runtime_state_path)))
    except Exception:  # noqa: BLE001
        return False
    conversation = runtime_state.get("conversation")
    detail = ""
    if isinstance(conversation, dict):
        detail = str(conversation.get("detail") or "")
    transient_fragments = (
        "ports are not available",
        "port is already allocated",
        "bind: An attempt was made to access a socket",
        "Failed to start container",
    )
    return any(fragment in detail for fragment in transient_fragments)


def _stage_failure_message(state: RunState, key: str) -> str:
    record = _stage_record(state, key)
    status = record.get("status")
    outputs = record.get("outputs")
    missing = []
    if isinstance(outputs, dict):
        for item in outputs.get("required", []):
            if isinstance(item, dict) and (not item.get("present") or not item.get("size")):
                missing.append(str(item.get("name")))
    detail = ""
    runtime_state_path = record.get("runtime_state")
    if runtime_state_path:
        try:
            runtime_state = read_json(Path(str(runtime_state_path)))
            conversation = runtime_state.get("conversation")
            if isinstance(conversation, dict):
                detail = str(conversation.get("detail") or "")
        except Exception:  # noqa: BLE001
            detail = ""
    pieces = [f"Stage {key} failed with status {_display_status(status)}."]
    if missing:
        pieces.append(f"Missing required outputs: {', '.join(missing)}.")
    if detail:
        pieces.append(f"OpenHands detail: {detail}")
    return " ".join(pieces)
