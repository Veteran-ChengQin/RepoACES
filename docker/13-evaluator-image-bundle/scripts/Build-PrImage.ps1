[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$Pr,

  [string]$ImagePrefix = "repoaces/eval",
  [string]$FastGptRepo = "https://github.com/labring/FastGPT.git",
  [string]$NodeImage = "ghcr.io/openhands/agent-server:1.26.0-python",
  [string]$NpmRegistry = "",
  [switch]$NoCache,
  [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
if (-not $env:DOCKER_CONFIG) {
  $env:DOCKER_CONFIG = Join-Path $root ".docker-config"
  New-Item -ItemType Directory -Force -Path $env:DOCKER_CONFIG | Out-Null
}
$caseId = if ($Pr.StartsWith("fastgpt-pr-")) { $Pr } else { "fastgpt-pr-$Pr" }
$configPath = Join-Path $root "configs\$caseId.eval.json"
$dockerfile = Join-Path $root "dockerfiles\FastGPT.Evaluator.Dockerfile"

if (-not (Test-Path -LiteralPath $configPath)) {
  throw "Config not found: $configPath"
}

$config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$prNumber = [string]$config.pr_number
$baseCommit = [string]$config.PSObject.Properties["base_commit"].Value
$pnpmVersion = [string]$config.PSObject.Properties["pnpm_version"].Value
$imageRef = "$ImagePrefix-$prNumber`:$($baseCommit.Substring(0, 12))"
$installBun = if ($config.PSObject.Properties.Name.Contains("requires_bun") -and $config.requires_bun) { "true" } else { "false" }

$args = @(
  "build",
  "-f", $dockerfile,
  "--build-arg", "PR_ID=$caseId",
  "--build-arg", "NODE_IMAGE=$NodeImage",
  "--build-arg", "BASE_COMMIT=$baseCommit",
  "--build-arg", "FASTGPT_REPO=$FastGptRepo",
  "--build-arg", "PNPM_VERSION=$pnpmVersion",
  "--build-arg", "INSTALL_BUN=$installBun"
)

if ($NpmRegistry) {
  $args += @("--build-arg", "NPM_REGISTRY=$NpmRegistry")
}
if ($NoCache) {
  $args += "--no-cache"
}

$args += @("-t", $imageRef, $root)

Write-Host "Building image: $imageRef"
Write-Host "Config: $configPath"
docker @args
if ($LASTEXITCODE -ne 0) {
  throw "docker build failed with exit code $LASTEXITCODE"
}

if (-not $SkipVerify) {
  Write-Host ""
  Write-Host "Verifying image env phase..."
  $resultDir = Join-Path $root "dist\verify-$caseId"
  New-Item -ItemType Directory -Force -Path $resultDir | Out-Null
  docker run --rm `
    -v "${resultDir}:/results" `
    $imageRef env
  if ($LASTEXITCODE -ne 0) {
    throw "image env verification failed with exit code $LASTEXITCODE"
  }
}

Write-Host ""
Write-Host "Built: $imageRef"
