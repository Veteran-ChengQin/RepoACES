#!/usr/bin/env python3
"""Minimal RepoACES Orchestrator mock for Dify integration smoke tests.

This service intentionally does not start a new OpenHands run yet. It accepts
the same shape of request the future orchestrator will receive, then replays
the existing PR7008 OpenHands artifacts so Dify's HTTP workflow integration can
be verified quickly.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


HOST = os.getenv("REPOACES_ORCHESTRATOR_HOST", "0.0.0.0")
PORT = int(os.getenv("REPOACES_ORCHESTRATOR_PORT", "8787"))
WORKSPACE_ROOT = Path(os.getenv("REPOACES_WORKSPACE_ROOT", "/workspace"))
ARTIFACT_ROOT = Path(
    os.getenv(
        "REPOACES_ARTIFACT_ROOT",
        str(WORKSPACE_ROOT / "tmp/experiments/evaluation/fastgpt/openhands/pr7008-run-003"),
    )
)
INSTANCE_ID = os.getenv("REPOACES_INSTANCE_ID", "fastgpt__pr7008")


def _read_text(path: Path, max_chars: int | None = None) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars] + "\n\n...[truncated]..."
    return text


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def _build_task_summary(instruction: str, report: dict[str, Any], patch_diff: str) -> dict[str, Any]:
    first_heading = "FastGPT Code Sandbox queueId Concurrency Issue"
    for line in instruction.splitlines():
        stripped = line.strip("# ").strip()
        if stripped:
            first_heading = stripped
            break

    changed_files: list[str] = []
    for line in patch_diff.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                changed_files.append(parts[3].removeprefix("b/"))

    case_report = report.get(INSTANCE_ID, {}) if isinstance(report, dict) else {}
    commands = case_report.get("commands", {}) if isinstance(case_report, dict) else {}

    return {
        "title": first_heading,
        "mode": "replay_existing_openhands_artifacts",
        "openhands_run": "pr7008-run-003",
        "instance": INSTANCE_ID,
        "instruction_chars": len(instruction),
        "changed_files": changed_files,
        "changed_file_count": len(changed_files),
        "patch_line_count": len(patch_diff.splitlines()),
        "resolved": bool(case_report.get("resolved")),
        "verification_commands": commands,
        "note": (
            "This response replays previously generated PR7008 artifacts. "
            "The next milestone is to replace replay mode with live OpenHands execution."
        ),
    }


def _artifact_paths() -> dict[str, Path]:
    task_dir = ARTIFACT_ROOT / "tasks" / "01-implementation"
    if task_dir.exists():
        return {
            "manifest": ARTIFACT_ROOT / "artifact-manifest.json",
            "instruction": task_dir / "instruction.md",
            "patch": task_dir / "patch.diff",
            "report": task_dir / "report.json",
            "result": task_dir / "result.json",
            "test_output": task_dir / "test_output.txt",
            "eval_script": task_dir / "eval.sh",
            "trajectory": task_dir / "trajectory.json",
            "trajectory_summary": task_dir / "trajectory-summary.json",
        }

    log_dir = ARTIFACT_ROOT / "logs" / INSTANCE_ID
    traj_dir = ARTIFACT_ROOT / "trajs"
    return {
        "manifest": ARTIFACT_ROOT / "artifact-manifest.json",
        "patch": log_dir / "patch.diff",
        "report": log_dir / "report.json",
        "test_output": log_dir / "test_output.txt",
        "eval_script": log_dir / "eval.sh",
        "trajectory": traj_dir / f"{INSTANCE_ID}-pr7008-run-003.json",
        "trajectory_summary": traj_dir / f"{INSTANCE_ID}-pr7008-run-003-summary.json",
    }


def _create_run(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    instruction = str(payload.get("instruction") or payload.get("openhands_instruction") or "")
    requested_case = str(payload.get("case_id") or "pr7008")
    run_id = str(payload.get("run_id") or f"{requested_case}-replay-{uuid.uuid4().hex[:8]}")

    paths = _artifact_paths()
    missing = [name for name, path in paths.items() if name in {"manifest", "patch", "report"} and not path.exists()]
    if missing:
        return 500, {
            "ok": False,
            "status": "artifact_missing",
            "run_id": run_id,
            "missing": missing,
            "artifact_root": str(ARTIFACT_ROOT),
        }

    patch_diff = _read_text(paths["patch"])
    report = _read_json(paths["report"])
    manifest = _read_json(paths["manifest"])

    response = {
        "ok": True,
        "status": "completed_from_cached_artifacts",
        "run_id": run_id,
        "case_id": requested_case,
        "created_at": int(time.time()),
        "task_summary": _build_task_summary(instruction, report, patch_diff),
        "patch_diff": patch_diff,
        "patch_diff_preview": patch_diff[:1200],
        "report": report,
        "artifact_manifest": manifest,
        "artifacts": {name: str(path) for name, path in paths.items()},
        "next_action": "wire_live_openhands_execution",
    }
    return 200, response


class Handler(BaseHTTPRequestHandler):
    server_version = "RepoACESOrchestratorMock/0.1"

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
        if self.path.rstrip("/") == "/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "service": "repoaces-orchestrator-mock",
                    "artifact_root": str(ARTIFACT_ROOT),
                },
            )
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/runs":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"instruction": raw}

        status, body = _create_run(payload)
        self._send_json(status, body)


def main() -> None:
    print(
        json.dumps(
            {
                "service": "repoaces-orchestrator-mock",
                "host": HOST,
                "port": PORT,
                "artifact_root": str(ARTIFACT_ROOT),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
