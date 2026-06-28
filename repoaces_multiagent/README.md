# RepoACES MultiAgent

`repoaces_multiagent/` 是 RepoACES 的多智能体工作流原型。它不替换现有 `repoaces/` 第一版实现，而是在现有能力之上拆出四个 OpenHands-backed 阶段：

```text
01-scope-explorer       确定变更范围，只读，输出 scope.json / scope.md
02-patch-planner        生成 patch 计划，只读，输出 patch_plan.json / patch_plan.md
03-patch-implementer    按计划修改 workspace，输出 patch.diff / implementation_summary.md
04-developer-validator  运行开发期 build/test/check，输出 validation_report.json
05-final-evaluator      复用现有 FinalEvaluator，独立评估 implementer patch
```

`prepare-dev-env` 和 final evaluator 的核心逻辑继续复用第一版 RepoACES。MultiAgent 新增的是阶段边界、阶段 prompt、阶段产物与 OpenHands 多次编排。

## 设计约束

- 每个阶段仍使用 OpenHands 作为执行 agent。
- Scope Explorer 和 Patch Planner 原则上不能修改仓库；如果产生 diff，会记录 `read_only_violation.patch` 并清理 workspace。
- 每个阶段的产物目录会额外挂载到 OpenHands sandbox 的 `/repoaces_stage`，阶段输出写到这里，避免污染代码仓库。
- Patch Implementer 是唯一主要修改源码的阶段，候选补丁固定输出到：

```text
tasks/03-patch-implementer/patch.diff
```

- Developer Validator 可以运行 build/test，但不覆盖 implementer patch；最终评估使用 implementer patch。
- 如果后续阶段发现上游阶段产物有问题，可以在有仓库证据的情况下调整当前行为，并把调整写入当前阶段报告。

## CLI

查看命令：

```powershell
python -m repoaces_multiagent.cli --help
```

初始化一个 run：

```powershell
python -m repoaces_multiagent.cli init-run `
  --case cases\18cases\fastgpt-pr-7138\case.yaml `
  --out tmp\experiments\repoaces-multiagent\fastgpt-pr-7138\demo-001 `
  --workspace-path /workspace/project
```

完整流程示例：

```powershell
$env:REPOACES_OPENHANDS_HOME_TEMPLATE='D:\projects\llm4se\AI_Developer_Agent_System\.openhands-home'

python -m repoaces_multiagent.cli fullflow `
  --case cases\18cases\fastgpt-pr-7138\case.yaml `
  --run-name multiagent-pr7138-001 `
  --workspace-path /workspace/project `
  --model gpt-5.4 `
  --wsl-distro Ubuntu-22.04 `
  --dev-image repoaces/oh-fastgpt-7138:ffa1037a3443 `
  --seed-workspace-from-image `
  --prepare-timeout 3600 `
  --stage-timeout 3600 `
  --final-eval-timeout 2400 `
  --poll-interval 60
```

也可以分阶段运行：

```powershell
python -m repoaces_multiagent.cli run-stage --artifact-root <run-root> --stage scope --model gpt-5.4
python -m repoaces_multiagent.cli run-stage --artifact-root <run-root> --stage plan --model gpt-5.4
python -m repoaces_multiagent.cli run-stage --artifact-root <run-root> --stage implement --model gpt-5.4
python -m repoaces_multiagent.cli run-stage --artifact-root <run-root> --stage validate --model gpt-5.4
python -m repoaces_multiagent.cli final-evaluate --case <case.yaml> --artifact-root <run-root>
```

## 主要产物

```text
tasks/01-scope-explorer/instruction.md
tasks/01-scope-explorer/scope.json
tasks/01-scope-explorer/scope.md
tasks/01-scope-explorer/trajectory.json

tasks/02-patch-planner/patch_plan.json
tasks/02-patch-planner/patch_plan.md

tasks/03-patch-implementer/patch.diff
tasks/03-patch-implementer/implementation_summary.md
tasks/03-patch-implementer/modified_files.json

tasks/04-developer-validator/validation_report.json
tasks/04-developer-validator/validation_summary.md

tasks/05-final-evaluator/final_evaluation_report.json
report/run_state.json
report/multiagent-manifest.json
```
