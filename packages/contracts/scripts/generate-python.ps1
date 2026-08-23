#Requires -Version 5.1
<#
.SYNOPSIS
  Generates Pydantic v2 models from packages/contracts/schemas into the agent service.

.DESCRIPTION
  Runs datamodel-code-generator through `uvx`, so no global Python install is
  polluted and the generator version is pinned in one place.

  --disable-timestamp is MANDATORY. Without it the generator stamps the current
  time into every file, every run differs, and the CI drift check becomes noise
  that everyone learns to ignore.

.EXAMPLE
  pwsh ./packages/contracts/scripts/generate-python.ps1
#>
[CmdletBinding()]
param(
    [string]$GeneratorVersion = "0.26.4"
)

$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSVersion.Major -ge 7) { $PSNativeCommandUseErrorActionPreference = $true }

$scriptRoot   = Split-Path -Parent $MyInvocation.MyCommand.Path
$contractsDir = Split-Path -Parent $scriptRoot
$repoRoot     = Split-Path -Parent (Split-Path -Parent $contractsDir)
$schemaDir    = Join-Path $contractsDir "schemas"
# Forward slashes deliberately. PowerShell on Linux - which is what the CI
# contracts-drift job runs on - does NOT treat \ as a path separator, so a
# Windows-style path string creates ONE directory whose name contains literal
# backslashes, and the drift check could then never pass.
$outDir       = Join-Path $repoRoot "services/agent/src/rinne_agent/contracts"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is not installed. Install it with:  winget install --id astral-sh.uv -e"
}

# Windows PowerShell 5.1 and Python both default file I/O to the system ANSI
# codepage (cp1252 here). The schemas contain non-ASCII characters - the section
# sign in "chosen per section 7 step 2" - so without this the generator emits cp1252
# bytes that ruff, mypy and Python 3 all reject as invalid UTF-8. PYTHONUTF8=1
# forces UTF-8 on every Python process uv spawns.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$header = @"
# GENERATED FILE - DO NOT EDIT BY HAND.
#
# Source of truth : packages/contracts/schemas
# Regenerate      : pwsh ./packages/contracts/scripts/generate-python.ps1
#
# CI regenerates and runs `git diff --exit-code`. A schema edit without a
# regeneration is a build failure.
"@

Get-ChildItem -Path $schemaDir -Filter "*.schema.json" | Sort-Object Name | ForEach-Object {
    $stem     = $_.BaseName -replace '\.schema$', ''
    $module   = ($stem -replace '-', '_') + ".py"
    $outFile  = Join-Path $outDir $module

    Write-Host "contracts: $($_.Name) -> rinne_agent/contracts/$module"

    uv tool run --from "datamodel-code-generator==$GeneratorVersion" datamodel-codegen `
        --input $_.FullName `
        --input-file-type jsonschema `
        --output $outFile `
        --output-model-type pydantic_v2.BaseModel `
        --target-python-version 3.12 `
        --use-standard-collections `
        --use-union-operator `
        --use-double-quotes `
        --use-schema-description `
        --use-field-description `
        --field-constraints `
        --snake-case-field `
        --disable-timestamp `
        --custom-file-header $header

    if ($LASTEXITCODE -ne 0) { throw "datamodel-codegen failed for $($_.Name)" }
    # Normalise to UTF-8 without BOM and LF endings. Windows text-mode I/O emits
    # CRLF, which would make the CI drift check fail forever against a Linux
    # runner for a reason that has nothing to do with the schema.
    $text = [System.IO.File]::ReadAllText($outFile, (New-Object System.Text.UTF8Encoding($false)))
    $text = $text -replace "`r`n", "`n" -replace "`r", "`n"
    [System.IO.File]::WriteAllText($outFile, $text, (New-Object System.Text.UTF8Encoding($false)))
}

# Package marker, written deterministically so the drift check stays stable.
$initPath = Join-Path $outDir "__init__.py"
$initBody = @"
$header

from rinne_agent.contracts.health import HealthReport
from rinne_agent.contracts.scene_description import SceneDescription

__all__ = ["HealthReport", "SceneDescription"]
"@
[System.IO.File]::WriteAllText($initPath, ($initBody -replace "`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))

Write-Host "contracts: Pydantic models written to services/agent/src/rinne_agent/contracts" -ForegroundColor Green
