# RepoACES PR Docker Compose Evaluators

这个文件是新版交付说明。旧 `README.md` 如果仍显示 6 个 PR，是因为它被本机程序占用，未在本次自动替换；本文件为准。

## 已完成内容

- 18 个 PR 全部有 `configs/fastgpt-pr-xxxx.eval.json`
- 18 个 PR 全部有 `compose/fastgpt-pr-xxxx/docker-compose.yml`
- 每个 PR 都有 `docker-compose.patch.yml`，用于挂载候选 patch
- 新增了 `Export-ComposeBundle.ps1`，可以导出师兄需要的 Compose 配置包
- 已实际验证 `fastgpt-pr-7138` 镜像：
  - `env` 通过
  - `build` 通过
  - 已导出镜像 tar

## 已覆盖 PR

```text
5776 6349 6473 6574 6578 6644 6660 6942 7008
7015 7017 7046 7066 7072 7126 7137 7138 7140
```

## 自检

```powershell
cd D:\RepoAces\prdockers
powershell -ExecutionPolicy Bypass -File .\scripts\Test-Configs.ps1
```

期望结果：

```text
Config check passed: 18 PR configs
Compose check passed: 18 docker-compose.yml files
```

## 用 Docker Compose 跑某个 PR

以 PR 7138 为例：

```powershell
cd D:\RepoAces\prdockers\compose\fastgpt-pr-7138
docker compose build
docker compose run --rm evaluator
```

默认 `.env` 里是：

```text
MODE=env
```

要跑其他阶段，修改 `.env`：

```text
MODE=test
MODE=build
MODE=docker
MODE=all
```

然后执行：

```powershell
docker compose run --rm evaluator
```

## 用候选 patch 跑

把 OpenHands 导出的候选 patch 复制到对应 PR 的 compose 目录，并命名为：

```text
candidate.patch
```

然后执行：

```powershell
docker compose -f docker-compose.yml -f docker-compose.patch.yml run --rm evaluator
```

结果会写到：

```text
D:\RepoAces\prdockers\dist\compose-results\fastgpt-pr-xxxx\
```

## 导出给师兄的 Compose 配置包

```powershell
cd D:\RepoAces\prdockers
powershell -ExecutionPolicy Bypass -File .\scripts\Export-ComposeBundle.ps1
```

生成：

```text
D:\RepoAces\prdockers\dist\share\compose-bundle
```

把整个 `compose-bundle` 文件夹发给师兄。里面包含：

```text
configs/
compose/
dockerfiles/
runtime/
scripts/
docs/
README.md
README-COMPOSE-BUNDLE.md
manifest.json
```

师兄收到后：

```powershell
cd compose-bundle\compose\fastgpt-pr-7138
docker compose build
docker compose run --rm evaluator
```

也可以先在 bundle 根目录运行整包自检：

```powershell
cd compose-bundle
powershell -ExecutionPolicy Bypass -File .\scripts\Verify-ComposeBundle.ps1
```

如果要在师兄电脑上做完整 smoke test：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Verify-ComposeBundle.ps1 -BuildSmoke -RunSmoke
```

## 导出已构建镜像 tar

如果你已经构建了某个 PR 镜像，可以导出 tar：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Export-PrImage.ps1 -Pr 7138
```

已生成过：

```text
D:\RepoAces\prdockers\dist\share\fastgpt-pr-7138
```

## 注意

- 不建议一次性构建 18 个完整镜像，体积会非常大。建议按 PR 构建。
- 7015、7017、6942、7126、7137 涉及 private `pro`，配置里有 guard；缺少 private submodule 时会明确失败。
- 5776 是 compose/deploy PR，不跑 root test，重点跑 `docker compose config`。
- 6644 需要 Bun，配置里 `requires_bun=true`。
- 7138 必须跑 `projects/app` build，因为 targeted tests 不能覆盖 shared/global 类型遗漏。
