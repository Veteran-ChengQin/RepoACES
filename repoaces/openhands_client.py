from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .io import write_json, write_patch_text, write_text
from .shell import require_ok, run_cmd


@dataclass(frozen=True)
class OpenHandsConfig:
    openhands_image: str = "docker.openhands.dev/openhands/openhands:1.8"
    agent_server_image_repository: str = "ghcr.io/openhands/agent-server"
    agent_server_image_tag: str = "1.26.0-python"
    openhands_home_template: Path | None = None
    model: str = "gpt-5.4"
    health_timeout_seconds: int = 180
    host_port: int | None = None
    docker_backend: str = "windows"
    wsl_distro: str = "Ubuntu-22.04"

    @classmethod
    def from_env(cls, project_root: Path) -> "OpenHandsConfig":
        template = Path(os.getenv("REPOACES_OPENHANDS_HOME_TEMPLATE", str(project_root / ".openhands-home")))
        return cls(
            openhands_image=os.getenv("REPOACES_OPENHANDS_IMAGE", cls.openhands_image),
            agent_server_image_repository=os.getenv(
                "REPOACES_AGENT_SERVER_IMAGE_REPOSITORY", cls.agent_server_image_repository
            ),
            agent_server_image_tag=os.getenv("REPOACES_AGENT_SERVER_IMAGE_TAG", cls.agent_server_image_tag),
            openhands_home_template=template,
            model=os.getenv("REPOACES_OPENHANDS_MODEL", cls.model),
            health_timeout_seconds=int(os.getenv("REPOACES_OPENHANDS_HEALTH_TIMEOUT", "180")),
            host_port=int(os.environ["REPOACES_OPENHANDS_PORT"]) if os.getenv("REPOACES_OPENHANDS_PORT") else None,
            docker_backend=os.getenv("REPOACES_DOCKER_BACKEND", cls.docker_backend),
            wsl_distro=os.getenv("REPOACES_WSL_DISTRO", cls.wsl_distro),
        )


def http_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 60) -> Any:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else None


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def docker_mount_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


