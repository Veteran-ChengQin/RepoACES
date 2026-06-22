from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import write_stage_result
from .io import write_json, write_text
from .models import FeatureCase
from .shell import run_cmd


@dataclass(frozen=True)
class DevEnvironmentResult:
    status: str
    workspace_unc: str
    workspace_wsl_path: str
    docker_backend: str
    wsl_distro: str
    image: str
    report_path: Path
    result_path: Path
    preflight_log_path: Path
    scripts: dict[str, Path]


class DevEnvironmentPreparer:
    """Prepare a Linux-compatible development workspace for OpenHands.

    The current implementation targets FastGPT-like Node/pnpm repositories. It
    creates a WSL/ext4 workspace, fixes ownership for the OpenHands container
    user, and validates the workspace through the same agent-server image that
    OpenHands will use later.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def prepare_wsl_fastgpt(
        self,
        *,
        case: FeatureCase,
        run_id: str,
        source_workspace: Path,
        output_dir: Path,
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
    ) -> DevEnvironmentResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        extra_commands = extra_commands or []

        wsl_root = wsl_root or os.getenv("REPOACES_WSL_WORKSPACES_ROOT") or self._default_wsl_root(wsl_distro)
        repo_name = case.input.repo.split("/")[-1]
        workspace_wsl = f"{wsl_root.rstrip('/')}/{_safe_path_part(run_id)}/{repo_name}"
        workspace_unc = self._wsl_unc_path(wsl_distro, workspace_wsl)
        source_wsl = self._windows_path_to_wsl(source_workspace, wsl_distro)
        output_wsl = self._windows_path_to_wsl(output_dir, wsl_distro)

        scripts = {
            "prepare_workspace": output_dir / "prepare_wsl_workspace.sh",
            "chown_workspace": output_dir / "chown_wsl_workspace_for_openhands.sh",
            "preflight": output_dir / "preflight.sh",
            "run_preflight": output_dir / "run_preflight_container.sh",
        }
        self._write_prepare_workspace_script(
            scripts["prepare_workspace"],
            workspace_wsl=workspace_wsl,
            source_wsl=source_wsl,
            repo_url=case.input.repo_url,
            base_commit=case.input.base_commit,
            pr_number=case.input.pr_number,
            image=image,
            force=force,
        )
        self._write_chown_script(
            scripts["chown_workspace"],
            workspace_wsl=workspace_wsl,
            image=image,
            container_uid=container_uid,
            container_gid=container_gid,
        )
        self._write_preflight_script(
            scripts["preflight"],
            run_install=run_install,
            run_smoke_tests=run_smoke_tests,
            extra_commands=extra_commands,
        )
        self._write_run_preflight_script(
            scripts["run_preflight"],
            workspace_wsl=workspace_wsl,
            output_wsl=output_wsl,
            image=image,
        )

        prepare_proc = self._run_wsl_script(wsl_distro, scripts["prepare_workspace"], timeout=timeout)
        prepare_log = output_dir / "prepare_wsl_workspace.log"
        write_text(prepare_log, _render_process_log(scripts["prepare_workspace"], prepare_proc))
        if prepare_proc.returncode != 0:
            raise RuntimeError(f"WSL workspace preparation failed. See {prepare_log}")

        chown_proc = self._run_wsl_script(wsl_distro, scripts["chown_workspace"], timeout=timeout)
        chown_log = output_dir / "chown_wsl_workspace_for_openhands.log"
        write_text(chown_log, _render_process_log(scripts["chown_workspace"], chown_proc))
        if chown_proc.returncode != 0:
            raise RuntimeError(f"WSL workspace ownership fix failed. See {chown_log}")

        preflight_proc = self._run_wsl_script(wsl_distro, scripts["run_preflight"], timeout=timeout)
        preflight_log = output_dir / "preflight.log"
        write_text(preflight_log, _render_process_log(scripts["run_preflight"], preflight_proc))

        git_status_proc = run_cmd(
            [
                "wsl",
                "-d",
                wsl_distro,
                "--",
                "bash",
                "-lc",
                f"git -C {shlex.quote(workspace_wsl)} status --short | head -120",
            ],
            timeout=120,
        )
        git_status_path = output_dir / "git-status-after-preflight.txt"
        write_text(git_status_path, git_status_proc.stdout + git_status_proc.stderr)

        status = "passed" if preflight_proc.returncode == 0 else "failed"
        report = {
            "status": status,
            "case_id": case.case_id,
            "repo": case.input.repo,
            "base_commit": case.input.base_commit,
            "source_workspace": str(source_workspace),
            "workspace_unc": workspace_unc,
            "workspace_wsl_path": workspace_wsl,
            "docker_backend": "wsl",
            "wsl_distro": wsl_distro,
            "wsl_root": wsl_root,
            "image": image,
            "container_uid": container_uid,
            "container_gid": container_gid,
            "run_install": run_install,
            "run_smoke_tests": run_smoke_tests,
            "extra_commands": extra_commands,
            "scripts": {key: str(path) for key, path in scripts.items()},
            "logs": {
                "prepare_workspace": str(prepare_log),
                "chown_workspace": str(chown_log),
                "preflight": str(preflight_log),
                "git_status_after_preflight": str(git_status_path),
            },
            "commands": {
                "prepare_workspace_returncode": prepare_proc.returncode,
                "chown_workspace_returncode": chown_proc.returncode,
                "preflight_returncode": preflight_proc.returncode,
            },
        }
        report_path = output_dir / "dev_environment_report.json"
        write_json(report_path, report)
        result_path = write_stage_result(
            run_root=_run_root(output_dir),
            stage_dir=output_dir,
            stage="prepare-dev-env",
            role="dev_environment",
            status=status,
            completed=True,
            result={
                "workspace_unc": workspace_unc,
                "workspace_wsl_path": workspace_wsl,
                "docker_backend": "wsl",
                "wsl_distro": wsl_distro,
                "image": image,
                "dev_environment_report": report_path,
                "preflight_log": preflight_log,
                "git_status_after_preflight": git_status_path,
                "passed": status == "passed",
            },
        )
        return DevEnvironmentResult(
            status=status,
            workspace_unc=workspace_unc,
            workspace_wsl_path=workspace_wsl,
            docker_backend="wsl",
            wsl_distro=wsl_distro,
            image=image,
            report_path=report_path,
            result_path=result_path,
            preflight_log_path=preflight_log,
            scripts=scripts,
        )

    def _default_wsl_root(self, distro: str) -> str:
        proc = run_cmd(["wsl", "-d", distro, "--", "bash", "-lc", 'printf "%s" "$HOME"'], timeout=60)
        if proc.returncode != 0 or not proc.stdout.strip():
            raise RuntimeError(f"Unable to determine WSL home for distro {distro}: {proc.stderr}")
        return f"{proc.stdout.strip().rstrip('/')}/repoaces-workspaces"

    def _windows_path_to_wsl(self, path: Path, distro: str) -> str:
        resolved = str(path.resolve()).replace("\\", "/")
        proc = run_cmd(["wsl", "-d", distro, "--", "wslpath", "-a", resolved], timeout=60)
        if proc.returncode != 0 or not proc.stdout.strip():
            raise RuntimeError(f"Unable to convert Windows path to WSL path: {path}\n{proc.stderr}")
        return proc.stdout.strip()

    def _run_wsl_script(self, distro: str, script: Path, *, timeout: int) -> Any:
        script_wsl = self._windows_path_to_wsl(script, distro)
        return run_cmd(["wsl", "-d", distro, "--", "bash", script_wsl], timeout=timeout)

    def _write_prepare_workspace_script(
        self,
        path: Path,
        *,
        workspace_wsl: str,
        source_wsl: str,
        repo_url: str,
        base_commit: str,
        pr_number: int,
        image: str,
        force: bool,
    ) -> None:
        force_value = "1" if force else "0"
        script = f"""#!/usr/bin/env bash
