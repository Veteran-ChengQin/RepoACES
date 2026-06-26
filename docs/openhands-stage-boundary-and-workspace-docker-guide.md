# OpenHands 阶段边界与 PR Workspace Docker 方案

本文回答两个问题：

1. OpenHands 是否会稳定按照 RepoACES 设计的 8 个阶段执行，并形成清晰交接产物。
2. 如何为不同 FastGPT PR 准备可 `pnpm install`、`build`、`test` 的 Docker/Workspace 环境，并让 OpenHands 在相同环境中完成代码修改。

## 1. OpenHands 是否天然执行 8 阶段

结论：不会。OpenHands 可以被 prompt 要求“按 8 阶段思考和汇报”，但它不会天然形成强边界、强状态机和强交接产物。

当前 `CaseBuilder.render_instruction()` 已经把任务描述为 8 个 Required Phases：

1. 需求理解
2. 仓库探索
3. 变更范围识别
4. 实现计划
5. 代码实现
6. 测试/文档实现
7. 构建与验证
8. 最终复核

但是，从 PR 7008 和 PR 7138 的 trajectory 可以看到：

- 这些阶段主要存在于 OpenHands 的自然语言 task tracker 和最终回复中。
- OpenHands 会在一个 conversation 中交错执行搜索、阅读、编辑、测试和总结。
- 阶段之间没有强制停止点。
- 阶段之间没有强制 schema 化交接产物。
- 外部系统只能拿到一个整体 `trajectory.json`、一个整体 `patch.diff`、一个整体 `result.json`。

因此，当前“8 阶段”更像是 prompt 内部的软约束，而不是工程上的 workflow。

## 2. 当前 RepoACES 外部流程

当前 `scripts/repoaces_fullflow.ps1` 的外部流程是 7 步：

```text
1. init-run
2. prepare-workspace
3. static repo intelligence
4. prepare-dev-env
5. start-openhands
6. poll-openhands
7. final-evaluate
```

其中真正由 OpenHands 自主完成的是第 5-6 步中的 implementation conversation。

当前可稳定记录的 OpenHands 产物是：

```text
tasks/01-implementation/
  instruction.md
  patch.diff
  trajectory.json
  conversation/
  openhands_runtime_state.json
  result.json
```

这些产物适合事后分析，但不足以证明 OpenHands 在每个阶段都正确完成了任务。例如：

- PR 7008 的仓库探索找到了 `projects/code-sandbox` 主路径，但没有把 `resource-limits.test.ts` 和 `vitest.config.ts` 纳入关键验证边界。
- PR 7138 的仓库探索找到了 API 和 service repo，但没有追踪到 `packages/global` 中的共享类型定义。

这说明如果后续要严谨分析“是哪一阶段失败”，需要把关键阶段外置为 workflow。

## 3. 建议的强阶段 workflow

建议不要让 OpenHands 一次性自由完成完整 8 阶段，而是拆成多个可观测 task。

推荐阶段：

```text
00 case-builder
01 prepare-workspace
02 prepare-dev-env
03 repo-intelligence / scope-exploration
04 technical-plan / validation-plan
05 openhands-implementation
06 openhands-self-validation
07 final-evaluator
08 report-packaging
```

### 03 repo-intelligence / scope-exploration

目标：只探索，不改代码。

输入：

- `public_case.json`
- `instruction.md`
- base workspace
- repo intelligence 产物

输出：

```text
tasks/03-scope-exploration/
  instruction.md
  trajectory.json
  explored_files.txt
  scope_report.json
  validation_candidates.json
  result.json
```

`scope_report.json` 建议字段：

```json
{
  "entrypoints": [],
  "likely_changed_files": [],
  "shared_type_or_schema_sources": [],
  "config_files": [],
  "existing_tests_to_protect": [],
  "new_tests_to_add": [],
  "risks": []
}
```

### 04 technical-plan / validation-plan

目标：把探索结果转化为代码实现计划和验证计划。

输出：

```text
tasks/04-technical-plan/
  implementation_plan.md
  selected_files.json
  validation_plan.json
  result.json
```

`validation_plan.json` 必须明确：

