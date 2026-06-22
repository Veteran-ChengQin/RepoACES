param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [string]$CaseId = 'pr7008',
  [string]$RunId = 'pr7008-run-003',
  [string]$InstanceId = 'fastgpt__pr7008',
  [string]$WorkspaceRel = '',
  [string]$TaskFileRel = 'cases/pr7008/task-naive-swebench.md',
  [string]$OpenHandsUrl = 'http://127.0.0.1:3000',
  [string]$ContainerName = 'openhands-pr7008-official',
  [string]$OpenHandsImage = 'docker.openhands.dev/openhands/openhands:1.8',
  [string]$AgentServerImageRepository = 'ghcr.io/openhands/agent-server',
  [string]$AgentServerImageTag = '1.26.0-python',
  [string]$Model = 'gpt-5.4',
  [string]$ModelCanonicalName = 'gpt-4o',
  [string]$BaseUrl = 'https://www.right.codes/codex/v1',
  [string]$ApiKeyEnv = 'RIGHT_CODES_API_KEY',
  [string]$WslDistro = 'Ubuntu-22.04',
  [string]$BaselineCommit = '4af1ef77674851e30478bef5a9e5cb6ded6db660',
  [int]$MaxIterations = 120,
  [int]$PollSeconds = 15,
  [int]$TimeoutMinutes = 180,
  [switch]$UseExistingWorkspace,
  [switch]$SkipOpenHandsRun,
  [switch]$SkipEval,
  [string]$ConversationId = ''
)

$ErrorActionPreference = 'Stop'

function Write-Step([string]$Message) {
  Write-Host "[pr7008] $Message"
}

function ConvertTo-JsonFile($Object, [string]$Path, [int]$Depth = 30) {
  $dir = Split-Path -Parent $Path
  if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  $json = $Object | ConvertTo-Json -Depth $Depth
  [System.IO.File]::WriteAllText($Path, $json + "`n", [System.Text.UTF8Encoding]::new($false))
}

function Protect-ArtifactString([string]$Value) {
  if ($null -eq $Value) { return $null }
  $redacted = $Value
  $redacted = $redacted -replace 'github_pat_[A-Za-z0-9_]+', 'github_pat_***'
  $redacted = $redacted -replace 'hf_[A-Za-z0-9]{12,}', 'hf_***'
  $redacted = $redacted -replace 'sk-[A-Za-z0-9_-]{8,}', 'sk-***'
  $redacted = $redacted -replace '(?i)("api[_-]?key"\s*:\s*")[^"]+(")', '$1***$2'
  $redacted = $redacted -replace '(?i)("authorization"\s*:\s*")[^"]+(")', '$1***$2'
  $redacted = $redacted -replace '(?i)("access[_-]?token"\s*:\s*")[^"]+(")', '$1***$2'
  return $redacted
}

function Protect-ArtifactObject($Value) {
  if ($null -eq $Value) { return $null }

  if ($Value -is [string]) {
    return Protect-ArtifactString $Value
  }

  if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string]) -and -not ($Value -is [System.Collections.IDictionary]) -and -not ($Value -is [pscustomobject])) {
    $items = @()
    foreach ($item in $Value) {
      $items += ,(Protect-ArtifactObject $item)
    }
    return $items
  }

  if ($Value -is [System.Collections.IDictionary]) {
    $result = [ordered]@{}
    foreach ($key in $Value.Keys) {
      $name = [string]$key
      if ($name -match '(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|github[_-]?token|authorization|secret|password)') {
        $result[$name] = '***'
      } else {
        $result[$name] = Protect-ArtifactObject $Value[$key]
      }
    }
    return $result
  }

  if ($Value -is [pscustomobject]) {
    $result = [ordered]@{}
    foreach ($property in $Value.PSObject.Properties) {
      $name = $property.Name
      if ($name -match '(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|github[_-]?token|authorization|secret|password)') {
        $result[$name] = '***'
      } else {
        $result[$name] = Protect-ArtifactObject $property.Value
      }
    }
    return $result
  }

  return $Value
}

