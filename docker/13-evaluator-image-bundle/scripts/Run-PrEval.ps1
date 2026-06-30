[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$Pr,

  [ValidateSet("env", "test", "build", "docker", "all")]
  [string]$Mode = "all",

  [string]$Patch = "",
  [string]$ImagePrefix = "repoaces/eval",
  [string]$ResultRoot = "",
  [switch]$MountDockerSocket
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
if (-not $env:DOCKER_CONFIG) {
  $env:DOCKER_CONFIG = Join-Path $root ".docker-config"
  New-Item -ItemType Directory -Force -Path $env:DOCKER_CONFIG | Out-Null
}
$caseId = if ($Pr.StartsWith("fastgpt-pr-")) { $Pr } else { "fastgpt-pr-$Pr" }
$configPath = Join-Path $root "configs\$caseId.eval.json"

if (-not (Test-Path -LiteralPath $configPath)) {
  throw "Config not found: $configPath"
}

$config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$prNumber = [string]$config.pr_number
$baseCommit = [string]$config.PSObject.Properties["base_commit"].Value
$imageRef = "$ImagePrefix-$prNumber`:$($baseCommit.Substring(0, 12))"

if (-not $ResultRoot) {
  $ResultRoot = Join-Path $root "dist\results\$caseId-$Mode-$(Get-Date -Format yyyyMMdd-HHmmss)"
}
New-Item -ItemType Directory -Force -Path $ResultRoot | Out-Null

$dockerArgs = @("run", "--rm", "-v", "${ResultRoot}:/results")

if ($Patch) {
  $patchPath = (Resolve-Path $Patch).Path
  $dockerArgs += @("-v", "${patchPath}:/patches/candidate.patch:ro")
}

if ($MountDockerSocket -or $Mode -in @("docker", "all")) {
  $dockerArgs += @("-v", "/var/run/docker.sock:/var/run/docker.sock")
}

$dockerArgs += @($imageRef, $Mode)

Write-Host "Running: docker $($dockerArgs -join ' ')"
docker @dockerArgs
$exit = $LASTEXITCODE

Write-Host ""
Write-Host "Results: $ResultRoot"
if ($exit -ne 0) {
  throw "evaluation failed with exit code $exit"
}
