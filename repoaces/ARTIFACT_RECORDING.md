# RepoACES 产物记录机制

本文说明当前 RepoACES 的真实运行流程和产物写入标准。

## 当前流程

```text
case.yaml
  -> Case Builder
  -> init-run
  -> prepare-workspace
  -> prepare-dev-env
  -> Repo Intelligence
  -> start-openhands implementation
  -> poll-openhands implementation
  -> final-evaluate
```

其中：

- `prepare-workspace` 只负责准备干净源码仓库。
- `prepare-dev-env` 负责准备 OpenHands 可用的 Linux/WSL 开发环境。
- `final-evaluate` 是后验确定性评测，不调用 LLM，不启动 OpenHands。

## 目录结构

每个 run 采用如下目录：

```text
case/
  public_case.json
  instruction.md
  requirement_spec.md
repo_intelligence/
  repo_context.json
  code_knowledge_graph.json
  command_map.json
  repo_overview.md
tasks/
  00-prepare-dev-env/
    prepare_wsl_workspace.sh
    prepare_wsl_workspace.log
    chown_wsl_workspace_for_openhands.sh
    chown_wsl_workspace_for_openhands.log
    preflight.sh
    run_preflight_container.sh
    preflight.log
    git-status-after-preflight.txt
    dev_environment_report.json
    result.json
  01-implementation/
    instruction.md
    patch.diff
    trajectory.json
    conversation/
    openhands_runtime_state.json
    result.json
  02-final-evaluator/
    candidate.patch
    baseline.patch
    eval.sh
    eval_plan.md
    commands.json
    test_output.txt
    final_evaluation_report.json
    result.json
report/
  private/private_validation_meta.json
  run_state.json
  artifact-manifest.json
```

## `case/`

`CaseBuilder` 从 `case.yaml` 生成公开任务输入。

- `public_case.json`：结构化公开需求。
- `instruction.md`：传给 OpenHands implementation agent 的指令。
- `requirement_spec.md`：面向人阅读的公开需求说明。
- `report/private/private_validation_meta.json`：私有 benchmark 元信息，不传给 OpenHands。

## `tasks/00-prepare-dev-env/`

`DevEnvironmentPreparer` 的输出目录。

当前实现面向 FastGPT / WSL2 / Docker Desktop：

1. 从 Windows `prepare-workspace` 产物复制或克隆到 WSL/ext4 workspace。
2. 将 WSL workspace checkout 到 case 的 base commit。
3. 使用自定义 OpenHands agent-server 镜像修复 workspace owner。
4. 在同一 agent-server 镜像中执行 preflight。
5. 将 run state 的 active workspace 切换到 WSL workspace 的 UNC 路径，并记录 WSL 原生路径。

关键产物：

- `prepare_wsl_workspace.sh`：可复现的 WSL workspace 准备脚本。
- `chown_wsl_workspace_for_openhands.sh`：用容器 root 将 workspace owner 改为 OpenHands 用户。
- `preflight.sh`：容器内开发环境验证脚本。
- `run_preflight_container.sh`：启动 preflight 容器的脚本。
- `preflight.log`：preflight stdout/stderr。
- `dev_environment_report.json`：结构化环境报告。
- `result.json`：阶段索引，记录 active workspace、WSL path、镜像和是否通过。

当前默认 preflight：

```text
git config --global --add safe.directory /workspace
git rev-parse HEAD
node -v && npm -v && pnpm -v && corepack --version && git --version && rg --version
chmod -R +x ./scripts/
pnpm install --frozen-lockfile
pnpm build:sdks
pnpm test:repo
```

可通过 CLI 参数跳过安装或 smoke tests：

```text
--skip-install
--skip-smoke-tests
```

## `repo_intelligence/`

当前保留已有实现：

- `StaticRepoIntelligence`：生成轻量仓库结构、命令映射和代码图。
- `CodeWikiRepoIntelligence`：在 CodeWiki CLI 可用时调用外部 CodeWiki。

当前 orchestrator 不强制运行 Repo Intelligence；需要通过 CLI 显式执行 `static-intel` 或 `codewiki-intel`。

## `tasks/01-implementation/`

`OpenHandsCodingAgent` 的 implementation 输出目录。

必须记录：

- `instruction.md`：实际传给 OpenHands 的 instruction。
- `patch.diff`：当前 active workspace 的 `git diff --binary`。
- `trajectory.json`：从 OpenHands conversation events 聚合得到的轨迹。
- `conversation/`：OpenHands 原始事件，能导出则保留。
- `openhands_runtime_state.json`：OpenHands 容器、conversation、sandbox 和 patch 导出状态。
- `result.json`：阶段状态索引。

如果 `prepare-dev-env` 已通过，OpenHands 启动会使用：

```text
docker backend: wsl
workspace mount: /home/.../repoaces-workspaces/<run-id>/FastGPT
agent-server image: repoaces/openhands-agent-fastgpt:node20-pnpm10
```

这避免直接把 Windows `D:\...` workspace 挂进 OpenHands sandbox。

## `tasks/02-final-evaluator/`

`FinalEvaluator` 的输出目录。

它不调用 LLM，不启动 OpenHands，只对修改后的 workspace 执行确定性检查。

必须记录：

- `candidate.patch`：被评测的候选 patch，默认来自 `tasks/01-implementation/patch.diff`。
- `baseline.patch`：case 中记录的基准 patch。
- `eval.sh`：可复现的评测命令脚本。
- `eval_plan.md`：命令来源和检查意图说明。
- `commands.json`：结构化命令计划。
- `test_output.txt`：所有命令的 stdout/stderr/exit code。
- `final_evaluation_report.json`：最终评测报告。
- `result.json`：阶段索引，引用 instruction、trajectory、patch、baseline patch 和 final report。

## 当前 CLI

保留入口：

```text
build-case
init-run
prepare-workspace
prepare-dev-env
static-intel
codewiki-intel
start-openhands --mode implementation
poll-openhands --mode implementation
final-evaluate
```

已移除入口：

```text
eval-plan
patch-shape
public-repair-feedback
build-repair-prompt
start-openhands --mode public-repair
```

## 推荐命令序列

```powershell
python .\scripts\repoaces.py init-run `
  --case .\cases\18cases\fastgpt-pr-7008\case.yaml `
  --out .\tmp\experiments\repoaces\fastgpt-pr-7008\<run-id>

python .\scripts\repoaces.py prepare-workspace `
  --case .\cases\18cases\fastgpt-pr-7008\case.yaml `
  --artifact-root .\tmp\experiments\repoaces\fastgpt-pr-7008\<run-id>

python .\scripts\repoaces.py prepare-dev-env `
  --case .\cases\18cases\fastgpt-pr-7008\case.yaml `
  --artifact-root .\tmp\experiments\repoaces\fastgpt-pr-7008\<run-id>

python .\scripts\repoaces.py start-openhands `
  --artifact-root .\tmp\experiments\repoaces\fastgpt-pr-7008\<run-id> `
  --sandbox-repo-path /workspace `
  --model gpt-5.4 `
  --auto-run true
```

## 约束

1. FastGPT workspace 不应直接从 Windows `D:\...` 挂载给 OpenHands。
2. WSL workspace 必须对 OpenHands 容器用户可写，当前 UID/GID 为 `10001:10001`。
3. `prepare-dev-env` 可以准备依赖和 smoke checks，但真正的候选 patch 判定仍由 `final-evaluate` 完成。