- targeted tests
- package-level build/typecheck
- package-level tests
- docker compose checks
- 哪些命令是 required
- 哪些命令是 best-effort

### 05 openhands-implementation

目标：按计划修改代码。

输出：

```text
tasks/05-implementation/
  instruction.md
  trajectory.json
  conversation/
  patch.diff
  changed_files.txt
  result.json
```

### 06 openhands-self-validation

目标：让 OpenHands 在修改后的 workspace 上执行 `validation_plan.json`。

输出：

```text
tasks/06-self-validation/
  instruction.md
  trajectory.json
  validation_commands.json
  validation_output.txt
  result.json
```

注意：self-validation 不能替代 final evaluator，只能作为 agent 自检。

### 07 final-evaluator

目标：确定性评测，不调用 LLM。

输出仍为：

```text
tasks/07-final-evaluator/
  candidate.patch
  baseline.patch
  eval.sh
  eval_plan.md
  commands.json
  test_output.txt
  final_evaluation_report.json
  result.json
```

## 4. PR Workspace Docker 的现状

当前仓库已经有 `docker/compose-bundle`，它接近 SWE-bench 的 per-instance evaluator image：

- 每个 PR 有一个 `configs/fastgpt-pr-xxxx.eval.json`。
- Dockerfile 在镜像构建阶段 clone FastGPT。
- checkout 到该 PR 的 base commit。
- 执行 `pnpm install --frozen-lockfile`。
- 运行时将候选 patch 挂载到 `/patches/candidate.patch`。
- 在镜像内 `/workspace` 上 apply patch。
- 按 eval config 执行 env/test/build/docker 阶段命令。

自检结果：

```text
Config check passed: 18 PR configs
Compose check passed: 18 docker-compose.yml files
```

## 4.1 阶段拆分的相关研究依据

阶段化 workflow 并不意味着完全否定 OpenHands 当前的“边思考、边搜索、边编辑、边验证”模式。相关工作大致分成两条路线：

### 支持交错探索/行动的路线

- ReAct: Synergizing Reasoning and Acting in Language Models
  https://arxiv.org/abs/2210.03629
  ReAct 提出让模型交错生成 reasoning traces 和 actions。它的观点是：reasoning 可以帮助维护和更新计划，action 可以从环境获取新信息。这与 OpenHands/SWE-agent 的交互式行为一致。

- SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering
  https://arxiv.org/abs/2405.15793
  SWE-agent 强调 agent-computer interface 对软件工程任务的重要性，让 agent 能浏览仓库、编辑文件、运行测试。它支持“交互式 agent + 工具反馈”的路线，但重点是 interface 设计，而不是强制固定 SDLC 阶段。

这类工作说明：对未知环境和长程任务，完全禁止 interleaving 可能反而削弱 agent 处理异常、动态调整计划的能力。

### 支持阶段化/模块化的路线

- Agentless: Demystifying LLM-based Software Engineering Agents
  https://arxiv.org/abs/2407.01489
  Agentless 不让 LLM 自主操作复杂工具，而采用 localization、repair、patch validation 等简化阶段。它说明在 SWE-bench Lite 上，简单、可解释、阶段化的流程可以成为强基线。

- AutoCodeRover: Autonomous Program Improvement
  https://arxiv.org/abs/2404.05427
  AutoCodeRover 把结构化 code search、上下文定位、测试反馈和 patch generation 结合起来，强调软件工程视角的程序结构搜索，而不是把仓库当成文件集合盲目浏览。

- MapCoder: Multi-Agent Code Generation for Competitive Problem Solving
  https://arxiv.org/abs/2405.11403
  MapCoder 将代码生成拆成 retrieval、planning、coding、debugging 等角色，证明多阶段、多角色 decomposition 在代码任务上有价值。虽然它面向竞赛编程，不是 repo-level feature PR，但对“拆阶段形成交付物”的设计有参考意义。

- Plan-and-Solve Prompting
  https://arxiv.org/abs/2305.04091
  Plan-and-Solve 指出先规划再执行可以减少 missing-step errors。这支持在复杂任务中显式产出 plan，但它不是 repo-level agent 论文，不能直接证明所有阶段化 workflow 都优于 interleaving。

