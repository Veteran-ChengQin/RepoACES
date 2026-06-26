from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import write_stage_result
from .io import write_json, write_patch_text, write_text
from .models import FeatureCase
from .shell import run_cmd


@dataclass(frozen=True)
class EvalCommand:
    name: str
    argv: list[str]
    cwd: Path
    timeout: int
    required: bool = True
    reason: str = ""


class FinalEvaluator:
    """Run deterministic final checks for a completed implementation.

    This evaluator does not call an LLM and does not start OpenHands. It records
    the candidate patch, the benchmark baseline patch, and command results from
    the modified workspace.
    """

    def evaluate(
        self,
        *,
        case: FeatureCase,
        repo_dir: Path,
        candidate_patch: Path | None,
        output_dir: Path,
        command_timeout: int = 1800,
        run_install: bool = False,
        execution_backend: dict[str, Any] | None = None,
    ) -> dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)

        candidate_patch_path = output_dir / "candidate.patch"
        if candidate_patch and candidate_patch.exists():
            shutil.copy2(candidate_patch, candidate_patch_path)
        else:
            self._export_git_diff(repo_dir, candidate_patch_path)

        baseline_patch_path = output_dir / "baseline.patch"
        baseline_source = case.case_path.parent / case.validation.patch_file
        if baseline_source.exists():
            shutil.copy2(baseline_source, baseline_patch_path)
        else:
            write_text(baseline_patch_path, "")

        if self._should_use_compose_bundle(case):
            bundle_root = self._find_compose_bundle_root(case.case_path)
            if bundle_root:
                return self._evaluate_with_compose_bundle(
                    case=case,
                    candidate_patch_path=candidate_patch_path,
                    baseline_patch_path=baseline_patch_path,
                    output_dir=output_dir,
                    command_timeout=command_timeout,
                    bundle_root=bundle_root,
                )

        command_plan = self._build_command_plan(
            repo_dir=repo_dir,
            candidate_patch=candidate_patch_path,
            timeout=command_timeout,
            run_install=run_install,
        )
        eval_script_path = output_dir / "eval.sh"
        eval_plan_path = output_dir / "eval_plan.md"
        commands_path = output_dir / "commands.json"
        self._write_eval_script(eval_script_path, command_plan, repo_dir, execution_backend=execution_backend)
        self._write_eval_plan(eval_plan_path, case, command_plan)
        write_json(commands_path, [self._command_to_json(command, repo_dir) for command in command_plan])

        command_results = [self._run_command(command, repo_dir, execution_backend=execution_backend) for command in command_plan]
        test_output_path = output_dir / "test_output.txt"
        write_text(test_output_path, self._render_test_output(command_results))

        candidate_files = self._files_from_patch(candidate_patch_path)
        baseline_files = self._files_from_patch(baseline_patch_path)
        report = {
            "case_id": case.case_id,
            "repo": case.input.repo,
            "base_commit": case.input.base_commit,
            "candidate_patch": str(candidate_patch_path),
            "baseline_patch": str(baseline_patch_path),
            "candidate_patch_sha256": self._sha256(candidate_patch_path),
            "baseline_patch_sha256": self._sha256(baseline_patch_path),
            "candidate_changed_files": candidate_files,
            "baseline_changed_files": baseline_files,
            "changed_file_overlap": sorted(set(candidate_files) & set(baseline_files)),
            "execution_backend": execution_backend or {"docker_backend": "host"},
            "commands": command_results,
            "passed": all((not item["required"]) or item["returncode"] == 0 for item in command_results),
            "note": (
                "Final evaluator runs deterministic repository checks only. "
                "Baseline patch comparison is diagnostic and not fed back to a repair agent."
            ),
        }
        report_path = output_dir / "final_evaluation_report.json"
        write_json(report_path, report)

        result_path = write_stage_result(
            run_root=_run_root(output_dir),
            stage_dir=output_dir,
            stage="final-evaluator",
            role="final_evaluator",
            status="passed" if report["passed"] else "failed",
            completed=True,
            result={
                "instruction": _run_root(output_dir) / "tasks" / "01-implementation" / "instruction.md",
                "trajectory": _run_root(output_dir) / "tasks" / "01-implementation" / "trajectory.json",
                "patch": _run_root(output_dir) / "tasks" / "01-implementation" / "patch.diff",
                "candidate_patch": candidate_patch_path,
                "baseline_patch": baseline_patch_path,
                "eval_script": eval_script_path,
                "eval_plan": eval_plan_path,
                "commands": commands_path,
                "test_output": test_output_path,
                "final_evaluation_report": report_path,
                "passed": report["passed"],
            },
        )

        return {
            "candidate_patch": candidate_patch_path,
            "baseline_patch": baseline_patch_path,
            "eval_script": eval_script_path,
            "eval_plan": eval_plan_path,
            "commands": commands_path,
            "test_output": test_output_path,
            "final_evaluation_report": report_path,
            "result": result_path,
        }

    def _should_use_compose_bundle(self, case: FeatureCase) -> bool:
        backend = os.getenv("REPOACES_FINAL_EVALUATOR_BACKEND", "auto").strip().lower()
        if backend in {"dynamic", "legacy", "repo"}:
            return False
        if backend in {"compose", "compose-bundle", "docker", "per-instance", "auto"}:
            bundle_root = self._find_compose_bundle_root(case.case_path)
            return bool(bundle_root and (bundle_root / "configs" / f"{case.case_id}.eval.json").exists())
        return False

    def _find_compose_bundle_root(self, start: Path) -> Path | None:
        for parent in [start.resolve(), *start.resolve().parents]:
            candidate = parent / "docker" / "compose-bundle"
            if (candidate / "configs").exists() and (candidate / "scripts" / "Run-PrEval.ps1").exists():
                return candidate
        cwd_candidate = Path.cwd() / "docker" / "compose-bundle"
        if (cwd_candidate / "configs").exists() and (cwd_candidate / "scripts" / "Run-PrEval.ps1").exists():
            return cwd_candidate
        return None

    def _evaluate_with_compose_bundle(
        self,
        *,
        case: FeatureCase,
        candidate_patch_path: Path,
        baseline_patch_path: Path,
        output_dir: Path,
        command_timeout: int,
        bundle_root: Path,
    ) -> dict[str, Path]:
        config_path = bundle_root / "configs" / f"{case.case_id}.eval.json"
        config = json.loads(config_path.read_text(encoding="utf-8-sig", errors="replace"))
        mode = os.getenv("REPOACES_COMPOSE_EVAL_MODE", "all").strip() or "all"
        image_prefix = os.getenv("REPOACES_COMPOSE_EVAL_IMAGE_PREFIX", "repoaces/eval").strip() or "repoaces/eval"
        image_ref = self._compose_bundle_image_ref(config, image_prefix=image_prefix)
        result_root = output_dir / "docker-bundle-results"
        result_root.mkdir(parents=True, exist_ok=True)

        eval_script_path = output_dir / "eval.sh"
        eval_plan_path = output_dir / "eval_plan.md"
        commands_path = output_dir / "commands.json"
        test_output_path = output_dir / "test_output.txt"
        report_path = output_dir / "final_evaluation_report.json"
        build_log_path = output_dir / "docker_image_build.log"

        self._write_compose_bundle_eval_script(
            eval_script_path,
            bundle_root=bundle_root,
            case_id=case.case_id,
            mode=mode,
            candidate_patch_path=candidate_patch_path,
            result_root=result_root,
            image_prefix=image_prefix,
        )
        self._write_compose_bundle_eval_plan(
            eval_plan_path,
            case=case,
            config=config,
            image_ref=image_ref,
            mode=mode,
            bundle_root=bundle_root,
        )
        write_json(
            commands_path,
            {
                "backend": "compose_bundle",
                "bundle_root": str(bundle_root),
                "config": str(config_path),
                "image": image_ref,
                "mode": mode,
                "commands": config.get("commands", []),
            },
        )

        build_output = ""
        image_status = self._ensure_compose_bundle_image(
            bundle_root=bundle_root,
            case_id=case.case_id,
            image_ref=image_ref,
            command_timeout=command_timeout,
            image_prefix=image_prefix,
        )
        build_output = image_status.get("output", "")
        write_text(build_log_path, build_output)

        run_proc: Any | None = None
        if image_status["available"]:
            run_proc = self._run_compose_bundle_eval(
                bundle_root=bundle_root,
                case_id=case.case_id,
                mode=mode,
                candidate_patch_path=candidate_patch_path,
                result_root=result_root,
                command_timeout=command_timeout,
                image_prefix=image_prefix,
            )

        container_report_path = result_root / "evaluation-report.json"
        container_summary_path = result_root / "evaluation-summary.txt"
        container_report: dict[str, Any] = {}
        if container_report_path.exists():
            try:
                container_report = json.loads(container_report_path.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError as exc:
                container_report = {"parse_error": str(exc)}

        stdout = run_proc.stdout if run_proc is not None else ""
        stderr = run_proc.stderr if run_proc is not None else image_status.get("error", "")
        summary_text = container_summary_path.read_text(encoding="utf-8", errors="replace") if container_summary_path.exists() else ""
        test_output = "\n".join(
            [
                "==> compose_bundle_image",
                image_ref,
                "",
                "==> docker_image_build",
                build_output,
                "",
                "==> compose_bundle_eval_stdout",
                stdout,
                "",
                "==> compose_bundle_eval_stderr",
                stderr,
                "",
                "==> evaluation-summary.txt",
                summary_text,
                "",
            ]
        )
        write_text(test_output_path, test_output)

        candidate_files = self._files_from_patch(candidate_patch_path)
        baseline_files = self._files_from_patch(baseline_patch_path)
        run_returncode = run_proc.returncode if run_proc is not None else 127
        passed = bool(image_status["available"]) and run_returncode == 0 and bool(container_report.get("passed", False))
        report = {
            "case_id": case.case_id,
            "repo": case.input.repo,
            "base_commit": case.input.base_commit,
            "candidate_patch": str(candidate_patch_path),
            "baseline_patch": str(baseline_patch_path),
            "candidate_patch_sha256": self._sha256(candidate_patch_path),
            "baseline_patch_sha256": self._sha256(baseline_patch_path),
            "candidate_changed_files": candidate_files,
            "baseline_changed_files": baseline_files,
            "changed_file_overlap": sorted(set(candidate_files) & set(baseline_files)),
            "execution_backend": {
                "type": "compose_bundle",
                "bundle_root": str(bundle_root),
                "config": str(config_path),
                "image": image_ref,
                "mode": mode,
                "result_root": str(result_root),
                "image_status": {k: v for k, v in image_status.items() if k != "output"},
            },
            "commands": container_report.get("commands", []),
            "compose_bundle_report": container_report,
            "docker_run_returncode": run_returncode,
            "passed": passed,
            "note": (
                "Final evaluator used the per-PR Docker compose-bundle backend. "
                "The candidate patch was applied inside the PR-specific evaluator image."
            ),
        }
        write_json(report_path, report)

        result_path = write_stage_result(
            run_root=_run_root(output_dir),
            stage_dir=output_dir,
            stage="final-evaluator",
            role="final_evaluator",
            status="passed" if report["passed"] else "failed",
            completed=True,
            result={
                "instruction": _run_root(output_dir) / "tasks" / "01-implementation" / "instruction.md",
                "trajectory": _run_root(output_dir) / "tasks" / "01-implementation" / "trajectory.json",
                "patch": _run_root(output_dir) / "tasks" / "01-implementation" / "patch.diff",
                "candidate_patch": candidate_patch_path,
                "baseline_patch": baseline_patch_path,
                "eval_script": eval_script_path,
                "eval_plan": eval_plan_path,
                "commands": commands_path,
                "test_output": test_output_path,
                "final_evaluation_report": report_path,
                "passed": report["passed"],
            },
        )

        return {
            "candidate_patch": candidate_patch_path,
            "baseline_patch": baseline_patch_path,
            "eval_script": eval_script_path,
            "eval_plan": eval_plan_path,
            "commands": commands_path,
            "test_output": test_output_path,
            "final_evaluation_report": report_path,
            "result": result_path,
        }

    def _compose_bundle_image_ref(self, config: dict[str, Any], *, image_prefix: str) -> str:
        pr_number = str(config["pr_number"])
        base_commit = str(config["base_commit"])
        return f"{image_prefix}-{pr_number}:{base_commit[:12]}"

    def _ensure_compose_bundle_image(
        self,
        *,
        bundle_root: Path,
        case_id: str,
        image_ref: str,
        command_timeout: int,
        image_prefix: str,
    ) -> dict[str, Any]:
        build_policy = os.getenv("REPOACES_COMPOSE_EVAL_BUILD", "auto").strip().lower()
        force_build = build_policy in {"always", "force", "rebuild", "true", "1", "yes"}
        inspect = run_cmd(["docker", "image", "inspect", image_ref], timeout=120)
        if inspect.returncode == 0 and not force_build:
            return {"available": True, "built": False, "returncode": 0, "output": inspect.stdout}

        if build_policy in {"never", "false", "0", "no"}:
            return {
                "available": False,
                "built": False,
                "returncode": inspect.returncode,
                "output": inspect.stdout + inspect.stderr,
                "error": f"Evaluator image is missing and auto-build is disabled: {image_ref}",
            }

        pr = case_id.removeprefix("fastgpt-pr-")
        script = bundle_root / "scripts" / "Build-PrImage.ps1"
        build_args = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Pr",
            pr,
            "-ImagePrefix",
            image_prefix,
            "-SkipVerify",
        ]
        npm_registry = os.getenv("REPOACES_COMPOSE_EVAL_NPM_REGISTRY", "").strip()
        fastgpt_repo = os.getenv("REPOACES_COMPOSE_EVAL_FASTGPT_REPO", "").strip()
        node_image = os.getenv("REPOACES_COMPOSE_EVAL_NODE_IMAGE", "").strip()
        if npm_registry:
            build_args.extend(["-NpmRegistry", npm_registry])
        if fastgpt_repo:
            build_args.extend(["-FastGptRepo", fastgpt_repo])
        if node_image:
            build_args.extend(["-NodeImage", node_image])

        build = run_cmd(
            build_args,
            cwd=bundle_root,
            timeout=max(command_timeout, 3600),
        )
        output = build.stdout + build.stderr
        if build.returncode != 0:
            return {
                "available": False,
                "built": True,
                "returncode": build.returncode,
                "output": output,
                "error": f"Evaluator image build failed: {image_ref}",
            }
        inspect_after = run_cmd(["docker", "image", "inspect", image_ref], timeout=120)
        return {
            "available": inspect_after.returncode == 0,
            "built": True,
            "returncode": inspect_after.returncode,
            "output": output + inspect_after.stdout + inspect_after.stderr,
            "error": "" if inspect_after.returncode == 0 else f"Built image was not found after build: {image_ref}",
        }

    def _run_compose_bundle_eval(
        self,
        *,
        bundle_root: Path,
        case_id: str,
        mode: str,
        candidate_patch_path: Path,
        result_root: Path,
        command_timeout: int,
        image_prefix: str,
    ) -> Any:
        pr = case_id.removeprefix("fastgpt-pr-")
        script = bundle_root / "scripts" / "Run-PrEval.ps1"
        return run_cmd(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-Pr",
                pr,
                "-Mode",
                mode,
                "-Patch",
                str(candidate_patch_path.resolve()),
                "-ResultRoot",
                str(result_root.resolve()),
                "-ImagePrefix",
                image_prefix,
            ],
            cwd=bundle_root,
            timeout=max(command_timeout, 3600),
        )

    def _write_compose_bundle_eval_script(
        self,
        path: Path,
        *,
        bundle_root: Path,
        case_id: str,
        mode: str,
        candidate_patch_path: Path,
        result_root: Path,
        image_prefix: str,
    ) -> None:
        pr = case_id.removeprefix("fastgpt-pr-")
        content = "\n".join(
            [
                "# Reproduce RepoACES compose-bundle final evaluation from PowerShell:",
                "powershell -NoProfile -ExecutionPolicy Bypass -File \\",
                f"  {_ps_quote(str(bundle_root / 'scripts' / 'Run-PrEval.ps1'))} \\",
                f"  -Pr {pr} \\",
                f"  -Mode {mode} \\",
                f"  -Patch {_ps_quote(str(candidate_patch_path.resolve()))} \\",
                f"  -ResultRoot {_ps_quote(str(result_root.resolve()))} \\",
                f"  -ImagePrefix {_ps_quote(image_prefix)}",
                "",
            ]
        )
        write_text(path, content)

    def _write_compose_bundle_eval_plan(
        self,
        path: Path,
        *,
        case: FeatureCase,
        config: dict[str, Any],
        image_ref: str,
        mode: str,
        bundle_root: Path,
    ) -> None:
        command_lines = []
        for command in config.get("commands", []):
            command_lines.append(
                "\n".join(
                    [
                        f"- `{command.get('phase')}:{command.get('name')}` in `{command.get('cwd')}`",
                        f"  Command: `{command.get('shell')}`",
                        f"  Required: `{command.get('required', True)}`",
                        f"  Reason: {command.get('reason', '')}",
                    ]
                )
            )
        content = f"""# Final Evaluation Plan

## Case

- Case ID: `{case.case_id}`
- Repository: `{case.input.repo}`
- Base commit: `{case.input.base_commit}`
- PR title: {case.input.pr_title_raw}

## Backend

- Type: `compose_bundle`
- Bundle root: `{bundle_root}`
- Image: `{image_ref}`
- Mode: `{mode}`

## Scope

This final evaluator runs the PR-specific Docker evaluator image from `docker/compose-bundle`.
The candidate patch is mounted into the container and applied to the clean base workspace inside the image.

## Commands

{chr(10).join(command_lines) if command_lines else "- No commands found in compose-bundle config."}
"""
        write_text(path, content)

    def _build_command_plan(
        self,
        *,
        repo_dir: Path,
        candidate_patch: Path,
        timeout: int,
        run_install: bool,
    ) -> list[EvalCommand]:
        commands: list[EvalCommand] = [
            EvalCommand(
                name="git_diff_check",
                argv=["git", "diff", "--check"],
                cwd=repo_dir,
                timeout=300,
                reason="Detect whitespace and patch formatting errors in the modified workspace.",
            )
        ]
        package_manager = self._package_manager(repo_dir)
        if not package_manager:
            return commands

        if run_install:
            commands.append(
                EvalCommand(
                    name="install_dependencies",
                    argv=[package_manager, "install", "--frozen-lockfile"],
                    cwd=repo_dir,
                    timeout=max(timeout, 2400),
                    reason="Install dependencies before build/test checks.",
                )
            )

        if (repo_dir / "tsconfig.json").exists():
            commands.append(
                EvalCommand(
                    name="typescript_root_no_emit",
                    argv=[package_manager, "exec", "tsc", "-p", "tsconfig.json", "--noEmit", "--pretty", "false"],
                    cwd=repo_dir,
                    timeout=timeout,
                    required=False,
                    reason=(
                        "Best-effort repository-wide TypeScript check. "
                        "FastGPT's package build is the required compile gate for changed app code."
                    ),
                )
            )

        changed_files = self._files_from_patch(candidate_patch)
        package_dirs = self._changed_package_dirs(repo_dir, changed_files)
        for package_dir in package_dirs:
            package_json = self._read_package_json(package_dir)
            scripts = package_json.get("scripts") if isinstance(package_json, dict) else {}
            if not isinstance(scripts, dict):
                continue
            rel = package_dir.relative_to(repo_dir).as_posix()
            if "build" in scripts:
                commands.append(
                    EvalCommand(
                        name=f"build_{self._slug(rel)}",
                        argv=[package_manager, "build"],
                        cwd=package_dir,
                        timeout=timeout,
                        reason=f"Run README/package build check for changed workspace package `{rel}`.",
                    )
                )
            if "test" in scripts:
                commands.append(
                    EvalCommand(
                        name=f"test_{self._slug(rel)}",
                        argv=[package_manager, "test"],
                        cwd=package_dir,
                        timeout=timeout,
                        reason=f"Run existing unit tests for changed workspace package `{rel}`.",
                    )
                )

        root_package = self._read_package_json(repo_dir)
        root_scripts = root_package.get("scripts") if isinstance(root_package, dict) else {}
        if isinstance(root_scripts, dict) and "test" in root_scripts and not package_dirs:
            commands.append(
                EvalCommand(
                    name="test_root",
                    argv=[package_manager, "test"],
                    cwd=repo_dir,
                    timeout=timeout,
                    reason="Run repository-level existing tests because no changed workspace package was detected.",
                )
            )

        compose_files = [file for file in changed_files if file.endswith((".yml", ".yaml")) and "docker-compose" in file]
        for rel in compose_files[:40]:
            commands.append(
                EvalCommand(
                    name=f"docker_compose_config_{self._slug(rel)}",
                    argv=["docker", "compose", "-f", rel, "config"],
                    cwd=repo_dir,
                    timeout=300,
                    required=False,
                    reason="Best-effort syntax validation for changed docker-compose files.",
                )
            )

        return commands

    def _run_command(
        self,
        command: EvalCommand,
        repo_dir: Path,
        *,
        execution_backend: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            proc = self._run_wsl_container_command(command, repo_dir, execution_backend, timeout=command.timeout)
            if proc is None:
                proc = run_cmd(command.argv, cwd=command.cwd, timeout=command.timeout)
            return {
                "name": command.name,
                "argv": command.argv,
                "cwd": command.cwd.relative_to(repo_dir).as_posix() if command.cwd != repo_dir else ".",
                "timeout": command.timeout,
                "required": command.required,
                "reason": command.reason,
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "name": command.name,
                "argv": command.argv,
                "cwd": command.cwd.relative_to(repo_dir).as_posix() if command.cwd != repo_dir else ".",
                "timeout": command.timeout,
                "required": command.required,
                "reason": command.reason,
                "returncode": -1,
                "stdout": exc.stdout or "",
                "stderr": f"Command timed out after {command.timeout}s.\n{exc.stderr or ''}",
            }
        except FileNotFoundError as exc:
            return {
                "name": command.name,
                "argv": command.argv,
                "cwd": command.cwd.relative_to(repo_dir).as_posix() if command.cwd != repo_dir else ".",
                "timeout": command.timeout,
                "required": command.required,
                "reason": command.reason,
                "returncode": 127,
                "stdout": "",
                "stderr": str(exc),
            }

    def _write_eval_script(
        self,
        path: Path,
        commands: list[EvalCommand],
        repo_dir: Path,
        *,
        execution_backend: dict[str, Any] | None = None,
    ) -> None:
        if execution_backend and execution_backend.get("docker_backend") == "wsl":
            self._write_wsl_container_eval_script(path, commands, repo_dir, execution_backend)
            return
        lines = ["#!/usr/bin/env bash", "set -u", ""]
        for command in commands:
            cwd = command.cwd.as_posix()
            argv = " ".join(_shell_quote(part) for part in command.argv)
            lines.extend(
                [
                    f"echo '==> {command.name}'",
                    f"cd {_shell_quote(cwd)}",
                    argv,
                    "",
                ]
            )
        write_text(path, "\n".join(lines).rstrip() + "\n")

    def _write_wsl_container_eval_script(
        self,
        path: Path,
        commands: list[EvalCommand],
        repo_dir: Path,
        execution_backend: dict[str, Any],
    ) -> None:
        workspace_wsl = str(execution_backend.get("workspace_wsl_path") or "").strip()
        image = str(execution_backend.get("image") or "").strip()
        distro = str(execution_backend.get("wsl_distro") or "Ubuntu-22.04").strip()
        pnpm_spec = self._pnpm_spec(repo_dir)
        lines = [
            "#!/usr/bin/env bash",
            "set -u",
            "",
            f"# Run this script inside WSL distro: {distro}",
            f"workspace={_shell_quote(workspace_wsl)}",
            f"image={_shell_quote(image)}",
            "",
        ]
        for command in commands:
            rel_cwd = "." if command.cwd == repo_dir else command.cwd.relative_to(repo_dir).as_posix()
            container_cwd = "/workspace" if rel_cwd == "." else f"/workspace/{rel_cwd}"
            shell_script = "\n".join(
                [
                    "set -eu",
                    "git config --global --add safe.directory /workspace",
                    _pnpm_setup_shell(pnpm_spec),
                    f"cd {_shell_quote(container_cwd)}",
                    "exec " + " ".join(_shell_quote(part) for part in _container_argv(command.argv)),
                ]
            )
            lines.extend(
                [
                    f"echo '==> {command.name}'",
                    "docker run --rm \\",
                    "  -e CI=true \\",
                    "  -e NODE_OPTIONS=--max-old-space-size=4096 \\",
                    '  -v "$workspace:/workspace:rw" \\',
                    "  -w /workspace \\",
                    "  --entrypoint sh \\",
                    '  "$image" \\',
                    f"  -lc {_shell_quote(shell_script)}",
                    "",
                ]
            )
        write_text(path, "\n".join(lines).rstrip() + "\n")

    def _write_eval_plan(self, path: Path, case: FeatureCase, commands: list[EvalCommand]) -> None:
        command_text = "\n".join(
            f"- `{command.name}` in `{command.cwd}`: `{' '.join(command.argv)}`\n  Reason: {command.reason}"
            for command in commands
        )
        content = f"""# Final Evaluation Plan

## Case

- Case ID: `{case.case_id}`
- Repository: `{case.input.repo}`
- Base commit: `{case.input.base_commit}`
- PR title: {case.input.pr_title_raw}

## Scope

This final evaluator runs deterministic checks against the modified workspace after the implementation agent finishes.
It records the candidate patch, the baseline patch, command outputs, and a final pass/fail report.
It does not start OpenHands and does not generate repair prompts.

## Commands

{command_text or "- No executable commands were inferred."}
"""
        write_text(path, content)

    def _render_test_output(self, results: list[dict[str, Any]]) -> str:
        chunks = []
        for item in results:
            chunks.append(
                "\n".join(
                    [
                        f"==> {item['name']}",
                        f"$ {' '.join(item['argv'])}",
                        f"cwd: {item['cwd']}",
                        f"required: {item['required']}",
                        f"returncode: {item['returncode']}",
                        "",
                        "STDOUT:",
                        item.get("stdout") or "",
                        "",
                        "STDERR:",
                        item.get("stderr") or "",
                        "",
                    ]
                )
            )
        return "\n".join(chunks)

    def _command_to_json(self, command: EvalCommand, repo_dir: Path) -> dict[str, Any]:
        return {
            "name": command.name,
            "argv": command.argv,
            "cwd": command.cwd.relative_to(repo_dir).as_posix() if command.cwd != repo_dir else ".",
            "timeout": command.timeout,
            "required": command.required,
            "reason": command.reason,
        }

    def _run_wsl_container_command(
        self,
        command: EvalCommand,
        repo_dir: Path,
        execution_backend: dict[str, Any] | None,
        *,
        timeout: int,
    ) -> subprocess.CompletedProcess[str] | None:
        if not execution_backend or execution_backend.get("docker_backend") != "wsl":
            return None
        workspace_wsl = str(execution_backend.get("workspace_wsl_path") or "").strip()
        image = str(execution_backend.get("image") or "").strip()
        distro = str(execution_backend.get("wsl_distro") or "Ubuntu-22.04").strip()
        if not workspace_wsl or not image:
            return None

        rel_cwd = "." if command.cwd == repo_dir else command.cwd.relative_to(repo_dir).as_posix()
        container_cwd = "/workspace" if rel_cwd == "." else f"/workspace/{rel_cwd}"
        pnpm_spec = self._pnpm_spec(repo_dir)
        shell_script = "\n".join(
            [
                "set -eu",
                "git config --global --add safe.directory /workspace",
                _pnpm_setup_shell(pnpm_spec),
                f"cd {_shell_quote(container_cwd)}",
                "exec " + " ".join(_shell_quote(part) for part in _container_argv(command.argv)),
            ]
        )
        return run_cmd(
            [
                "wsl",
                "-d",
                distro,
                "--",
                "docker",
                "run",
                "--rm",
                "-e",
                "CI=true",
                "-e",
                "NODE_OPTIONS=--max-old-space-size=4096",
                "-v",
                f"{workspace_wsl}:/workspace:rw",
                "-w",
                "/workspace",
                "--entrypoint",
                "sh",
                image,
                "-lc",
                shell_script,
            ],
            timeout=timeout,
        )

    def _package_manager(self, repo_dir: Path) -> str | None:
        package_json = self._read_package_json(repo_dir)
        declared = str(package_json.get("packageManager", "")) if isinstance(package_json, dict) else ""
        if declared.startswith("pnpm@") or (repo_dir / "pnpm-lock.yaml").exists():
            return "pnpm"
        if declared.startswith("yarn@") or (repo_dir / "yarn.lock").exists():
            return "yarn"
        if declared.startswith("npm@") or (repo_dir / "package-lock.json").exists() or (repo_dir / "package.json").exists():
            return "npm"
        return None

    def _pnpm_spec(self, repo_dir: Path) -> str:
        package_json = self._read_package_json(repo_dir)
        if not isinstance(package_json, dict):
            return ""
        declared = str(package_json.get("packageManager", "") or "").strip()
        if declared.startswith("pnpm@"):
            return declared.removeprefix("pnpm@")
        engines = package_json.get("engines")
        pnpm_engine = str(engines.get("pnpm", "") if isinstance(engines, dict) else "").strip()
        match = re.search(r"\d+", pnpm_engine)
        if not match:
            return ""
        return {"8": "8.15.9", "9": "9.15.9", "10": "10.33.4"}.get(match.group(0), match.group(0))

    def _changed_package_dirs(self, repo_dir: Path, changed_files: list[str]) -> list[Path]:
        package_dirs: set[Path] = set()
        for rel in changed_files:
            path = repo_dir / rel
            for parent in [path.parent, *path.parent.parents]:
                if parent == repo_dir.parent:
                    break
                if (parent / "package.json").exists():
                    if parent != repo_dir:
                        package_dirs.add(parent)
                    break
        return sorted(package_dirs, key=lambda path: path.as_posix())

    def _read_package_json(self, directory: Path) -> dict[str, Any]:
        path = directory / "package.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _files_from_patch(self, patch_path: Path) -> list[str]:
        if not patch_path.exists():
            return []
        text = patch_path.read_text(encoding="utf-8", errors="replace")
        files = []
        for match in re.finditer(r"^diff --git a/(.*?) b/(.*?)$", text, re.MULTILINE):
            files.append(match.group(2).strip())
        return sorted(set(files))

    def _export_git_diff(self, repo_dir: Path, patch_path: Path) -> None:
        proc = run_cmd(["git", "diff", "--binary"], cwd=repo_dir, timeout=300)
        write_patch_text(patch_path, proc.stdout if proc.returncode == 0 else "")

    def _sha256(self, path: Path) -> str | None:
        if not path.exists():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
        return slug or "root"


def git_diff(repo_dir: Path, output_patch: Path) -> Path:
    proc = run_cmd(["git", "diff", "--binary"], cwd=repo_dir, timeout=300)
    output_patch.parent.mkdir(parents=True, exist_ok=True)
    write_patch_text(output_patch, proc.stdout if proc.returncode == 0 else "")
    return output_patch


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _pnpm_setup_shell(pnpm_spec: str) -> str:
    if not pnpm_spec:
        return 'export npm_config_store_dir="/tmp/repoaces-pnpm-store"'
    return f"""corepack prepare {_shell_quote(f"pnpm@{pnpm_spec}")} --activate
export npm_config_store_dir="/tmp/repoaces-pnpm-store" """


def _container_argv(argv: list[str]) -> list[str]:
    if argv and argv[0] == "pnpm":
        return ["corepack", "pnpm", *argv[1:]]
    return argv


def _run_root(stage_dir: Path) -> Path:
    return stage_dir.parent.parent if stage_dir.parent.name == "tasks" else stage_dir.parent
