from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .io import write_json, write_text
from .shell import run_cmd


class StaticRepoIntelligence:
    """Fast, dependency-light repository analysis.

    This backend does not replace CodeWiki. It creates deterministic starter
    artifacts that the downstream agents can consume before a full repo wiki is
    available.
    """

    def build(self, repo_dir: Path, output_dir: Path, focus_terms: list[str] | None = None) -> dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        files = self._list_files(repo_dir)
        focus_terms = focus_terms or []
        matched_files = self._match_files(files, focus_terms)
        context = {
            "repo_dir": str(repo_dir),
            "file_count": len(files),
            "top_level": self._top_level_summary(files),
            "matched_files": matched_files,
            "package_managers": self._detect_package_managers(repo_dir),
            "command_map": self._command_map(repo_dir),
        }
        graph = self._simple_code_graph(files, matched_files)

        context_path = output_dir / "repo_context.json"
        graph_path = output_dir / "code_knowledge_graph.json"
        command_map_path = output_dir / "command_map.json"
        overview_path = output_dir / "repo_overview.md"

        write_json(context_path, context)
        write_json(graph_path, graph)
        write_json(command_map_path, context["command_map"])
        write_text(overview_path, self._render_overview(context))
        return {
            "repo_context": context_path,
            "code_knowledge_graph": graph_path,
            "command_map": command_map_path,
            "repo_overview": overview_path,
        }

    def _list_files(self, repo_dir: Path) -> list[str]:
        try:
            proc = run_cmd(["rg", "--files"], cwd=repo_dir, timeout=120)
            if proc.returncode == 0:
                return sorted(line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip())
        except FileNotFoundError:
            pass
        ignored = {".git", "node_modules", ".next", "dist", "build", ".pnpm-store", "__pycache__", ".venv"}
        files: list[str] = []
        for root, dirs, names in os.walk(repo_dir, onerror=lambda _error: None):
            dirs[:] = [name for name in dirs if name not in ignored]
            root_path = Path(root)
            if any(part in ignored for part in root_path.relative_to(repo_dir).parts):
                continue
            for name in names:
                path = root_path / name
                try:
                    if path.is_file():
                        files.append(path.relative_to(repo_dir).as_posix())
                except OSError:
                    continue
        return sorted(files)

    def _match_files(self, files: list[str], focus_terms: list[str]) -> list[str]:
        if not focus_terms:
            return []
        terms = [term.lower() for term in focus_terms if term]
        matched = []
        for file in files:
            lower = file.lower()
            if any(term in lower for term in terms):
                matched.append(file)
        return matched[:200]

    def _top_level_summary(self, files: list[str]) -> dict[str, int]:
        summary: dict[str, int] = {}
        for file in files:
            top = file.split("/", 1)[0]
            summary[top] = summary.get(top, 0) + 1
        return dict(sorted(summary.items(), key=lambda item: (-item[1], item[0]))[:50])

    def _detect_package_managers(self, repo_dir: Path) -> list[str]:
        markers = {
            "pnpm": "pnpm-lock.yaml",
            "npm": "package-lock.json",
            "yarn": "yarn.lock",
            "python-poetry": "poetry.lock",
            "python-pip": "requirements.txt",
        }
        return [name for name, marker in markers.items() if (repo_dir / marker).exists()]

    def _command_map(self, repo_dir: Path) -> dict[str, Any]:
        command_map: dict[str, Any] = {"recommended": [], "package_scripts": {}}
        package_json = repo_dir / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8", errors="replace"))
                scripts = data.get("scripts") or {}
                command_map["package_scripts"] = scripts
                runner = "pnpm" if (repo_dir / "pnpm-lock.yaml").exists() else "npm run"
                for name in ["lint", "typecheck", "test", "build"]:
                    if name in scripts:
                        command_map["recommended"].append(f"{runner} {name}")
            except json.JSONDecodeError:
                command_map["package_scripts_error"] = "package.json is not valid JSON"
        if list(repo_dir.glob("**/docker-compose*.yml")):
            command_map["recommended"].append("docker compose config")
        return command_map

    def _simple_code_graph(self, files: list[str], matched_files: list[str]) -> dict[str, Any]:
        nodes = []
        edges = []
        directories: set[str] = set()
        for file in files:
            parts = file.split("/")
            for index in range(1, len(parts)):
                directories.add("/".join(parts[:index]))
            if file in matched_files:
                nodes.append({"id": file, "type": "focus_file", "label": Path(file).name})
        for directory in sorted(directories):
            nodes.append({"id": directory, "type": "directory", "label": Path(directory).name})
            parent = str(Path(directory).parent).replace("\\", "/")
            if parent and parent != ".":
                edges.append({"source": parent, "target": directory, "type": "contains"})
        for file in matched_files:
            parent = str(Path(file).parent).replace("\\", "/")
            if parent and parent != ".":
                edges.append({"source": parent, "target": file, "type": "contains"})
        return {"nodes": nodes[:500], "edges": edges[:1000]}

    def _render_overview(self, context: dict[str, Any]) -> str:
        top_level = "\n".join(f"- `{name}`: {count} files" for name, count in context["top_level"].items())
        matched = "\n".join(f"- `{file}`" for file in context["matched_files"][:80]) or "- No focus matches."
        commands = "\n".join(f"- `{cmd}`" for cmd in context["command_map"].get("recommended", [])) or "- No commands inferred."
        return f"""# Repository Overview

## Top-Level Layout

{top_level}

## Focus-Matched Files

{matched}

## Inferred Commands

{commands}
"""


class CodeWikiRepoIntelligence:
    """Adapter for FSoft-AI4Code/CodeWiki.

    CodeWiki is an external CLI. Its README documents `codewiki generate`, which
    creates repository documentation under `./docs/`. This adapter keeps the
    integration replaceable while avoiding a hard dependency in RepoACES.
    """

    def build(self, repo_dir: Path, output_dir: Path, extra_args: list[str] | None = None) -> dict[str, Path]:
        if shutil.which("codewiki") is None:
            raise RuntimeError("CodeWiki CLI not found. Install/configure `codewiki` before using this backend.")
        output_dir.mkdir(parents=True, exist_ok=True)
        before_docs = repo_dir / "docs"
        cmd = ["codewiki", "generate", *(extra_args or [])]
        proc = run_cmd(cmd, cwd=repo_dir, timeout=7200)
        log_path = output_dir / "codewiki.log"
        write_text(log_path, f"$ {' '.join(cmd)}\n\nSTDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}\n")
        if proc.returncode != 0:
            raise RuntimeError(f"CodeWiki generation failed. See {log_path}")
        manifest = {"repo_dir": str(repo_dir), "codewiki_docs": str(before_docs), "log": str(log_path)}
        manifest_path = output_dir / "codewiki_manifest.json"
        write_json(manifest_path, manifest)
        return {"codewiki_manifest": manifest_path, "codewiki_log": log_path}
