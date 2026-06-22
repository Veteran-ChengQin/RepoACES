# Evaluation-only Per-instance Image 方案计划

## 1. 背景

当前 RepoACES 已经能够调用 OpenHands 生成候选 patch，并通过 `final-evaluator` 执行 build/tests 评估。但是在 FastGPT PR case 上，环境构建和评估稳定性暴露出几个问题：

1. 不同 FastGPT base commit 可能依赖不同 Node/pnpm 版本。
2. 部分子项目需要额外运行时，例如 `projects/volume-manager` 需要 Bun。
3. root `pnpm test` 可能引用 `@fastgpt/admin`，但 `pro` submodule 未初始化时 `pro/admin` 不存在。
4. 某些测试需要下载 MongoDB binary，首次运行成本高且容易引入 timeout。
5. deploy/template/workflow/submodule 类 PR 不适合直接 fallback 到 root test。
6. 当前 `prepare-dev-env` 试图用一套规则覆盖所有 PR，后续会不断堆叠特例，维护成本较高。

SWE-bench 的做法是：每个 instance 绑定一个确定的 base commit、完整环境镜像和评测脚本。RepoACES 可以先参考这个思想，为当前少量 FastGPT PR 构建 **evaluation-only per-instance image**，先把最终评估变得可复现、可解释、可缓存。

## 2. 目标

本阶段目标不是立刻让 OpenHands 在完全相同的镜像内工作，而是先把 final evaluation 收敛为确定性流程：

```text
OpenHands 生成 patch.diff
  -> final-evaluator 启动该 case 的 eval image
  -> 在镜像内干净 base workspace 上 apply patch.diff
  -> 执行该 case 的 eval.sh
  -> 输出 test_output.txt / report.json
```

该方案优先解决：

- final-evaluator 环境不稳定；
- 依赖重复安装；
- pnpm/Node/Bun/submodule 等环境差异；
- 评估命令对不同 PR 类型不适配；
- 无法区分环境问题和 candidate patch 问题。

暂不强制解决：

- OpenHands 生成 patch 过程中的完整 build/test 环境；
- OpenHands 是否主动运行测试；
- 过程内修复循环。

这些可以在后续阶段通过“从 per-instance image 派生 OpenHands workspace”解决。

## 3. 总体设计

每个 PR case 构建一个 evaluation-only Docker image：

```text
repoaces/fastgpt-pr-7008-eval:base
repoaces/fastgpt-pr-6660-eval:base
repoaces/fastgpt-pr-6644-eval:base
repoaces/fastgpt-pr-5776-eval:base
repoaces/fastgpt-pr-7138-eval:base
```

镜像内包含：

```text
/opt/repo/FastGPT       # checkout 到 base commit 的干净仓库
/opt/eval/eval.sh      # 当前 case 的评估脚本
/opt/eval/meta.json    # case、base commit、工具链、环境状态
/opt/eval/README.md    # 环境说明和手动运行方式
```

镜像构建时完成：

1. 安装系统工具：`git`、`curl`、`build-essential`、`docker` CLI 需要时再加。
2. 安装 Node，版本由 base commit 或 case 配置决定。
3. 安装/激活 pnpm，版本由 `packageManager` 或 `engines.pnpm` 决定。
4. 按需安装 Bun。
5. clone FastGPT，checkout 到 `case.yaml` 中的 `base_commit`。
6. 可选初始化 submodule。
7. 执行 `chmod -R +x ./scripts/`。
8. 执行 `pnpm install --frozen-lockfile`。
9. 执行 `pnpm build:sdks`，如果该 script 存在。
10. 可选预下载 MongoDB binary cache。
11. 写入 `meta.json`，记录环境是否完整。

评估时完成：

1. 从镜像内 `/opt/repo/FastGPT` 复制出一个临时 workspace。
2. 在临时 workspace 上 apply candidate patch。
3. 执行 `/opt/eval/eval.sh`。
4. 收集 stdout/stderr、exit code、patch apply 日志和结构化 report。