function Invoke-OpenHandsJson([string]$Method, [string]$Path, $Body = $null) {
  $uri = "$OpenHandsUrl$Path"
  $args = @{
    Uri = $uri
    Method = $Method
    ContentType = 'application/json'
    UseBasicParsing = $true
  }
  if ($null -ne $Body) {
    $args.Body = ($Body | ConvertTo-Json -Depth 50 -Compress)
  }
  return Invoke-RestMethod @args
}

function ConvertTo-WslPath([string]$WindowsPath) {
  $resolved = (Resolve-Path -LiteralPath $WindowsPath).Path
  $resolvedForWsl = $resolved -replace '\\','/'
  $out = wsl -d $WslDistro -- wslpath -a "$resolvedForWsl"
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($out)) {
    throw "Failed to convert path to WSL path: $WindowsPath"
  }
  return ($out | Select-Object -First 1).Trim()
}

function ConvertLiteralTo-WslPath([string]$WindowsPath) {
  $pathForWsl = ([System.IO.Path]::GetFullPath($WindowsPath)) -replace '\\','/'
  $out = wsl -d $WslDistro -- wslpath -a "$pathForWsl"
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($out)) {
    throw "Failed to convert literal path to WSL path: $WindowsPath"
  }
  return ($out | Select-Object -First 1).Trim()
}

function Wait-OpenHandsHealth {
  $deadline = (Get-Date).AddMinutes(5)
  while ((Get-Date) -lt $deadline) {
    try {
      $r = Invoke-WebRequest -Uri "$OpenHandsUrl/health" -UseBasicParsing -TimeoutSec 5
      if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { return }
    } catch {
      Start-Sleep -Seconds 3
    }
  }
  throw "OpenHands health endpoint did not become ready: $OpenHandsUrl/health"
}

function Start-OpenHandsContainer([string]$WorkspacePath) {
  Write-Step "Starting OpenHands container $ContainerName"
  $existing = docker ps -a --filter "name=^/$ContainerName$" --format '{{.Names}}'
  if ($existing -eq $ContainerName) {
    docker rm -f $ContainerName | Out-Null
  }

  $repoMount = ((Resolve-Path -LiteralPath $WorkspacePath).Path -replace '\\','/')
  $configPath = Join-Path $RepoRoot '.openhands-home'
  New-Item -ItemType Directory -Force -Path $configPath | Out-Null
  $configMount = ((Resolve-Path -LiteralPath $configPath).Path -replace '\\','/')
  $sandboxPath = "/projects/$RunId/FastGPT"
  $volumes = "${repoMount}:/workspace:rw,${repoMount}:${sandboxPath}:rw"

  docker run -d --pull=always `
    -e "AGENT_SERVER_IMAGE_REPOSITORY=$AgentServerImageRepository" `
    -e "AGENT_SERVER_IMAGE_TAG=$AgentServerImageTag" `
    -e "LOG_ALL_EVENTS=true" `
    -e "SANDBOX_VOLUMES=$volumes" `
    -v /var/run/docker.sock:/var/run/docker.sock `
    -v "${configMount}:/.openhands" `
    -p 3000:3000 `
    --add-host host.docker.internal:host-gateway `
    --name $ContainerName `
    $OpenHandsImage | Out-Null

  Wait-OpenHandsHealth
}

function Update-OpenHandsSettings {
  $apiKey = [Environment]::GetEnvironmentVariable($ApiKeyEnv)
  if ([string]::IsNullOrWhiteSpace($apiKey)) {
    throw "Environment variable $ApiKeyEnv is required to configure OpenHands LLM settings."
  }

  $payload = @{
    agent_settings_diff = @{
      llm = @{
        model = $Model
        model_canonical_name = $ModelCanonicalName
        api_key = $apiKey
        base_url = $BaseUrl
        num_retries = 2
        retry_min_wait = 8
        retry_max_wait = 64
        timeout = 180
        max_message_chars = 30000
        stream = $false
        drop_params = $true
        modify_params = $true
        native_tool_calling = $true
      }
    }
    conversation_settings_diff = @{
      max_iterations = $MaxIterations
      confirmation_mode = $false
      security_analyzer = 'llm'
    }
  }

  try {
    Invoke-OpenHandsJson -Method Patch -Path '/api/settings' -Body $payload | Out-Null
  } catch {
    Invoke-OpenHandsJson -Method Post -Path '/api/v1/settings' -Body $payload | Out-Null
  }
}

