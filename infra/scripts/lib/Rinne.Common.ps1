

Set-StrictMode -Version Latest

function Initialize-RinneShell {

    $script:ErrorActionPreference = 'Stop'
    if ($PSVersionTable.PSVersion.Major -ge 7) {
        $global:PSNativeCommandUseErrorActionPreference = $true
    }
}

function Write-Step {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host "    $Message" -ForegroundColor Green
}

function Write-Skip {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host "    $Message (already present)" -ForegroundColor DarkCyan
}

function Assert-Tool {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$InstallHint
    )
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is not on PATH. $InstallHint"
    }
}

function Invoke-Gcloud {
    <#
      .SYNOPSIS
        Runs gcloud and throws on a non-zero exit code.
      .PARAMETER Quiet
        Suppress stdout. Use for describe calls whose output you do not need.
    #>
    param(
        [Parameter(Mandatory, ValueFromRemainingArguments)][string[]]$Arguments,
        [switch]$Quiet
    )

    Write-Verbose "gcloud $($Arguments -join ' ')"

    if ($Quiet) {
        $output = & gcloud @Arguments 2>&1
    } else {
        $output = & gcloud @Arguments 2>&1 | Tee-Object -Variable teed
        $output = $teed
    }

    if ($LASTEXITCODE -ne 0) {
        throw "gcloud $($Arguments -join ' ') failed with exit code $LASTEXITCODE`n$($output -join "`n")"
    }
    return $output
}

function Test-GcloudResource {

    param([Parameter(Mandatory, ValueFromRemainingArguments)][string[]]$Arguments)

    $null = & gcloud @Arguments 2>&1
    $exists = ($LASTEXITCODE -eq 0)
    $global:LASTEXITCODE = 0
    return $exists
}

function Assert-Project {
    param(
        [Parameter(Mandatory)][string]$ProjectId,
        [Parameter(Mandatory)][string]$ExpectedNumber
    )

    $actual = (& gcloud projects describe $ProjectId --format="value(projectNumber)" 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot describe project '$ProjectId'. Run: gcloud auth login"
    }
    if ("$actual".Trim() -ne $ExpectedNumber) {
        throw "Project number mismatch. Expected $ExpectedNumber, got $actual. Wrong project - stopping before anything is created."
    }
    Write-Ok "Project $ProjectId ($ExpectedNumber) confirmed"
}