## 4. 为什么先做 evaluation-only

OpenHands 的 workspace 通常通过 volume mount 挂载到 `/workspace`。如果镜像内已经准备好了 `/workspace`，启动 OpenHands 时外部 mount 会覆盖镜像内的 `/workspace`，导致镜像里预装好的 repo/node_modules 不一定可见。

因此，第一阶段不把该镜像直接作为 OpenHands workspace 使用，而是只用于最终评估：

```text
普通 WSL workspace
  -> OpenHands 修改并导出 patch

per-instance eval image
  -> 干净 base repo
  -> apply patch
  -> deterministic evaluation
```

这样可以快速获得稳定的最终评估，而不需要立刻改造 OpenHands 启动机制。

## 5. 目录结构建议

建议为每个 case 增加环境定义目录：

```text
cases/18cases/fastgpt-pr-7008/
  case.yaml
  patches/
    fastgpt-pr-7008.patch
    fastgpt-pr-7008.changed_files.txt
  env/
    Dockerfile
    eval.sh
    meta.template.json
    README.md
```

批量构建产物放到：

```text
tmp/experiments/repoaces-env-images/
  fastgpt-pr-7008/
    build.log
    image-meta.json
    baseline-eval/
      test_output.txt
      report.json
  fastgpt-pr-6660/
  fastgpt-pr-6644/
  fastgpt-pr-5776/
  fastgpt-pr-7138/
```

每次 RepoACES run 的 final-evaluator 产物仍放在：

```text
tmp/experiments/repoaces/<case-id>/<run-name>/tasks/02-final-evaluator/
  candidate.patch
  baseline.patch
  eval.sh
  commands.json
  test_output.txt
  final_evaluation_report.json
  result.json
```

但其中 `eval.sh` 和 `commands.json` 应记录实际调用的是 per-instance image，而不是当前动态推断的一组 host/container 命令。

## 6. case.yaml 扩展建议

可以在 `case.yaml` 中增加 `environment` 字段：

```yaml
environment:
  type: docker_image
  image: repoaces/fastgpt-pr-7008-eval:base
  dockerfile: env/Dockerfile
  workspace_path: /opt/repo/FastGPT
  eval_script: /opt/eval/eval.sh
  node: "20.19.5"
  pnpm: "10.33.4"
  bun: false
  submodules: false
  root_test_eligible: false
```

对于 `6644`：

```yaml
environment:
  bun: true
```

对于可能涉及 `pro` submodule 的 case：

```yaml
environment:
  submodules: true
  root_test_eligible: true
```

如果 submodule 无法访问：

```yaml
environment:
  submodules: unavailable
  root_test_eligible: false
```

## 7. eval.sh 设计

每个 case 的 `eval.sh` 应只关注该 case 的可复现评估，不调用 LLM，不启动 OpenHands。

推荐接口：

```sh
/opt/eval/eval.sh /tmp/candidate.patch /tmp/output
```

脚本职责：

1. 创建临时 workspace。
2. 从 `/opt/repo/FastGPT` 复制干净 base repo。
3. 执行 `git apply --check`。
4. 执行 `git apply`。
5. 执行该 case 的 required checks。
6. 执行该 case 的 optional diagnostic checks。
7. 写出 `/tmp/output/report.json`。
8. 写出 `/tmp/output/test_output.txt`。

报告字段建议：

```json
{
  "case_id": "fastgpt-pr-7008",
  "base_commit": "...",
  "patch_apply": "passed",
  "commands": [
    {
      "name": "build_projects_code_sandbox",
      "required": true,
      "returncode": 0,
      "duration_seconds": 12.3
    }
  ],
  "passed": true,
  "failure_class": null
}
```

失败类型建议：

```text
patch_apply_failed
required_command_failed
environment_incomplete
timeout
```

