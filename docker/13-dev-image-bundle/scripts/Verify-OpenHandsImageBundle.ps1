[CmdletBinding()]
param(
  [string]$Root = "",
  [int]$ExpectedPrCount = 13,
  [switch]$CheckCompose
)

$ErrorActionPreference = "Stop"

if (-not $Root) {
  $scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
  $Root = Split-Path -Parent $scriptDir
}

foreach ($dir in @("configs", "oh-compose", "dockerfiles", "runtime", "scripts")) {
  $full = Join-Path $Root $dir
  if (-not (Test-Path -LiteralPath $full)) {
    throw "Missing $dir"
  }
  Write-Host "OK $dir"
}

$configs = @(Get-ChildItem -LiteralPath (Join-Path $Root "configs") -Filter "*.eval.json")
$composeDirs = @(Get-ChildItem -LiteralPath (Join-Path $Root "oh-compose") -Directory)

if ($configs.Count -ne $ExpectedPrCount) {
  throw "Expected $ExpectedPrCount configs, found $($configs.Count)"
}
if ($composeDirs.Count -ne $ExpectedPrCount) {
  throw "Expected $ExpectedPrCount oh-compose dirs, found $($composeDirs.Count)"
}

Write-Host "OK configs: $($configs.Count)"
Write-Host "OK oh compose: $($composeDirs.Count)"

$dockerfilePath = Join-Path $Root "dockerfiles\FastGPT.OpenHands.Dockerfile"
$dockerfileText = Get-Content -Raw -LiteralPath $dockerfilePath
if ($dockerfileText -notmatch "ghcr.io/openhands/agent-server:1\.26\.0-python") {
  throw "Dockerfile must use ghcr.io/openhands/agent-server:1.26.0-python as default base image"
}
if ($dockerfileText -match "oh-instructions|scopes|REPOACES_INSTRUCTION|REPOACES_SCOPE") {
  throw "Dockerfile contains handoff/instruction artifacts; image bundle should stay minimal"
}
if ($dockerfileText -notmatch "git clone --no-checkout" -or $dockerfileText -notmatch "install-fastgpt-deps.sh") {
  throw "Dockerfile must clone FastGPT and run the FastGPT dependency install helper"
}

foreach ($path in @(
  (Join-Path $Root "runtime\openhands-common-commands.sh"),
  (Join-Path $Root "runtime\install-fastgpt-deps.sh"),
  (Join-Path $Root "runtime\docker-compose-config.sh"),
  (Join-Path $Root "runtime\compose.env")
)) {
  if (-not (Test-Path -LiteralPath $path)) {
    throw "Missing runtime helper: $path"
  }
}

foreach ($extra in @(
  (Join-Path $Root "dockerfiles\FastGPT.Evaluator.Dockerfile"),
  (Join-Path $Root "runtime\run-eval.sh"),
  (Join-Path $Root "runtime\run-commands.mjs")
)) {
  if (Test-Path -LiteralPath $extra) {
    throw "Minimal image bundle should not include evaluator artifact: $extra"
  }
}

foreach ($config in $configs) {
  $caseId = $config.BaseName -replace "\.eval$", ""
  $configJson = Get-Content -Raw -LiteralPath $config.FullName | ConvertFrom-Json
  $baseCommit = [string]$configJson.PSObject.Properties["base_commit"].Value
  $composePath = Join-Path $Root "oh-compose\$caseId\docker-compose.yml"
  $envPath = Join-Path $Root "oh-compose\$caseId\.env"

  if ($configJson.PSObject.Properties.Name -contains "changed_files" -or $configJson.PSObject.Properties.Name -contains "commands") {
    throw "$caseId config contains evaluator fields changed_files/commands"
  }
  foreach ($required in @("case_id", "pr_number", "base_commit", "pnpm_version")) {
    if (-not ($configJson.PSObject.Properties.Name -contains $required)) {
      throw "$caseId config missing required image field: $required"
    }
  }

  if (-not (Test-Path -LiteralPath $composePath)) {
    throw "Missing compose file for $caseId"
  }
  if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Missing .env file for $caseId"
  }

  $composeText = Get-Content -Raw -LiteralPath $composePath
  $envText = Get-Content -Raw -LiteralPath $envPath

  if ($composeText -match "REPOACES_INSTRUCTION|REPOACES_SCOPE") {
    throw "$caseId compose contains handoff/instruction env vars"
  }
  if ($envText -notmatch "BASE_COMMIT=$baseCommit") {
    throw "$caseId .env base commit mismatch"
  }
}

if ($CheckCompose) {
  foreach ($dir in $composeDirs | Sort-Object Name) {
    Push-Location $dir.FullName
    try {
      docker compose config --quiet
      if ($LASTEXITCODE -ne 0) {
        throw "docker compose config failed: $($dir.Name)"
      }
      Write-Host "OK compose $($dir.Name)"
    } finally {
      Pop-Location
    }
  }
}

Write-Host ""
Write-Host "OpenHands image bundle verification passed"
