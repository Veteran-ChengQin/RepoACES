<#
.SYNOPSIS
Runs one RepoACES PR fullflow from a Windows PowerShell controller.

.DESCRIPTION
This script keeps Windows as the controller and uses the existing RepoACES CLI
to prepare a WSL/Docker FastGPT workspace, start OpenHands, poll until a
terminal status, run final evaluation, and clean OpenHands containers after
final evaluation.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\scripts\repoaces_fullflow.ps1 `
  -Case .\cases\18cases\fastgpt-pr-6660\case.yaml `
  -RunName fullflow-001 `
  -Model gpt-5.4
#>

param(
  [Parameter(Mandatory = $true)]
  [string]$Case,

  [string]$ArtifactRoot = "",
  [string]$RunName = "",
  [string]$Model = "gpt-5.4",
  [string]$WslDistro = "Ubuntu-22.04",
  [int]$OpenHandsPort = 3000,
  [int]$PrepareDevEnvTimeoutSeconds = 3600,
  [int]$OpenHandsStartTimeoutSeconds = 300,
  [int]$OpenHandsMaxSeconds = 3600,
  [int]$PollIntervalSeconds = 60,
  [int]$FinalEvalTimeoutSeconds = 1800,
  [string]$DevImage = "",
  [string]$SandboxRepoPath = "/workspace/project",
  [string[]]$Focus = @("agentSkills", "version", "openapi"),
  [switch]$Force,
  [switch]$SeedWorkspaceFromImage,
  [switch]$SkipStaticIntel,
  [switch]$SkipDevInstall,
  [switch]$SkipDevSmoke,
  [switch]$StopOnOpenHandsFailure
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

function Invoke-RepoACES {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
  Write-Host "python -m repoaces.cli $($Args -join ' ')" -ForegroundColor DarkGray
  $tmpBase = Join-Path ([System.IO.Path]::GetTempPath()) ("repoaces-cli-" + [System.Guid]::NewGuid().ToString("N"))
  $stdoutPath = "$tmpBase.out"
  $stderrPath = "$tmpBase.err"
  $processArgs = @("-m", "repoaces.cli") + $Args
  $proc = Start-Process `
    -FilePath "python" `
    -ArgumentList $processArgs `
    -NoNewWindow `
    -Wait `
    -PassThru `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath
  $exitCode = $proc.ExitCode
  $stdoutText = if (Test-Path -LiteralPath $stdoutPath) { Get-Content -Raw -LiteralPath $stdoutPath } else { "" }
  $stderrText = if (Test-Path -LiteralPath $stderrPath) { Get-Content -Raw -LiteralPath $stderrPath } else { "" }
  Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
  if ($stdoutText) {
    Write-Host $stdoutText.TrimEnd()
  }
  if ($stderrText) {
    Write-Host $stderrText.TrimEnd() -ForegroundColor Red
  }
  if ($exitCode -ne 0) {
    throw "RepoACES command failed with exit code ${exitCode}: python -m repoaces.cli $($Args -join ' ')`n$stderrText"
  }
  return $stdoutText
}

function Read-JsonFile {
  param([string]$Path)
  return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
}

function Get-CaseId {
  param([string]$CasePath)
  $code = @"
import sys
from pathlib import Path
from repoaces.case_builder import CaseBuilder
case = CaseBuilder().load_case(Path(sys.argv[1]))
print(case.case_id)
"@
  $raw = & python -c $code $CasePath
  if ($LASTEXITCODE -ne 0) {
    throw "Unable to read case id from $CasePath"
  }
  return [string]$raw
}

