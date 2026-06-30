[CmdletBinding()]
param(
  [string]$Root = "",
  [int]$ExpectedPrCount = 13,
  [string]$SmokePr = "7138",
  [switch]$RunSmoke,
  [switch]$BuildSmoke
)

$ErrorActionPreference = "Stop"

if (-not $Root) {
  $Root = (Resolve-Path ".").Path
}

if (-not $env:DOCKER_CONFIG) {
  $env:DOCKER_CONFIG = Join-Path $Root ".docker-config"
  New-Item -ItemType Directory -Force -Path $env:DOCKER_CONFIG | Out-Null
}

function Step {
  param([string]$Message)
  Write-Host ""
  Write-Host "==> $Message" -ForegroundColor Cyan
}

Step "Check bundle layout"
$requiredDirs = @("configs", "compose", "dockerfiles", "runtime", "scripts")
foreach ($dir in $requiredDirs) {
  $path = Join-Path $Root $dir
  if (-not (Test-Path -LiteralPath $path)) {
    throw "Missing required directory: $path"
  }
  Write-Host "OK $dir"
}

$configs = @(Get-ChildItem -LiteralPath (Join-Path $Root "configs") -Filter "*.eval.json")
$composeDirs = @(Get-ChildItem -LiteralPath (Join-Path $Root "compose") -Directory)
if ($configs.Count -ne $ExpectedPrCount) {
  throw "Expected $ExpectedPrCount configs, found $($configs.Count)"
}
if ($composeDirs.Count -ne $ExpectedPrCount) {
  throw "Expected $ExpectedPrCount compose directories, found $($composeDirs.Count)"
}
Write-Host "OK configs: $($configs.Count)"
Write-Host "OK compose dirs: $($composeDirs.Count)"

Step "Check Docker CLI"
docker --version | Out-Host
if ($LASTEXITCODE -ne 0) {
  throw "docker --version failed. Install Docker Desktop first."
}

docker compose version | Out-Host
if ($LASTEXITCODE -ne 0) {
  throw "docker compose version failed. Install Docker Compose plugin or update Docker Desktop."
}

Step "Check docker-compose.yml syntax for every PR"
$failed = @()
foreach ($dir in $composeDirs | Sort-Object Name) {
  Push-Location $dir.FullName
  docker compose config --quiet
  if ($LASTEXITCODE -ne 0) {
    $failed += $dir.Name
  } else {
    Write-Host "OK $($dir.Name)"
  }
  Pop-Location
}
if ($failed.Count -gt 0) {
  throw "docker compose config failed: $($failed -join ', ')"
}

if ($BuildSmoke -or $RunSmoke) {
  $caseId = if ($SmokePr.StartsWith("fastgpt-pr-")) { $SmokePr } else { "fastgpt-pr-$SmokePr" }
  $smokeDir = Join-Path (Join-Path $Root "compose") $caseId
  if (-not (Test-Path -LiteralPath $smokeDir)) {
    throw "Smoke PR compose directory not found: $smokeDir"
  }

  Push-Location $smokeDir
  try {
    if ($BuildSmoke) {
      Step "Build smoke image for $caseId"
      docker compose build
      if ($LASTEXITCODE -ne 0) {
        throw "docker compose build failed for $caseId"
      }
    }

    if ($RunSmoke) {
      Step "Run smoke env for $caseId"
      docker compose run --rm evaluator
      if ($LASTEXITCODE -ne 0) {
        throw "docker compose run failed for $caseId"
      }
      docker compose down | Out-Null
    }
  } finally {
    Pop-Location
  }
}

Step "Bundle verification passed"
Write-Host "This compose bundle is structurally ready for handoff."
if (-not ($BuildSmoke -or $RunSmoke)) {
  Write-Host "For a full machine-level smoke test, rerun with -BuildSmoke -RunSmoke."
}
