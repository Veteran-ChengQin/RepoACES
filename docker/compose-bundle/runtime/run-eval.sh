#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-all}"
CONFIG_PATH="${EVAL_CONFIG:-/opt/repoaces-pr/eval.json}"
PATCH_FILE="${PATCH_FILE:-/patches/candidate.patch}"
RESULT_DIR="${RESULT_DIR:-/results}"

mkdir -p "${RESULT_DIR}"

export npm_config_store_dir="${npm_config_store_dir:-/tmp/repoaces-pnpm-store}"
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
export CI="${CI:-true}"
export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=8192}"

BASE_COMMIT="$(node -e "const c=require('${CONFIG_PATH}'); process.stdout.write(c.base_commit)")"
PNPM_VERSION="$(node -e "const c=require('${CONFIG_PATH}'); process.stdout.write(c.pnpm_version || '')")"

if [[ -n "${PNPM_VERSION}" ]]; then
  corepack prepare "pnpm@${PNPM_VERSION}" --activate >/dev/null
fi

cd /workspace
git config --global --add safe.directory /workspace
git reset --hard "${BASE_COMMIT}" >/dev/null
git clean -fdx -e node_modules -e .pnpm-store >/dev/null

if [[ -s "${PATCH_FILE}" ]]; then
  echo "Applying patch: ${PATCH_FILE}"
  if ! git apply --whitespace=fix "${PATCH_FILE}"; then
    echo "Plain git apply failed; retrying with whitespace-tolerant apply."
    if ! git apply --ignore-space-change --ignore-whitespace --whitespace=fix "${PATCH_FILE}"; then
      echo "Whitespace-tolerant apply failed; retrying with --3way."
      git apply --3way --ignore-space-change --ignore-whitespace --whitespace=fix "${PATCH_FILE}"
    fi
  fi
else
  echo "No candidate patch mounted. Running checks on base workspace."
fi

node /opt/repoaces-pr/run-commands.mjs "${CONFIG_PATH}" "${MODE}" "${RESULT_DIR}"
