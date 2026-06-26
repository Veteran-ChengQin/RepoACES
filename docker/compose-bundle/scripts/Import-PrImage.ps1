[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$Tar
)

$ErrorActionPreference = "Stop"

$tarPath = (Resolve-Path $Tar).Path
docker load -i $tarPath
if ($LASTEXITCODE -ne 0) {
  throw "docker load failed with exit code $LASTEXITCODE"
}

Write-Host "Image loaded from $tarPath"
