param(
  [string]$CasesRoot = "cases\13cases_6_28",
  [string]$RunNamePrefix = "",
  [string]$Model = "gpt-5.4",
  [string]$WslDistro = "Ubuntu-22.04",
  [string]$OpenHandsPort = "3000",
  [int]$PrepareTimeout = 3600,
  [int]$StageTimeout = 3600,
  [int]$FinalEvalTimeout = 3600,
  [int]$PollInterval = 60,
  [int[]]$SkipPr = @(7008, 7138),
  [switch]$BuildMissingImages,
  [string]$NpmRegistry = "https://registry.npmmirror.com",
  [switch]$SkipEvaluatorImageVerify,
  [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
  $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Write-Host "[$timestamp] $Message"
}

function Read-CaseId([string]$CaseYaml) {
  foreach ($line in Get-Content -LiteralPath $CaseYaml) {
    if ($line.TrimStart().StartsWith("id:")) {
      return $line.Split(":", 2)[1].Trim().Trim("'").Trim('"')
    }
  }
  return (Split-Path -Leaf (Split-Path -Parent $CaseYaml))
}

function Read-BaseCommit([string]$ConfigPath, [string]$CaseYaml) {
  if (Test-Path -LiteralPath $ConfigPath) {
    $json = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
    if ($json.base_commit) {
      return [string]$json.base_commit
    }
  }
  foreach ($line in Get-Content -LiteralPath $CaseYaml) {
    if ($line.TrimStart().StartsWith("base_commit:")) {
      return $line.Split(":", 2)[1].Trim().Trim("'").Trim('"')
    }
  }
  throw "Cannot find base_commit for $CaseYaml"
}

function Test-DockerImageExists([string]$ImageRef) {
  $oldErrorActionPreference = $ErrorActionPreference
  $oldNativePreference = $null
  $hasNativePreference = Get-Variable -Name PSNativeCommandUseErrorActionPreference -Scope Global -ErrorAction SilentlyContinue
  if ($hasNativePreference) {
    $oldNativePreference = $global:PSNativeCommandUseErrorActionPreference
    $global:PSNativeCommandUseErrorActionPreference = $false
  }
  try {
    $ErrorActionPreference = "Continue"
    docker image inspect $ImageRef *> $null
    return ($LASTEXITCODE -eq 0)
  } catch {
    return $false
  } finally {
    $ErrorActionPreference = $oldErrorActionPreference
    if ($hasNativePreference) {
      $global:PSNativeCommandUseErrorActionPreference = $oldNativePreference
    }
  }
}

if (-not (Test-Path -LiteralPath "repoaces_multiagent\cli.py")) {
  throw "Run this script from the RepoACES repository root."
}

if (-not $RunNamePrefix) {
  $RunNamePrefix = "multiagent-13cases-" + (Get-Date -Format "yyyyMMdd-HHmmss")
}

$projectRoot = (Get-Location).Path
$batchRoot = Join-Path $projectRoot ("tmp\experiments\repoaces-multiagent-batches\" + $RunNamePrefix)
New-Item -ItemType Directory -Force -Path $batchRoot | Out-Null

$env:REPOACES_OPENHANDS_HOME_TEMPLATE = Join-Path $projectRoot ".openhands-home"
$env:REPOACES_OPENHANDS_PORT = $OpenHandsPort
$env:PYTHONUNBUFFERED = "1"
$env:REPOACES_COMPOSE_BUNDLE_ROOT = Join-Path $projectRoot "docker\13-evaluator-image-bundle"
$env:REPOACES_COMPOSE_EVAL_IMAGE_PREFIX = "repoaces/eval"

$skipSet = [System.Collections.Generic.HashSet[int]]::new()
foreach ($value in $SkipPr) {
  foreach ($part in ([string]$value).Split(",", [System.StringSplitOptions]::RemoveEmptyEntries)) {
    [void]$skipSet.Add([int]$part.Trim())
  }
}

$caseDirs = Get-ChildItem -Directory -LiteralPath $CasesRoot | Sort-Object Name
$plan = @()
foreach ($dir in $caseDirs) {
  $caseYaml = Join-Path $dir.FullName "case.yaml"
  if (-not (Test-Path -LiteralPath $caseYaml)) {
    continue
  }
  $caseId = Read-CaseId $caseYaml
  $pr = [int]($caseId -replace "^fastgpt-pr-", "")
  if ($skipSet.Contains($pr)) {
    continue
  }
  $devConfig = Join-Path $projectRoot ("docker\13-dev-image-bundle\configs\" + $caseId + ".eval.json")
  $baseCommit = Read-BaseCommit $devConfig $caseYaml
  $devImage = "repoaces/oh-fastgpt-$($pr):$($baseCommit.Substring(0, 12))"
  $evalImage = "repoaces/eval-$($pr):$($baseCommit.Substring(0, 12))"
  $runName = "$RunNamePrefix-pr$pr"
  $artifactRoot = Join-Path $projectRoot ("tmp\experiments\repoaces-multiagent\" + $caseId + "\" + $runName)
  $plan += [pscustomobject]@{
    case_id = $caseId
    pr = $pr
    case_yaml = (Resolve-Path -LiteralPath $caseYaml).Path
    base_commit = $baseCommit
    dev_image = $devImage
    eval_image = $evalImage
    run_name = $runName
    artifact_root = $artifactRoot
  }
}

$planPath = Join-Path $batchRoot "plan.json"
$plan | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $planPath -Encoding UTF8
Write-Step "Planned $($plan.Count) cases. Plan: $planPath"

if ($PlanOnly) {
  exit 0
}

if ($BuildMissingImages) {
  $devBuildScript = Join-Path $projectRoot "docker\13-dev-image-bundle\scripts\Build-OHImage.ps1"
  $evalBuildScript = Join-Path $projectRoot "docker\13-evaluator-image-bundle\scripts\Build-PrImage.ps1"
  foreach ($item in $plan) {
    if (-not (Test-DockerImageExists $item.dev_image)) {
      Write-Step "Building missing dev image for $($item.case_id): $($item.dev_image)"
      powershell -NoProfile -ExecutionPolicy Bypass -File $devBuildScript -Pr ([string]$item.pr) -NpmRegistry $NpmRegistry
      if ($LASTEXITCODE -ne 0) {
        throw "Failed to build dev image for $($item.case_id): $($item.dev_image)"
      }
    } else {
      Write-Step "Dev image exists for $($item.case_id): $($item.dev_image)"
    }

    if (-not (Test-DockerImageExists $item.eval_image)) {
      Write-Step "Building missing evaluator image for $($item.case_id): $($item.eval_image)"
      $evalArgs = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", $evalBuildScript,
        "-Pr", ([string]$item.pr),
        "-NpmRegistry", $NpmRegistry
      )
      if ($SkipEvaluatorImageVerify) {
        $evalArgs += "-SkipVerify"
      }
      powershell @evalArgs
      if ($LASTEXITCODE -ne 0) {
        throw "Failed to build evaluator image for $($item.case_id): $($item.eval_image)"
      }
    } else {
      Write-Step "Evaluator image exists for $($item.case_id): $($item.eval_image)"
    }
  }
}

$results = @()
foreach ($item in $plan) {
  Write-Step "Starting $($item.case_id) with dev image $($item.dev_image)"
  New-Item -ItemType Directory -Force -Path $item.artifact_root | Out-Null
  $stdout = Join-Path $item.artifact_root "controller.stdout.log"
  $stderr = Join-Path $item.artifact_root "controller.stderr.log"

  $argsList = @(
    "-u", "-m", "repoaces_multiagent.cli", "fullflow",
    "--case", $item.case_yaml,
    "--run-name", $item.run_name,
    "--workspace-path", "/workspace/project",
    "--model", $Model,
    "--wsl-distro", $WslDistro,
    "--dev-image", $item.dev_image,
    "--seed-workspace-from-image",
    "--prepare-timeout", [string]$PrepareTimeout,
    "--stage-timeout", [string]$StageTimeout,
    "--final-eval-timeout", [string]$FinalEvalTimeout,
    "--poll-interval", [string]$PollInterval
  )

  $start = Get-Date
  & python @argsList 1> $stdout 2> $stderr
  $exitCode = $LASTEXITCODE
  $end = Get-Date

  $manifestPath = Join-Path $item.artifact_root "report\multiagent-manifest.json"
  $status = "NO_MANIFEST"
  if (Test-Path -LiteralPath $manifestPath) {
    try {
      $status = (Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json).status
    } catch {
      $status = "MANIFEST_PARSE_ERROR"
    }
  }

  $result = [pscustomobject]@{
    case_id = $item.case_id
    pr = $item.pr
    run_name = $item.run_name
    artifact_root = $item.artifact_root
    stdout = $stdout
    stderr = $stderr
    exit_code = $exitCode
    status = $status
    started_at = $start.ToString("o")
    finished_at = $end.ToString("o")
    elapsed_seconds = [int]($end - $start).TotalSeconds
  }
  $results += $result
  $results | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $batchRoot "results.json") -Encoding UTF8
  Write-Step "Finished $($item.case_id): exit=$exitCode status=$status"
}

Write-Step "Batch completed. Results: $(Join-Path $batchRoot 'results.json')"
