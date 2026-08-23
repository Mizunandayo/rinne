#Requires -Version 5.1
<#
.SYNOPSIS
  Day 1 GCP resources: Artifact Registry, one least-privilege service account
  per Cloud Run service, and an image cleanup policy.

.DESCRIPTION
  Idempotent. Safe to re-run.

  PART 0 IS ALREADY COMPLETE AND THIS SCRIPT DOES NOT REPEAT IT. Project
  creation, billing linkage, API enablement, GPU quota, and budgets were done
  and verified on Aug 16 2026. This script asserts they are in place and then
  creates only what Parts 1-10 need.

  WHAT IT DELIBERATELY DOES NOT DO:
    * Grant roles/run.invoker. That binding is per-service and the services do
      not exist yet; deploy-all.ps1 grants it after each private deploy.
    * Touch the default compute service account. It carries project Editor and
      no Rinne service may ever use it.

.EXAMPLE
  pwsh .\infra\scripts\bootstrap-gcp.ps1 -Verbose
#>
[CmdletBinding()]
param(
    [string]$ProjectId     = "rinnehackathon",
    [string]$ProjectNumber = "900016126232",
    [string]$Region        = "asia-southeast1",
    [string]$RepoName      = "rinne"
)

. "$PSScriptRoot\lib\Rinne.Common.ps1"
Initialize-RinneShell

Assert-Tool -Name gcloud -InstallHint "Install the Google Cloud CLI: https://cloud.google.com/sdk/docs/install"

Write-Step "Confirming project identity"
Assert-Project -ProjectId $ProjectId -ExpectedNumber $ProjectNumber

Write-Step "Setting gcloud defaults for this shell"
Invoke-Gcloud config set project $ProjectId --quiet | Out-Null
Invoke-Gcloud config set run/region $Region --quiet | Out-Null
Write-Ok "project=$ProjectId  run/region=$Region"

# ---------------------------------------------------------------------
Write-Step "Verifying the APIs enabled in Part 0"
$required = @(
    'run.googleapis.com', 'artifactregistry.googleapis.com', 'cloudbuild.googleapis.com',
    'secretmanager.googleapis.com', 'aiplatform.googleapis.com', 'firestore.googleapis.com',
    'pubsub.googleapis.com', 'eventarc.googleapis.com', 'iamcredentials.googleapis.com'
)
$enabled = (Invoke-Gcloud services list --enabled --format="value(config.name)" --project=$ProjectId -Quiet) -split "`n" |
    ForEach-Object { $_.Trim() } | Where-Object { $_ }

$missing = $required | Where-Object { $enabled -notcontains $_ }
if ($missing) {
    throw "APIs missing (Part 0 claimed these were enabled): $($missing -join ', ')`nEnable with: gcloud services enable $($missing -join ' ')"
}
Write-Ok "All $($required.Count) required APIs confirmed enabled"

# ---------------------------------------------------------------------
Write-Step "Artifact Registry repository"
$repoExists = Test-GcloudResource artifacts repositories describe $RepoName `
    --location=$Region --project=$ProjectId --format="value(name)"

if ($repoExists) {
    Write-Skip "artifacts repository '$RepoName' in $Region"
} else {
    Invoke-Gcloud artifacts repositories create $RepoName `
        --repository-format=docker `
        --location=$Region `
        --project=$ProjectId `
        --description="Rinne service images" `
        --quiet | Out-Null
    Write-Ok "Created Docker repository '$RepoName' in $Region"
}

Write-Step "Container vulnerability scanning"
if (Test-GcloudResource services list --enabled --filter="config.name=containerscanning.googleapis.com" `
        --format="value(config.name)" --project=$ProjectId) {
    Invoke-Gcloud services enable containerscanning.googleapis.com --project=$ProjectId --quiet | Out-Null
    Write-Ok "containerscanning.googleapis.com enabled"
}

# ---------------------------------------------------------------------
Write-Step "Service accounts, one per service, least privilege"


$serviceAccounts = @(
    @{
        Id      = "rinne-web-sa"
        Display = "Rinne web (public cockpit and manifest)"
        Roles   = @('roles/logging.logWriter')

    },
    @{
        Id      = "rinne-physics-sa"
        Display = "Rinne physics (headless Rapier)"
        Roles   = @('roles/logging.logWriter')

    },
    @{
        Id      = "rinne-agent-sa"
        Display = "Rinne agent (FastAPI and ADK)"
        Roles   = @('roles/logging.logWriter')
    },
    @{
        Id      = "rinne-reconstruction-sa"
        Display = "Rinne reconstruction (TripoSR on GPU)"
        Roles   = @('roles/logging.logWriter')
    }
)

foreach ($sa in $serviceAccounts) {
    $email = "$($sa.Id)@$ProjectId.iam.gserviceaccount.com"

    if (Test-GcloudResource iam service-accounts describe $email --project=$ProjectId --format="value(email)") {
        Write-Skip "service account $($sa.Id)"
    } else {
        Invoke-Gcloud iam service-accounts create $sa.Id `
            --display-name=$sa.Display `
            --project=$ProjectId --quiet | Out-Null
        Write-Ok "Created $email"
    }

    foreach ($role in $sa.Roles) {
        Invoke-Gcloud projects add-iam-policy-binding $ProjectId `
            --member="serviceAccount:$email" `
            --role=$role `
            --condition=None `
            --quiet -Quiet | Out-Null
        Write-Ok "  $($sa.Id) -> $role"
    }
}

# ---------------------------------------------------------------------
Write-Step "Artifact Registry cleanup policy"

$policyPath = Join-Path $PSScriptRoot "..\policies\artifact-cleanup-policy.json"
if (-not (Test-Path $policyPath)) {
    throw "Missing $policyPath"
}

try {
    Invoke-Gcloud artifacts repositories set-cleanup-policies $RepoName `
        --location=$Region --project=$ProjectId `
        --policy=$policyPath --no-dry-run --quiet | Out-Null
    Write-Ok "Cleanup policy applied: keep 5 most recent, delete untagged after 7 days"
} catch {
    Write-Warning "Cleanup policy not applied. Verify current syntax with:"
    Write-Warning "  gcloud artifacts repositories set-cleanup-policies --help"
    Write-Warning $_.Exception.Message
}

# ---------------------------------------------------------------------
Write-Step "Bootstrap complete"
Write-Host ""
Write-Host "  Artifact Registry : $Region-docker.pkg.dev/$ProjectId/$RepoName" -ForegroundColor White
Write-Host "  Service accounts  : rinne-{web,physics,agent,reconstruction}-sa" -ForegroundColor White
Write-Host ""
Write-Host "  Next:  pwsh .\infra\scripts\deploy-all.ps1" -ForegroundColor White
Write-Host ""