## 8. 当前 5 个 PR 的初始评估策略

### fastgpt-pr-7008

变更集中在 `projects/code-sandbox` 和 service client。

建议 required checks：

```sh
cd /opt/work/FastGPT/projects/code-sandbox
pnpm build
pnpm test
```

可选 diagnostics：

```sh
cd /opt/work/FastGPT/packages/service
pnpm test
```

### fastgpt-pr-6660

变更集中在 `projects/app`、`packages/global/openapi`。

建议 required checks：

```sh
cd /opt/work/FastGPT/projects/app
pnpm build
```

可选 diagnostics：

```sh
cd /opt/work/FastGPT
pnpm exec tsc -p tsconfig.json --noEmit --pretty false
```

root tsc 当前容易出现 `RangeError: Maximum call stack size exceeded`，建议先设为 optional。

### fastgpt-pr-6644

涉及 `projects/volume-manager`、deploy compose、openapi。

环境要求：

```text
bun: required
```

建议 required checks：

```sh
cd /opt/work/FastGPT/projects/volume-manager
pnpm build
pnpm test
```

compose 检查应区分模板和真实 compose 文件：

- 对 `deploy/dev/docker-compose*.yml` 可以执行 `docker compose config`。
- 对 `deploy/templates/*.yml` 不应直接执行 `docker compose config`，除非先渲染模板变量。
- 对 patch 中删除的 compose 文件不做内容检查。

### fastgpt-pr-5776

主要是 deploy template/copy 文件。

不建议 required root `pnpm test`。

建议 required checks：

```text
1. YAML/template parse check
2. 模板变量完整性检查
3. 如果存在生成脚本，则从 template 生成 copy 文件并比较
4. 对可直接运行的 deploy/dev compose 文件执行 docker compose config
```

root test 可以作为 full-regression optional，不作为该 case 的主判定。

### fastgpt-pr-7138

涉及 app/service/systemTool 逻辑和 shared 类型。

建议 required checks：

```sh
cd /opt/work/FastGPT/packages/service
pnpm test

cd /opt/work/FastGPT/projects/app
pnpm build
pnpm test
```

`projects/app pnpm build` 必须作为 required，因为之前失败正是 TypeScript 类型边界问题。

## 9. baseline evaluation

每个 image 构建完成后，应先在未应用 candidate patch 的 base workspace 上执行一次 baseline evaluation。

目的：

- 验证 image 本身可用；
- 验证 eval.sh 命令在 base commit 上不失败；
- 记录哪些命令是稳定 pass-to-pass checks；
- 避免把环境问题误判为 candidate patch 问题。

产物：

```text
tmp/experiments/repoaces-env-images/<case-id>/baseline-eval/
  test_output.txt
  report.json
```

判定逻辑：

```text
baseline pass + candidate pass => 通过
baseline pass + candidate fail => 候选 patch 引入失败
baseline fail + candidate fail => 环境或 evaluator 不可靠
baseline fail + candidate pass => 需要人工解释，可能是 feature behavior check
```

## 10. final-evaluator 接入方式

`repoaces/evaluator.py` 后续可以增加两种 backend：

```text
dynamic_commands
  当前实现，根据 changed files 推断命令并直接执行。

per_instance_image
  使用 case.yaml 中 environment.image 调用 Docker 镜像评估。
```

当 `case.yaml` 存在：

```yaml
environment:
  type: docker_image
```

则 final-evaluator 走：

```sh
docker run --rm \
  -v <candidate.patch>:/tmp/candidate.patch:ro \
  -v <output_dir>:/tmp/output:rw \
  <environment.image> \
  /opt/eval/eval.sh /tmp/candidate.patch /tmp/output
```

输出仍转换为当前统一产物：

```text
candidate.patch
baseline.patch
eval.sh
commands.json
test_output.txt
final_evaluation_report.json
result.json
```

