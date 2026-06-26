[CmdletBinding()]
param(
  [string]$Root = "",
  [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

if (-not $Root) {
  $Root = Split-Path -Parent $PSScriptRoot
}

if (-not $OutDir) {
  $OutDir = Join-Path $Root "dist\share\compose-bundle"
}

if (Test-Path -LiteralPath $OutDir) {
  Remove-Item -LiteralPath $OutDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

foreach ($name in @("configs", "compose", "dockerfiles", "runtime", "scripts", "docs")) {
  Copy-Item -LiteralPath (Join-Path $Root $name) -Destination (Join-Path $OutDir $name) -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $Root "manifest.json") -Destination (Join-Path $OutDir "manifest.json") -Force
if (Test-Path -LiteralPath (Join-Path $Root "README-COMPOSE.md")) {
  Copy-Item -LiteralPath (Join-Path $Root "README-COMPOSE.md") -Destination (Join-Path $OutDir "README.md") -Force
  Copy-Item -LiteralPath (Join-Path $Root "README-COMPOSE.md") -Destination (Join-Path $OutDir "README-COMPOSE.md") -Force
} else {
  Copy-Item -LiteralPath (Join-Path $Root "README.md") -Destination (Join-Path $OutDir "README.md") -Force
}

@"
# RepoACES PR Docker Compose Bundle

This bundle contains:

- configs/*.eval.json
- compose/fastgpt-pr-*/docker-compose.yml
- dockerfiles/FastGPT.Evaluator.Dockerfile
- runtime evaluator scripts
- PowerShell helper scripts

Quick start:

1. Open PowerShell in this bundle root.
2. Pick a PR, for example:

   cd .\compose\fastgpt-pr-7138

3. Build:

   docker compose build

4. Run env check:

   docker compose run --rm evaluator

5. Run with patch:

   copy D:\path\to\candidate.patch .\candidate.patch
   docker compose -f docker-compose.yml -f docker-compose.patch.yml run --rm evaluator

Change MODE in .env to test/build/docker/all when needed.
"@ | Set-Content -LiteralPath (Join-Path $OutDir "README-COMPOSE-BUNDLE.md") -Encoding UTF8

Write-Host "Exported compose bundle: $OutDir"