综合来看，论文并不能给出“拆 scope-exploration 一定更优”的绝对结论。更稳妥的判断是：

- 对 agent 自主解决未知问题，保留 ReAct-style interleaving 是有价值的。
- 对 benchmark、系统工程、失败归因和模块替换，外置关键阶段和结构化产物更有价值。
- RepoACES 可以采用混合方案：阶段之间强边界，阶段内部允许 OpenHands 自由使用 ReAct 式探索/行动。

典型命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\docker\compose-bundle\scripts\Build-PrImage.ps1 `
  -Pr 7138

powershell -NoProfile -ExecutionPolicy Bypass -File .\docker\compose-bundle\scripts\Run-PrEval.ps1 `
  -Pr 7138 `
  -Mode all `
  -Patch .\tmp\experiments\repoaces\fastgpt-pr-7138\manual-pr7138-002\tasks\01-implementation\patch.diff
```

## 4.2 开发环境镜像与 final evaluator 镜像的差异

后续设计中需要明确区分两类镜像。

### 开发环境镜像 / workspace seed image

用途：给 OpenHands implementation 阶段使用。

特点：

- 面向“开发过程”，而不是最终判题。
- 包含 Node、pnpm、git、rg、docker/compose 等通用工具。
- 可以为某个 PR/base commit 预装依赖。
- 可以在根目录或主要 package 上运行通用 smoke checks，例如：
  - `pnpm install --frozen-lockfile`
  - `pnpm run build:sdks`
  - `pnpm test:repo`
  - `pnpm build`
  - `docker compose config`
- OpenHands 可以在该环境中探索、修改、运行自选验证命令。
- 不应该包含 golden patch，也不应该暴露基准 changed files 推导出的隐藏评测意图。

### final evaluator 镜像

用途：给 RepoACES final evaluator 使用。

特点：

- 面向“确定性评测”，不调用 LLM，不启动 OpenHands。
- 从干净 base commit 开始。
- apply candidate patch 后运行固定评测命令。
- 命令可以由 benchmark 私有信息、基准 changed files、人工分析或 eval config 推导。
- 输出 `final_evaluation_report.json`、`test_output.txt` 等可复现结果。
- 不应被 implementation 阶段污染。

因此，较合理的关系是：

```text
dev workspace image/container
  -> 帮助 OpenHands 更顺利地开发和自测

final evaluator image/container
  -> 在干净环境中独立判定候选 patch
```

二者可以共享基础 toolchain，但职责和信息边界必须分开。

## 5. OpenHands 能否直接修改通用开发环境容器中的 workspace

这里的“通用开发环境容器”不是 final evaluator 容器，而是另一个包含 Node、pnpm、git、rg、docker/compose 等通用开发工具的容器。

结论：可以复用这个通用环境容器的镜像和工具链，但不建议让 OpenHands 直接依赖某个已经运行中的容器内部 `/workspace` 作为唯一工作区。

RepoACES 需要区分三类容器：

1. OpenHands server container：负责 Web/API/会话管理。
2. OpenHands sandbox/agent container：真正执行 shell、编辑文件、运行测试的工作容器，可以使用通用开发环境镜像。
3. final evaluator container：干净、确定性、只用于 apply candidate patch 后评测，不应被 implementation 阶段污染。

原因：

- 一个已经运行中的通用开发容器内部 `/workspace` 属于该容器的 writable layer，不是稳定共享接口。
- OpenHands agent-server 可能会重新创建 sandbox/container，直接绑定另一个容器内部 filesystem 会让生命周期、权限和清理变复杂。
- 即使通过 `docker commit`、`docker cp` 或 `volumes-from` 间接传递，也不如显式 bind mount / named volume 可控。
- implementation workspace 应该可写、可导出 patch、可清理；final evaluator workspace 应该干净、可复现、不可被 OH 直接修改。

正确做法是共享“外部可挂载 workspace”：

1. WSL/ext4 bind mount workspace。
2. Docker named volume workspace。

当前 RepoACES 使用的是第 1 种。

如果要充分利用通用开发环境容器，推荐方式是：

```text
通用开发环境镜像
  -> 作为 OH sandbox/agent image
  -> 通过 SANDBOX_VOLUMES 挂载外部 workspace 到 /workspace
  -> OH 在 /workspace 中修改代码和运行验证
