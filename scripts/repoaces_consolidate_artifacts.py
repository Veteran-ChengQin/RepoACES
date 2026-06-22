#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_file(src: Path | None, dst: Path) -> Path | None:
    if not src or not src.exists() or not src.is_file():
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def copy_tree(src: Path | None, dst: Path) -> Path | None:
    if not src or not src.exists() or not src.is_dir():
        return None
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(
        src,
        dst,
        ignore=lambda _dir, names: [name for name in names if name.endswith(".lock")],
    )
    return dst


def rel(root: Path, path: Path | None) -> str | None:
    if not path:
        return None
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def load_optional_json(path: Path | None) -> Any | None:
    if not path or not path.exists():
        return None
    try:
        return read_json(path)
    except json.JSONDecodeError:
        return None


def find_first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def find_implementation_log_dir(source_root: Path, instance_id: str | None = None) -> Path | None:
    logs_dir = source_root / "logs"
    if instance_id:
        explicit = logs_dir / instance_id
        return explicit if explicit.exists() else None
    if not logs_dir.exists():
        return None
    candidates = sorted(path for path in logs_dir.iterdir() if path.is_dir())
    return candidates[0] if candidates else None


def find_implementation_trajectory(source_root: Path, instance_id: str | None = None) -> Path | None:
    traj_dir = source_root / "trajs"
    if not traj_dir.exists():
        return None
    candidates = sorted(path for path in traj_dir.glob("*.json") if "summary" not in path.name)
    if instance_id:
        matching = [path for path in candidates if instance_id in path.stem]
        if matching:
            return matching[0]
    return candidates[0] if candidates else None


def build_event_trajectory(conversation_dir: Path, output_path: Path) -> dict[str, Any]:
    events_dir = conversation_dir / "events"
    event_paths = []
    if events_dir.exists():
        event_paths = sorted(
            [path for path in events_dir.glob("event-*.json")],
            key=lambda path: int(re.search(r"event-(\d+)-", path.name).group(1))
            if re.search(r"event-(\d+)-", path.name)
            else -1,
        )
    events = []
    for event_path in event_paths:
        event = load_optional_json(event_path)
        events.append({"file": event_path.name, "event": event})
    trajectory = {
        "format": "repoaces-openhands-event-trajectory",
        "source_conversation_dir": str(conversation_dir),
        "event_count": len(events),
        "events": events,
    }
    write_json(output_path, trajectory)
    return trajectory


