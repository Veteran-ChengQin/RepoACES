#!/usr/bin/env bash
set -euo pipefail

file="${1:?compose file is required}"
env_file="${COMPOSE_ENV_FILE:-/opt/repoaces-oh/compose.env}"

if [[ ! -f "${env_file}" && -f /opt/repoaces-pr/compose.env ]]; then
  env_file=/opt/repoaces-pr/compose.env
fi

if docker compose version >/dev/null 2>&1; then
  docker compose --env-file "${env_file}" -f "${file}" config
elif command -v docker-compose >/dev/null 2>&1; then
  docker-compose --env-file "${env_file}" -f "${file}" config
else
  echo "Neither 'docker compose' nor 'docker-compose' is available." >&2
  exit 127
fi
