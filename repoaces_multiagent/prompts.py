from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Any

from repoaces.io import read_json

from .stages import stage_definition


def build_stage_instruction(
    *,
    stage: str,
    run_root: Path,
    workspace_path: str,
    case_instruction_path: Path,
    repo_context_path: Path | None = None,
) -> str:
    definition = stage_definition(stage)
    base_instruction = _read_text(case_instruction_path)
    repo_context = _optional_artifact(repo_context_path, max_chars=12000)
    if definition.key == "scope":
        return _scope_instruction(
            base_instruction=base_instruction,
            workspace_path=workspace_path,
            repo_context=repo_context,
        )
    if definition.key == "plan":
        return _plan_instruction(
            base_instruction=base_instruction,
            workspace_path=workspace_path,
            scope=_stage_artifact(run_root, "01-scope-explorer", "scope.json"),
            scope_md=_stage_artifact(run_root, "01-scope-explorer", "scope.md", max_chars=12000),
            repo_context=repo_context,
        )
    if definition.key == "implement":
        return _implement_instruction(
            base_instruction=base_instruction,
            workspace_path=workspace_path,
            scope=_stage_artifact(run_root, "01-scope-explorer", "scope.json"),
            plan=_stage_artifact(run_root, "02-patch-planner", "patch_plan.json"),
            plan_md=_stage_artifact(run_root, "02-patch-planner", "patch_plan.md", max_chars=12000),
        )
    if definition.key == "validate":
        return _validate_instruction(
            base_instruction=base_instruction,
            workspace_path=workspace_path,
            scope=_stage_artifact(run_root, "01-scope-explorer", "scope.json"),
            plan=_stage_artifact(run_root, "02-patch-planner", "patch_plan.json"),
            implement_summary=_stage_artifact(
                run_root,
                "03-patch-implementer",
                "implementation_summary.md",
                max_chars=12000,
            ),
            modified_files=_stage_artifact(run_root, "03-patch-implementer", "modified_files.json"),
        )
    raise AssertionError(f"Unhandled stage: {stage}")


def _scope_instruction(*, base_instruction: str, workspace_path: str, repo_context: str) -> str:
    return dedent(
        f"""
        # RepoACES MultiAgent Stage: Scope Explorer

        You are the Scope Explorer. Your job is to determine the repository change
        scope for this feature request before any implementation starts.

        ## Hard Rules

        - Work in repository path: `{workspace_path}`.
        - Do not modify repository files.
        - You may run read-only search/inspection commands such as `rg`, `find`, `ls`,
          `git grep`, `git status`, `sed`, `cat`, and package metadata reads.
        - Write all stage outputs only under `/repoaces_stage`.
        - If you discover that the initial requirement is ambiguous, record the
          uncertainty and the evidence. Do not invent hidden golden patch details.

        ## Original Public Task

        {base_instruction}

        ## Existing Repo Intelligence

        {repo_context}

        ## Required Outputs

        Create `/repoaces_stage/scope.json` with this shape:

        ```json
        {{
          "stage": "scope",
          "status": "completed",
          "primary_files": [
            {{"path": "...", "reason": "...", "evidence": ["..."]}}
          ],
          "supporting_files": [
            {{"path": "...", "reason": "...", "evidence": ["..."]}}
          ],
          "type_or_contract_files": [
            {{"path": "...", "reason": "...", "evidence": ["..."]}}
          ],
          "test_files": [
            {{"path": "...", "reason": "...", "evidence": ["..."]}}
          ],
          "documentation_or_config_files": [
            {{"path": "...", "reason": "...", "evidence": ["..."]}}
          ],
          "suggested_validation_commands": [
            {{"command": "...", "reason": "...", "required_for_confidence": true}}
          ],
          "risks": [
            {{"risk": "...", "why_it_matters": "...", "mitigation": "..."}}
          ],
          "uncertainties": [
            {{"question": "...", "evidence_needed": "..."}}
          ],
          "search_log": [
            {{"command": "...", "key_finding": "..."}}
          ]
        }}
        ```

        Also create `/repoaces_stage/scope.md` for humans. The markdown should
        explain the scope boundary, important files, risks, and validation hints.
        """
    ).strip()


def _plan_instruction(
    *,
    base_instruction: str,
    workspace_path: str,
    scope: str,
    scope_md: str,
    repo_context: str,
) -> str:
    return dedent(
        f"""
        # RepoACES MultiAgent Stage: Patch Planner

        You are the Patch Planner. Convert the feature requirement and Scope
        Explorer output into a concrete patch generation plan.

        ## Hard Rules

        - Work in repository path: `{workspace_path}`.
        - Do not modify repository files.
        - You may run extra read-only searches if the scope appears incomplete.
        - If you find evidence that the Scope Explorer missed important files or
          made a wrong assumption, record the correction in `scope_adjustments`.
        - Write all outputs only under `/repoaces_stage`.

        ## Original Public Task

        {base_instruction}

        ## Scope Explorer JSON

        {scope}

        ## Scope Explorer Notes

        {scope_md}

        ## Repo Intelligence

        {repo_context}

        ## Required Outputs

        Create `/repoaces_stage/patch_plan.json` with this shape:

        ```json
        {{
          "stage": "plan",
          "status": "completed",
          "scope_assessment": {{
            "scope_is_sufficient": true,
            "scope_adjustments": [
              {{"path": "...", "reason": "...", "evidence": "..."}}
            ]
          }},
          "implementation_strategy": "...",
          "patch_steps": [
            {{
              "step": 1,
              "target_files": ["..."],
              "change": "...",
              "reason": "...",
              "acceptance_check": "..."
            }}
          ],
          "tests_or_checks_to_update": [
            {{"path_or_command": "...", "reason": "..."}}
          ],
          "validation_plan": [
            {{"command": "...", "cwd": "...", "reason": "...", "required": true}}
          ],
          "risk_controls": [
            {{"risk": "...", "control": "..."}}
          ],
          "implementation_constraints": [
            "..."
          ]
        }}
        ```

        Also create `/repoaces_stage/patch_plan.md` for humans.
        """
    ).strip()


