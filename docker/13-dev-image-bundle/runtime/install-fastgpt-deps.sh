#!/usr/bin/env bash
set -euo pipefail

log_file="$(mktemp)"
cleanup() {
  rm -f "${log_file}"
}
trap cleanup EXIT

if pnpm install --frozen-lockfile 2>&1 | tee "${log_file}"; then
  exit 0
fi

status=$?
if ! grep -q "ERR_PNPM_OUTDATED_LOCKFILE" "${log_file}"; then
  exit "${status}"
fi

echo "WARN: frozen lockfile install failed because this base commit has an outdated pnpm-lock.yaml." >&2
echo "WARN: Falling back to pnpm install --no-frozen-lockfile, then restoring pnpm-lock.yaml to keep the workspace clean." >&2

pnpm install --no-frozen-lockfile

if git rev-parse --is-inside-work-tree >/dev/null 2>&1 && [[ -f pnpm-lock.yaml ]]; then
  git checkout -- pnpm-lock.yaml
fi
