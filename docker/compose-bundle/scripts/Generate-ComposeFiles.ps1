[CmdletBinding()]
param(
  [string]$Root = (Split-Path -Parent $PSScriptRoot),
  [string]$ImagePrefix = "repoaces/eval",
  [string]$NodeImage = "repoaces/openhands-agent-fastgpt:node20-pnpm10",
  [string]$NpmRegistry = "https://registry.npmmirror.com"
)

$ErrorActionPreference = "Stop"

$configDir = Join-Path $Root "configs"
$composeRoot = Join-Path $Root "compose"
New-Item -ItemType Directory -Force -Path $composeRoot | Out-Null

$configs = Get-ChildItem -LiteralPath $configDir -Filter "*.eval.json" | Sort-Object Name
foreach ($configPath in $configs) {
  $config = Get-Content -Raw -LiteralPath $configPath.FullName | ConvertFrom-Json
  $caseId = [string]$config.case_id
  $prNumber = [string]$config.pr_number
  $shortSha = ([string]$config.base_commit).Substring(0, 12)
  $installBun = if ($config.PSObject.Properties.Name.Contains("requires_bun") -and $config.requires_bun) { "true" } else { "false" }

  $dir = Join-Path $composeRoot $caseId
  New-Item -ItemType Directory -Force -Path $dir | Out-Null

  $envText = @"
CASE_ID=$caseId
PR_NUMBER=$prNumber
BASE_COMMIT=$($config.base_commit)
PNPM_VERSION=$($config.pnpm_version)
INSTALL_BUN=$installBun
NODE_IMAGE=$NodeImage
NPM_REGISTRY=$NpmRegistry
IMAGE_REF=$ImagePrefix-$prNumber`:$shortSha
MODE=env
"@
  Set-Content -LiteralPath (Join-Path $dir ".env") -Value $envText -Encoding UTF8

  $composeText = @"
services:
  evaluator:
    image: `${IMAGE_REF}
    build:
      context: ../..
      dockerfile: dockerfiles/FastGPT.Evaluator.Dockerfile
      args:
        PR_ID: `${CASE_ID}
        BASE_COMMIT: `${BASE_COMMIT}
        FASTGPT_REPO: https://github.com/labring/FastGPT.git
        PNPM_VERSION: `${PNPM_VERSION}
        INSTALL_BUN: `${INSTALL_BUN}
        NODE_IMAGE: `${NODE_IMAGE}
        NPM_REGISTRY: `${NPM_REGISTRY}
    command: `${MODE:-env}
    environment:
      CI: "true"
      NODE_OPTIONS: "--max-old-space-size=8192"
    volumes:
      - ../../dist/compose-results/`${CASE_ID}:/results
"@
  Set-Content -LiteralPath (Join-Path $dir "docker-compose.yml") -Value $composeText -Encoding UTF8

  $patchComposeText = @"
services:
  evaluator:
    volumes:
      - ./candidate.patch:/patches/candidate.patch:ro
"@
  Set-Content -LiteralPath (Join-Path $dir "docker-compose.patch.yml") -Value $patchComposeText -Encoding UTF8

  $readmeText = @"
# $caseId Docker Compose evaluator

## Build image

````powershell
docker compose build
````

## Run env check

````powershell
docker compose run --rm evaluator
````

## Run a phase

Edit `.env` and set `MODE=test`, `MODE=build`, `MODE=docker`, or `MODE=all`, then run:

````powershell
docker compose run --rm evaluator
````

## Run with a patch

Copy the candidate patch to this folder as `candidate.patch`, then run:

````powershell
docker compose -f docker-compose.yml -f docker-compose.patch.yml run --rm evaluator
````

Results are written to:

````text
../../dist/compose-results/$caseId/
````

Image ref:

````text
$ImagePrefix-$prNumber`:$shortSha
````
"@
  Set-Content -LiteralPath (Join-Path $dir "README.md") -Value $readmeText -Encoding UTF8

  Write-Host "Generated compose for $caseId"
}

Write-Host ""
Write-Host "Generated $($configs.Count) compose directories under $composeRoot"
