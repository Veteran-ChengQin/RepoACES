# RepoACES

RepoACES（Repository-level Agentic Code Engineering System）是一个面向仓库级新功能增量开发的 AI Native 软件研发智能体系统原型。

当前项目以 FastGPT feature-add Pull Request 为主要实验对象，围绕“从需求描述到功能新增”的研发流程，组织 OpenHands、仓库上下文、开发环境镜像、补丁生成和最终评估，产出可复现实验记录。

## 当前能力

RepoACES 目前包含两套实现：

- `repoaces/`：第一版单 Agent 流程。主要验证 Case Builder、workspace 准备、OpenHands 代码实现、patch 导出、final evaluator 等基础链路。
- `repoaces_multiagent/`：MultiAgent 版流程。将 OpenHands 的一次性自由开发拆分为多个阶段，让每个阶段都有明确职责和可检查产物。

MultiAgent 版当前是主线实验流程，阶段如下：

```text
1. init-run
2. prepare-workspace
3. static-intel
4. prepare-dev-env
5. scope explorer
6. patch planner
7. patch implementer
8. developer validator
9. final evaluator
```

其中 5-8 阶段仍由 OpenHands 执行，但每个阶段使用不同 prompt 和不同产物目录：

```text
tasks/01-scope-explorer/
tasks/02-patch-planner/
tasks/03-patch-implementer/
tasks/04-developer-validator/
tasks/05-final-evaluator/
```

## 目录结构

```text
repoaces/                         # 第一版 RepoACES 核心模块
repoaces_multiagent/              # MultiAgent 版 RepoACES
scripts/                          # PowerShell/Python 控制脚本
cases/18cases/                    # 早期 FastGPT PR case
cases/13cases_6_28/               # 新增 13 个 FastGPT PR case
docker/compose-bundle/            # 早期 final evaluator 镜像包
docker/openhands-image-bundle/    # 早期 OpenHands dev image 包
docker/13-dev-image-bundle/       # 新增 13 case 的 OpenHands 开发镜像包
docker/13-evaluator-image-bundle/ # 新增 13 case 的 final evaluator 镜像包
docs/                             # 设计、复现、评估方案文档
web-demo/                         # 演示用静态 Web
```

运行时会生成以下目录，这些目录默认不提交到 GitHub：

```text
tmp/               # 实验产物、评估报告、日志
runs/              # OpenHands 运行状态和临时产物
workspaces/        # Windows 侧 FastGPT checkout workspace
recycle_bin/       # 清理出的历史产物
.openhands-home/   # 本地 OpenHands 配置，可能包含密钥
```

## 前置条件

当前复现流程以 Windows 作为控制端，通过 WSL2 和 Docker Desktop 运行 Linux workspace、OpenHands agent-server 和 evaluator 镜像。

推荐环境：

- Windows 11
- PowerShell 5.1+ 或 PowerShell 7+
- Python 3.10+
- Git
- Docker Desktop
- WSL2
- Ubuntu 22.04 WSL 发行版，默认名称为 `Ubuntu-22.04`
- Docker Desktop 已为该 WSL 发行版启用 WSL Integration
- 可以访问 GitHub、Docker 镜像源、npm/pnpm registry
- 已在本地配置 OpenHands 可用的 LLM provider

安装 Python 依赖：

```powershell
python -m pip install -r requirements.txt
```

检查 Docker 和 WSL：

```powershell
docker info
wsl -l -v
```

## OpenHands 与模型配置

RepoACES 不提交任何 API key、base URL、GitHub token 或 OpenHands settings。同事复现时需要在本机配置 OpenHands LLM provider。

常用环境变量：

```powershell
$env:REPOACES_OPENHANDS_HOME_TEMPLATE = "D:\path\to\RepoACES\.openhands-home"
$env:REPOACES_OPENHANDS_PORT = "3000"
$env:PYTHONUNBUFFERED = "1"
```

模型名称通过 CLI 参数传入，例如：

```powershell
--model gpt-5.4
```

不要提交以下内容：

- `.openhands-home/`
- OpenHands settings
- API key
- GitHub token
- HuggingFace token
- 大型运行日志和实验产物

## 单个 MultiAgent Fullflow

以 FastGPT PR 7138 为例：

```powershell
$env:REPOACES_OPENHANDS_HOME_TEMPLATE = "D:\projects\llm4se\AI_Developer_Agent_System\.openhands-home"
$env:REPOACES_OPENHANDS_PORT = "3000"
$env:PYTHONUNBUFFERED = "1"

python -m repoaces_multiagent.cli fullflow `
  --case cases\18cases\fastgpt-pr-7138\case.yaml `
  --run-name multiagent-pr7138-demo-001 `
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

如果你的 WSL 发行版名称不是 `Ubuntu-22.04`，需要修改：

```powershell
--wsl-distro Ubuntu
```

主要产物会写入：

