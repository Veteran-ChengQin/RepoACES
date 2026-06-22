from __future__ import annotations

import subprocess
from pathlib import Path


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
