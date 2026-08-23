

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

    # WHY THE PREFERENCE IS RELAXED AROUND THIS CALL:
    # gcloud writes routine informational output to STDERR - "Updated property
    # [core/project].", "Creating...", "Listing items under project..." are all
    # stderr, not errors. Windows PowerShell 5.1 turns redirected native stderr
    # into ErrorRecords, and with $ErrorActionPreference = 'Stop' the FIRST such
    # line becomes a terminating error. The result is a script that dies on a
    # success message.
    #
    # The exit code is the only trustworthy success signal for a native command,
    # and it is checked below. Relaxing the preference for the duration of the
    # call does not weaken that check - it is what makes the check reachable.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # Capture everything, then echo it when not -Quiet.
        # Deliberately NOT `Tee-Object -Variable`: Tee-Object never CREATES the
        # variable when the command emits no output at all, and plenty of gcloud
        # commands are silent on success (`services enable --quiet` is). Reading
        # the unset variable then trips Set-StrictMode, so a silent SUCCESS
        # became a script-ending error.
        $output = @(& gcloud @Arguments 2>&1)
        if (-not $Quiet -and $output.Count -gt 0) {
            # A merged stderr line arrives as an ErrorRecord whose default
            # rendering is the useless "System.Management.Automation.RemoteException".
            # The actual text lives on .Exception.Message.
            $output | ForEach-Object {
                $line = if ($_ -is [System.Management.Automation.ErrorRecord]) {
                    if ($_.Exception -and $_.Exception.Message) { $_.Exception.Message } else { $_.ToString() }
                } else { [string]$_ }
                if ($line.Trim()) { Write-Host "    $line" }
            }
        }
    } finally {
        $ErrorActionPreference = $previous
    }

    if ($LASTEXITCODE -ne 0) {
        throw "gcloud $($Arguments -join ' ') failed with exit code $LASTEXITCODE`n$($output -join "`n")"
    }
    return $output
}

function Test-GcloudResource {

    param([Parameter(Mandatory, ValueFromRemainingArguments)][string[]]$Arguments)

    # Same stderr caveat as Invoke-Gcloud. This probe EXPECTS failure half the
    # time (that is how it detects a missing resource), so a stderr line must
    # never be allowed to terminate the script.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $null = & gcloud @Arguments 2>&1
        $exists = ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $previous
    }
    $global:LASTEXITCODE = 0
    return $exists
}

function Assert-Project {
    param(
        [Parameter(Mandatory)][string]$ProjectId,
        [Parameter(Mandatory)][string]$ExpectedNumber
    )

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $actual = (& gcloud projects describe $ProjectId --format="value(projectNumber)" 2>&1)
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot describe project '$ProjectId'. Run: gcloud auth login"
    }
    if ("$actual".Trim() -ne $ExpectedNumber) {
        throw "Project number mismatch. Expected $ExpectedNumber, got $actual. Wrong project - stopping before anything is created."
    }
    Write-Ok "Project $ProjectId ($ExpectedNumber) confirmed"
}
