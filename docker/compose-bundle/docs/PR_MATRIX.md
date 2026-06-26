# PR Evaluation Matrix

| PR | Scope | Required gates |
| --- | --- | --- |
| 5776 | deploy/docker-compose healthcheck | env, docker compose config |
| 6349 | vector DB migration | service vector tests, app build |
| 6473 | docs analytics script | document build, document Dockerfile build |
| 6574 | skill permission management | agent skill controller tests, app build |
| 6578 | agent skill reference logging | focused service/app tests, app build |
| 6644 | agent skill version list + volume-manager | bun env, compose config, volume-manager build, app build |
| 6660 | skill version update/switch | app build |
| 6942 | image dataset search | pro guard, service dataset search tests, app build |
| 7008 | code-sandbox queueId limit | queue unit/integration tests, code-sandbox build |
| 7015 | context compression benchmark adapter | pro guard, service typecheck |
| 7017 | browser sandbox image packaging | pro/browser-sandbox guard, typecheck/test/build/docker build |
| 7046 | MiniMax docs config | document build |
| 7066 | markdown/code block rendering | app build |
| 7072 | docx image upload/read file worker | focused service/global tests, app build |
| 7126 | OpenAPI API-key auth proxy | pro guard, OpenAPI service/app tests, app build |
| 7137 | helper bot through pro | pro guard, helper bot tests, app build |
| 7138 | system tool status filtering | global/service/app tests, app build |
| 7140 | agent dataset auth entry | global/service tests, app build |

## Compose entry

Each PR has:

```text
compose/fastgpt-pr-xxxx/
  .env
  docker-compose.yml
  docker-compose.patch.yml
  README.md
```

Default mode is `env`. Change `.env` to run `test`, `build`, `docker`, or `all`.