```

而不是：

```text
先启动一个通用开发容器
  -> 让 OH 去“进入”这个容器内部的 /workspace
```

## 6. 推荐短期方案：WSL workspace + per-PR evaluator image

短期最稳的方案：

```text
prepare-workspace
  -> 在 Windows/WSL 准备 base commit workspace

prepare-dev-env
  -> 在 WSL/ext4 workspace 中安装依赖
  -> 使用 OpenHands agent-server 镜像跑 preflight

OpenHands implementation
  -> 将同一个 WSL workspace bind mount 到 OH sandbox 的 /workspace
  -> OH 修改该 workspace

final-evaluator
  -> 导出 patch.diff
  -> 将 patch.diff 应用到 per-PR evaluator image 的干净 /workspace
  -> 运行该 PR 的 eval config
```

优势：

- OpenHands 有真实可写 workspace。
- final evaluator 使用干净镜像，避免 workspace 污染。
- 与 SWE-bench “在干净 base 上 apply candidate patch 后评测”的范式一致。
- 不需要让 OpenHands 直接进入 evaluator 镜像内部工作区。

劣势：

- OpenHands implementation 阶段和 final evaluator 阶段不是同一个容器。
- 如果 prepare-dev-env 的 WSL workspace 环境不够完整，OpenHands 自己运行 build/test 仍可能失败。

缓解：

- `prepare-dev-env` 应尽量复用 per-PR eval config 的 env/build smoke commands。
- `instruction.md` 中要给 OpenHands 明确的 FastGPT build/test 指南。
- OpenHands 自测失败不等于 final evaluator 失败，但必须记录 blocker。

## 7. 中期方案：per-PR workspace seed image + Docker named volume

如果希望 OpenHands 也使用 per-PR 完整环境，可以引入 workspace seed image。

流程：

```text
Build seed image:
  repoaces/dev-fastgpt-pr-7138:<base12>
    /opt/repoaces/base-workspace
    node/pnpm/git/rg/docker
    pnpm install 完成后的 node_modules / store

Create named volume:
  repoaces-ws-fastgpt-pr-7138-<run-id>

Init volume:
  docker run --rm
    -v repoaces-ws-fastgpt-pr-7138-<run-id>:/workspace
    repoaces/dev-fastgpt-pr-7138:<base12>
    sh -lc 'cp -a /opt/repoaces/base-workspace/. /workspace/'

Start OpenHands:
  SANDBOX_VOLUMES=repoaces-ws-fastgpt-pr-7138-<run-id>:/workspace:rw

Export patch:
  docker run --rm
    -v repoaces-ws-fastgpt-pr-7138-<run-id>:/workspace
    repoaces/dev-fastgpt-pr-7138:<base12>
    sh -lc 'cd /workspace && git diff --binary HEAD'

Final evaluate:
  apply exported patch to fresh evaluator image
```

优势：

- OpenHands 和验证工具看到的是同一种 Linux/Docker 环境。
- 不依赖 Windows path。
- 更接近 SWE-bench 的容器化思想。

劣势：

- 需要额外实现 named volume 生命周期管理。
- 需要确认 OpenHands 的 `SANDBOX_VOLUMES` 对 Docker named volume 的支持情况。
- patch/export/debug 比 WSL bind mount 稍复杂。

## 8. 不推荐方案：让 OH 直接进入 evaluator container

不推荐：

```text
evaluator container 内部 /workspace
  -> 试图挂载给 OH container 修改