class OpenHandsRuntime:
    """Run-specific OpenHands Docker server and app-server REST adapter."""

    def __init__(self, config: OpenHandsConfig, run_root: Path) -> None:
        self.config = config
        self.run_root = run_root

    def start_server(
        self,
        *,
        run_id: str,
        repo_dir: Path,
        sandbox_repo_path: str,
        repo_mount_path: str | None = None,
        extra_sandbox_volumes: list[tuple[Path, str, str]] | None = None,
    ) -> dict[str, Any]:
        port = self.config.host_port or find_free_port()
        container_name = f"repoaces-oh-{run_id}"[:120]
        openhands_home = self._copy_openhands_home(run_id)

        repo_mount = repo_mount_path or self._docker_mount_path(repo_dir)
        home_mount = self._docker_mount_path(openhands_home)
        sandbox_volumes = [f"{repo_mount}:{sandbox_repo_path}:rw"]
        for host_path, container_path, mode in extra_sandbox_volumes or []:
            mount = self._docker_mount_path(host_path)
            sandbox_volumes.append(f"{mount}:{container_path}:{mode}")
        sandbox_volumes_value = ",".join(sandbox_volumes)

        self._run_docker(["rm", "-f", container_name], timeout=60)
        cmd = [
            "run",
            "-d",
            "-e",
            f"AGENT_SERVER_IMAGE_REPOSITORY={self.config.agent_server_image_repository}",
            "-e",
            f"AGENT_SERVER_IMAGE_TAG={self.config.agent_server_image_tag}",
            "-e",
            "LOG_ALL_EVENTS=true",
            "-e",
            f"SANDBOX_VOLUMES={sandbox_volumes_value}",
            "-v",
            "/var/run/docker.sock:/var/run/docker.sock",
            "-v",
            f"{home_mount}:/.openhands",
            "-p",
            f"{port}:3000",
            "--add-host",
            "host.docker.internal:host-gateway",
            "--name",
            container_name,
            self.config.openhands_image,
        ]
        proc = self._run_docker(cmd, timeout=300)
        require_ok(proc, "docker run OpenHands")

        base_url = f"http://127.0.0.1:{port}"
        self._wait_for_health(base_url)
        return {
            "container": container_name,
            "port": port,
            "base_url": base_url,
            "sandbox_volumes": sandbox_volumes_value,
            "openhands_home": str(openhands_home),
            "docker_backend": self.config.docker_backend,
            "wsl_distro": self.config.wsl_distro,
            "repo_mount": repo_mount,
        }

    def start_conversation(
        self,
        *,
        base_url: str,
        run_id: str,
        instruction: str,
        model: str | None = None,
        auto_run: bool = True,
        wait_start_seconds: int = 180,
    ) -> dict[str, Any]:
        payload = {
            "initial_message": {
                "role": "user",
                "content": [{"type": "text", "text": instruction}],
                "run": auto_run,
            },
            "title": f"RepoACES {run_id}",
            "trigger": "openhands_api",
            "llm_model": model or self.config.model,
            "agent_type": "default",
        }
        task = http_json("POST", f"{base_url}/api/v1/app-conversations", payload, timeout=60)
        start_task_id = task["id"]
        latest = task
        deadline = time.time() + wait_start_seconds
        while time.time() < deadline:
            tasks = http_json("GET", f"{base_url}/api/v1/app-conversations/start-tasks?ids={start_task_id}", timeout=60)
            latest = tasks[0]
            if latest.get("status") in {"READY", "ERROR", "FAILED", "STOPPED"}:
                break
            time.sleep(3)
        return {
            "start_task_id": start_task_id,
            "start_task_status": latest.get("status"),
            "conversation_id": latest.get("app_conversation_id"),
            "sandbox_id": latest.get("sandbox_id"),
            "agent_server_url": latest.get("agent_server_url"),
            "detail": latest.get("detail"),
        }

    def get_conversation(self, *, base_url: str, conversation_id: str, include_agent_stats: bool = True) -> dict[str, Any] | None:
        data = http_json("GET", f"{base_url}/api/v1/app-conversations?ids={conversation_id}", timeout=60)
        if not data:
            return None
        conv = data[0]
        if not isinstance(conv, dict):
            return None
        session_api_key = conv.pop("session_api_key", None)
        conversation_url = conv.get("conversation_url")
        if include_agent_stats and session_api_key and conversation_url:
            req = Request(str(conversation_url), headers={"X-Session-API-Key": str(session_api_key)})
            try:
                with urlopen(req, timeout=60) as resp:
                    agent_conv = json.loads(resp.read().decode("utf-8", errors="replace"))
                conv["execution_status"] = agent_conv.get("execution_status") or conv.get("execution_status")
                conv["title"] = agent_conv.get("title") or conv.get("title")
                if agent_conv.get("stats"):
                    conv["agent_server_stats"] = agent_conv.get("stats")
            except Exception:
                pass
        return conv

    def export_patch(self, *, repo_dir: Path, patch_path: Path, repo_git_path: str | None = None) -> dict[str, Any]:
        status = ""
        mark_untracked: dict[str, Any] | None = None
        if self.config.docker_backend == "wsl" and repo_git_path:
            mark_untracked = self._mark_untracked_intent_to_add_wsl(repo_git_path)
            status_proc = self._run_git_in_agent_container(
                repo_git_path,
                "git status --short",
                timeout=120,
            )
            status = status_proc.stdout if status_proc.returncode == 0 else ""
            proc = self._run_git_in_agent_container(repo_git_path, "git diff --binary HEAD", timeout=300)
        else:
            self._mark_untracked_intent_to_add_local(repo_dir)
            status_proc = run_cmd(
                ["git", "-c", f"safe.directory={_git_safe_directory(repo_dir)}", "status", "--short"],
                cwd=repo_dir,
                timeout=120,
            )
            status = status_proc.stdout if status_proc.returncode == 0 else ""
            proc = run_cmd(
                ["git", "-c", f"safe.directory={_git_safe_directory(repo_dir)}", "diff", "--binary", "HEAD"],
                cwd=repo_dir,
                timeout=300,
            )
        patch = proc.stdout if proc.returncode == 0 else ""
        write_patch_text(patch_path, patch)
        result: dict[str, Any] = {
            "patch_path": str(patch_path),
            "patch_diff_chars": len(patch),
            "patch_line_count": len(patch.splitlines()),
            "export_returncode": proc.returncode,
            "export_stderr": proc.stderr[-4000:],
            "git_status_short": status[-4000:],
        }
        if mark_untracked is not None:
            result["mark_untracked"] = mark_untracked
        return result

    def _run_git_in_agent_container(self, repo_git_path: str, script: str, *, timeout: int) -> Any:
        image = f"{self.config.agent_server_image_repository}:{self.config.agent_server_image_tag}"
        safe_script = f"git config --global --add safe.directory /workspace && {script}"
        return run_cmd(
            [
                "wsl",
                "-d",
                self.config.wsl_distro,
                "--",
                "docker",
                "run",
                "--rm",
                "-v",
                f"{repo_git_path}:/workspace:rw",
                "-w",
                "/workspace",
                "--entrypoint",
                "sh",
                image,
                "-lc",
                safe_script,
            ],
            timeout=timeout,
        )

    def _mark_untracked_intent_to_add_wsl(self, repo_git_path: str) -> dict[str, Any]:
        proc = self._run_git_in_agent_container(
            repo_git_path,
            "git ls-files --others --exclude-standard -z",
            timeout=120,
        )
        if proc.returncode != 0:
            return {
                "returncode": proc.returncode,
                "stderr": proc.stderr[-4000:],
                "untracked_count": 0,
                "added_intent_count": 0,
            }
        files = _patchable_untracked_files(proc.stdout.split("\0"))
        if files:
            quoted_files = " ".join(shlex.quote(path) for path in files)
            add_proc = self._run_git_in_agent_container(
                repo_git_path,
                f"git add -N -- {quoted_files}",
                timeout=120,
            )
            return {
                "returncode": add_proc.returncode,
                "stderr": add_proc.stderr[-4000:],
                "untracked_count": len(files),
                "added_intent_count": len(files) if add_proc.returncode == 0 else 0,
            }
        return {
            "returncode": 0,
            "stderr": "",
            "untracked_count": 0,
            "added_intent_count": 0,
        }

    def _mark_untracked_intent_to_add_local(self, repo_dir: Path) -> None:
        proc = run_cmd(
            [
                "git",
                "-c",
                f"safe.directory={_git_safe_directory(repo_dir)}",
                "-C",
                str(repo_dir),
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            timeout=120,
        )
        if proc.returncode != 0:
            return
        files = _patchable_untracked_files(proc.stdout.split("\0"))
        if files:
            run_cmd(
                [
                    "git",
                    "-c",
                    f"safe.directory={_git_safe_directory(repo_dir)}",
                    "-C",
                    str(repo_dir),
                    "add",
                    "-N",
                    "--",
                    *files,
                ],
                timeout=120,
            )

    def write_runtime_state(self, path: Path, state: dict[str, Any]) -> None:
        write_json(path, state)

    def cleanup_runtime_containers(self, runtime_state: dict[str, Any]) -> dict[str, Any]:
        """Remove OpenHands containers recorded for a completed task.

        The cleanup is best-effort: artifact export should remain useful even if
        Docker is already stopped or a container was removed manually.
        """
        openhands = runtime_state.get("openhands") if isinstance(runtime_state.get("openhands"), dict) else {}
        conversation = runtime_state.get("conversation") if isinstance(runtime_state.get("conversation"), dict) else {}
        candidates = [
            ("openhands", openhands.get("container")),
            ("sandbox", conversation.get("sandbox_id")),
        ]
        seen: set[str] = set()
        results = []
        for role, raw_name in candidates:
            name = str(raw_name or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            proc = self._run_docker(["rm", "-f", name], timeout=120)
            already_absent = "No such container" in f"{proc.stdout}\n{proc.stderr}"
            removed = proc.returncode == 0 or already_absent
            results.append(
                {
                    "role": role,
                    "container": name,
                    "returncode": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "removed": removed,
                    "already_absent": already_absent,
                }
            )
        return {
            "enabled": True,
            "attempted": bool(results),
            "results": results,
            "all_removed": all(item["removed"] for item in results) if results else True,
        }

    def copy_from_container(self, *, container: str, source_path: str, destination: Path) -> dict[str, Any]:
        destination.mkdir(parents=True, exist_ok=True)
        if self.config.docker_backend == "wsl":
            dest = self._windows_path_to_wsl(destination)
        else:
            dest = str(destination.resolve())
        proc = self._run_docker(["cp", f"{container}:{source_path.rstrip('/')}/.", dest], timeout=120)
        return {
            "container": container,
            "source_path": source_path,
            "destination": str(destination),
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
            "copied": proc.returncode == 0,
        }

    def export_conversation_artifacts(
        self,
        *,
        openhands_home: Path,
        conversation_id: str | None,
        artifact_dir: Path,
    ) -> dict[str, Any]:
        source, strategy = self._find_conversation_dir(openhands_home, conversation_id)
        if not source:
            trajectory_path = artifact_dir / "trajectory.json"
            write_json(
                trajectory_path,
                {
                    "format": "repoaces-openhands-event-trajectory",
                    "source_conversation_dir": None,
                    "match_strategy": "not_found",
                    "event_count": 0,
                    "events": [],
                },
            )
            return {
                "conversation_dir": None,
                "trajectory_path": str(trajectory_path),
                "event_count": 0,
                "match_strategy": "not_found",
            }

        destination = artifact_dir / "conversation"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination, ignore=self._ignore_runtime_locks)
        trajectory_path, event_count = self._write_trajectory(destination, artifact_dir / "trajectory.json", strategy)
        return {
            "source_conversation_dir": str(source),
            "conversation_dir": str(destination),
            "trajectory_path": str(trajectory_path),
            "event_count": event_count,
            "match_strategy": strategy,
        }

    def _copy_openhands_home(self, run_id: str) -> Path:
        target = self.run_root / run_id / "openhands-home"
        if target.exists():
            return target
        target.parent.mkdir(parents=True, exist_ok=True)

        def ignore(_dir: str, names: list[str]) -> set[str]:
            ignored = {".settings.lock", ".workspaces.lock", "openhands.db", "v1_conversations", "agent-canvas"}
            return {name for name in names if name in ignored}

        template = self.config.openhands_home_template
        if template and template.exists():
            shutil.copytree(template, target, ignore=ignore)
        else:
            target.mkdir(parents=True, exist_ok=True)
        return target

    def _find_conversation_dir(self, openhands_home: Path, conversation_id: str | None) -> tuple[Path | None, str]:
        roots = [
            openhands_home / "agent-canvas" / "conversations",
            openhands_home / "v1_conversations",
        ]
        if conversation_id:
            for root in roots:
                exact = root / conversation_id
                if exact.exists() and exact.is_dir():
                    return exact, "exact_conversation_id"

        candidates: list[Path] = []
        for root in roots:
            if root.exists():
                candidates.extend(path for path in root.iterdir() if path.is_dir())
        if not candidates:
            return None, "not_found"

        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return candidates[0], "latest_conversation_fallback"

    def _write_trajectory(self, conversation_dir: Path, output_path: Path, match_strategy: str) -> tuple[Path, int]:
        event_files = self._conversation_event_files(conversation_dir)
        events = []
        for event_path in event_files:
            try:
                event: Any = json.loads(event_path.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError:
                event = {"parse_error": "json_decode_error", "raw": event_path.read_text(encoding="utf-8", errors="replace")}
            events.append({"file": event_path.name, "event": event})

        write_json(
            output_path,
            {
                "format": "repoaces-openhands-event-trajectory",
                "source_conversation_dir": str(conversation_dir),
                "match_strategy": match_strategy,
                "event_count": len(events),
                "events": events,
            },
        )
        return output_path, len(events)

    def _conversation_event_files(self, conversation_dir: Path) -> list[Path]:
        event_dir = conversation_dir / "events"
        if event_dir.exists():
            return sorted(
                event_dir.glob("event-*.json"),
                key=lambda path: int(match.group(1)) if (match := re.search(r"event-(\d+)-", path.name)) else -1,
            )
        return sorted(conversation_dir.glob("*.json"), key=lambda path: (path.stat().st_mtime, path.name))

    def _ignore_runtime_locks(self, _dir: str, names: list[str]) -> set[str]:
        return {name for name in names if name.endswith(".lock")}

    def _wait_for_health(self, base_url: str) -> None:
        deadline = time.time() + self.config.health_timeout_seconds
        last_error = ""
        while time.time() < deadline:
            try:
                with urlopen(f"{base_url}/health", timeout=5) as resp:
                    if resp.status == 200:
                        return
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
            time.sleep(2)
        raise TimeoutError(f"OpenHands server did not become healthy: {last_error}")

    def _run_docker(self, args: list[str], *, timeout: int) -> Any:
        if self.config.docker_backend == "wsl":
            return run_cmd(["wsl", "-d", self.config.wsl_distro, "--", "docker", *args], timeout=timeout)
        return run_cmd(["docker", *args], timeout=timeout)

    def _docker_mount_path(self, path: Path) -> str:
        if self.config.docker_backend == "wsl":
            return self._windows_path_to_wsl(path)
        return docker_mount_path(path)

    def _windows_path_to_wsl(self, path: Path) -> str:
        resolved = str(path.resolve()).replace("\\", "/")
        proc = run_cmd(["wsl", "-d", self.config.wsl_distro, "--", "wslpath", "-a", resolved], timeout=60)
        require_ok(proc, f"wslpath {path}")
        return proc.stdout.strip()


def _git_safe_directory(repo_dir: Path) -> str:
    text = str(repo_dir)
    if text.startswith("\\\\"):
        return "//" + text.lstrip("\\").replace("\\", "/")
    return str(repo_dir.resolve())


def _patchable_untracked_files(paths: list[str]) -> list[str]:
    ignored_prefixes = (
        ".pnpm-store/",
        "bash_events/",
        "conversations/",
        "node_modules/",
    )
    ignored_names = {".DS_Store"}
    result = []
    for raw in paths:
        path = raw.strip()
        if not path or path in ignored_names:
            continue
        normalized = path.replace("\\", "/")
        if any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in ignored_prefixes):
            continue
        result.append(path)
    return result
