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

cd /workspace
git config --global --add safe.directory /workspace
git reset --hard "${BASE_COMMIT}" >/dev/null
git clean -fdx -e node_modules -e .pnpm-store >/dev/null

if [[ -s "${PATCH_FILE}" ]]; then
  echo "Applying patch: ${PATCH_FILE}"
  if ! git apply --whitespace=fix "${PATCH_FILE}"; then
    echo "Plain git apply failed; retrying with --3way."
    git apply --3way --whitespace=fix "${PATCH_FILE}"
  fi
else
  echo "No candidate patch mounted. Running checks on base workspace."
fi

REQUIRED_PNPM="$(node -e "const fs=require('fs'); const p=JSON.parse(fs.readFileSync('package.json','utf8')); const pm=(p.packageManager||'').match(/^pnpm@(.+)$/); process.stdout.write((pm&&pm[1]) || (p.engines&&p.engines.pnpm) || '')")"
if [[ -n "${REQUIRED_PNPM}" ]]; then
  PNPM_TARGET="${REQUIRED_PNPM}"
  if [[ "${PNPM_TARGET}" =~ ^([0-9]+)\.x$ ]]; then
    REQUIRED_MAJOR="${BASH_REMATCH[1]}"
    if [[ "${PNPM_VERSION}" == "${REQUIRED_MAJOR}."* ]]; then
      PNPM_TARGET="${PNPM_VERSION}"
    else
      PNPM_TARGET="${REQUIRED_MAJOR}"
    fi
  fi
  echo "Using pnpm@${PNPM_TARGET} for required range ${REQUIRED_PNPM}"
  npm install -g --force "pnpm@${PNPM_TARGET}" >/dev/null
  ln -sf "$(command -v pnpm)" /usr/local/bin/pnpm
elif [[ -n "${PNPM_VERSION}" ]]; then
  echo "Using configured pnpm@${PNPM_VERSION}"
  npm install -g --force "pnpm@${PNPM_VERSION}" >/dev/null
  ln -sf "$(command -v pnpm)" /usr/local/bin/pnpm
fi

node /opt/repoaces-pr/run-commands.mjs "${CONFIG_PATH}" "${MODE}" "${RESULT_DIR}"