```

问题：

- 容器内部文件系统不是稳定共享接口。
- 容器停止后状态难以管理。
- 很难保证 `git diff`、权限、生命周期和清理逻辑一致。
- 和 final evaluator 的“干净 base + candidate patch”原则冲突。

## 9. 给 OpenHands 的运行指南

已在 `repoaces.case_builder.CaseBuilder.render_instruction()` 中加入 FastGPT 专用运行指南。后续生成的 `tasks/01-implementation/instruction.md` 会包含：

- 如何处理缺失依赖。
- 什么时候需要 `pnpm install --frozen-lockfile`。
- 什么时候需要 `pnpm run build:sdks`。
- `projects/app`、`packages/service`、`packages/global`、`projects/code-sandbox`、`document`、`deploy/dev` 对应的 build/test/compose 检查。
- targeted tests 不能替代 package-level build/typecheck 的约束。

这能直接缓解 PR 7008 和 PR 7138 暴露的问题：

- PR 7008：要求 code-sandbox 变更必须考虑完整 `pnpm test`，不能只跑新增 queueId tests。
- PR 7138：要求 app/global/service 类型相关变更必须跑 `projects/app pnpm build`。

## 10. 下一步实施建议

建议按两步推进：

1. 短期保留当前 WSL workspace 实现，把 `compose-bundle` 作为 final evaluator 默认后端。
2. 中期新增 `workspace-volume` backend，支持 per-PR seed image + Docker named volume，让 OpenHands implementation 阶段也复用完整 per-PR 环境。

最小改造点：

- 在 `prepare-dev-env` 中读取 `docker/compose-bundle/configs/<case-id>.eval.json`。
- 将 `phase=env` 和必要的 `phase=build/test` smoke command 写入 `tasks/00-prepare-dev-env/preflight.sh`。
- 在 `start-openhands` 前，把 PR-specific runtime guide 写入 instruction。
- 在 `poll-openhands` 后，额外导出：
  - `openhands_validation_commands.json`
  - `explored_files.txt`
  - `scope_report_draft.json`

这样既保持当前系统可运行，又能逐步把 OH 自由探索变成可观测、可复盘、可替换的 workflow。

## 11. scope-exploration 是否应该独立出来

结论：不应该把“探索”和“实现”完全割裂成不可回头的瀑布流程；但应该把第一次 scope-exploration 独立成一个可审计 checkpoint。

原因：

1. OpenHands 当前的 ReAct 式交错探索有价值。实现过程中遇到类型错误、测试失败或新依赖时，agent 必须继续搜索和修正。
2. 但是完全自由交错会导致关键决策不可控。PR 7008 和 PR 7138 都说明，agent 可以自认为探索充分、targeted tests 通过，但真实失败发生在未纳入范围的相邻测试或共享类型上。
3. 独立 scope-exploration 的目标不是禁止后续再探索，而是要求 agent 在编辑前提交一份初始范围假设，便于后续检测偏移。

推荐方式：

```text
scope-exploration checkpoint:
  - explored_files.txt
  - scope_report.json
  - validation_candidates.json

implementation:
  - 允许继续探索
  - 但如果新增关键文件或推翻 scope，需要记录 scope_delta.json

final report:
  - 对比 initial scope、scope delta、candidate patch、final evaluator failure
```

这样设计比“完全自由一次性 conversation”更适合比赛和研究复盘，因为它能回答：

- agent 最初是否找到了正确模块？
- 漏掉的文件是探索阶段没有发现，还是实现阶段放弃了？
- 验证命令是根据 scope 合理推导出来的，还是只跑了新增测试？
- 失败属于 scope miss、implementation bug、validation miss，还是环境问题？

相关研究并不支持“强行瀑布化一定更好”，但支持把定位、上下文检索、修复、验证做成可解释阶段：

- Agentless 采用 localization、repair、patch validation 三阶段，说明在 SWE-bench 类软件任务中，简单、可解释的阶段化流程可以成为强 baseline。
- AutoCodeRover 将代码上下文检索、定位和 patch construction 分开，并强调利用程序结构和测试信息指导检索。
- SWE-agent 和 ReAct 则提醒我们，交互式环境中的 reasoning/action 交错很重要，不能让 workflow 阻止 agent 在实现和验证中继续探索。

因此，RepoACES 更适合采用“checkpoint 化的迭代 workflow”：

```text
先独立 scope checkpoint
再允许 implementation 中继续 ReAct 式探索
最后把 scope delta 和 final evaluator 结果一起归档
```