function New-ConversationPayload([string]$TaskText) {
  $usageId = "$CaseId-$RunId-$Model-" + ([guid]::NewGuid().ToString('N').Substring(0, 10))
  return @{
    workspace = @{
      working_dir = "/projects/$RunId/FastGPT"
      kind = 'LocalWorkspace'
    }
    worktree = $false
    max_iterations = $MaxIterations
    agent_settings = @{
      schema_version = 3
      agent_kind = 'openhands'
      agent = 'CodeActAgent'
      llm = @{
        model = $Model
        model_canonical_name = $ModelCanonicalName
        api_key = [Environment]::GetEnvironmentVariable($ApiKeyEnv)
        base_url = $BaseUrl
        num_retries = 2
        retry_min_wait = 8
        retry_max_wait = 64
        timeout = 180
        max_message_chars = 30000
        stream = $false
        drop_params = $true
        modify_params = $true
        native_tool_calling = $true
        usage_id = $usageId
      }
      tools = @()
      enable_sub_agents = $true
      enable_switch_llm_tool = $true
      mcp_config = @{}
      condenser = @{
        enabled = $true
        max_size = 240
      }
      verification = @{
        critic_enabled = $false
        critic_mode = 'finish_and_message'
        enable_iterative_refinement = $false
      }
    }
    initial_message = @{
      role = 'user'
      content = @(@{ type = 'text'; text = $TaskText })
      run = $false
    }
    tags = @{
      case = $CaseId
      mode = 'naive'
      style = 'swebench'
      model = $Model
      run = $RunId
    }
    autotitle = $false
  }
}

function Start-OpenHandsTask([string]$TaskPath, [string]$ArtifactRoot) {
  Write-Step "Creating OpenHands conversation"
  $taskText = Get-Content -Raw -LiteralPath $TaskPath
  $taskText = $taskText -replace '/projects/pr7008-run-003/FastGPT', "/projects/$RunId/FastGPT"
  $payload = New-ConversationPayload -TaskText $taskText

  $redacted = $payload | ConvertTo-Json -Depth 50 | ConvertFrom-Json
  $redacted.agent_settings.llm.api_key = '***'
  ConvertTo-JsonFile $redacted (Join-Path $ArtifactRoot 'create-request.redacted.json')

  $conversation = Invoke-OpenHandsJson -Method Post -Path '/api/conversations' -Body $payload
  ConvertTo-JsonFile $conversation (Join-Path $ArtifactRoot 'create-response.json')
  $id = $conversation.id
  if ([string]::IsNullOrWhiteSpace($id)) {
    throw 'OpenHands did not return a conversation id.'
  }
  Set-Content -LiteralPath (Join-Path $ArtifactRoot 'conversation-id.txt') -Value $id -Encoding ASCII

  Write-Step "Running conversation $id"
  Invoke-OpenHandsJson -Method Post -Path "/api/conversations/$id/run" | Out-Null
  return $id
}

function Wait-Conversation([string]$Id, [string]$ArtifactRoot) {
  Write-Step "Polling OpenHands conversation $Id"
  $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
  $lastStatus = ''
  while ((Get-Date) -lt $deadline) {
    $conversation = Invoke-OpenHandsJson -Method Get -Path "/api/conversations/$Id"
    ConvertTo-JsonFile $conversation (Join-Path $ArtifactRoot 'conversation-latest.json')
    $status = [string]$conversation.execution_status
    if ($status -ne $lastStatus) {
      Write-Step "execution_status=$status"
      $lastStatus = $status
    }
    if ($status -in @('finished', 'error', 'paused', 'stopped')) {
      return $status
    }
    Start-Sleep -Seconds $PollSeconds
  }
  throw "Conversation $Id did not finish before timeout."
}

