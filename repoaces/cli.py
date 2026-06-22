from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent_orchestrator import RepoACESOrchestrator
from .case_builder import CaseBuilder
from .repo_intelligence import CodeWikiRepoIntelligence, StaticRepoIntelligence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repoaces", description="RepoACES modular prototype CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    build_case = sub.add_parser("build-case", help="Build public case artifacts from case.yaml")
    build_case.add_argument("--case", required=True, type=Path)
    build_case.add_argument("--out", required=True, type=Path)
    build_case.add_argument("--workspace-path", default="/workspace")

    init_run = sub.add_parser("init-run", help="Initialize a RepoACES run artifact tree")
    init_run.add_argument("--case", required=True, type=Path)
    init_run.add_argument("--out", type=Path)
    init_run.add_argument("--workspace-path", default="/workspace")

    prepare_workspace = sub.add_parser("prepare-workspace", help="Prepare a clean repository workspace for a run")
    prepare_workspace.add_argument("--case", required=True, type=Path)
    prepare_workspace.add_argument("--artifact-root", required=True, type=Path)
    prepare_workspace.add_argument("--force", action="store_true")

    prepare_dev_env = sub.add_parser("prepare-dev-env", help="Prepare a WSL/Linux dev environment for OpenHands")
    prepare_dev_env.add_argument("--case", required=True, type=Path)
    prepare_dev_env.add_argument("--artifact-root", required=True, type=Path)
    prepare_dev_env.add_argument("--wsl-distro", default="Ubuntu-22.04")
    prepare_dev_env.add_argument("--wsl-root", help="WSL root directory for RepoACES workspaces; defaults to $HOME/repoaces-workspaces")
    prepare_dev_env.add_argument("--image", default="repoaces/openhands-agent-fastgpt:node20-pnpm10")
    prepare_dev_env.add_argument("--container-uid", type=int, default=10001)
    prepare_dev_env.add_argument("--container-gid", type=int, default=10001)
    prepare_dev_env.add_argument("--force", action="store_true")
    prepare_dev_env.add_argument("--skip-install", action="store_true")
    prepare_dev_env.add_argument("--skip-smoke-tests", action="store_true")
    prepare_dev_env.add_argument("--extra-command", action="append", default=[])
    prepare_dev_env.add_argument("--timeout", type=int, default=3600)

    start_openhands = sub.add_parser("start-openhands", help="Start OpenHands for an initialized run")
    start_openhands.add_argument("--artifact-root", required=True, type=Path)
    start_openhands.add_argument("--sandbox-repo-path", default="/workspace")
    start_openhands.add_argument("--instruction-path", type=Path)
    start_openhands.add_argument("--mode", choices=["implementation"], default="implementation")
    start_openhands.add_argument("--model")
    start_openhands.add_argument("--auto-run", choices=["true", "false"], default="true")
    start_openhands.add_argument("--wait-start-seconds", type=int, default=180)
    start_openhands.add_argument("--wait-completion-seconds", type=int, default=0)

    poll_openhands = sub.add_parser("poll-openhands", help="Refresh OpenHands status and patch for a run")
    poll_openhands.add_argument("--artifact-root", required=True, type=Path)
    poll_openhands.add_argument("--mode", choices=["implementation"], default="implementation")

    static_intel = sub.add_parser("static-intel", help="Build static repo intelligence artifacts")
    static_intel.add_argument("--repo", required=True, type=Path)
    static_intel.add_argument("--out", required=True, type=Path)
    static_intel.add_argument("--focus", action="append", default=[])

    codewiki = sub.add_parser("codewiki-intel", help="Run CodeWiki repository wiki generation")
    codewiki.add_argument("--repo", required=True, type=Path)
    codewiki.add_argument("--out", required=True, type=Path)
    codewiki.add_argument("extra_args", nargs="*")

    final_eval = sub.add_parser("final-evaluate", help="Run final deterministic build/test evaluation for a run")
    final_eval.add_argument("--case", required=True, type=Path)
    final_eval.add_argument("--artifact-root", required=True, type=Path)
    final_eval.add_argument("--patch", type=Path, help="Candidate patch to evaluate; defaults to tasks/01-implementation/patch.diff")
    final_eval.add_argument("--timeout", type=int, default=1800)
    final_eval.add_argument("--install", action="store_true", help="Run package-manager install before build/test checks")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = Path.cwd()

    if args.command == "build-case":
        artifacts = CaseBuilder().write_case_artifacts(args.case, args.out, workspace_path=args.workspace_path)
        print(json.dumps({k: str(v) for k, v in artifacts.items()}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "init-run":
        state = RepoACESOrchestrator(project_root).init_run(args.case, artifact_root=args.out, workspace_path=args.workspace_path)
        print(json.dumps({"run_id": state.run_id, "artifact_root": str(state.artifact_root)}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "prepare-workspace":
        state = RepoACESOrchestrator(project_root).prepare_workspace(
            artifact_root=args.artifact_root,
            case_yaml=args.case,
            force=args.force,
        )
        print(
            json.dumps(
                {"run_id": state.run_id, "status": state.status, "workspace": str(state.workspace)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "prepare-dev-env":
        state = RepoACESOrchestrator(project_root).prepare_dev_environment(
            artifact_root=args.artifact_root,
            case_yaml=args.case,
            wsl_distro=args.wsl_distro,
            wsl_root=args.wsl_root,
            image=args.image,
            container_uid=args.container_uid,
            container_gid=args.container_gid,
            force=args.force,
            run_install=not args.skip_install,
            run_smoke_tests=not args.skip_smoke_tests,
            extra_commands=args.extra_command,
            timeout=args.timeout,
        )
        dev_env = state.data.get("modules", {}).get("dev_environment", {})
        print(
            json.dumps(
                {
                    "run_id": state.run_id,
                    "status": state.status,
                    "workspace": str(state.workspace),
                    "workspace_wsl_path": dev_env.get("workspace_wsl_path"),
                    "preflight_log": dev_env.get("preflight_log"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "start-openhands":
        state = RepoACESOrchestrator(project_root).start_openhands_coding(
            artifact_root=args.artifact_root,
            sandbox_repo_path=args.sandbox_repo_path,
            instruction_path=args.instruction_path,
            mode=args.mode,
            model=args.model,
            auto_run=args.auto_run == "true",
            wait_start_seconds=args.wait_start_seconds,
            wait_completion_seconds=args.wait_completion_seconds,
        )
        print(json.dumps({"run_id": state.run_id, "status": state.status}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "poll-openhands":
        state = RepoACESOrchestrator(project_root).refresh_openhands_coding(
            artifact_root=args.artifact_root,
            mode=args.mode,
        )
        print(json.dumps({"run_id": state.run_id, "status": state.status}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "static-intel":
        artifacts = StaticRepoIntelligence().build(args.repo, args.out, focus_terms=args.focus)
        print(json.dumps({k: str(v) for k, v in artifacts.items()}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "codewiki-intel":
        artifacts = CodeWikiRepoIntelligence().build(args.repo, args.out, extra_args=args.extra_args)
        print(json.dumps({k: str(v) for k, v in artifacts.items()}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "final-evaluate":
        state = RepoACESOrchestrator(project_root).run_final_evaluation(
            artifact_root=args.artifact_root,
            case_yaml=args.case,
            candidate_patch=args.patch,
            command_timeout=args.timeout,
            run_install=args.install,
        )
        print(
            json.dumps(
                {"run_id": state.run_id, "status": state.status, "artifact_root": str(state.artifact_root)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
