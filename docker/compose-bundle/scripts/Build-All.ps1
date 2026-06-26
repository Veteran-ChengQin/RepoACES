[CmdletBinding()]
param(
  [string]$ImagePrefix = "repoaces/eval",
  [string]$NpmRegistry = "",
  [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$configs = Get-ChildItem -LiteralPath (Join-Path $root "configs") -Filter "*.eval.json" | Sort-Object Name

foreach ($configPath in $configs) {
  $config = Get-Content -Raw -LiteralPath $configPath.FullName | ConvertFrom-Json
  & (Join-Path $PSScriptRoot "Build-PrImage.ps1") `
    -Pr $config.pr_number `
    -ImagePrefix $ImagePrefix `
    -NpmRegistry $NpmRegistry `
    -SkipVerify:$SkipVerify
}
