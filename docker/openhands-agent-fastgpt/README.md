# RepoACES OpenHands FastGPT Agent Server Image

This directory builds a custom OpenHands `agent-server` image for RepoACES feature-development runs.

The OpenHands web/server image remains unchanged. RepoACES switches only the execution sandbox image through:

```powershell
$env:REPOACES_AGENT_SERVER_IMAGE_REPOSITORY = "repoaces/openhands-agent-fastgpt"
$env:REPOACES_AGENT_SERVER_IMAGE_TAG = "node20-pnpm10"
```

## Contents

Base image:

```text
ghcr.io/openhands/agent-server:1.26.0-python
```

Pinned toolchain:

```text
Node.js 20.19.5
pnpm 10.11.0
git
ripgrep
jq
build-essential
pkg-config
```

The original OpenHands entrypoint is inherited from the base image.

## Build

From the repository root:

```powershell
.\scripts\build_openhands_agent_fastgpt.ps1
```

With an npm registry mirror:

```powershell
.\scripts\build_openhands_agent_fastgpt.ps1 -NpmRegistry "https://registry.npmmirror.com"
```

With a proxy:

```powershell
.\scripts\build_openhands_agent_fastgpt.ps1 -Proxy "http://127.0.0.1:7890"
```

## Verify

The build script runs this check after building:

```bash
node --version
npm --version
pnpm --version
git --version
rg --version
whoami
```

Expected user:

```text
openhands
```

## Use With RepoACES

```powershell
$env:REPOACES_AGENT_SERVER_IMAGE_REPOSITORY = "repoaces/openhands-agent-fastgpt"
$env:REPOACES_AGENT_SERVER_IMAGE_TAG = "node20-pnpm10"

python .\scripts\repoaces.py start-openhands `
  --artifact-root .\tmp\experiments\repoaces\fastgpt-pr-7008\<run-id> `
  --sandbox-repo-path /workspace `
  --model gpt-5.4 `
  --auto-run true
```

The image prepares only the coding environment. Repository checkout still belongs to `prepare-workspace`, and deterministic validation still belongs to `final-evaluate`.
