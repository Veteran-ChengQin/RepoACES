[CmdletBinding()]
param(
  [string]$ImageName = "repoaces/openhands-agent-fastgpt",
  [string]$Tag = "node20-pnpm10",
  [string]$BaseImage = "ghcr.io/openhands/agent-server:1.26.0-python",
  [string]$NodeVersion = "20.19.5",
  [string]$PnpmVersion = "10.11.0",
  [string]$NpmRegistry = "",
  [string]$Proxy = "",
  [string]$NoProxy = "localhost,127.0.0.1,host.docker.internal",
  [switch]$NoPull,
  [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$context = Join-Path $repoRoot "docker\openhands-agent-fastgpt"
$dockerfile = Join-Path $context "Dockerfile"

if (-not (Test-Path -LiteralPath $dockerfile)) {
  throw "Dockerfile not found: $dockerfile"
}

$imageRef = "${ImageName}:${Tag}"
$buildArgs = @(
  "build",
  "--build-arg", "BASE_IMAGE=$BaseImage",
  "--build-arg", "NODE_VERSION=$NodeVersion",
  "--build-arg", "PNPM_VERSION=$PnpmVersion"
)

if (-not $NoPull) {
  $buildArgs += "--pull"
}

if ($NpmRegistry) {
  $buildArgs += @("--build-arg", "NPM_REGISTRY=$NpmRegistry")
}

if ($Proxy) {
  $buildArgs += @(
    "--build-arg", "HTTP_PROXY=$Proxy",
    "--build-arg", "HTTPS_PROXY=$Proxy",
    "--build-arg", "http_proxy=$Proxy",
    "--build-arg", "https_proxy=$Proxy",
    "--build-arg", "ALL_PROXY=$Proxy",
    "--build-arg", "all_proxy=$Proxy",
    "--build-arg", "NO_PROXY=$NoProxy",
    "--build-arg", "no_proxy=$NoProxy"
  )
}

$buildArgs += @("-t", $imageRef, $context)

Write-Host "Building $imageRef"
Write-Host "Context: $context"
docker @buildArgs
if ($LASTEXITCODE -ne 0) {
  throw "docker build failed with exit code $LASTEXITCODE"
}

if (-not $SkipVerify) {
  Write-Host "Verifying $imageRef"
  docker run --rm --entrypoint sh $imageRef -lc "node --version && npm --version && pnpm --version && git --version && rg --version | head -1 && whoami"
  if ($LASTEXITCODE -ne 0) {
    throw "docker run verification failed with exit code $LASTEXITCODE"
  }
}

Write-Host ""
Write-Host "Built image: $imageRef"
Write-Host "Use it with:"
Write-Host "`$env:REPOACES_AGENT_SERVER_IMAGE_REPOSITORY = `"$ImageName`""
Write-Host "`$env:REPOACES_AGENT_SERVER_IMAGE_TAG = `"$Tag`""
