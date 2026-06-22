<#
.SYNOPSIS
Runs RepoACES fullflow for all FastGPT cases whose size_label is in a target set.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\repoaces_batch_by_size.ps1 `
  -Sizes "size/L","size/S","size/XL" `
  -RunTag size-s-l-xl-001 `
  -Model gpt-5.4
#>

param(
  [string]$SummaryJson = "cases\18cases\fastgpt_summary_cases.json",
  [string[]]$Sizes = @("size/L", "size/S", "size/XL"),
  [string[]]$OnlyPrs = @(),
  [int[]]$RunLastPrs = @(6660, 7008, 5776),
  [int[]]$SkipPrs = @(7138, 7017),
  [string]$RunTag = "",
  [string]$Model = "gpt-5.4",
  [string]$WslDistro = "Ubuntu-22.04",
  [int]$OpenHandsPort = 3000,
  [int]$OpenHandsMaxSeconds = 5400,
  [int]$PollIntervalSeconds = 60,
  [int]$PrepareDevEnvTimeoutSeconds = 3600,
  [int]$FinalEvalTimeoutSeconds = 1800,
  [switch]$Force,
  [switch]$ContinueOnFailure,
  [switch]$SkipStaticIntel,
  [switch]$SkipDevInstall,
  [switch]$SkipDevSmoke,
  [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath "repoaces\cli.py") -or -not (Test-Path -LiteralPath "scripts\repoaces_fullflow.ps1")) {
  throw "Please run this script from the AI_Developer_Agent_System project root."
}

function Write-Step {
  param([string]$Message)
  $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Write-Host ""
  Write-Host "[$timestamp] $Message" -ForegroundColor Cyan
}

function Save-Json {
  param(
    [Parameter(Mandatory = $true)]$Value,
    [Parameter(Mandatory = $true)][string]$Path
  )
  $dir = Split-Path -Parent $Path
  if ($dir) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
  }
  $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Cleanup-OpenHandsFromArtifactRoot {
  param([string]$ArtifactRoot)
  $runtimeStatePath = Join-Path $ArtifactRoot "tasks\01-implementation\openhands_runtime_state.json"
  if (-not (Test-Path -LiteralPath $runtimeStatePath)) {
    return
  }
  try {
    $runtimeState = Get-Content -Raw -LiteralPath $runtimeStatePath | ConvertFrom-Json
    $names = @()
    if ($runtimeState.openhands.container) {
      $names += [string]$runtimeState.openhands.container
    }
    if ($runtimeState.conversation.sandbox_id) {
      $names += [string]$runtimeState.conversation.sandbox_id
    }
    $names = @($names | Where-Object { $_ } | Select-Object -Unique)
    foreach ($name in $names) {
      Write-Host "Best-effort cleanup container: $name" -ForegroundColor Yellow
      docker rm -f $name 2>$null | Out-Null
      wsl -d $WslDistro -- docker rm -f $name 2>$null | Out-Null
    }
  } catch {
    Write-Host "Best-effort cleanup skipped: $($_.Exception.Message)" -ForegroundColor Yellow
  }
}

if (-not $RunTag) {
  $RunTag = "size-batch-" + (Get-Date -Format "yyyyMMdd-HHmmss")
}

$summaryPath = (Resolve-Path $SummaryJson).Path
$selected = @($(
  & python scripts\repoaces_make_size_plan.py `
    --summary-json $summaryPath `
    --sizes ($Sizes -join ",") `
    --only-prs ($OnlyPrs -join ",") `
    --run-last-prs ($RunLastPrs -join ",") `
    --skip-prs ($SkipPrs -join ",") `
    --run-tag $RunTag | ConvertFrom-Json
))
if ($LASTEXITCODE -ne 0) {
  throw "Unable to build batch plan from $summaryPath"
}

$batchRoot = "tmp\experiments\repoaces-batches\$RunTag"
New-Item -ItemType Directory -Force -Path $batchRoot | Out-Null
$planPath = Join-Path $batchRoot "plan.json"
$summaryOutPath = Join-Path $batchRoot "summary.json"
$logPath = Join-Path $batchRoot "batch.log"

$plan = @(
  $selected | ForEach-Object {
    [ordered]@{
      id = $_.id
      pr_number = [int]$_.pr_number
      size_label = $_.size_label
      changed_files = [int]$_.changed_files
      title_raw = $_.title_raw
      case_yaml = "cases\18cases\$($_.id)\case.yaml"
      run_name = "$RunTag-$($_.id)"
      artifact_root = "tmp\experiments\repoaces\$($_.id)\$RunTag"
      run_last = $RunLastPrs -contains [int]$_.pr_number
    }
  }
)
Save-Json $plan $planPath

Write-Step "RepoACES size batch started"
Write-Host "Run tag: $RunTag"
Write-Host "Sizes:   $($Sizes -join ', ')"
if ($OnlyPrs.Count -gt 0) {
  Write-Host "Only PRs: $($OnlyPrs -join ', ')"
}
Write-Host "Skip PRs: $($SkipPrs -join ', ')"
Write-Host "Cases:   $($plan.Count)"
Write-Host "Plan:    $planPath"
Write-Host "Log:     $logPath"

if ($PlanOnly) {
  Write-Step "Plan only; no fullflow tasks started"
  Get-Content -Raw -LiteralPath $planPath
  return
}

$results = @()
$index = 0
foreach ($item in $plan) {
  $index += 1
  $caseYaml = [string]$item.case_yaml
  $artifactRoot = [string]$item.artifact_root

  Write-Step "[$index/$($plan.Count)] $($item.id) $($item.size_label), changed_files=$($item.changed_files)"
  $caseLog = Join-Path $batchRoot "$($item.id).log"

  $args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", ".\scripts\repoaces_fullflow.ps1",
    "-Case", $caseYaml,
    "-ArtifactRoot", $artifactRoot,
    "-Model", $Model,
    "-WslDistro", $WslDistro,
    "-OpenHandsPort", [string]$OpenHandsPort,
    "-OpenHandsMaxSeconds", [string]$OpenHandsMaxSeconds,
    "-PollIntervalSeconds", [string]$PollIntervalSeconds,
    "-PrepareDevEnvTimeoutSeconds", [string]$PrepareDevEnvTimeoutSeconds,
    "-FinalEvalTimeoutSeconds", [string]$FinalEvalTimeoutSeconds
  )
  if ($Force) { $args += "-Force" }
  if ($SkipStaticIntel) { $args += "-SkipStaticIntel" }
  if ($SkipDevInstall) { $args += "-SkipDevInstall" }
  if ($SkipDevSmoke) { $args += "-SkipDevSmoke" }

  $startedAt = Get-Date
  try {
    $caseHeader = @"
===== RepoACES batch item started =====
Time:          $($startedAt.ToString("yyyy-MM-dd HH:mm:ss"))
Case:          $($item.id)
PR:            $($item.pr_number)
Size:          $($item.size_label)
Changed files: $($item.changed_files)
Artifact root: $artifactRoot
Command:       powershell $($args -join ' ')
=======================================
"@
    $caseHeader | Tee-Object -FilePath $caseLog | Tee-Object -FilePath $logPath -Append

    & powershell @args 2>&1 |
      Tee-Object -FilePath $caseLog -Append |
      Tee-Object -FilePath $logPath -Append
    $exitCode = $LASTEXITCODE
    $finishedAt = Get-Date

    $caseFooter = @"
===== RepoACES batch item finished =====
Time:      $($finishedAt.ToString("yyyy-MM-dd HH:mm:ss"))
Case:      $($item.id)
Exit code: $exitCode
Duration:  $([int]($finishedAt - $startedAt).TotalSeconds)s
========================================
"@
    $caseFooter | Tee-Object -FilePath $caseLog -Append | Tee-Object -FilePath $logPath -Append

    if ($exitCode -ne 0) {
      throw "fullflow exited with code $exitCode"
    }
    $runStatePath = Join-Path $artifactRoot "report\run_state.json"
    $status = "UNKNOWN"
    if (Test-Path -LiteralPath $runStatePath) {
      $status = (Get-Content -Raw -LiteralPath $runStatePath | ConvertFrom-Json).status
    }
    $results += [ordered]@{
      id = $item.id
      pr_number = $item.pr_number
      size_label = $item.size_label
      changed_files = $item.changed_files
      status = $status
      exit_code = $exitCode
      artifact_root = $artifactRoot
      log = $caseLog
      started_at = $startedAt.ToString("o")
      finished_at = $finishedAt.ToString("o")
    }
  } catch {
    $message = [string]$_.Exception.Message
    Write-Host $message -ForegroundColor Red
    Cleanup-OpenHandsFromArtifactRoot $artifactRoot
    $message | Add-Content -LiteralPath $caseLog
    $message | Add-Content -LiteralPath $logPath
    $results += [ordered]@{
      id = $item.id
      pr_number = $item.pr_number
      size_label = $item.size_label
      changed_files = $item.changed_files
      status = "BATCH_FAILED"
      exit_code = $LASTEXITCODE
      artifact_root = $artifactRoot
      log = $caseLog
      error = $message
      started_at = $startedAt.ToString("o")
      finished_at = (Get-Date).ToString("o")
    }
    Save-Json $results $summaryOutPath
    if (-not $ContinueOnFailure) {
      throw
    }
  }
  Save-Json $results $summaryOutPath
}

Write-Step "RepoACES size batch completed"
Write-Host "Summary: $summaryOutPath"
Get-Content -Raw -LiteralPath $summaryOutPath
