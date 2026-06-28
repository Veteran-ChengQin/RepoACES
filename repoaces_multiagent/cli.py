from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from .orchestrator import MultiAgentRepoACESOrchestrator
from .stages import STAGE_ORDER, normalize_stage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repoaces-multiagent",
        description="RepoACES MultiAgent workflow prototype",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_run = sub.add_parser("init-run", help="Initialize a MultiAgent RepoACES run")
    init_run.add_argument("--case", required=True, type=Path)
    init_run.add_argument("--out", type=Path)
    init_run.add_argument("--workspace-path", default="/workspace/project")

    prepare_workspace = sub.add_parser("prepare-workspace", help="Prepare a clean repository workspace")
    prepare_workspace.add_argument("--case", required=True, type=Path)
    prepare_workspace.add_argument("--artifact-root", required=True, type=Path)
    prepare_workspace.add_argument("--force", action="store_true")

    prepare_dev_env = sub.add_parser("prepare-dev-env", help="Prepare WSL/Docker development workspace")
    prepare_dev_env.add_argument("--case", required=True, type=Path)
    prepare_dev_env.add_argument("--artifact-root", required=True, type=Path)
    prepare_dev_env.add_argument("--wsl-distro", default="Ubuntu-22.04")
    prepare_dev_env.add_argument("--wsl-root")
    prepare_dev_env.add_argument("--image", default="repoaces/openhands-agent-fastgpt:node20-pnpm10")
    prepare_dev_env.add_argument("--seed-workspace-from-image", action="store_true")
    prepare_dev_env.add_argument("--seed-source-path", default="/workspace")
    prepare_dev_env.add_argument("--container-uid", type=int, default=10001)
    prepare_dev_env.add_argument("--container-gid", type=int, default=10001)
    prepare_dev_env.add_argument("--force", action="store_true")
    prepare_dev_env.add_argument("--skip-install", action="store_true")
    prepare_dev_env.add_argument("--skip-smoke-tests", action="store_true")
    prepare_dev_env.add_argument("--extra-command", action="append", default=[])
    prepare_dev_env.add_argument("--timeout", type=int, default=3600)

    static_intel = sub.add_parser("static-intel", help="Build static repo intelligence")
    static_intel.add_argument("--artifact-root", required=True, type=Path)
    static_intel.add_argument("--focus", action="append", default=[])

    start_stage = sub.add_parser("start-stage", help="Start one OpenHands-backed MultiAgent stage")
    start_stage.add_argument("--artifact-root", required=True, type=Path)
    start_stage.add_argument("--stage", required=True, choices=list(STAGE_ORDER))
    start_stage.add_argument("--sandbox-repo-path", default="/workspace/project")
    start_stage.add_argument("--model")
    start_stage.add_argument("--auto-run", choices=["true", "false"], default="true")
    start_stage.add_argument("--wait-start-seconds", type=int, default=180)
    start_stage.add_argument("--wait-completion-seconds", type=int, default=0)

    poll_stage = sub.add_parser("poll-stage", help="Refresh one MultiAgent stage")
    poll_stage.add_argument("--artifact-root", required=True, type=Path)
    poll_stage.add_argument("--stage", required=True, choices=list(STAGE_ORDER))

    run_stage = sub.add_parser("run-stage", help="Run one stage until OpenHands reaches a terminal status")
    run_stage.add_argument("--artifact-root", required=True, type=Path)
    run_stage.add_argument("--stage", required=True, choices=list(STAGE_ORDER))
    run_stage.add_argument("--sandbox-repo-path", default="/workspace/project")
    run_stage.add_argument("--model")
    run_stage.add_argument("--wait-start-seconds", type=int, default=180)
    run_stage.add_argument("--timeout", type=int, default=3600)
    run_stage.add_argument("--poll-interval", type=int, default=60)

    final_eval = sub.add_parser("final-evaluate", help="Run final evaluator against the implementer patch")
    final_eval.add_argument("--case", required=True, type=Path)
    final_eval.add_argument("--artifact-root", required=True, type=Path)
    final_eval.add_argument("--timeout", type=int, default=1800)
    final_eval.add_argument("--install", action="store_true")

    fullflow = sub.add_parser("fullflow", help="Run init, workspace, dev-env, four agents, and final evaluator")
    fullflow.add_argument("--case", required=True, type=Path)
    fullflow.add_argument("--out", type=Path)
    fullflow.add_argument("--run-name", default="")
    fullflow.add_argument("--workspace-path", default="/workspace/project")
    fullflow.add_argument("--model")
    fullflow.add_argument("--wsl-distro", default="Ubuntu-22.04")
    fullflow.add_argument("--dev-image", default="repoaces/openhands-agent-fastgpt:node20-pnpm10")
    fullflow.add_argument("--seed-workspace-from-image", action="store_true")
    fullflow.add_argument("--seed-source-path", default="/workspace")
    fullflow.add_argument("--prepare-timeout", type=int, default=3600)
    fullflow.add_argument("--stage-timeout", type=int, default=3600)
    fullflow.add_argument("--final-eval-timeout", type=int, default=1800)
    fullflow.add_argument("--poll-interval", type=int, default=60)
    fullflow.add_argument("--force", action="store_true")
    fullflow.add_argument("--skip-static-intel", action="store_true")
    fullflow.add_argument("--skip-dev-install", action="store_true")
    fullflow.add_argument("--skip-dev-smoke", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = Path.cwd()
    orchestrator = MultiAgentRepoACESOrchestrator(project_root)

    if args.command == "init-run":
        state = orchestrator.init_run(args.case, artifact_root=args.out, workspace_path=args.workspace_path)
        return _print_state(state)

    if args.command == "prepare-workspace":
        state = orchestrator.prepare_workspace(args.artifact_root, args.case, force=args.force)
        return _print_state(state)

    if args.command == "prepare-dev-env":
        state = orchestrator.prepare_dev_environment(
            args.artifact_root,
            args.case,
            wsl_distro=args.wsl_distro,
            wsl_root=args.wsl_root,
            image=args.image,
            seed_workspace_from_image=args.seed_workspace_from_image,
            seed_source_path=args.seed_source_path,
            container_uid=args.container_uid,
            container_gid=args.container_gid,
            force=args.force,
            run_install=not args.skip_install,
            run_smoke_tests=not args.skip_smoke_tests,
            extra_commands=args.extra_command,
            timeout=args.timeout,
        )
        return _print_state(state)

    if args.command == "static-intel":
        state = orchestrator.build_static_intelligence(args.artifact_root, focus_terms=args.focus)
        return _print_state(state)

    if args.command == "start-stage":
        state = orchestrator.start_stage(
            args.artifact_root,
            stage=normalize_stage(args.stage),
            sandbox_repo_path=args.sandbox_repo_path,
            model=args.model,
            auto_run=args.auto_run == "true",
            wait_start_seconds=args.wait_start_seconds,
            wait_completion_seconds=args.wait_completion_seconds,
        )
        return _print_state(state)

    if args.command == "poll-stage":
        state = orchestrator.poll_stage(args.artifact_root, stage=normalize_stage(args.stage))
        return _print_state(state)

    if args.command == "run-stage":
        state = orchestrator.run_stage_until_terminal(
            args.artifact_root,
            stage=normalize_stage(args.stage),
            sandbox_repo_path=args.sandbox_repo_path,
            model=args.model,
            wait_start_seconds=args.wait_start_seconds,
            timeout_seconds=args.timeout,
            poll_interval_seconds=args.poll_interval,
        )
        return _print_state(state)

    if args.command == "final-evaluate":
        state = orchestrator.run_final_evaluation(
            args.artifact_root,
            args.case,
            command_timeout=args.timeout,
            run_install=args.install,
        )
        return _print_state(state)

    if args.command == "fullflow":
        artifact_root = args.out
        if not artifact_root:
            case_id = _case_id_from_yaml(args.case)
            run_name = args.run_name or "multiagent-fullflow"
            artifact_root = project_root / "tmp" / "experiments" / "repoaces-multiagent" / case_id / run_name
        _log_step(f"fullflow started case={args.case} artifact_root={artifact_root}")
        _log_step("1/8 init-run")
        state = orchestrator.init_run(args.case, artifact_root=artifact_root, workspace_path=args.workspace_path)
        _log_state(state)
        _log_step("2/8 prepare-workspace")
        state = orchestrator.prepare_workspace(state.artifact_root, args.case, force=args.force)
        _log_state(state)
        if not args.skip_static_intel:
            _log_step("3/8 static-intel")
            state = orchestrator.build_static_intelligence(
                state.artifact_root,
                focus_terms=["agentSkills", "version", "openapi"],
            )
            _log_state(state)
        else:
            _log_step("3/8 static-intel skipped")
        _log_step("4/8 prepare-dev-env")
        state = orchestrator.prepare_dev_environment(
            state.artifact_root,
            args.case,
            wsl_distro=args.wsl_distro,
            image=args.dev_image,
            seed_workspace_from_image=args.seed_workspace_from_image,
            seed_source_path=args.seed_source_path,
            force=args.force,
            run_install=not args.skip_dev_install,
            run_smoke_tests=not args.skip_dev_smoke,
            timeout=args.prepare_timeout,
        )
        _log_state(state)
        stage_numbers = {
            "scope": "5/8",
            "plan": "6/8",
            "implement": "7/8",
            "validate": "8/8",
        }
        for stage in STAGE_ORDER:
            _log_step(f"{stage_numbers.get(stage, '?/8')} run-stage {stage}")
            state = orchestrator.run_stage_until_terminal(
                state.artifact_root,
                stage=stage,
                sandbox_repo_path=args.workspace_path,
                model=args.model,
                timeout_seconds=args.stage_timeout,
                poll_interval_seconds=args.poll_interval,
                progress=_log,
            )
            _log_state(state)
        _log_step("final-evaluate")
        state = orchestrator.run_final_evaluation(
            state.artifact_root,
            args.case,
            command_timeout=args.final_eval_timeout,
        )
        _log_state(state)
        _log_step("fullflow completed")
        return _print_state(state)

    raise AssertionError(f"Unhandled command: {args.command}")


def _print_state(state: object) -> int:
    print(
        json.dumps(
            {
                "run_id": getattr(state, "run_id"),
                "case_id": getattr(state, "case_id"),
                "status": getattr(state, "status"),
                "artifact_root": str(getattr(state, "artifact_root")),
                "workspace": str(getattr(state, "workspace")) if getattr(state, "workspace") else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def _log_step(message: str) -> None:
    _log(_style(message, "1", "36"))


def _log_state(state: object) -> None:
    _log(
        "state "
        f"run_id={getattr(state, 'run_id')} "
        f"status={getattr(state, 'status')} "
        f"artifact_root={getattr(state, 'artifact_root')}"
    )


def _style(text: str, *codes: str) -> str:
    if not _color_enabled() or not codes:
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR") or os.environ.get("REPOACES_NO_COLOR"):
        return False
    return bool(os.environ.get("FORCE_COLOR") or sys.stdout.isatty())


def _case_id_from_yaml(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.strip().startswith("id:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return path.parent.name


if __name__ == "__main__":
    raise SystemExit(main())
