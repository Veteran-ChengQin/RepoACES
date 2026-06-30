#!/usr/bin/env bash
set -euo pipefail

env_file="${COMPOSE_ENV_FILE:-/opt/repoaces-oh/compose.env}"

if [[ ! -f "${env_file}" && -f /opt/repoaces-pr/compose.env ]]; then
  env_file=/opt/repoaces-pr/compose.env
fi

run_config() {
  local file="$1"
  if docker compose version >/dev/null 2>&1; then
    docker compose --env-file "${env_file}" -f "${file}" config
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose --env-file "${env_file}" -f "${file}" config
  else
    echo "Neither 'docker compose' nor 'docker-compose' is available." >&2
    exit 127
  fi
}

if [[ "$#" -gt 0 ]]; then
  run_config "$1"
  exit 0
fi

files=(
  "deploy/dev/docker-compose.yml"
  "deploy/dev/docker-compose.cn.yml"
  "deploy/docker/cn/docker-compose.pg.yml"
  "deploy/docker/global/docker-compose.pg.yml"
)

found=0
for file in "${files[@]}"; do
  if [[ -f "${file}" ]]; then
    found=1
    echo "== docker compose config: ${file}"
    run_config "${file}"
  fi
done

if [[ "${found}" -eq 0 ]]; then
  echo "No common real docker compose files were found in this base commit."
fi
