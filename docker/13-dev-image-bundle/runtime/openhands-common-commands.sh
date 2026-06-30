#!/usr/bin/env bash
set -euo pipefail

phase="${1:-all}"

run_env() {
  node --version
  npm --version
  pnpm --version
  git --version
  rg --version | head -1
  bash /opt/repoaces-oh/install-fastgpt-deps.sh
  git diff --check
}

run_build() {
  pnpm build
}

run_test() {
  pnpm test
}

run_compose() {
  local files=(
    "deploy/dev/docker-compose.yml"
    "deploy/dev/docker-compose.cn.yml"
    "deploy/docker/cn/docker-compose.pg.yml"
    "deploy/docker/global/docker-compose.pg.yml"
  )

  local found=0
  for file in "${files[@]}"; do
    if [[ -f "${file}" ]]; then
      found=1
      echo "== docker compose config: ${file}"
      bash /opt/repoaces-oh/docker-compose-config.sh "${file}"
    fi
  done

  if [[ "${found}" -eq 0 ]]; then
    echo "No common real docker compose files were found in this base commit."
  fi
}

case "${phase}" in
  env)
    run_env
    ;;
  build)
    run_build
    ;;
  test)
    run_test
    ;;
  compose|docker)
    run_compose
    ;;
  all)
    run_env
    run_build
    run_test
    run_compose
    ;;
  *)
    echo "Usage: $0 {env|build|test|compose|all}" >&2
    exit 2
    ;;
esac
