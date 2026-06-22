#!/usr/bin/env python3
"""RepoACES Orchestrator prototype.

The orchestrator is intentionally outside Dify. Dify calls `/runs`; this service
prepares a clean repository, starts an OpenHands server with that repository
mounted into the sandbox, and submits the instruction through the same
OpenHands app-server REST path used by the GUI.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
HOST = os.getenv("REPOACES_ORCHESTRATOR_HOST", "0.0.0.0")
PORT = int(os.getenv("REPOACES_ORCHESTRATOR_PORT", "8788"))
RUNS_ROOT = Path(os.getenv("REPOACES_RUNS_ROOT", str(ROOT / "runs" / "repoaces-orchestrator")))
WORKSPACES_ROOT = Path(os.getenv("REPOACES_WORKSPACES_ROOT", str(ROOT / "workspaces" / "repoaces-runs")))
EVAL_ROOT = Path(
    os.getenv("REPOACES_EVAL_ROOT", str(ROOT / "tmp" / "experiments" / "evaluation" / "fastgpt" / "openhands"))
)
OPENHANDS_HOME_TEMPLATE = Path(os.getenv("REPOACES_OPENHANDS_HOME_TEMPLATE", str(ROOT / ".openhands-home")))
OPENHANDS_IMAGE = os.getenv("REPOACES_OPENHANDS_IMAGE", "docker.openhands.dev/openhands/openhands:1.8")
AGENT_SERVER_IMAGE_REPOSITORY = os.getenv("REPOACES_AGENT_SERVER_IMAGE_REPOSITORY", "ghcr.io/openhands/agent-server")
AGENT_SERVER_IMAGE_TAG = os.getenv("REPOACES_AGENT_SERVER_IMAGE_TAG", "1.26.0-python")
DEFAULT_REPO_URL = os.getenv("REPOACES_DEFAULT_REPO_URL", "https://github.com/labring/FastGPT.git")
DEFAULT_REFERENCE_REPO = Path(
    os.getenv("REPOACES_FASTGPT_REFERENCE_REPO", str(ROOT / "workspaces" / "pr7008-run-003" / "FastGPT"))
)
DEFAULT_MODEL = os.getenv("REPOACES_OPENHANDS_MODEL", "gpt-5.4")
INSTANCE_ID = os.getenv("REPOACES_INSTANCE_ID", "fastgpt__pr7008")
DEFAULT_WAIT_START_SECONDS = int(os.getenv("REPOACES_WAIT_START_SECONDS", "180"))
DEFAULT_WAIT_COMPLETION_SECONDS = int(os.getenv("REPOACES_WAIT_COMPLETION_SECONDS", "0"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_run_id(value: str | None = None) -> str:
    raw = value or f"pr7008-live-{uuid.uuid4().hex[:8]}"
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", raw).strip(".-")
    return safe[:60] or f"run-{uuid.uuid4().hex[:8]}"


def run_cmd(cmd: list[str], *, cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def require_ok(proc: subprocess.CompletedProcess[str], action: str) -> None:
    if proc.returncode != 0:
        raise RuntimeError(
            f"{action} failed with exit code {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )


def http_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 60) -> Any:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else None


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def docker_mount_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def parse_instruction_fields(instruction: str, payload: dict[str, Any]) -> dict[str, str]:
    base_commit = str(payload.get("base_commit") or "").strip()
    if not base_commit:
        match = re.search(r"Base commit:\s*`?([0-9a-fA-F]{7,40})`?", instruction)
        if match:
            base_commit = match.group(1)

    repo_url = str(payload.get("repo_url") or "").strip()
    pr_url = str(payload.get("pr_url") or "").strip()
    if not pr_url:
        match = re.search(r"https://github\.com/[^/\s]+/[^/\s]+/pull/\d+", instruction)
        if match:
            pr_url = match.group(0)

    if (not base_commit or not repo_url) and pr_url:
        pr_meta = fetch_github_pr_metadata(pr_url)
        base_commit = base_commit or pr_meta.get("base_commit", "")
        repo_url = repo_url or pr_meta.get("repo_url", "")

    repo_url = repo_url or DEFAULT_REPO_URL

    sandbox_repo_path = str(payload.get("sandbox_repo_path") or "").strip()
    if not sandbox_repo_path:
        match = re.search(r"directory\s+`([^`]+)`", instruction)
        if match and match.group(1).startswith("/"):
            sandbox_repo_path = match.group(1).rstrip("/")
    if not sandbox_repo_path:
        sandbox_repo_path = "/workspace"

    return {
        "repo_url": repo_url,
        "base_commit": base_commit,
        "sandbox_repo_path": sandbox_repo_path,
    }


def fetch_github_pr_metadata(pr_url: str) -> dict[str, str]:
    match = re.fullmatch(r"https://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)", pr_url.rstrip("/"))
    if not match:
        return {}
    owner, repo, number = match.groups()
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "RepoACES-Orchestrator",
    }
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(api_url, headers=headers)
    with urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    base = data.get("base") or {}
    base_repo = base.get("repo") or {}
    return {
        "base_commit": str(base.get("sha") or ""),
        "repo_url": str(base_repo.get("clone_url") or ""),
    }


def reference_has_commit(reference_repo: Path, commit: str) -> bool:
    if not commit or not (reference_repo / ".git").exists():
        return False
    proc = run_cmd(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=reference_repo, timeout=60)
    return proc.returncode == 0


def prepare_repo(run_id: str, repo_url: str, base_commit: str) -> Path:
    if not base_commit:
        raise ValueError("base_commit is required. Include `Base commit: <sha>` in the instruction or payload.")

    repo_dir = WORKSPACES_ROOT / run_id / "FastGPT"
    if repo_dir.exists():
        return repo_dir

    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    reference_repo = DEFAULT_REFERENCE_REPO
    if reference_has_commit(reference_repo, base_commit):
        clone = run_cmd(["git", "clone", "--shared", "--no-checkout", str(reference_repo), str(repo_dir)], timeout=900)
    else:
        clone = run_cmd(["git", "clone", "--no-checkout", repo_url, str(repo_dir)], timeout=1800)
    require_ok(clone, "git clone")

    checkout = run_cmd(["git", "checkout", base_commit], cwd=repo_dir, timeout=600)
    require_ok(checkout, f"git checkout {base_commit}")
    reset = run_cmd(["git", "reset", "--hard", base_commit], cwd=repo_dir, timeout=300)
    require_ok(reset, f"git reset --hard {base_commit}")
    clean = run_cmd(["git", "clean", "-fdx"], cwd=repo_dir, timeout=300)
    require_ok(clean, "git clean")
    return repo_dir


def copy_openhands_home(run_id: str) -> Path:
    target = RUNS_ROOT / run_id / "openhands-home"
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)

    def ignore(_dir: str, names: list[str]) -> set[str]:
        ignored = {".settings.lock", ".workspaces.lock", "openhands.db", "v1_conversations"}
        return {name for name in names if name in ignored}

    if OPENHANDS_HOME_TEMPLATE.exists():
        shutil.copytree(OPENHANDS_HOME_TEMPLATE, target, ignore=ignore)
    else:
        target.mkdir(parents=True, exist_ok=True)
    return target


def start_openhands_server(run_id: str, repo_dir: Path, sandbox_repo_path: str) -> dict[str, Any]:
    port = find_free_port()
    container_name = f"repoaces-oh-{run_id}"[:120]
    openhands_home = copy_openhands_home(run_id)

    repo_mount = docker_mount_path(repo_dir)
    home_mount = docker_mount_path(openhands_home)
    sandbox_volumes = [f"{repo_mount}:/workspace:rw"]
    if sandbox_repo_path != "/workspace":
        sandbox_volumes.append(f"{repo_mount}:{sandbox_repo_path}:rw")
    sandbox_volumes_value = ",".join(sandbox_volumes)

    run_cmd(["docker", "rm", "-f", container_name], timeout=60)
    cmd = [
        "docker",
        "run",
        "-d",
        "-e",
        f"AGENT_SERVER_IMAGE_REPOSITORY={AGENT_SERVER_IMAGE_REPOSITORY}",
        "-e",
        f"AGENT_SERVER_IMAGE_TAG={AGENT_SERVER_IMAGE_TAG}",
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
        OPENHANDS_IMAGE,
    ]
    proc = run_cmd(cmd, timeout=300)
    require_ok(proc, "docker run OpenHands")

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 180
    last_error = ""
    while time.time() < deadline:
        try:
            with urlopen(f"{base_url}/health", timeout=5) as resp:
                if resp.status == 200:
                    return {
                        "container": container_name,
                        "port": port,
                        "base_url": base_url,
                        "sandbox_volumes": sandbox_volumes_value,
                        "openhands_home": str(openhands_home),
                    }
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(2)
    raise TimeoutError(f"OpenHands server did not become healthy: {last_error}")


def start_openhands_conversation(
    base_url: str,
    run_id: str,
    instruction: str,
    *,
    model: str,
    auto_run: bool,
    wait_start_seconds: int,
) -> dict[str, Any]:
    payload = {
        "initial_message": {
            "role": "user",
            "content": [{"type": "text", "text": instruction}],
            "run": auto_run,
        },
        "title": f"RepoACES {run_id}",
        "trigger": "openhands_api",
        "llm_model": model,
        "agent_type": "default",
    }
    task = http_json("POST", f"{base_url}/api/v1/app-conversations", payload, timeout=60)
    start_task_id = task["id"]

    deadline = time.time() + wait_start_seconds
    latest = task
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


def get_conversation(base_url: str, conversation_id: str) -> dict[str, Any] | None:
    try:
        data = http_json("GET", f"{base_url}/api/v1/app-conversations?ids={conversation_id}", timeout=60)
        if not data:
            return None
        conv = data[0]
        if isinstance(conv, dict):
            session_api_key = conv.pop("session_api_key", None)
            conversation_url = conv.get("conversation_url")
            if session_api_key and conversation_url:
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
    except Exception:
        return None


def export_patch(run_id: str, repo_dir: Path) -> dict[str, Any]:
    patch_proc = run_cmd(["git", "diff", "--binary"], cwd=repo_dir, timeout=300)
    patch = patch_proc.stdout if patch_proc.returncode == 0 else ""
    task_dir = EVAL_ROOT / run_id / "tasks" / "01-implementation"
    task_dir.mkdir(parents=True, exist_ok=True)
    patch_path = task_dir / "patch.diff"
    patch_path.write_text(patch, encoding="utf-8", errors="replace")
    return {
        "patch": patch,
        "patch_path": str(patch_path),
        "task_dir": str(task_dir),
        "patch_diff_chars": len(patch),
        "patch_line_count": len(patch.splitlines()),
    }


def write_task_instruction(run_id: str, instruction: str) -> Path:
    task_dir = EVAL_ROOT / run_id / "tasks" / "01-implementation"
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / "instruction.md"
    path.write_text(instruction, encoding="utf-8")
    return path


def write_task_result(run_id: str, state: dict[str, Any], patch_info: dict[str, Any]) -> Path:
    task_dir = EVAL_ROOT / run_id / "tasks" / "01-implementation"
    path = task_dir / "result.json"
    payload = {
        "stage": "01-implementation",
        "role": "coding_agent",
        "status": state.get("status"),
        "completed": bool(patch_info.get("patch_path")),
        "instruction": "instruction.md",
        "trajectory": None,
        "patch": "patch.diff",
        "runtime_state": str(state_path(run_id)),
        "patch_diff_chars": patch_info.get("patch_diff_chars", 0),
        "patch_line_count": patch_info.get("patch_line_count", 0),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def state_path(run_id: str) -> Path:
    return RUNS_ROOT / run_id / "state.json"


def save_state(state: dict[str, Any]) -> None:
    path = state_path(state["run_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_state = dict(state)
    path.write_text(json.dumps(safe_state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state(run_id: str) -> dict[str, Any] | None:
    path = state_path(run_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def build_task_summary(instruction: str, state: dict[str, Any], patch_info: dict[str, Any]) -> dict[str, Any]:
    title = "RepoACES OpenHands live run"
    for line in instruction.splitlines():
        stripped = line.strip("# ").strip()
        if stripped:
            title = stripped
            break
    return {
        "title": title,
        "mode": "live_openhands_start",
        "instruction_chars": len(instruction),
        "repo_url": state.get("repo_url"),
        "base_commit": state.get("base_commit"),
        "repo_dir": state.get("repo_dir"),
        "sandbox_repo_path": state.get("sandbox_repo_path"),
        "openhands_container": state.get("openhands", {}).get("container"),
        "openhands_base_url": state.get("openhands", {}).get("base_url"),
        "conversation_id": state.get("openhands_conversation", {}).get("conversation_id"),
        "execution_status": state.get("conversation", {}).get("execution_status"),
        "patch_diff_chars": patch_info.get("patch_diff_chars", 0),
        "note": "OpenHands was started through the app-server REST API with the instruction as initial_message.",
    }


def refresh_run(run_id: str) -> tuple[int, dict[str, Any]]:
    state = load_state(run_id)
    if not state:
        return 404, {"ok": False, "error": "run_not_found", "run_id": run_id}

    conv_info = state.get("openhands_conversation") or {}
    base_url = (state.get("openhands") or {}).get("base_url")
    conversation_id = conv_info.get("conversation_id")
    if base_url and conversation_id:
        conversation = get_conversation(base_url, conversation_id)
        if conversation:
            state["conversation"] = conversation
            execution_status = conversation.get("execution_status")
            if execution_status:
                state["status"] = f"openhands_{execution_status}"

    patch_info = export_patch(run_id, Path(state["repo_dir"]))
    state["patch_path"] = patch_info["patch_path"]
    state["patch_diff_chars"] = patch_info["patch_diff_chars"]
    result_path = write_task_result(run_id, state, patch_info)
    state["task_result_path"] = str(result_path)
    state["updated_at"] = now_iso()
    save_state(state)

    return 200, {
        "ok": True,
        "run_id": run_id,
        "status": state.get("status"),
        "task_summary": build_task_summary(state.get("instruction", ""), state, patch_info),
        "patch_diff": patch_info["patch"],
        "patch_diff_preview": patch_info["patch"][:1200],
        "patch_pending": patch_info["patch_diff_chars"] == 0,
        "state": {k: v for k, v in state.items() if k != "instruction"},
    }


def create_live_run(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    instruction = str(payload.get("instruction") or payload.get("openhands_instruction") or "")
    if not instruction:
        return 400, {"ok": False, "error": "instruction_required"}

    run_id = safe_run_id(str(payload.get("run_id") or ""))
    fields = parse_instruction_fields(instruction, payload)
    repo_dir = prepare_repo(run_id, fields["repo_url"], fields["base_commit"])
    openhands = start_openhands_server(run_id, repo_dir, fields["sandbox_repo_path"])
    auto_run = bool(payload.get("auto_run", True))
    wait_start_seconds = int(payload.get("wait_start_seconds", DEFAULT_WAIT_START_SECONDS))
    model = str(payload.get("model") or DEFAULT_MODEL)
    conv_info = start_openhands_conversation(
        openhands["base_url"],
        run_id,
        instruction,
        model=model,
        auto_run=auto_run,
        wait_start_seconds=wait_start_seconds,
    )

    state = {
        "run_id": run_id,
        "status": "openhands_started",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "instruction": instruction,
        "repo_url": fields["repo_url"],
        "base_commit": fields["base_commit"],
        "repo_dir": str(repo_dir),
        "sandbox_repo_path": fields["sandbox_repo_path"],
        "openhands": openhands,
        "openhands_conversation": conv_info,
        "model": model,
        "auto_run": auto_run,
    }
    instruction_path = write_task_instruction(run_id, instruction)
    state["task_instruction_path"] = str(instruction_path)

    if conv_info.get("start_task_status") == "ERROR":
        state["status"] = "openhands_start_error"
    elif conv_info.get("conversation_id"):
        conversation = get_conversation(openhands["base_url"], conv_info["conversation_id"])
        if conversation:
            state["conversation"] = conversation
            if conversation.get("execution_status"):
                state["status"] = f"openhands_{conversation['execution_status']}"

    patch_info = export_patch(run_id, repo_dir)
    state["patch_path"] = patch_info["patch_path"]
    state["patch_diff_chars"] = patch_info["patch_diff_chars"]
    result_path = write_task_result(run_id, state, patch_info)
    state["task_result_path"] = str(result_path)
    save_state(state)

    wait_completion_seconds = int(payload.get("wait_completion_seconds", DEFAULT_WAIT_COMPLETION_SECONDS))
    if wait_completion_seconds > 0 and conv_info.get("conversation_id"):
        deadline = time.time() + wait_completion_seconds
        while time.time() < deadline:
            conversation = get_conversation(openhands["base_url"], conv_info["conversation_id"])
            if conversation:
                state["conversation"] = conversation
                execution_status = conversation.get("execution_status")
                if execution_status:
                    state["status"] = f"openhands_{execution_status}"
                if execution_status in {"finished", "error", "stuck"}:
                    break
            time.sleep(10)
        patch_info = export_patch(run_id, repo_dir)
        state["patch_path"] = patch_info["patch_path"]
        state["patch_diff_chars"] = patch_info["patch_diff_chars"]
        result_path = write_task_result(run_id, state, patch_info)
        state["task_result_path"] = str(result_path)
        state["updated_at"] = now_iso()
        save_state(state)

    return 200, {
        "ok": True,
        "status": state["status"],
        "run_id": run_id,
        "case_id": str(payload.get("case_id") or "pr7008"),
        "created_at": int(time.time()),
        "task_summary": build_task_summary(instruction, state, patch_info),
        "patch_diff": patch_info["patch"],
        "patch_diff_preview": patch_info["patch"][:1200],
        "patch_pending": patch_info["patch_diff_chars"] == 0,
        "artifacts": {
            "task_dir": patch_info.get("task_dir"),
            "instruction": str(instruction_path),
            "patch": patch_info["patch_path"],
            "result": state.get("task_result_path"),
            "state": str(state_path(run_id)),
        },
        "openhands": {
            "base_url": openhands["base_url"],
            "container": openhands["container"],
            "conversation_id": conv_info.get("conversation_id"),
            "start_task_id": conv_info.get("start_task_id"),
            "start_task_status": conv_info.get("start_task_status"),
            "sandbox_id": conv_info.get("sandbox_id"),
        },
    }


def create_replay_run(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from repoaces_orchestrator_mock import _create_run  # type: ignore

    return _create_run(payload)


def parse_request_body(raw: str) -> dict[str, Any]:
    try:
        body = json.loads(raw) if raw else {}
        if isinstance(body, dict):
            return body
        return {"instruction": raw}
    except json.JSONDecodeError:
        return {"instruction": raw}


class Handler(BaseHTTPRequestHandler):
    server_version = "RepoACESOrchestrator/0.2"

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type, authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json(200, {"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.rstrip("/")
        if path == "/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "service": "repoaces-orchestrator",
                    "runs_root": str(RUNS_ROOT),
                    "workspaces_root": str(WORKSPACES_ROOT),
                },
            )
            return
        match = re.fullmatch(r"/runs/([^/]+)", path)
        if match:
            status, body = refresh_run(match.group(1))
            self._send_json(status, body)
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/runs":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        payload = parse_request_body(raw)
        mode = str(payload.get("mode") or os.getenv("REPOACES_ORCHESTRATOR_MODE", "live")).lower()
        try:
            if mode == "replay":
                status, body = create_replay_run(payload)
            else:
                status, body = create_live_run(payload)
        except (RuntimeError, TimeoutError, ValueError, HTTPError, URLError, subprocess.TimeoutExpired) as exc:
            status, body = 500, {"ok": False, "error": type(exc).__name__, "detail": str(exc)}
        self._send_json(status, body)


def main() -> None:
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    WORKSPACES_ROOT.mkdir(parents=True, exist_ok=True)
    print(
        json.dumps(
            {
                "service": "repoaces-orchestrator",
                "host": HOST,
                "port": PORT,
                "runs_root": str(RUNS_ROOT),
                "workspaces_root": str(WORKSPACES_ROOT),
                "mode": os.getenv("REPOACES_ORCHESTRATOR_MODE", "live"),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
