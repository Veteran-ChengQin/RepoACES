[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$Pr,
  [string]$Root = "",
  [string]$ImagePrefix = "repoaces/oh-fastgpt",
  [string]$OhBaseImage = "ghcr.io/openhands/agent-server:1.26.0-python",
  [string]$NpmRegistry = "https://registry.npmmirror.com"
)

$ErrorActionPreference = "Stop"

if (-not $Root) {
  $scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
  $Root = Split-Path -Parent $scriptDir
}

$caseId = if ($Pr.StartsWith("fastgpt-pr-")) { $Pr } else { "fastgpt-pr-$Pr" }
$configPath = Join-Path $Root "configs\$caseId.eval.json"
if (-not (Test-Path -LiteralPath $configPath)) {
  throw "Config not found: $configPath"
}

$config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$prNumber = [string]$config.pr_number
$baseCommit = [string]$config.PSObject.Properties["base_commit"].Value
$pnpmVersion = [string]$config.PSObject.Properties["pnpm_version"].Value
$shortSha = $baseCommit.Substring(0, 12)
$imageRef = "$ImagePrefix-$prNumber`:$shortSha"
$installBun = if ($config.PSObject.Properties.Name.Contains("requires_bun") -and $config.requires_bun) { "true" } else { "false" }

docker build `
  -f (Join-Path $Root "dockerfiles\FastGPT.OpenHands.Dockerfile") `
  --build-arg "PR_ID=$caseId" `
  --build-arg "BASE_COMMIT=$baseCommit" `
  --build-arg "PNPM_VERSION=$pnpmVersion" `
  --build-arg "INSTALL_BUN=$installBun" `
  --build-arg "OH_BASE_IMAGE=$OhBaseImage" `
  --build-arg "NPM_REGISTRY=$NpmRegistry" `
  -t $imageRef `
  $Root

if ($LASTEXITCODE -ne 0) {
  throw "docker build failed with exit code $LASTEXITCODE"
}

Write-Host "Built OpenHands image: $imageRef"
