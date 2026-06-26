from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path

from .io import read_yaml, write_json, write_text
from .models import CaseInput, CaseValidation, FeatureCase, PublicCase


DEFAULT_CONSTRAINTS = [
    "Do not look up the original pull request, golden commit, golden patch, head commit, or online implementation.",
    "Use only the repository at the provided base commit and the public feature request.",
    "Keep changes focused on the requested feature and preserve unrelated behavior.",
    "If tests or documentation are appropriate for this feature, add or update them narrowly.",
    "Record important commands, results, and remaining risks in the final response.",
]


class CaseBuilder:
    """Build public task artifacts from a private benchmark case."""

    def load_case(self, case_yaml: Path) -> FeatureCase:
        raw = read_yaml(case_yaml)
        case_id = str(raw["id"])
        input_raw = raw["input"]
        validation_raw = raw["validation"]
        case_input = CaseInput(
            case_id=case_id,
            repo=str(input_raw["repo"]),
            repo_url=str(input_raw["repo_url"]),
            base_branch=str(input_raw.get("base_branch", "")),
            base_commit=str(input_raw["base_commit"]),
            pr_number=int(input_raw["pr_number"]),
            pr_url=str(input_raw["pr_url"]),
            pr_title_raw=str(input_raw["pr_title_raw"]),
            summary_source=str(input_raw.get("summary_source", "")),
            summary_raw_markdown=str(input_raw.get("summary_raw_markdown", "")).strip(),
        )
        validation = CaseValidation(
            head_commit=str(validation_raw.get("head_commit", "")),
            merge_commit=validation_raw.get("merge_commit"),
            patch_source=str(validation_raw.get("patch_source", "")),
            patch_file=str(validation_raw.get("patch_file", "")),
            patch_sha256=str(validation_raw.get("patch_sha256", "")),
            changed_files_file=str(validation_raw.get("changed_files_file", "")),
            manual_functionality_description=str(
                validation_raw.get("manual_functionality_description", "")
            ).strip(),
        )
        return FeatureCase(case_id=case_id, input=case_input, validation=validation, case_path=case_yaml)

    def build_public_case(self, case: FeatureCase) -> PublicCase:
        criteria = self._extract_acceptance_criteria(case.input.summary_raw_markdown)
        if not criteria:
            criteria = [self._sentence(case.input.pr_title_raw)]
        return PublicCase(
            case_id=case.case_id,
            repo=case.input.repo,
            repo_url=case.input.repo_url,
            base_branch=case.input.base_branch,
            base_commit=case.input.base_commit,
            pr_number=case.input.pr_number,
            pr_title=case.input.pr_title_raw,
            feature_summary=case.input.summary_raw_markdown,
            acceptance_criteria=criteria,
            constraints=DEFAULT_CONSTRAINTS,
            hidden_fields=[
                "validation.head_commit",
                "validation.patch_file",
                "validation.patch_sha256",
                "validation.changed_files_file",
                "validation.manual_functionality_description",
            ],
        )

    def write_case_artifacts(
        self,
        case_yaml: Path,
        output_dir: Path,
        workspace_path: str = "/workspace",
        private_output_dir: Path | None = None,
    ) -> dict[str, Path]:
        case = self.load_case(case_yaml)
        public_case = self.build_public_case(case)
        output_dir.mkdir(parents=True, exist_ok=True)
        private_output_dir = private_output_dir or output_dir
        private_output_dir.mkdir(parents=True, exist_ok=True)
        public_case_path = output_dir / "public_case.json"
        instruction_path = output_dir / "instruction.md"
        requirement_path = output_dir / "requirement_spec.md"
        private_meta_path = private_output_dir / "private_validation_meta.json"

        write_json(public_case_path, public_case)
        write_text(instruction_path, self.render_instruction(public_case, workspace_path=workspace_path))
        write_text(requirement_path, self.render_requirement_spec(public_case))
        write_json(private_meta_path, {"case": case.case_id, "validation": asdict(case.validation)})

        return {
            "public_case": public_case_path,
            "instruction": instruction_path,
            "requirement_spec": requirement_path,
            "private_validation_meta": private_meta_path,
        }

    def render_instruction(self, public_case: PublicCase, workspace_path: str = "/workspace") -> str:
        criteria = "\n".join(f"- {item}" for item in public_case.acceptance_criteria)
        constraints = "\n".join(f"- {item}" for item in public_case.constraints)
        summary = public_case.feature_summary.strip() or public_case.pr_title
        return f"""# RepoACES Feature Implementation Task

You are working on a repository-level feature implementation task.

Repository: `{public_case.repo}`
Workspace directory: `{workspace_path}`
Base commit: `{public_case.base_commit}`

## Feature Request

{public_case.pr_title}

{summary}

## Acceptance Criteria

{criteria}

## Constraints

{constraints}

## Required Phases

1. Requirement understanding: restate the feature, compatibility requirements, edge cases, and non-goals.
2. Repository exploration: identify package manager, relevant scripts, relevant modules, and existing conventions.
3. Change scope identification: list likely files and explain why each file is in scope.
4. Implementation plan: create a concrete ordered plan before editing files.
5. Code implementation: make focused changes in the workspace.
6. Test/documentation implementation: add or update narrowly scoped tests or docs when appropriate.
7. Build and validation: run the most relevant available checks. If a check cannot run, record the exact blocker.
8. Final review: compare the final diff against the feature request and report changed files, validation results, and residual risks.

Do not browse the original pull request, golden patch, head commit, or online implementation.
Quality and completeness are more important than speed.
{self._render_runtime_guidance(public_case)}
"""

    def render_requirement_spec(self, public_case: PublicCase) -> str:
        criteria = "\n".join(f"- {item}" for item in public_case.acceptance_criteria)
        constraints = "\n".join(f"- {item}" for item in public_case.constraints)
        return f"""# Requirement Specification

## Case

- Case ID: `{public_case.case_id}`
- Repository: `{public_case.repo}`
- Base commit: `{public_case.base_commit}`
- PR number: `{public_case.pr_number}`
- Title: {public_case.pr_title}

## Feature Summary

{public_case.feature_summary}

## Acceptance Criteria

{criteria}

## Constraints

{constraints}

## Hidden Benchmark Fields

The coding agent must not receive the golden patch, head commit, changed-files list, or validation-only metadata.
"""

    def _extract_acceptance_criteria(self, markdown: str) -> list[str]:
        criteria: list[str] = []
        for line in markdown.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            match = re.match(r"^[-*]\s+(.*)$", stripped)
            item = match.group(1).strip() if match else stripped
            if item:
                criteria.append(self._sentence(item))
        return criteria

    def _sentence(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        return text.rstrip(".") + "."

    def _render_runtime_guidance(self, public_case: PublicCase) -> str:
        if "fastgpt" not in public_case.repo.lower():
            return ""
        return """

## FastGPT Build/Test Runtime Guide

Use this guide while validating changes in the FastGPT workspace.

- Work from the repository root unless a command explicitly changes directory.
- The workspace may already be prepared by a RepoACES OpenHands FastGPT image. If `/opt/repoaces-oh/openhands-common-commands.sh` exists, use it for quick root-level feedback:
  - `/opt/repoaces-oh/openhands-common-commands.sh env`
  - `/opt/repoaces-oh/openhands-common-commands.sh build`
  - `/opt/repoaces-oh/openhands-common-commands.sh test`
  - `/opt/repoaces-oh/openhands-common-commands.sh compose`
- Prefer `pnpm` through the repository's configured Corepack or image-provided version.
- If dependencies are missing, or a package cannot be found in the workspace, run `pnpm install --frozen-lockfile` from the repository root and record the result. Avoid deleting `node_modules` unless necessary.
- If `build:sdks` exists, run `pnpm run build:sdks` before app builds that depend on generated SDK artifacts.
- Targeted tests are useful while developing, but they do not replace package-level build/type checks.
- If files under `projects/app/**`, `packages/global/**`, or app-facing service types are changed, run `cd projects/app && pnpm build` unless a clear environment blocker prevents it.
- If files under `packages/service/**` are changed, run `cd packages/service && pnpm test` or a narrower Vitest command first, then report whether the package-level test suite was run.
- If files under `projects/code-sandbox/**` are changed, run `cd projects/code-sandbox && pnpm build`; run targeted Vitest tests first if needed, but also run `pnpm test` when the change can affect worker lifecycle, resource limits, security, or API behavior.
- If files under `document/**` are changed, run `cd document && pnpm build`.
- If files under `deploy/dev/**` or Docker Compose files are changed, run `docker compose config` in the relevant compose directory. Use `docker compose up -d` only when runtime services are required for the feature check.
- In the final response, list every validation command, whether it passed, and any exact blocker.
"""
