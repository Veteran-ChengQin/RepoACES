# OpenHands FastGPT Runtime Guide

这份指南用于放入 OpenHands 的任务 instruction，或作为 `/workspace` 中的运行说明。

## 基本原则

- 默认仓库根目录是 `/workspace`。
- 优先使用仓库声明的 Corepack/pnpm 版本，不要随意升级 pnpm。
- targeted tests 可以用于快速迭代，但不能替代 package-level build/typecheck。
- 每次最终回复必须记录实际运行过的命令、结果、失败原因和未运行原因。

## 环境检查

```bash
cd /workspace
git rev-parse HEAD
node --version
npm --version
corepack --version
pnpm --version
git --version
rg --version | head -1
```

如果依赖缺失，或出现 `No package found with name ... in workspace`：

```bash
cd /workspace
pnpm install --frozen-lockfile
```

如果 `package.json` 中存在 `build:sdks`，且本次变更影响 `projects/app`、OpenAPI、SDK 或跨包类型：

```bash
cd /workspace
pnpm run build:sdks
```

## 按变更路径选择验证命令

### `projects/app/**`

```bash
cd /workspace/projects/app
pnpm build
pnpm test
```

如果完整测试过慢，可以先跑相关测试，但最终必须说明是否执行过 `pnpm build`。

### `packages/service/**`

```bash
cd /workspace/packages/service
pnpm test
```

如果只跑 targeted Vitest，最终回复中必须说明没有覆盖完整 package test 的原因。

### `packages/global/**`

`packages/global` 通常是共享类型、Schema、枚举来源。修改后应至少触发依赖它的 app/service 类型检查。

```bash
cd /workspace
pnpm run build:sdks
cd /workspace/projects/app
pnpm build
```

### `projects/code-sandbox/**`

```bash
cd /workspace/projects/code-sandbox
pnpm build
pnpm test
```

如果改动涉及 worker 生命周期、资源限制、安全策略、API 请求体或并发控制，不能只跑新增测试；必须考虑已有 regression tests。

### `document/**`

```bash
cd /workspace/document
pnpm build
```

### `deploy/dev/**` 或 Docker Compose 文件

```bash
cd /workspace/deploy/dev
docker compose config
```

只有当功能确实需要本地依赖服务时，才运行：

```bash
docker compose up -d
```

运行后需要记录启动了哪些服务，以及是否需要清理。

## 使用 PR-specific evaluator config

如果 RepoACES 提供了 `docker/compose-bundle/configs/<case-id>.eval.json`，其中的 commands 是该 PR 的最终评测参考。

OpenHands 在实现阶段不能读取基准 patch，但可以遵循公开的 build/test/dev 命令原则：

- `phase=env`：环境检查。
- `phase=test`：功能相关测试。
- `phase=build`：编译、类型检查、文档构建。
- `phase=docker`：Dockerfile 或 Compose 构建检查。

## 最终回复格式

最终回复至少包含：

```text
Changed files:
- ...

Validation:
- PASS/FAIL command ...
- PASS/FAIL command ...

Not run:
- command: exact reason/blocker

Residual risks:
- ...
```