function Convert-ToRelativeIfPossible {
  param([string]$PathText)
  try {
    $root = (Resolve-Path ".").Path
    $full = (Resolve-Path $PathText).Path
    if ($full.StartsWith($root)) {
      return $full.Substring($root.Length).TrimStart("\", "/")
    }
    return $full
  } catch {
    return $PathText
  }
}

function Get-RunState {
  param([string]$Root)
  return Read-JsonFile (Join-Path $Root "report\run_state.json")
}

function Get-WindowsSourceWorkspace {
  param([object]$State)
  $workspace = $State.data.modules.agent_orchestrator.workspace.repo_dir
  if (-not $workspace) {
    throw "Unable to locate prepared Windows workspace in run_state.json"
  }
  return [string]$workspace
}

function Get-DevImageFromBundle {
  param([string]$CaseId)
  $envPath = Join-Path "docker\openhands-image-bundle\oh-compose\$CaseId" ".env"
  if (-not (Test-Path -LiteralPath $envPath)) {
    return ""
  }
  foreach ($line in Get-Content -LiteralPath $envPath) {
    if ($line -match '^IMAGE_REF=(.+)$') {
      return $Matches[1].Trim()
    }
  }
  return ""
}

function Is-OpenHandsTerminal {
  param([string]$Status)
  return @(
    "openhands_finished",
    "openhands_error",
    "openhands_failed",
    "openhands_stopped",
    "openhands_stuck"
  ) -contains $Status
}

$projectRoot = (Resolve-Path ".").Path
$casePath = (Resolve-Path $Case).Path
$caseId = Get-CaseId $casePath
if (-not $DevImage -and $SeedWorkspaceFromImage) {
  $DevImage = Get-DevImageFromBundle $caseId
  if (-not $DevImage) {
    throw "SeedWorkspaceFromImage was requested, but no DevImage was provided and no IMAGE_REF was found for $caseId."
  }
}

if (-not $ArtifactRoot) {
  if (-not $RunName) {
    $RunName = "fullflow-" + (Get-Date -Format "yyyyMMdd-HHmmss")
  }
  $ArtifactRoot = Join-Path $projectRoot "tmp\experiments\repoaces\$caseId\$RunName"
}
$ArtifactRoot = Convert-ToRelativeIfPossible $ArtifactRoot
$caseArg = Convert-ToRelativeIfPossible $casePath

if ((Test-Path -LiteralPath $ArtifactRoot) -and -not $Force) {
  throw "Artifact root already exists: $ArtifactRoot. Use -Force to reuse it, or choose another -RunName/-ArtifactRoot."
}

if ($OpenHandsPort -gt 0) {
  $env:REPOACES_OPENHANDS_PORT = [string]$OpenHandsPort
} else {
  Remove-Item Env:\REPOACES_OPENHANDS_PORT -ErrorAction SilentlyContinue
}
$env:REPOACES_WSL_DISTRO = $WslDistro

Write-Step "RepoACES fullflow started"
Write-Host "Case:          $caseArg"
Write-Host "Case ID:       $caseId"
Write-Host "Artifact root: $ArtifactRoot"
Write-Host "Model:         $Model"
Write-Host "WSL distro:    $WslDistro"
Write-Host "OH port:       $(if ($OpenHandsPort -gt 0) { $OpenHandsPort } else { 'auto' })"
Write-Host "Dev image:     $(if ($DevImage) { $DevImage } else { 'default' })"
Write-Host "Seed image:    $([bool]$SeedWorkspaceFromImage)"
Write-Host "Sandbox path:  $SandboxRepoPath"

Write-Step "1/7 init-run"
$initArgs = @("init-run", "--case", $caseArg, "--out", $ArtifactRoot, "--workspace-path", $SandboxRepoPath)
Invoke-RepoACES @initArgs | Out-Null

Write-Step "2/7 prepare-workspace"
$prepareWorkspaceArgs = @("prepare-workspace", "--case", $caseArg, "--artifact-root", $ArtifactRoot)
if ($Force) {
  $prepareWorkspaceArgs += "--force"
}
Invoke-RepoACES @prepareWorkspaceArgs | Out-Null

$state = Get-RunState $ArtifactRoot
$sourceWorkspace = Get-WindowsSourceWorkspace $state

if (-not $SkipStaticIntel) {
  Write-Step "3/7 static repo intelligence"
  $intelArgs = @("static-intel", "--repo", $sourceWorkspace, "--out", (Join-Path $ArtifactRoot "repo_intelligence"))
  foreach ($term in $Focus) {
    if ($term) {
      $intelArgs += @("--focus", $term)
    }
  }
  Invoke-RepoACES @intelArgs | Out-Null
} else {
  Write-Step "3/7 static repo intelligence skipped"
}

Write-Step "4/7 prepare-dev-env"
$devEnvArgs = @(
  "prepare-dev-env",
  "--case", $caseArg,
  "--artifact-root", $ArtifactRoot,
  "--wsl-distro", $WslDistro,
  "--timeout", [string]$PrepareDevEnvTimeoutSeconds
)
if ($DevImage) {
  $devEnvArgs += @("--image", $DevImage)
}
if ($SeedWorkspaceFromImage) {
  $devEnvArgs += "--seed-workspace-from-image"
}
if ($Force) {
  $devEnvArgs += "--force"
}
if ($SkipDevInstall) {
  $devEnvArgs += "--skip-install"
}
if ($SkipDevSmoke) {
  $devEnvArgs += "--skip-smoke-tests"
}
Invoke-RepoACES @devEnvArgs | Out-Null

Write-Step "5/7 start-openhands"
$startArgs = @(
  "start-openhands",
  "--artifact-root", $ArtifactRoot,
  "--sandbox-repo-path", $SandboxRepoPath,
  "--model", $Model,
  "--auto-run", "true",
  "--wait-start-seconds", [string]$OpenHandsStartTimeoutSeconds,
  "--wait-completion-seconds", "0"
)
Invoke-RepoACES @startArgs | Out-Null

Write-Step "6/7 poll-openhands"
$deadline = (Get-Date).AddSeconds($OpenHandsMaxSeconds)
$lastStatus = ""
while ((Get-Date) -lt $deadline) {
  $pollRaw = Invoke-RepoACES "poll-openhands" "--artifact-root" $ArtifactRoot
  $poll = $pollRaw | ConvertFrom-Json
  $lastStatus = [string]$poll.status
  Write-Host "OpenHands status: $lastStatus"
  if (Is-OpenHandsTerminal $lastStatus) {
    break
  }
  Start-Sleep -Seconds $PollIntervalSeconds
}

if (-not (Is-OpenHandsTerminal $lastStatus)) {
  throw "OpenHands did not reach a terminal status within $OpenHandsMaxSeconds seconds. Last status: $lastStatus"
}
if ($lastStatus -ne "openhands_finished" -and $StopOnOpenHandsFailure) {
  throw "OpenHands finished with non-success terminal status: $lastStatus"
}

Write-Step "7/7 final-evaluate"
$finalRaw = Invoke-RepoACES `
  "final-evaluate" `
  "--case" $caseArg `
  "--artifact-root" $ArtifactRoot `
  "--timeout" ([string]$FinalEvalTimeoutSeconds)
$final = $finalRaw | ConvertFrom-Json

$finalState = Get-RunState $ArtifactRoot
$summary = [ordered]@{
  run_id = $final.run_id
  case_id = $caseId
  status = $final.status
  openhands_status = $lastStatus
  artifact_root = $ArtifactRoot
  run_state = (Join-Path $ArtifactRoot "report\run_state.json")
  implementation_patch = (Join-Path $ArtifactRoot "tasks\01-implementation\patch.diff")
  trajectory = (Join-Path $ArtifactRoot "tasks\01-implementation\trajectory.json")
  final_report = (Join-Path $ArtifactRoot "tasks\02-final-evaluator\final_evaluation_report.json")
  cleanup_report = $finalState.data.modules.final_evaluator.openhands_container_cleanup
}

Write-Step "RepoACES fullflow completed"
$summary | ConvertTo-Json -Depth 6 | Tee-Object -FilePath (Join-Path $ArtifactRoot "report\fullflow-summary.json")