def summarize_patch_shape(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {"available": False}
    return {
        "available": True,
        "candidate_patch_exists": report.get("candidate_patch_exists"),
        "golden_changed_file_count": report.get("golden_changed_file_count"),
        "candidate_changed_file_count": report.get("candidate_changed_file_count"),
        "file_overlap_count": report.get("file_overlap_count"),
        "missing_golden_file_count": len(report.get("missing_golden_files") or []),
        "extra_candidate_file_count": len(report.get("extra_candidate_files") or []),
    }


def files_from_patch(path: Path | None) -> list[str]:
    if not path or not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    files = []
    for match in re.finditer(r"^diff --git a/(.*?) b/(.*?)$", text, re.MULTILINE):
        files.append(match.group(2).strip())
    return sorted(set(files))


def write_candidate_diff_report(case_id: str, patch_path: Path | None, output_path: Path) -> Path:
    text = patch_path.read_text(encoding="utf-8", errors="replace") if patch_path and patch_path.exists() else ""
    files = files_from_patch(patch_path)
    report = {
        "case_id": case_id,
        "uses_golden_metadata": False,
        "candidate_patch_exists": bool(patch_path and patch_path.exists()),
        "candidate_patch_non_empty": bool(text.strip()),
        "candidate_changed_file_count": len(files),
        "candidate_changed_files": files,
        "note": "Public candidate diff inspection only. This report intentionally omits golden patch and changed-files metadata.",
    }
    write_json(output_path, report)
    return output_path


def summarize_candidate_diff(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {"available": False}
    return {
        "available": True,
        "candidate_patch_exists": report.get("candidate_patch_exists"),
        "candidate_patch_non_empty": report.get("candidate_patch_non_empty"),
        "candidate_changed_file_count": report.get("candidate_changed_file_count"),
    }


def summarize_legacy_eval_report(report: Any) -> Any:
    if not isinstance(report, dict):
        return None
    if len(report) == 1:
        return next(iter(report.values()))
    return report


def write_case_readme(root: Path) -> Path:
    content = """# case 目录说明

本目录保存 Case Builder 生成的公开任务输入。

- `public_case.json` 是结构化的公开任务源数据，后续所有角色 prompt 都应该优先从这里组装。
- `instruction.md` 是当前传给 coding agent 的实现任务 prompt。
- `requirement_spec.md` 是早期保留的可读需求摘要，目前和 `instruction.md` 有较多重复。后续建议弱化或删除它，将需求事实统一收敛到 `public_case.json`，再按角色生成 implementation / evaluator / repairer prompt。

当前整理没有删除 `requirement_spec.md`，是为了保持已有脚本和历史产物可追溯。
"""
    path = root / "case" / "README.md"
    write_text(path, content)
    return path


def write_repo_intelligence_readme(root: Path) -> Path:
    content = """# repo_intelligence 目录说明

本目录用于保存 Repo Intelligence 模块的输出，目标是让后续 agent 不必完全依赖临场搜索。

预期产物包括：

- `repo_context.json`：仓库结构、关键包、入口模块、重要配置文件摘要。
- `command_map.json`：可复用的安装、构建、测试、lint、局部验证命令。
- `code_graph.json`：与需求相关的文件、符号、调用/依赖关系。
- `codewiki/`：后续接入 CodeWiki 后生成的仓库 wiki、模块说明和检索索引。

本次 `fastgpt-pr-7008/public-only-rerun-001` 没有实际运行 Repo Intelligence/CodeWiki，因此这里之前为空。当前文件只用于说明目录职责；这不是 coding agent 的输入缺失，而是该模块尚未纳入本轮实验。
"""
    path = root / "repo_intelligence" / "README.md"
    write_text(path, content)
    return path


def write_artifacts_md(root: Path, index: dict[str, Any]) -> Path:
    run_id = index.get("run_id", "unknown")
    case_id = index.get("case_id", "unknown")
    content = f"""# RepoACES PR7008 产物目录说明

本文件是当前实验产物的规范化索引。原始文件没有被删除或移动；整理脚本只是把分散在 `case/`、`planning/`、`logs/`、`report/` 中的关键证据复制到统一的 `tasks/` 阶段目录。

## 基本信息

- Case ID：`{case_id}`
- Run ID：`{run_id}`
- 规范产物根目录：`{root}`
- OpenHands 运行态目录：`runs/repoaces-openhands/{run_id}`

`runs/repoaces-openhands/{run_id}` 只作为 OpenHands 的运行缓存和会话源，不建议作为交付产物整体归档；其中可能包含数据库、缓存、临时会话、session key 等运行态文件。当前规范产物统一以本目录为准。

## 推荐目录结构

```text
case/
  public_case.json
  instruction.md
  requirement_spec.md
  README.md
repo_intelligence/
  README.md
tasks/
  01-implementation/
    instruction.md
    trajectory.json
    patch.diff
    result.json
  02-evaluator-initial/
    eval_plan.md
    candidate_diff_report.json
    result.json
  03-public-repair/
    instruction.md
    trajectory.json
    conversation/
    patch.diff
    result.json
  04-evaluator-final/
    eval_plan.md
    patch_shape_report.json
    behavior_queue_id_report.json
    public_repair_final_summary.json
    final-git-status.txt
    result.json
report/
  normalized-artifact-manifest.json
```

## 阶段语义

- `01-implementation`：初始 coding agent 产物。本次不是重新运行得到，而是导入旧的 naive OpenHands run3 patch 和 trajectory。
- `02-evaluator-initial`：针对初始 implementation patch 的 public 评估产物，主要包含候选 diff 摘要、可运行检查计划和是否需要 repair 的结论；不包含 golden changed-files。
- `03-public-repair`：public-only repair agent 产物，包含传给 OpenHands 的修复 instruction、conversation 事件、统一 trajectory 和修复 patch。
- `04-evaluator-final`：针对 repair 后最终 patch 的评估产物，包含 patch-shape、静态行为检查、最终总结和 git 状态。

## 当前结论

- 初始 implementation 旧报告显示粗粒度验证通过；public 初评阶段只能记录候选 diff 和公开验证结果，golden changed-files 覆盖率只能作为 final/private 诊断。
- public-repair 后静态行为检查认为核心 queueId 并发特性“可能满足”，但最终仍未达到 benchmark-resolved：缺少若干基准 PR 关键文件，存在额外文件和锁文件污染，构建/测试环境也未稳定跑通。
- `requirement_spec.md` 与 `instruction.md` 重复是当前 Case Builder 的设计遗留；后续应以 `public_case.json` 为事实源，按角色生成不同 prompt。
- `repo_intelligence/` 为空是因为本轮实验未运行 Repo Intelligence/CodeWiki，不代表该目录无用。

更机器可读的索引见 `report/normalized-artifact-manifest.json`。
"""
    path = root / "ARTIFACTS.md"
    write_text(path, content)
    return path


def consolidate(args: argparse.Namespace) -> dict[str, Any]:
    root = args.artifact_root.resolve()
    source_root = args.implementation_source_root.resolve()
    manifest_path = root / "report" / "artifact-manifest.json"
    manifest = load_optional_json(manifest_path) or {}
    run_state = load_optional_json(root / "report" / "run_state.json") or {}
    run_id = manifest.get("run_id") or run_state.get("run_id") or root.parent.name
    case_id = manifest.get("case_id") or run_state.get("case_id") or root.parent.name

    tasks_dir = root / "tasks"
    report_dir = root / "report"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    patches_dir = root / "patches" if args.copy_patch_aliases else None
    if patches_dir:
        patches_dir.mkdir(parents=True, exist_ok=True)

    case_instruction = root / "case" / "instruction.md"
    eval_plan = root / "report" / "eval_plan.md"
    implementation_patch = root / "logs" / "openhands" / "implementation" / "implementation.patch"
    implementation_log_dir = find_implementation_log_dir(source_root, args.implementation_instance_id)
    legacy_implementation_patch = implementation_log_dir / "patch.diff" if implementation_log_dir else None
    implementation_patch_src = implementation_patch if implementation_patch.exists() else legacy_implementation_patch
    implementation_trajectory = find_implementation_trajectory(source_root, args.implementation_instance_id)
    legacy_eval_report = implementation_log_dir / "report.json" if implementation_log_dir else None

    final_patch_shape_src = root / "report" / "private" / "public-repair" / "patch_shape_report.json"
    behavior_report_src = root / "report" / "private" / "public-repair" / "behavior_queue_id_report.json"
    final_summary_src = root / "report" / "private" / "public-repair" / "public_repair_final_summary.json"

    public_repair_instruction = root / "planning" / "repair_instruction_public.md"
    public_repair_patch = root / "logs" / "openhands" / "public-repair" / "public-repair.patch"
    public_repair_conversation = root / "logs" / "openhands" / "public-repair" / "conversation"
    public_repair_runtime = root / "logs" / "openhands" / "public-repair" / "openhands_runtime_state.json"
    final_git_status = root / "logs" / "openhands" / "public-repair" / "final-git-status.txt"

    copied: dict[str, Any] = {"tasks": {}, "docs": {}}
    if args.copy_patch_aliases:
        copied["patch_aliases"] = {}

    impl_dir = tasks_dir / "01-implementation"
    impl_instruction = copy_file(case_instruction, impl_dir / "instruction.md")
    impl_patch = copy_file(implementation_patch_src, impl_dir / "patch.diff")
    impl_traj = copy_file(implementation_trajectory, impl_dir / "trajectory.json")
    impl_legacy_report = copy_file(legacy_eval_report, impl_dir / "legacy_eval_report.json")
    impl_patch_public = (
        copy_file(implementation_patch_src, patches_dir / "01-implementation.patch") if patches_dir else None
    )
    legacy_report = load_optional_json(legacy_eval_report)
    impl_result = {
        "stage": "01-implementation",
        "role": "coding_agent",
        "source": f"imported from {source_root}",
        "status": "imported_existing_openhands_run",
        "completed": bool(impl_patch),
        "instruction": rel(root, impl_instruction),
        "trajectory": rel(root, impl_traj),
        "patch": rel(root, impl_patch),
        "legacy_eval_report": rel(root, impl_legacy_report),
        "legacy_eval_summary": summarize_legacy_eval_report(legacy_report),
        "note": "This stage was not produced by the current public-only rerun; it imports the earlier naive OpenHands run3 output.",
    }
    write_json(impl_dir / "result.json", impl_result)
    copied["tasks"]["01-implementation"] = impl_result
    if impl_patch_public:
        copied["patch_aliases"]["01-implementation"] = rel(root, impl_patch_public)

    eval_initial_dir = tasks_dir / "02-evaluator-initial"
    initial_eval_plan = copy_file(eval_plan, eval_initial_dir / "eval_plan.md")
    initial_candidate_diff = write_candidate_diff_report(
        case_id,
        impl_patch,
        eval_initial_dir / "candidate_diff_report.json",
    )
    initial_candidate_diff_report = load_optional_json(initial_candidate_diff)
    initial_result = {
        "stage": "02-evaluator-initial",
        "role": "evaluator",
        "status": "completed",
        "completed": bool(initial_candidate_diff),
        "input_patch": rel(root, impl_patch),
        "eval_plan": rel(root, initial_eval_plan),
        "candidate_diff_report": rel(root, initial_candidate_diff),
        "candidate_diff_summary": summarize_candidate_diff(initial_candidate_diff_report),
        "uses_golden_metadata": False,
        "resolved": False,
        "note": "Public initial evaluation inspects the candidate diff and runnable checks only; golden metadata is intentionally excluded.",
    }
    write_json(eval_initial_dir / "result.json", initial_result)
    copied["tasks"]["02-evaluator-initial"] = initial_result

    repair_dir = tasks_dir / "03-public-repair"
    repair_instruction = copy_file(public_repair_instruction, repair_dir / "instruction.md")
    repair_patch = copy_file(public_repair_patch, repair_dir / "patch.diff")
    repair_patch_public = copy_file(public_repair_patch, patches_dir / "03-public-repair.patch") if patches_dir else None
    repair_runtime = copy_file(public_repair_runtime, repair_dir / "openhands_runtime_state.json")
    repair_status = copy_file(final_git_status, repair_dir / "final-git-status.txt")
    repair_conversation = copy_tree(public_repair_conversation, repair_dir / "conversation")
    repair_trajectory_path = None
    repair_event_count = 0
    if repair_conversation:
        trajectory = build_event_trajectory(repair_conversation, repair_dir / "trajectory.json")
        repair_trajectory_path = repair_dir / "trajectory.json"
        repair_event_count = int(trajectory["event_count"])
    repair_result = {
        "stage": "03-public-repair",
        "role": "repairer",
        "source": "current public-only rerun OpenHands conversation",
        "status": "exported_after_openhands_stall",
        "completed": bool(repair_patch),
        "instruction": rel(root, repair_instruction),
        "trajectory": rel(root, repair_trajectory_path),
        "conversation": rel(root, repair_conversation),
        "conversation_event_count": repair_event_count,
        "patch": rel(root, repair_patch),
        "runtime_state": rel(root, repair_runtime),
        "final_git_status": rel(root, repair_status),
        "note": "OpenHands entered dependency-install / validation stall; artifacts were exported before stopping the runtime.",
    }
    write_json(repair_dir / "result.json", repair_result)
    copied["tasks"]["03-public-repair"] = repair_result
    if repair_patch_public:
        copied["patch_aliases"]["03-public-repair"] = rel(root, repair_patch_public)

    eval_final_dir = tasks_dir / "04-evaluator-final"
    final_eval_plan = copy_file(eval_plan, eval_final_dir / "eval_plan.md")
    final_patch_shape = copy_file(final_patch_shape_src, eval_final_dir / "patch_shape_report.json")
    behavior_report = copy_file(behavior_report_src, eval_final_dir / "behavior_queue_id_report.json")
    final_summary = copy_file(final_summary_src, eval_final_dir / "public_repair_final_summary.json")
    final_status = copy_file(final_git_status, eval_final_dir / "final-git-status.txt")
    final_patch_shape_report = load_optional_json(final_patch_shape_src)
    behavior = load_optional_json(behavior_report_src)
    summary = load_optional_json(final_summary_src)
    final_result = {
        "stage": "04-evaluator-final",
        "role": "evaluator",
        "status": "completed",
        "completed": bool(final_patch_shape and behavior_report),
        "input_patch": rel(root, repair_patch),
        "eval_plan": rel(root, final_eval_plan),
        "patch_shape_report": rel(root, final_patch_shape),
        "behavior_queue_id_report": rel(root, behavior_report),
        "public_repair_final_summary": rel(root, final_summary),
        "final_git_status": rel(root, final_status),
        "patch_shape_summary": summarize_patch_shape(final_patch_shape_report),
        "behavior_summary": {
            "available": isinstance(behavior, dict),
            "static_core_feature_likely_satisfied": behavior.get("static_core_feature_likely_satisfied")
            if isinstance(behavior, dict)
            else None,
            "resolved": behavior.get("resolved") if isinstance(behavior, dict) else None,
        },
        "resolved": summary.get("resolved") if isinstance(summary, dict) else False,
        "headline": summary.get("headline") if isinstance(summary, dict) else None,
    }
    write_json(eval_final_dir / "result.json", final_result)
    copied["tasks"]["04-evaluator-final"] = final_result

    case_readme = write_case_readme(root)
    repo_intelligence_readme = write_repo_intelligence_readme(root)
    copied["docs"]["case_readme"] = rel(root, case_readme)
    copied["docs"]["repo_intelligence_readme"] = rel(root, repo_intelligence_readme)

    canonical_layout = {
        "case": "case/",
        "repo_intelligence": "repo_intelligence/",
        "logs": "logs/",
        "reports": "report/",
        "tasks": "tasks/",
    }
    if patches_dir:
        canonical_layout["patch_aliases"] = "patches/"

    index = {
        "case_id": case_id,
        "run_id": run_id,
        "artifact_root": str(root),
        "runtime_root": f"runs/repoaces-openhands/{run_id}",
        "canonical_layout": canonical_layout,
        "copied": copied,
        "notes": [
            "runs/repoaces-openhands/<run_id> is runtime scratch space, not the canonical deliverable directory.",
            "requirement_spec.md is retained for compatibility but duplicates instruction.md in the current prototype.",
            "repo_intelligence is currently explanatory only because this rerun did not execute StaticRepoIntelligence or CodeWiki.",
        ],
    }
    artifacts_md = write_artifacts_md(root, index)
    copied["docs"]["artifact_layout"] = rel(root, artifacts_md)
    index["copied"] = copied
    normalized_manifest = report_dir / "normalized-artifact-manifest.json"
    write_json(normalized_manifest, index)
    return {
        "artifact_root": str(root),
        "normalized_manifest": str(normalized_manifest),
        "artifact_layout": str(artifacts_md),
        "tasks_dir": str(tasks_dir),
        "patches_dir": str(patches_dir) if patches_dir else None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Consolidate RepoACES run artifacts into stage-oriented directories.")
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument(
        "--implementation-source-root",
        type=Path,
        default=Path("tmp/experiments/evaluation/fastgpt/openhands/pr7008-run-003"),
        help="Existing implementation run used as the source for imported implementation trajectory/report.",
    )
    parser.add_argument(
        "--implementation-instance-id",
        help="Optional instance directory name under implementation-source-root/logs.",
    )
    parser.add_argument(
        "--copy-patch-aliases",
        action="store_true",
        help="Also copy stage patches into top-level patches/. Disabled by default to keep tasks/ canonical.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = consolidate(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
