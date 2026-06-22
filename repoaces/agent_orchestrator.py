from __future__ import annotations

import uuid
from dataclasses import asdict
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .case_builder import CaseBuilder
from .coding_agents import CodingTask, OpenHandsCodingAgent
from .dev_environment import DevEnvironmentPreparer
from .evaluator import FinalEvaluator
from .io import path_to_jsonable, read_json, write_json
from .models import ArtifactLayout, RunState
from .openhands_client import OpenHandsConfig, OpenHandsRuntime
from .repositories import RepositoryManager


class RepoACESOrchestrator:
    """Artifact-driven orchestrator for the five RepoACES modules."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.case_builder = CaseBuilder()
        self.dev_environment = DevEnvironmentPreparer(project_root)
        self.final_evaluator = FinalEvaluator()
        self.repository_manager = RepositoryManager(
            workspaces_root=project_root / "workspaces" / "repoaces-runs",
            reference_repo=project_root / "workspaces" / "pr7008-run-003" / "FastGPT",
        )

    def init_run(self, case_yaml: Path, artifact_root: Path | None = None, workspace_path: str = "/workspace") -> RunState:
        case = self.case_builder.load_case(case_yaml)
        run_id = f"{case.case_id}-{uuid.uuid4().hex[:8]}"
        root = artifact_root or self.project_root / "tmp" / "experiments" / "repoaces" / case.case_id / run_id
        layout = ArtifactLayout.create(root)

        case_artifacts = self.case_builder.write_case_artifacts(
            case_yaml,
            layout.case_dir,
            workspace_path=workspace_path,
            private_output_dir=layout.report_dir / "private",
        )
        state = RunState(
            run_id=run_id,
            case_id=case.case_id,
            status="INITIALIZED",
            artifact_root=root,
            data={
                "created_at": datetime.now(timezone.utc).isoformat(),
                "modules": {
                    "case_builder": path_to_jsonable(case_artifacts),
                    "dev_environment": {},
                    "repo_intelligence": {},
                    "agent_orchestrator": {"state": str(layout.report_dir / "run_state.json")},
                    "coding_agents": {},
                    "final_evaluator": {},
                },
            },
        )
        self.write_state(state)
        self.write_manifest(state)
        return state

    def load_state(self, artifact_root: Path) -> RunState:
        state_path = artifact_root / "report" / "run_state.json"
        raw = read_json(state_path)
        return RunState(
            run_id=str(raw["run_id"]),
            case_id=str(raw["case_id"]),
            status=str(raw["status"]),
            artifact_root=Path(raw["artifact_root"]),
            workspace=Path(raw["workspace"]) if raw.get("workspace") else None,
            data=raw.get("data") or {},
        )

    def prepare_workspace(self, artifact_root: Path, case_yaml: Path, *, force: bool = False) -> RunState:
        state = self.load_state(artifact_root)
        case = self.case_builder.load_case(case_yaml)
        workspace = self.repository_manager.prepare_clean_repo(
            run_id=state.run_id,
            repo_url=case.input.repo_url,
            base_commit=case.input.base_commit,
            pr_number=case.input.pr_number,
            repo_name=case.input.repo.split("/")[-1],
            force=force,
        )
        state.workspace = workspace.repo_dir
        state.status = "WORKSPACE_READY"
        state.data.setdefault("modules", {}).setdefault("agent_orchestrator", {})["workspace"] = {
            "repo_dir": str(workspace.repo_dir),
            "repo_url": workspace.repo_url,
            "base_commit": workspace.base_commit,
            "clone_source": workspace.clone_source,
        }
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
        container_uid: int = 10001,
        container_gid: int = 10001,
        force: bool = False,
        run_install: bool = True,
        run_smoke_tests: bool = True,
        extra_commands: list[str] | None = None,
        timeout: int = 3600,
    ) -> RunState:
        state = self.load_state(artifact_root)
        if not state.workspace:
            raise ValueError("Workspace is not ready. Run prepare-workspace first.")
        case = self.case_builder.load_case(case_yaml)
        layout = ArtifactLayout.create(state.artifact_root)
        task_dir = layout.task_dir("prepare-dev-env")
        dev_env_state = state.data.get("modules", {}).get("dev_environment", {})
        source_workspace = state.workspace
        recorded_source = dev_env_state.get("source_workspace") if isinstance(dev_env_state, dict) else None
        if recorded_source and Path(recorded_source).exists():
            source_workspace = Path(recorded_source)
        result = self.dev_environment.prepare_wsl_fastgpt(
            case=case,
            run_id=state.run_id,
            source_workspace=source_workspace,
            output_dir=task_dir,
            wsl_distro=wsl_distro,
            wsl_root=wsl_root,
            image=image,
            container_uid=container_uid,
            container_gid=container_gid,
            force=force,
            run_install=run_install,
            run_smoke_tests=run_smoke_tests,
            extra_commands=extra_commands or [],
            timeout=timeout,
        )
        original_workspace = source_workspace
        state.workspace = Path(result.workspace_unc)
        state.status = "DEV_ENV_READY" if result.status == "passed" else "DEV_ENV_FAILED"
        state.data.setdefault("modules", {})["dev_environment"] = {
            "status": result.status,
            "task_dir": str(task_dir),
            "source_workspace": str(original_workspace),
            "active_workspace": result.workspace_unc,
            "workspace_unc": result.workspace_unc,
            "workspace_wsl_path": result.workspace_wsl_path,
            "docker_backend": result.docker_backend,
            "wsl_distro": result.wsl_distro,
            "image": result.image,
            "dev_environment_report": str(result.report_path),
            "preflight_log": str(result.preflight_log_path),
            "result": str(result.result_path),
            "scripts": {key: str(path) for key, path in result.scripts.items()},
        }
        self.write_state(state)
        self.write_manifest(state)
        return state

    def start_openhands_coding(
        self,
        artifact_root: Path,
        *,
        sandbox_repo_path: str = "/workspace",
        instruction_path: Path | None = None,
        mode: str = "implementation",
        auto_run: bool = True,
        wait_start_seconds: int = 180,
        wait_completion_seconds: int = 0,
        model: str | None = None,
    ) -> RunState:
        if mode != "implementation":
            raise ValueError("RepoACES currently supports only OpenHands implementation mode.")
        state = self.load_state(artifact_root)
        if not state.workspace:
            raise ValueError("Workspace is not ready. Run prepare-workspace first.")
        layout = ArtifactLayout.create(state.artifact_root)
        instruction_path = instruction_path or layout.case_dir / "instruction.md"
        task_dir = layout.task_dir(mode)
        dev_env = state.data.get("modules", {}).get("dev_environment", {})
        config = OpenHandsConfig.from_env(self.project_root)
        repo_mount_path = None
        repo_git_path = None
        if dev_env.get("docker_backend") == "wsl" and dev_env.get("workspace_wsl_path"):
            image_repo, image_tag = _split_docker_image(str(dev_env.get("image") or ""), config.agent_server_image_repository, config.agent_server_image_tag)
            config = replace(
                config,
                docker_backend="wsl",
                wsl_distro=str(dev_env.get("wsl_distro") or config.wsl_distro),
                agent_server_image_repository=image_repo,
                agent_server_image_tag=image_tag,
            )
            repo_mount_path = str(dev_env["workspace_wsl_path"])
            repo_git_path = str(dev_env["workspace_wsl_path"])
        agent = OpenHandsCodingAgent(project_root=self.project_root, config=config)
        result = agent.run(
            CodingTask(
                run_id=state.run_id,
                workspace=state.workspace,
                instruction_path=instruction_path,
                artifact_dir=task_dir,
                mode=mode,
                sandbox_repo_path=sandbox_repo_path,
                model=model,
                auto_run=auto_run,
                wait_start_seconds=wait_start_seconds,
                wait_completion_seconds=wait_completion_seconds,
                repo_mount_path=repo_mount_path,
                repo_git_path=repo_git_path,
            )
        )
        state.status = result.status
        state.data.setdefault("modules", {}).setdefault("coding_agents", {}).setdefault("openhands", {})[mode] = {
            "status": result.status,
            "summary": result.summary,
            "patch_path": str(result.patch_path) if result.patch_path else None,
            "trajectory_path": str(result.trajectory_path) if result.trajectory_path else None,
            "runtime_state": str(task_dir / "openhands_runtime_state.json"),
            "instruction_path": str(instruction_path),
            "task_dir": str(task_dir),
            "result": str(task_dir / "result.json"),
        }
        self.write_state(state)
        self.write_manifest(state)
        return state

    def refresh_openhands_coding(self, artifact_root: Path, *, mode: str = "implementation") -> RunState:
        if mode != "implementation":
            raise ValueError("RepoACES currently supports only OpenHands implementation mode.")
        state = self.load_state(artifact_root)
        if not state.workspace:
            raise ValueError("Workspace is not recorded in run state.")
        layout = ArtifactLayout.create(state.artifact_root)
        task_dir = layout.task_dir(mode)
        dev_env = state.data.get("modules", {}).get("dev_environment", {})
        config = OpenHandsConfig.from_env(self.project_root)
        if dev_env.get("docker_backend") == "wsl":
            image_repo, image_tag = _split_docker_image(str(dev_env.get("image") or ""), config.agent_server_image_repository, config.agent_server_image_tag)
            config = replace(
                config,
                docker_backend="wsl",
                wsl_distro=str(dev_env.get("wsl_distro") or config.wsl_distro),
                agent_server_image_repository=image_repo,
                agent_server_image_tag=image_tag,
            )
        agent = OpenHandsCodingAgent(project_root=self.project_root, config=config)
        result = agent.refresh(workspace=state.workspace, artifact_dir=task_dir, mode=mode)
        if not state.status.startswith("EVALUATION_"):
            state.status = result.status
        state.data.setdefault("modules", {}).setdefault("coding_agents", {}).setdefault("openhands", {}).setdefault(
            mode, {}
        ).update(
            {
                "status": result.status,
                "summary": result.summary,
                "patch_path": str(result.patch_path) if result.patch_path else None,
                "trajectory_path": str(result.trajectory_path) if result.trajectory_path else None,
                "runtime_state": str(task_dir / "openhands_runtime_state.json"),
                "task_dir": str(task_dir),
                "result": str(task_dir / "result.json"),
            }
        )
        self.write_state(state)
        self.write_manifest(state)
        return state

    def run_final_evaluation(
        self,
        artifact_root: Path,
        case_yaml: Path,
        *,
        candidate_patch: Path | None = None,
        command_timeout: int = 1800,
        run_install: bool = False,
    ) -> RunState:
        state = self.load_state(artifact_root)
        if not state.workspace:
            raise ValueError("Workspace is not ready. Run prepare-workspace first.")
        case = self.case_builder.load_case(case_yaml)
        layout = ArtifactLayout.create(state.artifact_root)
        task_dir = layout.task_dir("final-evaluator")
        implementation_dir = layout.task_dir("implementation")
        patch_path = candidate_patch or implementation_dir / "patch.diff"
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
            candidate_patch=patch_path,
            output_dir=task_dir,
            command_timeout=command_timeout,
            run_install=run_install,
            execution_backend=execution_backend,
        )
        report = read_json(artifacts["final_evaluation_report"])
        state.status = "EVALUATION_PASSED" if report.get("passed") else "EVALUATION_FAILED"
        cleanup_path = task_dir / "openhands_container_cleanup.json"
        cleanup_result = self._cleanup_openhands_runtime_after_evaluation(
            layout=layout,
            dev_env=dev_env,
            cleanup_path=cleanup_path,
        )
        state.data.setdefault("modules", {})["final_evaluator"] = {
            "task_dir": str(task_dir),
            "passed": bool(report.get("passed")),
            "candidate_patch": str(artifacts["candidate_patch"]),
            "baseline_patch": str(artifacts["baseline_patch"]),
            "eval_script": str(artifacts["eval_script"]),
            "test_output": str(artifacts["test_output"]),
            "final_evaluation_report": str(artifacts["final_evaluation_report"]),
            "openhands_container_cleanup": str(cleanup_path) if cleanup_result else None,
            "result": str(artifacts["result"]),
        }
        self.write_state(state)
        self.write_manifest(state)
        return state

    def _cleanup_openhands_runtime_after_evaluation(
        self,
        *,
        layout: ArtifactLayout,
        dev_env: dict,
        cleanup_path: Path,
    ) -> dict | None:
        runtime_state_path = layout.task_dir("implementation") / "openhands_runtime_state.json"
        if not runtime_state_path.exists():
            return None
        runtime_state = read_json(runtime_state_path)
        existing_cleanup = runtime_state.get("container_cleanup")
        if isinstance(existing_cleanup, dict) and existing_cleanup.get("attempted") and existing_cleanup.get("all_removed"):
            cleanup_result = dict(existing_cleanup)
            cleanup_result["stage"] = "final-evaluator"
            runtime_state["container_cleanup"] = cleanup_result
            write_json(runtime_state_path, runtime_state)
        else:
            config = OpenHandsConfig.from_env(self.project_root)
            if dev_env.get("docker_backend") == "wsl":
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
            runtime = OpenHandsRuntime(config, self.project_root / "runs" / "repoaces-openhands")
            cleanup_result = runtime.cleanup_runtime_containers(runtime_state)
            cleanup_result["stage"] = "final-evaluator"
            runtime_state["container_cleanup"] = cleanup_result
            write_json(runtime_state_path, runtime_state)
        write_json(cleanup_path, cleanup_result)
        return cleanup_result

    def write_state(self, state: RunState) -> Path:
        path = state.artifact_root / "report" / "run_state.json"
        write_json(path, path_to_jsonable(asdict(state)))
        return path

    def write_manifest(self, state: RunState) -> Path:
        manifest = {
            "run_id": state.run_id,
            "case_id": state.case_id,
            "status": state.status,
            "artifact_root": str(state.artifact_root),
            "workspace": str(state.workspace) if state.workspace else None,
            "tasks_root": str(state.artifact_root / "tasks"),
            "modules": state.data.get("modules", {}),
        }
        path = state.artifact_root / "report" / "artifact-manifest.json"
        write_json(path, manifest)
        return path


def _split_docker_image(image: str, default_repository: str, default_tag: str) -> tuple[str, str]:
    image = image.strip()
    if not image or "@" in image:
        return default_repository, default_tag
    slash_index = image.rfind("/")
    colon_index = image.rfind(":")
    if colon_index > slash_index:
        return image[:colon_index], image[colon_index + 1 :]
    return image, default_tag
