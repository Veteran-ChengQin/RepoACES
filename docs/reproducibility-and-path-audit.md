# RepoACES 复现前置条件与路径检查

本文档用于在上传 GitHub 前检查当前 RepoACES 原型的复现条件、路径可移植性和不应提交的运行产物。

## 1. 推荐运行环境

当前主流程以 Windows 作为控制端，通过 WSL2 + Docker Desktop 启动 Linux 工作区和 OpenHands。

推荐环境：

- Windows 11
- PowerShell 5.1+ 或 PowerShell 7+
- Python 3.10+
- Git for Windows
- Docker Desktop
- WSL2
- 一个 Linux WSL 发行版，默认脚本参数为 `Ubuntu-22.04`
- Docker Desktop 已开启对应 WSL 发行版的 WSL Integration
- 能访问 GitHub、Docker Hub/GHCR、OpenHands 镜像源、npm/pnpm registry

Python 依赖：

```powershell
python -m pip install -r requirements.txt
```

Docker 相关镜像：

```text
docker.openhands.dev/openhands/openhands:1.8
ghcr.io/openhands/agent-server:1.26.0-python
repoaces/openhands-agent-fastgpt:node20-pnpm10
```

其中 `repoaces/openhands-agent-fastgpt:node20-pnpm10` 是本项目构建的自定义 OpenHands agent-server 镜像。

构建命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_openhands_agent_fastgpt.ps1
```

网络不稳定时可以使用 npm 镜像源或代理：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_openhands_agent_fastgpt.ps1 `
  -NpmRegistry "https://registry.npmmirror.com"
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_openhands_agent_fastgpt.ps1 `
  -Proxy "http://127.0.0.1:7890"
```

## 2. OpenHands LLM 配置

RepoACES 当前通过 OpenHands 调用模型。模型名称可以通过脚本参数传入：

```powershell
-Model gpt-5.4
```

但 API key、base URL、provider 映射等 OpenHands 运行时配置通常来自本地 `.openhands-home/settings.json` 或 OpenHands 自身配置。

注意：

- `.openhands-home/` 已被 `.gitignore` 忽略，不能提交到 GitHub。
- 不要把 API key、GitHub token、HuggingFace token 写入仓库。
- 同事复现时需要在自己的机器上配置 OpenHands 模型 provider。

当前代码会读取以下环境变量调整 OpenHands 运行方式：

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

## 3. 一键运行命令

单个 PR 全流程：

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

批量运行指定 PR：

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

如果同事的 WSL 发行版名称不是 `Ubuntu-22.04`，需要改 `-WslDistro`，例如：

```powershell
-WslDistro Ubuntu
```

## 4. 路径可移植性检查

### 主流程路径

主流程已经尽量使用相对路径：

- `scripts/repoaces_fullflow.ps1`
- `scripts/repoaces_batch_by_size.ps1`
- `repoaces/cli.py`
- `repoaces/agent_orchestrator.py`

默认运行产物路径：

```text
tmp/experiments/repoaces/<case-id>/<run-name>/
workspaces/repoaces-runs/<run-id>/
runs/repoaces-openhands/<run-id>/
```

这些目录都属于运行产物，不应提交。

### WSL 路径

WSL 内部 workspace 默认放在：

```text
$HOME/repoaces-workspaces/<run-id>/FastGPT
```

该路径不是绝对写死到某个用户，而是运行时通过 WSL 的 `$HOME` 推断。

如需自定义，可使用：

```powershell
python -m repoaces.cli prepare-dev-env `
  --wsl-root /home/<user>/custom-repoaces-workspaces
```

或在后续脚本中扩展对应参数。

### 仍存在的默认值

以下不是绝对路径，但属于本机环境默认值：

```text
Ubuntu-22.04
OpenHands port 3000
repoaces/openhands-agent-fastgpt:node20-pnpm10
docker.openhands.dev/openhands/openhands:1.8
```

这些值都可以通过脚本参数或环境变量覆盖。

## 5. 已处理的绝对路径问题

`cases/18cases/fastgpt_summary_cases.json` 和 `cases/18cases/fastgpt_summary_cases.csv` 原先包含采集机器上的绝对 `case_dir`，例如：

```text
<old-local-absolute-path>\benchmark\cases\fastgpt-pr-7008
```

这些字段已经改为相对路径：

```text
cases/18cases/fastgpt-pr-7008
```

当前批量脚本实际不依赖原始绝对 `case_dir`，而是使用 case `id` 拼接：

```text
cases\18cases\<case-id>\case.yaml
```

## 6. 不应上传的目录和文件

已添加 `.gitignore`，默认忽略：

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

原因：

- `tmp/`：实验输出、评估报告、日志、注册材料等。
- `runs/`：OpenHands 运行状态、会话数据库、conversation events。
- `workspaces/`：FastGPT checkout，体积大且可重新生成。
- `.openhands-home/`：可能包含本地 OpenHands 配置、模型 provider、密钥。
- 压缩包：可能重复包含 benchmark 数据或本地路径。

上传前建议执行：

```powershell
git status --short
```

确认不会提交运行产物、密钥或大型 workspace。

## 7. 当前仍需注意的问题

### OpenHands 模型配置不可随仓库完全复现

仓库不应该包含 API key，所以同事必须自行配置 OpenHands 的 LLM provider。

### WSL + Docker 是当前强依赖

当前 `prepare-dev-env` 默认走 WSL/Linux workspace，因为 FastGPT 官方也建议在 *nix 环境开发。直接把 Windows `D:\...` workspace 挂载给 OpenHands 容易出现权限、路径和 git safe.directory 问题。

### final-evaluator 环境还在演进

当前动态 evaluator 已能运行，但 FastGPT 的环境差异较多。后续建议按 `docs/evaluation-only-per-instance-image-plan.md` 实施 per-instance eval image。

## 8. 上传前建议清单

上传 GitHub 前建议确认：

```powershell
python -m pip install -r requirements.txt
python -m repoaces.cli --help
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_openhands_agent_fastgpt.ps1 -SkipVerify
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\repoaces_batch_by_size.ps1 -OnlyPrs "6660" -RunTag plancheck -PlanOnly
```

如果上述命令能正常执行，说明源码层面基本可复现。完整 OpenHands 运行还需要 Docker、WSL、模型 provider 和网络可用。
