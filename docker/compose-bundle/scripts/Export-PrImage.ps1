[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$Pr,

  [string]$ImagePrefix = "repoaces/eval",
  [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$caseId = if ($Pr.StartsWith("fastgpt-pr-")) { $Pr } else { "fastgpt-pr-$Pr" }
$configPath = Join-Path $root "configs\$caseId.eval.json"

if (-not (Test-Path -LiteralPath $configPath)) {
  throw "Config not found: $configPath"
}

$config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$imageRef = "$ImagePrefix-$($config.pr_number):$($config.base_commit.Substring(0, 12))"

if (-not $OutDir) {
  $OutDir = Join-Path $root "dist\share\$caseId"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$tarPath = Join-Path $OutDir "$caseId-image.tar"
$configOut = Join-Path $OutDir "$caseId.eval.json"
$runnerOut = Join-Path $OutDir "Run-PrEval.ps1"
$importOut = Join-Path $OutDir "Import-PrImage.ps1"

docker image inspect $imageRef *> $null
if ($LASTEXITCODE -ne 0) {
  throw "Image not found locally: $imageRef. Build it first."
}

docker save -o $tarPath $imageRef
if ($LASTEXITCODE -ne 0) {
  throw "docker save failed with exit code $LASTEXITCODE"
}

Copy-Item -LiteralPath $configPath -Destination $configOut -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Run-PrEval.ps1") -Destination $runnerOut -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Import-PrImage.ps1") -Destination $importOut -Force

@"
# $caseId image handoff

1. Load image:

   powershell -ExecutionPolicy Bypass -File .\Import-PrImage.ps1 -Tar .\$caseId-image.tar

2. Run env check:

   powershell -ExecutionPolicy Bypass -File .\Run-PrEval.ps1 -Pr $($config.pr_number) -Mode env

3. Run with candidate patch:

   powershell -ExecutionPolicy Bypass -File .\Run-PrEval.ps1 -Pr $($config.pr_number) -Mode all -Patch D:\path\to\candidate.patch

Image: $imageRef
"@ | Set-Content -LiteralPath (Join-Path $OutDir "README-HANDOFF.md") -Encoding UTF8

Write-Host "Exported handoff package: $OutDir"