## 11. OpenHands 环境问题的后续路线

evaluation-only image 只能保证最终评估稳定，不能完全保证 OpenHands 过程内环境完整。后续可以按两步增强。

### 阶段二：OpenHands 使用同版本工具链镜像

为 OpenHands agent-server 构建按工具链分组的镜像：

```text
repoaces/openhands-agent-fastgpt:node20-pnpm10-bun
repoaces/openhands-agent-fastgpt:node20-pnpm9
repoaces/openhands-agent-fastgpt:node20-pnpm8
```

OpenHands workspace 仍由外部挂载，但容器工具链和 evaluator 更接近。

### 阶段三：从 per-instance image 派生 OpenHands workspace

启动 OpenHands 前：

```text
docker create <case eval image>
docker cp <container>:/opt/repo/FastGPT <WSL workspace>
docker rm <container>
chown workspace to OpenHands uid/gid
```

然后将该 workspace 挂载给 OpenHands。

这样 OpenHands 和 final-evaluator 的 base workspace 来源一致。

## 12. 实施步骤

建议按以下顺序实施：

1. 为 `fastgpt-pr-7008` 手工创建 `env/Dockerfile` 和 `env/eval.sh`。
2. 编写 `scripts/repoaces_build_case_eval_image.ps1`。
3. 编写 `scripts/repoaces_run_case_eval_image.ps1`。
4. 先验证 `7008`：
   - 构建 image；
   - baseline eval；
   - apply 当前 OpenHands candidate patch；
   - 输出 report。
5. 将模板复制到 `6660`、`6644`、`5776`、`7138`。
6. 修改 `case.yaml` 增加 `environment` 字段。
7. 修改 `repoaces/evaluator.py`，支持 `per_instance_image` backend。
8. 保留当前 dynamic evaluator 作为 fallback。
9. 批量重跑 5 个 PR。

## 13. 风险与处理

### 镜像体积过大

原因：每个镜像包含 repo、node_modules、MongoDB binary cache。

处理：

- 当前只有 5 个 PR，可以接受。
- 后续可抽取公共 base image，例如 `repoaces/fastgpt-base-node20-pnpm10`。

### submodule 无权限

处理：

- image build 阶段明确记录 `submodules: unavailable`。
- evaluator 不运行依赖 `@fastgpt/admin` 的 root test。
- 对涉及 submodule 的 PR 单独设计 workspace/submodule consistency check。

### eval.sh 过度特化

处理：

- 当前 5 个 PR 可以先 case-specific。
- 后续将 eval.sh 模板化，由 `changed_files` 和 repo command map 生成。

### OpenHands 过程内环境仍不完整

处理：

- 第一阶段接受该限制，以 final-evaluator 为准。
- 第二阶段为 OpenHands 使用同工具链 agent-server 镜像。
- 第三阶段从 eval image 复制 prepared workspace。

## 14. 成功标准

第一阶段完成后，应达到：

1. 每个 PR 都有一个可构建的 eval image。
2. 每个 PR 的 base commit 能运行 baseline eval，并记录结果。
3. final-evaluator 可以把 candidate patch 应用到 eval image 的干净 workspace。
4. 每个 case 的失败原因能清晰归类为：
   - patch apply failed；
   - required command failed；
   - environment incomplete；
   - evaluator unsupported；
   - timeout。
5. 当前 5 个 PR 的评估结果不再依赖临时动态环境推断。

## 15. 推荐结论

RepoACES 后续应将每个 benchmark case 逐步升级为 SWE-bench 风格 instance：

```text
case metadata
+ public instruction
+ base commit
+ baseline patch
+ per-instance eval image
+ deterministic eval script
+ final report
```

短期先做 evaluation-only image，稳定最终评估；中期再让 OpenHands 使用同源环境；长期目标是让 case 构建、agent 运行和最终验证都围绕同一个可复现 instance 环境展开。
