# RepoACES

RepoACES（Repository-level Agentic Code Engineering System）是一个面向仓库级新功能增量开发的智能体系统原型。当前版本主要围绕 FastGPT feature-add PR case，使用 OpenHands 作为 coding agent 底座，完成任务构造、仓库准备、代码生成、patch 导出、trajectory 记录和最终 build/test 评估。

当前项目还处于原型阶段，重点是验证以下流程：

- 从 `case.yaml` 构造公开任务输入；
- 为 OpenHands 准备干净的 FastGPT base commit workspace；
- 在 WSL/Linux 环境中准备开发依赖；
- 启动 OpenHands 执行 feature implementation；
- 导出 OpenHands 的 `patch.diff` 和 conversation/trajectory；
- 执行 final-evaluator，记录 build/test 结果；
- 支持单 PR 和批量 PR 的自动化运行。

## 目录结构

```text
repoaces/                 # RepoACES 核心模块
scripts/                  # PowerShell/Python 控制脚本
docker/                   # 自定义 OpenHands agent-server 镜像
cases/                    # FastGPT PR case 与基准 patch
docs/                     # 设计与复现文档
web-demo/                 # RepoACES 展示用静态 Web
```

运行过程中会生成以下目录，它们不会提交到 GitHub：

```text
tmp/                      # 实验产物、评估报告、日志
runs/                     # OpenHands 运行状态和会话产物
workspaces/               # FastGPT checkout workspace
recycle_bin/              # 清理出的历史产物
.openhands-home/          # 本地 OpenHands 配置
```

## 前置条件

当前主流程以 Windows 作为控制端，通过 WSL2 + Docker Desktop 运行 Linux workspace 和 OpenHands。

推荐环境：

- Windows 11；
- PowerShell 5.1+ 或 PowerShell 7+；
- Python 3.10+；
- Git；
- Docker Desktop；
- WSL2；
- 一个 Linux WSL 发行版，默认名称为 `Ubuntu-22.04`；
- Docker Desktop 已为该 WSL 发行版启用 WSL Integration；
- 能访问 GitHub、Docker 镜像源、npm/pnpm registry；
- 已在本机 OpenHands 配置好 LLM provider。

安装 Python 依赖：

```powershell
python -m pip install -r requirements.txt
```

## 构建 OpenHands Agent 镜像

当前流程需要一个自定义 OpenHands agent-server 镜像，用于在容器内提供 Node 20、pnpm 和 FastGPT 常用开发工具。

构建命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_openhands_agent_fastgpt.ps1
```

如果网络访问 npm registry 不稳定，可以使用镜像源：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_openhands_agent_fastgpt.ps1 `
  -NpmRegistry "https://registry.npmmirror.com"
```

如果需要代理：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_openhands_agent_fastgpt.ps1 `
  -Proxy "http://127.0.0.1:7890"
```

构建完成后默认镜像为：

```text
repoaces/openhands-agent-fastgpt:node20-pnpm10
```

## OpenHands 模型配置

RepoACES 不会把 API key、base URL 或模型 provider 配置提交到仓库。同事复现时需要在自己的机器上完成 OpenHands LLM 配置。

常用可配置项包括：

```text
REPOACES_OPENHANDS_IMAGE
REPOACES_AGENT_SERVER_IMAGE_REPOSITORY
REPOACES_AGENT_SERVER_IMAGE_TAG
REPOACES_OPENHANDS_HOME_TEMPLATE
REPOACES_OPENHANDS_MODEL
REPOACES_OPENHANDS_HEALTH_TIMEOUT
REPOACES_OPENHANDS_PORT
REPOACES_DOCKER_BACKEND
REPOACES_WSL_DISTRO
REPOACES_WSL_WORKSPACES_ROOT
```

注意：

- `.openhands-home/` 已被 `.gitignore` 忽略；
- 不要提交 OpenHands settings、API key、GitHub token 或 HuggingFace token；
- 模型名称可以通过脚本参数 `-Model` 传入。

## 快速检查

确认 CLI 可用：

```powershell
python -m repoaces.cli --help
```

生成批量运行计划，不真正启动 OpenHands：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\repoaces_batch_by_size.ps1 `
  -OnlyPrs "7008,6660,6644,5776" `
  -RunTag plancheck `
  -PlanOnly
