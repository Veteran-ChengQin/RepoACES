# 7008/7138 通过 evaluator 的产物与一键运行命令

本文记录当前已通过 final evaluator 的两个 FastGPT case，以及使用 `scripts/repoaces_fullflow.ps1` 重新启动全流程的命令。

## 已通过 evaluator 的产物路径

### fastgpt-pr-7008

通过 evaluator 的 run：

```text
tmp/experiments/repoaces/fastgpt-pr-7008/devimage-pr7008-002
```

关键产物：

```text
tmp/experiments/repoaces/fastgpt-pr-7008/devimage-pr7008-002/tasks/01-implementation/instruction.md
tmp/experiments/repoaces/fastgpt-pr-7008/devimage-pr7008-002/tasks/01-implementation/patch.diff
tmp/experiments/repoaces/fastgpt-pr-7008/devimage-pr7008-002/tasks/01-implementation/trajectory.json
tmp/experiments/repoaces/fastgpt-pr-7008/devimage-pr7008-002/tasks/01-implementation/conversation/
tmp/experiments/repoaces/fastgpt-pr-7008/devimage-pr7008-002/tasks/02-final-evaluator/candidate.patch
tmp/experiments/repoaces/fastgpt-pr-7008/devimage-pr7008-002/tasks/02-final-evaluator/baseline.patch
tmp/experiments/repoaces/fastgpt-pr-7008/devimage-pr7008-002/tasks/02-final-evaluator/test_output.txt
tmp/experiments/repoaces/fastgpt-pr-7008/devimage-pr7008-002/tasks/02-final-evaluator/final_evaluation_report.json
tmp/experiments/repoaces/fastgpt-pr-7008/devimage-pr7008-002/report/run_state.json
```

对应开发镜像：

```text
repoaces/oh-fastgpt-7008:4af1ef776748
```

对应评估镜像：

```text
repoaces/eval-7008:4af1ef776748
```

### fastgpt-pr-7138

通过 evaluator 的 run：

```text
tmp/experiments/repoaces/fastgpt-pr-7138/devimage-pr7138-001
```

关键产物：

```text
tmp/experiments/repoaces/fastgpt-pr-7138/devimage-pr7138-001/tasks/01-implementation/instruction.md
tmp/experiments/repoaces/fastgpt-pr-7138/devimage-pr7138-001/tasks/01-implementation/patch.diff
tmp/experiments/repoaces/fastgpt-pr-7138/devimage-pr7138-001/tasks/01-implementation/trajectory.json
tmp/experiments/repoaces/fastgpt-pr-7138/devimage-pr7138-001/tasks/01-implementation/conversation/
tmp/experiments/repoaces/fastgpt-pr-7138/devimage-pr7138-001/tasks/02-final-evaluator/candidate.patch
tmp/experiments/repoaces/fastgpt-pr-7138/devimage-pr7138-001/tasks/02-final-evaluator/baseline.patch
tmp/experiments/repoaces/fastgpt-pr-7138/devimage-pr7138-001/tasks/02-final-evaluator/test_output.txt
tmp/experiments/repoaces/fastgpt-pr-7138/devimage-pr7138-001/tasks/02-final-evaluator/final_evaluation_report.json
tmp/experiments/repoaces/fastgpt-pr-7138/devimage-pr7138-001/report/run_state.json
```

对应开发镜像：

```text
repoaces/oh-fastgpt-7138:ffa1037a3443
```

对应评估镜像：

```text
repoaces/eval-7138:ffa1037a3443
```

## 一键启动 fullflow

运行前需要确保：

- Docker Desktop 正常运行；
- Docker Desktop 已对 `Ubuntu-22.04` 开启 WSL Integration；
- 本机已经配置 OpenHands LLM provider；
- 对应的开发镜像和 evaluator 镜像已经存在，或网络环境允许脚本构建/拉取基础镜像；
- 若使用开发镜像种子 workspace，需要传入 `-SeedWorkspaceFromImage` 和对应 `-DevImage`。

### 启动 fastgpt-pr-7138

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\repoaces_fullflow.ps1 `
  -Case .\cases\18cases\fastgpt-pr-7138\case.yaml `
  -RunName repro-pr7138-001 `
  -Model gpt-5.4 `
  -WslDistro Ubuntu-22.04 `
  -OpenHandsPort 3000 `
  -OpenHandsMaxSeconds 5400 `
  -PollIntervalSeconds 60 `
  -PrepareDevEnvTimeoutSeconds 3600 `
  -FinalEvalTimeoutSeconds 2400 `
  -SeedWorkspaceFromImage `
  -DevImage repoaces/oh-fastgpt-7138:ffa1037a3443
```

### 启动 fastgpt-pr-7008

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\repoaces_fullflow.ps1 `
  -Case .\cases\18cases\fastgpt-pr-7008\case.yaml `
  -RunName repro-pr7008-001 `
  -Model gpt-5.4 `
  -WslDistro Ubuntu-22.04 `
  -OpenHandsPort 3000 `
  -OpenHandsMaxSeconds 5400 `
  -PollIntervalSeconds 60 `
  -PrepareDevEnvTimeoutSeconds 3600 `
  -FinalEvalTimeoutSeconds 2400 `
  -SeedWorkspaceFromImage `
  -DevImage repoaces/oh-fastgpt-7008:4af1ef776748
```

## 说明

`tmp/`、`runs/`、`workspaces/`、`.openhands-home/` 都是本地运行产物或本地配置，不提交到 GitHub。clone 后重新运行 fullflow 会在本机重新生成这些目录。

当前 evaluator 通过只说明候选 patch 通过了现有命令集。对于 PR 7008 这种新增并发语义的 case，后续仍建议增加 evaluator 自己注入的黑盒行为测试，而不是只依赖候选 patch 中的测试文件。
