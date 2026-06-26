[CmdletBinding()]
param(
  [string]$Root = ""
)

$ErrorActionPreference = "Stop"

if (-not $Root) {
  $Root = Split-Path -Parent $PSScriptRoot
}

$configDir = Join-Path $Root "configs"
$runtimeDir = Join-Path $Root "runtime"
$dockerfile = Join-Path $Root "dockerfiles\FastGPT.Evaluator.Dockerfile"

if (-not (Test-Path -LiteralPath $dockerfile)) {
  throw "Missing Dockerfile: $dockerfile"
}

foreach ($path in @(
  "run-eval.sh",
  "run-commands.mjs",
  "docker-compose-config.sh",
  "compose.env"
)) {
  $full = Join-Path $runtimeDir $path
  if (-not (Test-Path -LiteralPath $full)) {
    throw "Missing runtime file: $full"
  }
}

$configs = @(Get-ChildItem -LiteralPath $configDir -Filter "*.eval.json" | Sort-Object Name)
if ($configs.Count -eq 0) {
  throw "No eval configs found in $configDir"
}

foreach ($configPath in $configs) {
  $config = Get-Content -Raw -LiteralPath $configPath.FullName | ConvertFrom-Json
  foreach ($required in @("case_id", "pr_number", "base_commit", "pnpm_version", "commands")) {
    if (-not $config.PSObject.Properties.Name.Contains($required)) {
      throw "$($configPath.Name) missing required field: $required"
    }
  }
  if (-not $config.case_id.StartsWith("fastgpt-pr-")) {
    throw "$($configPath.Name) has invalid case_id: $($config.case_id)"
  }
  if ($config.commands.Count -eq 0) {
    throw "$($configPath.Name) has no commands"
  }
  foreach ($command in $config.commands) {
    foreach ($required in @("name", "phase", "cwd", "shell", "timeout_seconds")) {
      if (-not $command.PSObject.Properties.Name.Contains($required)) {
        throw "$($configPath.Name) command missing field $required"
      }
    }
    if (@("env", "test", "build", "docker") -notcontains $command.phase) {
      throw "$($configPath.Name) command $($command.name) has invalid phase: $($command.phase)"
    }
  }
  Write-Host "OK $($configPath.Name): $($config.commands.Count) commands"
}

Write-Host ""
Write-Host "Config check passed: $($configs.Count) PR configs"

$composeDir = Join-Path $Root "compose"
if (Test-Path -LiteralPath $composeDir) {
  $composeFiles = @(Get-ChildItem -LiteralPath $composeDir -Recurse -Filter "docker-compose.yml")
  if ($composeFiles.Count -gt 0 -and $composeFiles.Count -ne $configs.Count) {
    throw "Compose count ($($composeFiles.Count)) does not match config count ($($configs.Count))"
  }
  if ($composeFiles.Count -gt 0) {
    Write-Host "Compose check passed: $($composeFiles.Count) docker-compose.yml files"
  }
}
