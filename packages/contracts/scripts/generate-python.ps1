#Requires -Version 5.1
<#
.SYNOPSIS
  Generates Pydantic v2 models from packages/contracts/schemas into EVERY Python
  service that consumes a contract.

.DESCRIPTION
  Runs datamodel-code-generator through `uvx`, so no global Python install is
  polluted and the generator version is pinned in one place.

  --disable-timestamp is MANDATORY. Without it the generator stamps the current
  time into every file, every run differs, and the CI drift check becomes noise
  that everyone learns to ignore.

  EVERY TARGET GETS EVERY SCHEMA. There is deliberately no per-target filter
  list: a filter is a second source of truth and it drifts. rinne_reconstruction
  needs HealthReport today and rinne_agent needs ReconstructionResult on Day 4.
  The cost of the rule is that scene_description.py is dead code inside
  rinne_reconstruction until Day 5 - generated, excluded from ruff and mypy,
  and free at import.

  THE AGENT'S FILES MUST NOT MOVE. This script replaced a single-target
  predecessor, and health.py / scene_description.py under services/agent are
  expected to regenerate byte-for-byte. Same flags, same header text. If either
  model file shows a diff after a run, a flag was changed by accident.

.EXAMPLE
  .\packages\contracts\scripts\generate-python.ps1
#>
[CmdletBinding()]
param(
    [string]$GeneratorVersion = "0.74.0"
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
$targets = @(
    @{ Package = "rinne_agent";          Out = "services/agent/src/rinne_agent/contracts" },
    @{ Package = "rinne_reconstruction"; Out = "services/reconstruction/src/rinne_reconstruction/contracts" }
)

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is not installed. Install it with:  winget install --id astral-sh.uv -e"
}

# Windows PowerShell 5.1 and Python both default file I/O to the system ANSI
# codepage (cp1252 here).
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# UTF-8 with NO byte order mark, used for every read and every write below.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# The rendered text must stay byte-identical to what the single-target
# predecessor wrote, or every agent contract file shows a spurious diff.
$header = @"
# GENERATED FILE - DO NOT EDIT BY HAND.
#
# Source of truth : packages/contracts/schemas
# Regenerate      : pwsh ./packages/contracts/scripts/generate-python.ps1
#
# CI regenerates and runs git diff --exit-code. A schema edit without a
# regeneration is a build failure.
"@

$header = $header -replace "`r`n", "`n"

$schemaFiles = Get-ChildItem -Path $schemaDir -Filter "*.schema.json" | Sort-Object Name
if ($schemaFiles.Count -eq 0) {
    throw "No *.schema.json files found in $schemaDir"
}

# Read every title ONCE, before generating anything. The class name in the
# generated module comes from the schema title, and so does the import written
# into __init__.py - deriving both from the same read is what stops the two
# from disagreeing. A schema with no title is a hard failure, not a fallback.
$modules = @()
foreach ($file in $schemaFiles) {
    $stem = $file.BaseName -replace '\.schema$', ''
    $json = [System.IO.File]::ReadAllText($file.FullName, $utf8NoBom) | ConvertFrom-Json
    if (-not $json.title) {
        throw "$($file.Name) has no `"title`". The generated class name is derived from it."
    }
    $modules += [pscustomobject]@{
        Module = $stem -replace '-', '_'
        Class  = $json.title
        Path   = $file.FullName
        Name   = $file.Name
    }
}

foreach ($target in $targets) {
    $outDir = Join-Path $repoRoot $target.Out
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null

    foreach ($m in $modules) {
        $outFile = Join-Path $outDir "$($m.Module).py"

        Write-Host "contracts: $($m.Name) -> $($target.Package)/contracts/$($m.Module).py"

        uv tool run --from "datamodel-code-generator==$GeneratorVersion" datamodel-codegen `
            --input $m.Path `
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
            --formatters black isort `
            --custom-file-header $header

        if ($LASTEXITCODE -ne 0) { throw "datamodel-codegen failed for $($m.Name)" }

        # Normalise to UTF-8 without BOM and LF endings. Windows text-mode I/O emits
        # CRLF, which would make the CI drift check fail forever against a Linux
        # runner for a reason that has nothing to do with the schema.
        $text = [System.IO.File]::ReadAllText($outFile, $utf8NoBom)
        $text = $text -replace "`r`r`n", "`n" -replace "`r`n", "`n" -replace "`r", "`n"
        [System.IO.File]::WriteAllText($outFile, $text, $utf8NoBom)
    }

    # Package marker, written deterministically so the drift check stays stable.
    # Both the imports and __all__ are derived from the schema titles read above,
    # so adding a schema needs no edit here.
    $imports = ($modules | ForEach-Object {
        "from $($target.Package).contracts.$($_.Module) import $($_.Class)"
    }) -join "`n"

    $exported = ($modules | ForEach-Object { """$($_.Class)""" }) -join ", "

    $initBody = @"
$header

$imports

__all__ = [$exported]

"@
    $initPath = Join-Path $outDir "__init__.py"
    [System.IO.File]::WriteAllText($initPath, ($initBody -replace "`r`n", "`n"), $utf8NoBom)

    Write-Host "contracts: $($modules.Count) model(s) + __init__.py written to $($target.Out)" -ForegroundColor Green
}
