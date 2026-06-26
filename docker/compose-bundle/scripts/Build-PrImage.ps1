[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$Pr,

  [string]$ImagePrefix = "repoaces/eval",
  [string]$FastGptRepo = "https://github.com/labring/FastGPT.git",
  [string]$NodeImage = "node:20.19.5-bookworm",
  [string]$NpmRegistry = "",
  [switch]$NoCache,
  [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$caseId = if ($Pr.StartsWith("fastgpt-pr-")) { $Pr } else { "fastgpt-pr-$Pr" }
$configPath = Join-Path $root "configs\$caseId.eval.json"
$dockerfile = Join-Path $root "dockerfiles\FastGPT.Evaluator.Dockerfile"

if (-not (Test-Path -LiteralPath $configPath)) {
  throw "Config not found: $configPath"
}

$config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$imageRef = "$ImagePrefix-$($config.pr_number):$($config.base_commit.Substring(0, 12))"
$installBun = if ($config.PSObject.Properties.Name.Contains("requires_bun") -and $config.requires_bun) { "true" } else { "false" }

$args = @(
  "build",
  "-f", $dockerfile,
  "--build-arg", "PR_ID=$caseId",
  "--build-arg", "NODE_IMAGE=$NodeImage",
  "--build-arg", "BASE_COMMIT=$($config.base_commit)",
  "--build-arg", "FASTGPT_REPO=$FastGptRepo",
  "--build-arg", "PNPM_VERSION=$($config.pnpm_version)",
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