```text
tmp/experiments/repoaces-multiagent/<case-id>/<run-name>/
```

关键产物包括：

```text
tasks/01-scope-explorer/instruction.md
tasks/01-scope-explorer/scope.json
tasks/01-scope-explorer/trajectory.json

tasks/02-patch-planner/patch_plan.json
tasks/02-patch-planner/trajectory.json

tasks/03-patch-implementer/patch.diff
tasks/03-patch-implementer/trajectory.json

tasks/04-developer-validator/validation_report.json
tasks/04-developer-validator/trajectory.json

tasks/05-final-evaluator/candidate.patch
tasks/05-final-evaluator/baseline.patch
tasks/05-final-evaluator/final_evaluation_report.json

report/run_state.json
report/multiagent-manifest.json
```

## 新增 13 Case 批量实验

新增 case 位于：

```text
cases/13cases_6_28/
```

对应的 OpenHands 开发镜像配置位于：

```text
docker/13-dev-image-bundle/
```

对应的最终评估镜像配置位于：

```text
docker/13-evaluator-image-bundle/
```

批量脚本：

```text
scripts/repoaces_multiagent_batch_13cases.ps1
```

该脚本默认跳过已经通过 evaluator 的 `7008` 和 `7138`，实际运行其余 11 个 case。

只生成计划，不启动实验：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\repoaces_multiagent_batch_13cases.ps1 `
  -PlanOnly `
  -RunNamePrefix multiagent-13cases-plan
```

构建缺失镜像并运行完整批量实验：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\repoaces_multiagent_batch_13cases.ps1 `
  -RunNamePrefix multiagent-13cases-001 `
  -Model gpt-5.4 `
  -WslDistro Ubuntu-22.04 `
  -OpenHandsPort 3000 `
  -PrepareTimeout 3600 `
  -StageTimeout 3600 `
  -FinalEvalTimeout 3600 `
  -PollInterval 60 `
  -BuildMissingImages `
  -SkipEvaluatorImageVerify
```

批量总控产物：

```text
tmp/experiments/repoaces-multiagent-batches/<run-name>/
```

每个 case 的 fullflow 产物：

```text
tmp/experiments/repoaces-multiagent/<case-id>/<run-name>-pr<pr-number>/
```

## 手动构建 13 Case 镜像

构建某个 PR 的 OpenHands 开发镜像：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\docker\13-dev-image-bundle\scripts\Build-OHImage.ps1 `
  -Pr 7138 `
  -NpmRegistry https://registry.npmmirror.com
```

构建某个 PR 的 final evaluator 镜像：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\docker\13-evaluator-image-bundle\scripts\Build-PrImage.ps1 `
  -Pr 7138 `
  -NpmRegistry https://registry.npmmirror.com `
  -SkipVerify
```

运行某个 PR 的 evaluator：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\docker\13-evaluator-image-bundle\scripts\Run-PrEval.ps1 `
  -Pr 7138 `
  -Mode all `
  -Patch D:\path\to\candidate.patch
```

## 第一版单 Agent Fullflow

第一版仍保留在 `repoaces/` 中，可用于对照实验。

示例：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\repoaces_fullflow.ps1 `
  -Case .\cases\18cases\fastgpt-pr-6660\case.yaml `
  -RunName repro-pr6660-001 `
  -Model gpt-5.4 `
  -WslDistro Ubuntu-22.04 `
  -OpenHandsPort 3000 `
  -OpenHandsMaxSeconds 5400 `
  -PollIntervalSeconds 60
```

主要产物：

```text
tmp/experiments/repoaces/<case-id>/<run-name>/
```

## 当前边界

当前系统仍是研究原型，需要注意：

1. FastGPT 的构建和测试环境随 base commit 变化明显，不同 PR 可能需要不同 Node、pnpm、Bun、submodule 或 compose 条件。
2. `prepare-dev-env` 通过 per-case dev image 改善 OpenHands 的开发环境，但仍不能保证 OpenHands 一定主动运行足够的 build/test。
3. final evaluator 当前主要覆盖环境、语法、构建、通用测试和 docker compose config，不等价于完整业务行为验证。
4. 对新增文件命名高度自由的 feature，golden patch 的文件级对比只能作为辅助信号，不能作为唯一评估标准。
5. 大批量运行会显著占用 Docker 存储空间，实验后需要按需清理镜像、容器、volume 和 `tmp/` 产物。

相关设计文档：

```text
docs/evaluation-only-per-instance-image-plan.md
docs/reproducibility-and-path-audit.md
repoaces/ARTIFACT_RECORDING.md
repoaces_multiagent/README.md
```

## 上传 GitHub 前检查

提交前建议执行：

```powershell
git status --short
```

确认不会提交：

- `.openhands-home/`
- `tmp/`
- `runs/`
- `workspaces/`
- `recycle_bin/`
- `.env` 或真实密钥文件
- 大型实验日志
- 本地编辑器或 Obsidian 配置