set -euo pipefail
workspace={shlex.quote(workspace_wsl)}
workspace_parent="$(dirname "$workspace")"
source_workspace={shlex.quote(source_wsl)}
repo_url={shlex.quote(repo_url)}
base_commit={shlex.quote(base_commit)}
pr_number={shlex.quote(str(pr_number))}
image={shlex.quote(image)}
force={force_value}

case "$workspace" in
  "$HOME"/repoaces-workspaces/*|/home/*/repoaces-workspaces/*) ;;
  *) echo "Refusing to manage unexpected WSL workspace: $workspace" >&2; exit 1 ;;
esac

if [ "$force" = "1" ] && [ -e "$workspace" ]; then
  workspace_name="$(basename "$workspace")"
  docker run --rm --user root \\
    -e WORKSPACE_NAME="$workspace_name" \\
    -v "$workspace_parent:/repoaces-parent:rw" \\
    --entrypoint sh \\
    "$image" \\
    -lc 'rm -rf "/repoaces-parent/$WORKSPACE_NAME"' || rm -rf "$workspace"
fi

mkdir -p "$workspace_parent"
if [ ! -d "$workspace/.git" ]; then
  if ! git clone --no-hardlinks "$source_workspace" "$workspace"; then
    rm -rf "$workspace"
    git clone --no-checkout "$repo_url" "$workspace"
  fi
fi

git -C "$workspace" remote set-url origin "$repo_url"

checkout_base() {{
  git -C "$workspace" checkout --force "$base_commit" &&
  git -C "$workspace" reset --hard "$base_commit"
}}

if ! checkout_base; then
  if [ -n "$pr_number" ] && [ "$pr_number" != "0" ]; then
    git -C "$workspace" fetch origin "pull/${{pr_number}}/head:refs/remotes/origin/pr-${{pr_number}}-head" --no-tags
    checkout_base
  else
    echo "Unable to checkout base commit and no PR number was provided: $base_commit" >&2
    exit 1
  fi
fi
git -C "$workspace" clean -fdx
git -C "$workspace" rev-parse HEAD
"""
        _write_lf(path, script)

    def _write_chown_script(
        self,
        path: Path,
        *,
        workspace_wsl: str,
        image: str,
        container_uid: int,
        container_gid: int,
    ) -> None:
        script = f"""#!/usr/bin/env bash
set -euo pipefail
workspace={shlex.quote(workspace_wsl)}
image={shlex.quote(image)}
uid_gid={shlex.quote(f"{container_uid}:{container_gid}")}

docker run --rm --user root \\
  -v "$workspace:/workspace:rw" \\
  --entrypoint sh \\
  "$image" \\
  -lc "chown -R $uid_gid /workspace"

docker run --rm \\
  -v "$workspace:/workspace:rw" \\
  -w /workspace \\
  --entrypoint sh \\
  "$image" \\
  -lc "whoami && stat -c '%u:%g %A %n' /workspace"
"""
        _write_lf(path, script)

    def _write_preflight_script(
        self,
        path: Path,
        *,
        run_install: bool,
        run_smoke_tests: bool,
        extra_commands: list[str],
    ) -> None:
        install_block = (
            """
if [ -f pnpm-lock.yaml ]; then
  run_step pnpm_install run_pnpm install --frozen-lockfile
fi
"""
            if run_install
            else ""
        )
        smoke_block = (
            """
if node -e "const s=require('./package.json').scripts||{}; process.exit(s['build:sdks'] ? 0 : 1)" 2>/dev/null; then
  run_step build_sdks run_pnpm build:sdks
fi

if node -e "const s=require('./package.json').scripts||{}; process.exit(s['test:repo'] ? 0 : 1)" 2>/dev/null; then
  run_step test_repo run_pnpm test:repo
fi
"""
            if run_smoke_tests
            else ""
        )
        extra_block = "\n".join(
            f"run_step extra_{index:02d} sh -lc {shlex.quote(command)}" for index, command in enumerate(extra_commands, start=1)
        )
        script = f"""#!/usr/bin/env sh
set -eu

run_step() {{
  name="$1"
  shift
  echo ""
  echo "===== STEP: $name ====="
  date -Iseconds
  "$@"
  echo "===== STEP DONE: $name ====="
  date -Iseconds
}}

run_step safe_directory git config --global --add safe.directory /workspace
run_step git_worktree_config sh -lc 'git config core.fileMode false && mkdir -p .git/info && grep -qxF ".pnpm-store/" .git/info/exclude 2>/dev/null || echo ".pnpm-store/" >> .git/info/exclude'

detect_pnpm_spec() {{
  node -e 'const p=require("./package.json"); const e=((p.engines&&p.engines.pnpm)||"").trim(); const pinned={{"8":"8.15.9","9":"9.15.9","10":"10.33.4"}}; let s=""; if (p.packageManager&&p.packageManager.startsWith("pnpm@")) s=p.packageManager.slice(5); else {{ const m=e.match(/\\d+/); if (m) s=pinned[m[0]]||m[0]; }} process.stdout.write(s);' 2>/dev/null || true
}}

PNPM_SPEC="$(detect_pnpm_spec)"
if [ -n "$PNPM_SPEC" ] && command -v corepack >/dev/null 2>&1; then
  run_step pnpm_prepare corepack prepare "pnpm@$PNPM_SPEC" --activate
  PNPM_SHIM_DIR="${{TMPDIR:-/tmp}}/repoaces-pnpm-bin"
  mkdir -p "$PNPM_SHIM_DIR"
  cat > "$PNPM_SHIM_DIR/pnpm" <<'PNPM_SHIM'
#!/usr/bin/env sh
exec corepack pnpm "$@"
PNPM_SHIM
  chmod +x "$PNPM_SHIM_DIR/pnpm"
  export PATH="$PNPM_SHIM_DIR:$PATH"
fi
export npm_config_store_dir="${{TMPDIR:-/tmp}}/repoaces-pnpm-store"

run_pnpm() {{
  if [ -n "$PNPM_SPEC" ] && command -v corepack >/dev/null 2>&1; then
    corepack pnpm "$@"
  else
    pnpm "$@"
  fi
}}

run_step repo_head git rev-parse HEAD
run_step toolchain sh -lc 'node -v && npm -v && corepack --version && git --version && rg --version | head -1'
run_step pnpm_version run_pnpm -v

if [ -d ./scripts ]; then
  run_step chmod_scripts chmod -R +x ./scripts/
fi
{install_block}
{smoke_block}
{extra_block}
"""
        _write_lf(path, script)

    def _write_run_preflight_script(
        self,
        path: Path,
        *,
        workspace_wsl: str,
        output_wsl: str,
        image: str,
    ) -> None:
        script = f"""#!/usr/bin/env bash
set -euo pipefail
workspace={shlex.quote(workspace_wsl)}
output_dir={shlex.quote(output_wsl)}
image={shlex.quote(image)}

docker run --rm \\
  -e CI=true \\
  -v "$output_dir:/testbed:rw" \\
  -v "$workspace:/workspace:rw" \\
  -w /workspace \\
  --entrypoint sh \\
  "$image" \\
  /testbed/preflight.sh
"""
        _write_lf(path, script)

    def _wsl_unc_path(self, distro: str, wsl_path: str) -> str:
        suffix = wsl_path.lstrip("/").replace("/", "\\")
        return f"\\\\wsl.localhost\\{distro}\\{suffix}"


def _safe_path_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    if not cleaned:
        raise ValueError("Path component must not be empty")
    return cleaned


def _write_lf(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    path.write_bytes(normalized.encode("utf-8"))


def _render_process_log(script_path: Path, proc: Any) -> str:
    return (
        f"$ bash {script_path}\n"
        f"exit_code={proc.returncode}\n\n"
        f"STDOUT:\n{proc.stdout}\n\n"
        f"STDERR:\n{proc.stderr}\n"
    )


def _run_root(stage_dir: Path) -> Path:
    return stage_dir.parent.parent if stage_dir.parent.name == "tasks" else stage_dir.parent
