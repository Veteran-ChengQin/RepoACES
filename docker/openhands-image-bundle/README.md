# RepoACES FastGPT OpenHands PR 镜像包

本包仅覆盖每个 PR 所需的 OpenHands 工作区镜像。每个 PR 基于以下基础镜像生成一个 Docker Compose 构建项：

```text
ghcr.io/openhands/agent-server:1.26.0-python
```

该镜像会克隆 FastGPT、检出 PR 的 base commit、通过 `pnpm install --frozen-lockfile` 安装 FastGPT 依赖，并提供常用的根级 build/test/compose 命令。

镜像在运行时会固定使用 Node.js `20.19.5`，因为较旧的 FastGPT base commit 在 OpenHands 基础镜像自带的 Node.js 版本下可能无法正常安装原生依赖。

## 构建单个 PR 镜像

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\scripts\Build-OHImage.ps1 -Pr 7138
```

或使用 Docker Compose：

```powershell
cd .\oh-compose\fastgpt-pr-7138
docker compose build
```

## 在容器内验证

```powershell
cd .\oh-compose\fastgpt-pr-7138
docker compose run --rm --entrypoint bash openhands
```

容器内常用命令：

```bash
bash /opt/repoaces-oh/openhands-common-commands.sh env
bash /opt/repoaces-oh/openhands-common-commands.sh build
bash /opt/repoaces-oh/openhands-common-commands.sh test
bash /opt/repoaces-oh/openhands-common-commands.sh compose
```

这些辅助命令分别对应：

- `env`：工具链版本信息、`pnpm install --frozen-lockfile`、`git diff --check`
- `build`：根目录 `pnpm build`
- `test`：根目录 `pnpm test`
- `compose`：base commit 中存在的常用 FastGPT `docker compose config` 文件（如有）

## 验证包文件

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\scripts\Verify-OpenHandsImageBundle.ps1 -CheckCompose
```

## 说明

本包有意限定于镜像/构建环境这一职责范围，不包含 OpenHands 用户指令或变更文件/模块命令的交付文件。
