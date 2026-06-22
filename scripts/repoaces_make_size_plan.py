from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a RepoACES batch plan from fastgpt_summary_cases.json")
    parser.add_argument("--summary-json", required=True, type=Path)
    parser.add_argument("--sizes", required=True, help="Comma-separated size labels, e.g. size/L,size/S,size/XL")
    parser.add_argument("--only-prs", default="", help="Comma-separated PR numbers to include; overrides size selection")
    parser.add_argument("--run-last-prs", default="", help="Comma-separated PR numbers to move to the end")
    parser.add_argument("--skip-prs", default="", help="Comma-separated PR numbers to exclude from the plan")
    parser.add_argument("--run-tag", required=True)
    args = parser.parse_args()

    sizes = {item.strip() for item in args.sizes.split(",") if item.strip()}
    only_prs = [int(item.strip()) for item in args.only_prs.split(",") if item.strip()]
    only_pr_set = set(only_prs)
    run_last = [int(item.strip()) for item in args.run_last_prs.split(",") if item.strip()]
    skip_prs = {int(item.strip()) for item in args.skip_prs.split(",") if item.strip()}

    cases = json.loads(args.summary_json.read_text(encoding="utf-8-sig"))
    available_prs = {int(case["pr_number"]) for case in cases}
    missing_prs = sorted(only_pr_set - available_prs)
    if missing_prs:
        raise SystemExit(f"Requested PR(s) not found in summary json: {', '.join(map(str, missing_prs))}")

    if only_prs:
        selected = [
            case
            for case in cases
            if int(case["pr_number"]) in only_pr_set and int(case["pr_number"]) not in skip_prs
        ]
    else:
        selected = [
            case
            for case in cases
            if case.get("size_label") in sizes and int(case["pr_number"]) not in skip_prs
        ]

    def sort_key(case: dict) -> tuple:
        pr = int(case["pr_number"])
        if only_prs:
            return (only_prs.index(pr),)
        return (
            1 if pr in run_last else 0,
            run_last.index(pr) if pr in run_last else -1,
            str(case.get("size_label", "")),
            int(case.get("changed_files", 0)),
            -pr,
        )

    plan = []
    for case in sorted(selected, key=sort_key):
        case_id = str(case["id"])
        pr = int(case["pr_number"])
        plan.append(
            {
                "id": case_id,
                "pr_number": pr,
                "size_label": case.get("size_label"),
                "changed_files": int(case.get("changed_files", 0)),
                "title_raw": case.get("title_raw"),
                "case_yaml": f"cases\\18cases\\{case_id}\\case.yaml",
                "run_name": f"{args.run_tag}-{case_id}",
                "artifact_root": f"tmp\\experiments\\repoaces\\{case_id}\\{args.run_tag}",
                "run_last": pr in run_last,
            }
        )

    print(json.dumps(plan, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