```

如果该命令能正常输出 `case_yaml` 和 `artifact_root`，说明源码层面的路径和 case 元数据基本可用。

## 单 PR 全流程运行

示例：运行 FastGPT PR 6660。

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

如果你的 WSL 发行版名称不是 `Ubuntu-22.04`，例如叫 `Ubuntu`，则改为：

```powershell
-WslDistro Ubuntu
```

主要产物会写入：

```text
tmp/experiments/repoaces/<case-id>/<run-name>/
```

其中关键文件包括：

```text
case/instruction.md
tasks/00-prepare-dev-env/preflight.log
tasks/01-implementation/instruction.md
tasks/01-implementation/patch.diff
tasks/01-implementation/trajectory.json
tasks/01-implementation/conversation/
tasks/02-final-evaluator/candidate.patch
tasks/02-final-evaluator/baseline.patch
tasks/02-final-evaluator/test_output.txt
tasks/02-final-evaluator/final_evaluation_report.json
report/run_state.json
```

## 批量运行

示例：只运行 `7008,6660,6644,5776`。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\repoaces_batch_by_size.ps1 `
  -OnlyPrs "7008,6660,6644,5776" `
  -RunTag repro-7008-6660-6644-5776-001 `
  -Model gpt-5.4 `
  -WslDistro Ubuntu-22.04 `
  -OpenHandsPort 3000 `
  -OpenHandsMaxSeconds 5400 `
  -PollIntervalSeconds 60 `
  -PrepareDevEnvTimeoutSeconds 3600 `
  -FinalEvalTimeoutSeconds 1800 `
  -ContinueOnFailure
```

批量运行日志会写入：

```text
tmp/experiments/repoaces-batches/<run-tag>/
```

## 当前 Case 数据

当前 `cases/18cases/` 下包含多个 FastGPT PR case，每个 case 通常包含：

```text
case.yaml
patches/<case-id>.patch
patches/<case-id>.changed_files.txt
```

`case.yaml` 中记录：

- repo；
- base commit；
- PR number；
- 公开 feature 描述；
- hidden validation 元信息；
- 基准 patch 路径。

OpenHands 只会收到公开任务输入，不会收到 golden patch、head commit 或 changed-files list。

## 当前限制

当前系统仍是研究原型，有几个限制需要注意：

1. FastGPT 的 build/test 环境复杂，不同 base commit 可能需要不同 Node/pnpm/Bun/submodule 状态。
2. 目前 `prepare-dev-env` 是通用环境准备，尚不能完全覆盖所有 PR 的最优评估环境。
3. OpenHands 在生成 patch 过程中不一定会完整运行 build/tests。
4. final-evaluator 当前仍是动态命令选择，后续计划升级为 SWE-bench 风格的 per-instance evaluation image。
5. `pro` submodule 不可用时，root `pnpm test` 可能因为找不到 `@fastgpt/admin` 失败。

后续环境评估方案见：

[docs/evaluation-only-per-instance-image-plan.md](docs/evaluation-only-per-instance-image-plan.md)

复现与路径审计见：

[docs/reproducibility-and-path-audit.md](docs/reproducibility-and-path-audit.md)

## 上传 GitHub 前检查

本项目已添加 `.gitignore`，默认忽略运行产物和本地配置：

```text
tmp/
runs/
workspaces/
recycle_bin/
.openhands-home/
__pycache__/
*.pyc
*.log
*.rar
*.zip
.env
.env.*
```

上传前建议执行：

```powershell
git status --short
```

确认不会提交以下内容：

- OpenHands 本地配置；
- API key、GitHub token、HuggingFace token；
- FastGPT checkout workspace；
- OpenHands conversation 数据库；
- 大型实验日志和临时产物。

## Web Demo

展示用静态页面位于：

```text
web-demo/repoaces/index.html
```

可以直接用浏览器打开，不需要安装 npm 依赖或启动开发服务器。