def _implement_instruction(
    *,
    base_instruction: str,
    workspace_path: str,
    scope: str,
    plan: str,
    plan_md: str,
) -> str:
    return dedent(
        f"""
        # RepoACES MultiAgent Stage: Patch Implementer

        You are the Patch Implementer. Apply the feature change in the workspace
        according to the plan. This is the only stage whose main job is to edit
        repository files.

        ## Hard Rules

        - Work in repository path: `{workspace_path}`.
        - Follow the Patch Planner output unless you find concrete repository
          evidence that the plan is wrong or incomplete.
        - If you deviate from the plan, create `/repoaces_stage/plan_deviation.md`
          explaining the old plan, the evidence, and the actual change.
        - Keep changes scoped to the feature request.
        - Write stage outputs under `/repoaces_stage`.
        - Do not browse the original pull request, golden patch, or hidden answer.

        ## Original Public Task

        {base_instruction}

        ## Scope JSON

        {scope}

        ## Patch Plan JSON

        {plan}

        ## Patch Plan Notes

        {plan_md}

        ## Required Outputs

        Modify the repository as needed. Then create:

        - `/repoaces_stage/implementation_summary.md`
        - `/repoaces_stage/modified_files.json`

        `modified_files.json` shape:

        ```json
        {{
          "stage": "implement",
          "status": "completed",
          "modified_files": [
            {{"path": "...", "reason": "...", "plan_step": 1}}
          ],
          "new_files": [
            {{"path": "...", "reason": "...", "planned_component": "..."}}
          ],
          "plan_step_status": [
            {{"step": 1, "status": "done", "notes": "..."}}
          ],
          "validation_commands_run_by_implementer": [
            {{"command": "...", "returncode": 0, "summary": "..."}}
          ],
          "known_limitations": [
            "..."
          ]
        }}
        ```
        """
    ).strip()


def _validate_instruction(
    *,
    base_instruction: str,
    workspace_path: str,
    scope: str,
    plan: str,
    implement_summary: str,
    modified_files: str,
) -> str:
    return dedent(
        f"""
        # RepoACES MultiAgent Stage: Developer Validator

        You are the Developer Validator. Inspect the modified workspace and run
        relevant build/test/dev/docker-compose checks. Your role is to provide
        development feedback before the independent final evaluator runs.

        ## Hard Rules

        - Work in repository path: `{workspace_path}`.
        - You may run build/test/typecheck/docker compose config commands.
        - Do not intentionally change feature code. Build caches and generated
          outputs may appear, but your report must distinguish them from source
          changes.
        - If Scope or Plan outputs are incomplete, record the evidence and adjust
          the validation behavior accordingly.
        - Write all outputs only under `/repoaces_stage`.
        - Final evaluator remains independent; do not claim final benchmark pass.

        ## Original Public Task

        {base_instruction}

        ## Scope JSON

        {scope}

        ## Patch Plan JSON

        {plan}

        ## Implementation Summary

        {implement_summary}

        ## Modified Files JSON

        {modified_files}

        ## FastGPT Validation Guidance

        - Run `git diff --check`.
        - If `build:sdks` exists, run `pnpm run build:sdks` before app/package
          builds that depend on SDK artifacts.
        - If files under `projects/app`, `packages/global`, or app-facing
          service types changed, run `cd projects/app && pnpm build` unless a
          concrete environment blocker prevents it.
        - If files under `packages/service` changed, run `cd packages/service &&
          pnpm test` or an evidence-backed narrower command.
        - If files under `projects/code-sandbox` changed, run `cd
          projects/code-sandbox && pnpm build`; run tests relevant to API,
          worker lifecycle, queueing, resource limits, security, and error paths.
        - If Docker Compose files changed, run `docker compose config` in the
          relevant directory.

        ## Required Outputs

        Create `/repoaces_stage/validation_report.json`:

        ```json
        {{
          "stage": "validate",
          "status": "completed",
          "overall_passed": false,
          "scope_or_plan_adjustments": [
            {{"issue": "...", "evidence": "...", "validation_response": "..."}}
          ],
          "commands": [
            {{
              "command": "...",
              "cwd": "...",
              "returncode": 0,
              "passed": true,
              "required": true,
              "summary": "..."
            }}
          ],
          "feature_behavior_checks": [
            {{"check": "...", "result": "passed|failed|not_run", "evidence": "..."}}
          ],
          "failed_commands": [],
          "environment_blockers": [],
          "recommended_repair": [
            {{"priority": "high", "instruction": "...", "evidence": "..."}}
          ]
        }}
        ```

        Also create `/repoaces_stage/validation_summary.md`. Include exact
        commands and concise outcomes.
        """
    ).strip()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _optional_artifact(path: Path | None, *, max_chars: int) -> str:
    if not path or not path.exists():
        return "(not available)"
    text = _read_text(path)
    return text[:max_chars] + ("\n...[truncated]" if len(text) > max_chars else "")


def _stage_artifact(run_root: Path, stage_dir: str, filename: str, *, max_chars: int = 20000) -> str:
    path = run_root / "tasks" / stage_dir / filename
    if not path.exists():
        return f"(missing: {path})"
    if path.suffix == ".json":
        try:
            return json.dumps(read_json(path), ensure_ascii=False, indent=2)[:max_chars]
        except Exception:
            pass
    text = _read_text(path)
    return text[:max_chars] + ("\n...[truncated]" if len(text) > max_chars else "")