function Save-OpenHandsEvents([string]$Id, [string]$ArtifactRoot) {
  Write-Step "Saving OpenHands events"
  $all = @()
  $pageId = $null
  do {
    $path = "/api/conversations/$Id/events/search?limit=100"
    if ($pageId) { $path += "&page_id=$pageId" }
    $page = Invoke-OpenHandsJson -Method Get -Path $path
    if ($page.items) { $all += $page.items }
    $pageId = $page.next_page_id
  } while ($pageId)

  $eventsObject = @{ items = $all; next_page_id = $null }
  ConvertTo-JsonFile $eventsObject (Join-Path $ArtifactRoot 'events.json')

  try {
    Invoke-WebRequest -Uri "$OpenHandsUrl/api/file/download-trajectory/$Id" `
      -UseBasicParsing `
      -OutFile (Join-Path $ArtifactRoot 'trajectory.zip') | Out-Null
  } catch {
    Set-Content -LiteralPath (Join-Path $ArtifactRoot 'trajectory-download-error.txt') `
      -Value $_.Exception.Message `
      -Encoding UTF8
  }
}

function Find-LocalOpenHandsConversationDir([string]$Needle) {
  $root = Join-Path $RepoRoot '.openhands-home/v1_conversations'
  if (-not (Test-Path -LiteralPath $root)) {
    return $null
  }

  $dirs = Get-ChildItem -LiteralPath $root -Directory | Sort-Object LastWriteTime -Descending
  foreach ($dir in $dirs) {
    try {
      $hit = Select-String -Path (Join-Path $dir.FullName '*.json') `
        -Pattern $Needle `
        -SimpleMatch `
        -Quiet `
        -ErrorAction SilentlyContinue
      if ($hit) {
        return $dir.FullName
      }
    } catch {
      continue
    }
  }

  return $null
}

function Save-LocalOpenHandsTrajectory([string]$ArtifactRoot, [string]$OutputDir = '') {
  $trajDir = if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    Join-Path $ArtifactRoot 'trajs'
  } else {
    $OutputDir
  }
  New-Item -ItemType Directory -Force -Path $trajDir | Out-Null

  $conversationDir = Find-LocalOpenHandsConversationDir -Needle $RunId
  if (-not $conversationDir) {
    $noteName = if ([string]::IsNullOrWhiteSpace($OutputDir)) {
      "$InstanceId-$RunId-trajectory-source-missing.txt"
    } else {
      'trajectory-source-missing.txt'
    }
    $notePath = Join-Path $trajDir $noteName
    Set-Content -LiteralPath $notePath `
      -Value "No local OpenHands v1_conversations directory matched run id: $RunId" `
      -Encoding UTF8
    return @{
      source_dir = $null
      trajectory = $null
      summary = $notePath
      event_count = 0
    }
  }

  Write-Step "Saving local OpenHands trajectory from $conversationDir"
  $items = @()
  foreach ($file in (Get-ChildItem -LiteralPath $conversationDir -File -Filter '*.json' | Sort-Object LastWriteTime, Name)) {
    $raw = Get-Content -Raw -LiteralPath $file.FullName
    try {
      $event = $raw | ConvertFrom-Json
      $safeEvent = Protect-ArtifactObject $event
      $timestamp = $null
      if ($event.PSObject.Properties.Name -contains 'timestamp') {
        $timestamp = [string]$event.timestamp
      }
      $kind = $null
      if ($event.PSObject.Properties.Name -contains 'kind') {
        $kind = [string]$event.kind
      }
      $source = $null
      if ($event.PSObject.Properties.Name -contains 'source') {
        $source = [string]$event.source
      }
      $items += ,[ordered]@{
        source_file = $file.Name
        timestamp = $timestamp
        kind = $kind
        source = $source
        event = $safeEvent
      }
    } catch {
      $items += ,[ordered]@{
        source_file = $file.Name
        timestamp = $null
        kind = 'UnparsedEvent'
        source = $null
        parse_error = 'ConvertFrom-Json failed; redacted raw event is preserved in raw.'
        raw = Protect-ArtifactString $raw
      }
    }
  }

  $trajectoryName = if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    "$InstanceId-$RunId.json"
  } else {
    'trajectory.json'
  }
  $trajectoryPath = Join-Path $trajDir $trajectoryName
  ConvertTo-JsonFile $items $trajectoryPath 80

  $kindCounts = [ordered]@{}
  $sourceCounts = [ordered]@{}
  foreach ($item in $items) {
    $kind = if ([string]::IsNullOrWhiteSpace($item.kind)) { 'unknown' } else { $item.kind }
    $source = if ([string]::IsNullOrWhiteSpace($item.source)) { 'unknown' } else { $item.source }
    if (-not $kindCounts.Contains($kind)) { $kindCounts[$kind] = 0 }
    if (-not $sourceCounts.Contains($source)) { $sourceCounts[$source] = 0 }
    $kindCounts[$kind] += 1
    $sourceCounts[$source] += 1
  }

  $summaryName = if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    "$InstanceId-$RunId-summary.json"
  } else {
    'trajectory-summary.json'
  }
  $summaryPath = Join-Path $trajDir $summaryName
  $summary = [ordered]@{
    source_dir = $conversationDir
    event_count = $items.Count
    kind_counts = $kindCounts
    source_counts = $sourceCounts
    trajectory = $trajectoryPath
  }
  ConvertTo-JsonFile $summary $summaryPath 30

  return @{
    source_dir = $conversationDir
    trajectory = $trajectoryPath
    summary = $summaryPath
    event_count = $items.Count
  }
}

