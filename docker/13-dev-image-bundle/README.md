RepoACES FastGPT OpenHands PR 镜像包
此包仅覆盖按 PR 生成 OpenHands 工作区镜像的需求。当前批次为 typescript_similar_cases_2026-06-28，包含 13 个 FastGPT PR 案例。每个 PR 都会获得一个 Docker Compose 构建条目，基于：
ghcr.io/openhands/agent-server:1.26.0-python
该镜像会克隆 FastGPT，checkout 到 PR 的 base commit，使用 pnpm install --frozen-lockfile 安装 FastGPT 依赖，并提供通用的根目录级构建/测试/compose 命令。
该镜像还会在运行时将 Node.js 固定到 20.19.5，因为较旧的 FastGPT base commit 在 OpenHands 基础镜像内置的 Node.js 版本下，可能无法安装原生依赖。checkout 后，Dockerfile 会读取 base commit 的 package.json，并在运行依赖安装前切换到所需的 packageManager / engines.pnpm 版本。它会先尝试 pnpm install --frozen-lockfile；如果旧的 base commit 使用了过时的 lockfile，则回退到 --no-frozen-lockfile，并恢复 pnpm-lock.yaml，以保持工作区干净。
构建单个 PR 镜像
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\scripts\Build-OHImage.ps1 -Pr 7138
或使用 Docker Compose：
cd .\oh-compose\fastgpt-pr-7138
docker compose build
在容器内验证
cd .\oh-compose\fastgpt-pr-7138
docker compose run --rm --entrypoint bash openhands
容器内的常用命令：
bash /opt/repoaces-oh/openhands-common-commands.sh env
bash /opt/repoaces-oh/openhands-common-commands.sh build
bash /opt/repoaces-oh/openhands-common-commands.sh test
bash /opt/repoaces-oh/openhands-common-commands.sh compose
该 helper 的映射关系为：
* env：工具链版本、pnpm install --frozen-lockfile、git diff --check
* build：根目录 pnpm build
* test：根目录 pnpm test
* compose：如果 base commit 中存在常见的真实 FastGPT docker compose config 文件，则检查这些文件
验证 Bundle 文件
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\scripts\Verify-OpenHandsImageBundle.ps1 -CheckCompose
备注
这有意限定在镜像/构建环境任务范围内。它不包含 OpenHands 用户说明，也不包含变更文件/模块命令交接文件。