function Write-EvalScript([string]$EvalScriptPath, [string]$WorkspacePath, [string]$PatchPath, [string]$ReportPath) {
  $workspaceWsl = ConvertTo-WslPath $WorkspacePath
  $patchWsl = ConvertTo-WslPath $PatchPath
  $reportWsl = ConvertLiteralTo-WslPath $ReportPath
  $evalRoot = "`$HOME/repoaces/eval/$RunId-artifact"

  $script = @"
#!/usr/bin/env bash
set -uxo pipefail
export PATH="`$HOME/.local/bin:`$PATH"

SRC="$workspaceWsl"
PATCH="$patchWsl"
REPORT="$reportWsl"
BASELINE="$BaselineCommit"
EVAL_ROOT="$evalRoot"
TESTBED="`$EVAL_ROOT/FastGPT"

case "`$EVAL_ROOT" in
  "`$HOME"/repoaces/eval/*-artifact) ;;
  *) echo "Refusing unexpected EVAL_ROOT=`$EVAL_ROOT" >&2; exit 2 ;;
esac

rm -rf "`$EVAL_ROOT"
mkdir -p "`$EVAL_ROOT"
git clone --no-hardlinks "`$SRC" "`$TESTBED"
cd "`$TESTBED"
git checkout "`$BASELINE"
git apply "`$PATCH"
git status --short

diff_check_status=0
git diff --check || diff_check_status=`$?

install_status=0
pnpm install --frozen-lockfile --ignore-scripts || install_status=`$?

sdk_build_status=0
pnpm -r --filter @fastgpt-sdk/storage --filter @fastgpt-sdk/otel --filter @fastgpt-sdk/sandbox-adapter build || sdk_build_status=`$?

cd "`$TESTBED/projects/code-sandbox"
export SANDBOX_MAX_MEMORY_MB=256
export SANDBOX_TOKEN=test
export SANDBOX_QUEUE_ID_CONCURRENCY=1

build_status=0
pnpm build || build_status=`$?

test_status=0
pnpm test || test_status=`$?

smoke_file="`$PWD/.repoaces-pr7008-queue-smoke.mjs"
cat > "`$smoke_file" <<'JS'
import { app, poolReady } from './dist/index.js';

const headers = { 'Content-Type': 'application/json', Authorization: 'Bearer test' };

async function execute(queueId) {
  const started = Date.now();
  const res = await app.request('/sandbox/js', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      code: "async function main() {\n" +
        "  const start = Date.now();\n" +
        "  await delay(500);\n" +
        "  return { elapsed: Date.now() - start };\n" +
        "}",
      variables: {},
      queueId
    })
  });
  const json = await res.json();
  return {
    queueId,
    ok: json.success,
    status: res.status,
    message: json.message ?? null,
    requestMs: Date.now() - started,
    workerElapsed: json.data?.codeReturn?.elapsed ?? null
  };
}

async function batch(queueIds) {
  const started = Date.now();
  const results = await Promise.all(queueIds.map((queueId) => execute(queueId)));
  return { totalMs: Date.now() - started, results };
}

await poolReady;
const same = await batch(['same-q', 'same-q', 'same-q']);
const different = await batch(['diff-a', 'diff-b', 'diff-c']);
console.log(JSON.stringify({ same, different }, null, 2));
const allOk = [...same.results, ...different.results].every((r) => r.ok);
if (!allOk) process.exit(10);
if (same.totalMs < 1300) process.exit(11);
if (different.totalMs > 1200) process.exit(12);
process.exit(0);
JS

queue_smoke_status=0
NODE_ENV=test node "`$smoke_file" || queue_smoke_status=`$?
rm -f "`$smoke_file"

python3 - <<PY
import json
report = {
  "$InstanceId": {
    "patch_exists": True,
    "patch_successfully_applied": True,
    "resolved": bool($([int]($false))),
    "commands": {
      "git_diff_check": `$diff_check_status,
      "pnpm_install": `$install_status,
      "sdk_build": `$sdk_build_status,
      "code_sandbox_build": `$build_status,
      "code_sandbox_test": `$test_status,
      "queue_id_smoke": `$queue_smoke_status
    }
  }
}
report["$InstanceId"]["resolved"] = (
  report["$InstanceId"]["commands"]["git_diff_check"] == 0
  and report["$InstanceId"]["commands"]["pnpm_install"] == 0
  and report["$InstanceId"]["commands"]["sdk_build"] == 0
  and report["$InstanceId"]["commands"]["code_sandbox_build"] == 0
  and report["$InstanceId"]["commands"]["queue_id_smoke"] == 0
)
with open("$reportWsl", "w", encoding="utf-8") as f:
  json.dump(report, f, ensure_ascii=False, indent=2)
print(json.dumps(report, ensure_ascii=False, indent=2))
PY
"@

  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $EvalScriptPath) | Out-Null
  $script = $script -replace "`r", ''
  [System.IO.File]::WriteAllText($EvalScriptPath, $script, [System.Text.UTF8Encoding]::new($false))
}

function Build-Artifacts([string]$WorkspacePath, [string]$ArtifactRoot) {
  $logDir = Join-Path $ArtifactRoot 'tasks/01-implementation'
  New-Item -ItemType Directory -Force -Path $logDir | Out-Null

  $patchPath = Join-Path $logDir 'patch.diff'
  Write-Step "Writing patch.diff"
  $patchText = (& git -C $WorkspacePath -c core.fileMode=false diff --binary) -join "`n"
  [System.IO.File]::WriteAllText($patchPath, $patchText + "`n", [System.Text.UTF8Encoding]::new($false))

  $reportPath = Join-Path $logDir 'report.json'
  $evalScriptPath = Join-Path $logDir 'eval.sh'
  Write-EvalScript -EvalScriptPath $evalScriptPath -WorkspacePath $WorkspacePath -PatchPath $patchPath -ReportPath $reportPath

  if (-not $SkipEval) {
    Write-Step "Running WSL eval.sh"
    $evalWsl = ConvertTo-WslPath $evalScriptPath
    $testOutputPath = Join-Path $logDir 'test_output.txt'
    $testOutputWsl = ConvertLiteralTo-WslPath $testOutputPath
    wsl -d $WslDistro -- bash -lc "bash '$evalWsl' > '$testOutputWsl' 2>&1"
    if ($LASTEXITCODE -ne 0) {
      Write-Step "eval.sh exited with code $LASTEXITCODE; see $testOutputPath"
    }
  } else {
    Write-Step "Skipping evaluation run; eval.sh was still generated."
  }

  $resolved = $false
  $reportObject = $null
  if (Test-Path -LiteralPath $reportPath) {
    try {
      $reportObject = Get-Content -Raw -LiteralPath $reportPath | ConvertFrom-Json
      if ($reportObject.PSObject.Properties.Name -contains $InstanceId) {
        $resolved = [bool]$reportObject.$InstanceId.resolved
      }
    } catch {
      $reportObject = $null
    }
  }

  ConvertTo-JsonFile ([ordered]@{
    stage = '01-implementation'
    role = 'coding_agent'
    status = if ($SkipEval) { 'patch_exported_eval_skipped' } else { 'evaluated' }
    completed = (Test-Path -LiteralPath $patchPath)
    instruction = 'instruction.md'
    trajectory = 'trajectory.json'
    patch = 'patch.diff'
    eval_script = 'eval.sh'
    test_output = if ($SkipEval) { $null } else { 'test_output.txt' }
    report = 'report.json'
    resolved = $resolved
    legacy_report = $reportObject
  }) (Join-Path $logDir 'result.json') 80

  return @{
    task_dir = $logDir
    patch = $patchPath
    eval_script = $evalScriptPath
    report = $reportPath
    result = (Join-Path $logDir 'result.json')
  }
}

if ([string]::IsNullOrWhiteSpace($WorkspaceRel)) {
  $WorkspaceRel = "workspaces/$RunId/FastGPT"
}

$workspacePath = Join-Path $RepoRoot $WorkspaceRel
$taskPath = Join-Path $RepoRoot $TaskFileRel
$artifactRoot = Join-Path $RepoRoot "tmp/experiments/evaluation/fastgpt/openhands/$RunId"
New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null
$implementationTaskDir = Join-Path $artifactRoot 'tasks/01-implementation'
New-Item -ItemType Directory -Force -Path $implementationTaskDir | Out-Null

if (-not (Test-Path -LiteralPath $workspacePath)) {
  throw "Workspace not found: $workspacePath"
}
if (-not (Test-Path -LiteralPath $taskPath)) {
  throw "Task file not found: $taskPath"
}

$taskTextForArtifact = Get-Content -Raw -LiteralPath $taskPath
$taskTextForArtifact = $taskTextForArtifact -replace '/projects/pr7008-run-003/FastGPT', "/projects/$RunId/FastGPT"
[System.IO.File]::WriteAllText(
  (Join-Path $implementationTaskDir 'instruction.md'),
  $taskTextForArtifact,
  [System.Text.UTF8Encoding]::new($false)
)

if (-not $SkipOpenHandsRun -and -not $UseExistingWorkspace) {
  Start-OpenHandsContainer -WorkspacePath $workspacePath
  Update-OpenHandsSettings
  $ConversationId = Start-OpenHandsTask -TaskPath $taskPath -ArtifactRoot $artifactRoot
  $status = Wait-Conversation -Id $ConversationId -ArtifactRoot $artifactRoot
  Write-Step "OpenHands finished with status=$status"
}

if (-not [string]::IsNullOrWhiteSpace($ConversationId)) {
  try {
    Save-OpenHandsEvents -Id $ConversationId -ArtifactRoot $implementationTaskDir
  } catch {
    Set-Content -LiteralPath (Join-Path $artifactRoot 'events-download-error.txt') -Value $_.Exception.Message -Encoding UTF8
  }
}

$artifacts = Build-Artifacts -WorkspacePath $workspacePath -ArtifactRoot $artifactRoot
$trajectoryArtifacts = Save-LocalOpenHandsTrajectory -ArtifactRoot $artifactRoot -OutputDir $implementationTaskDir
$artifacts['trajectory'] = $trajectoryArtifacts.trajectory
$artifacts['trajectory_summary'] = $trajectoryArtifacts.summary
$artifacts['trajectory_source_dir'] = $trajectoryArtifacts.source_dir
$artifacts['trajectory_event_count'] = $trajectoryArtifacts.event_count
ConvertTo-JsonFile @{
  case = $CaseId
  run = $RunId
  instance = $InstanceId
  workspace = $workspacePath
  artifact_root = $artifactRoot
  tasks_root = (Join-Path $artifactRoot 'tasks')
  conversation_id = $ConversationId
  artifacts = $artifacts
} (Join-Path $artifactRoot 'artifact-manifest.json')

Write-Step "Artifacts written to $artifactRoot"
