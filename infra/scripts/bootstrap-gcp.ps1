#Requires -Version 5.1
<#
.SYNOPSIS
  Day 1 GCP resources: Artifact Registry, one least-privilege service account
  per Cloud Run service, and an image cleanup policy. Day 4 adds the Firestore
  database, the scan-queue bucket, and the Eventarc trigger identity.

.DESCRIPTION
  Idempotent. Safe to re-run.

  PART 0 IS ALREADY COMPLETE AND THIS SCRIPT DOES NOT REPEAT IT. Project
  creation, billing linkage, API enablement, GPU quota, and budgets were done
  and verified on Aug 16 2026. This script asserts they are in place and then
  creates only what Parts 1-10 need.

  WHAT IT DELIBERATELY DOES NOT DO:
    * Grant roles/run.invoker. That binding is per-service and the services do
      not exist yet; deploy-all.ps1 grants it after each private deploy.
    * Create the Eventarc trigger. Same reason: the trigger names a Cloud Run
      service and a path, so it belongs beside the deploy that creates them.
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

function Add-ProjectRole {
    <#
      A role binding issued straight after `service-accounts create` can fail
      with "Service account ... does not exist" - hit for real on Aug 30, 2026.
      The account IS real: the SA directory and the IAM policy backend are
      different systems, and the policy write raced the directory's replication.
      Polling `describe` does NOT fix it - describe succeeded while the binding
      was still being refused - so the retry has to wrap the binding itself.

      Concurrent policy edits (ABORTED) get the same treatment for the same
      reason. Anything else rethrows immediately rather than burning 40 seconds
      re-trying a real permission failure.
    #>
    param(
        [Parameter(Mandatory)][string]$ProjectId,
        [Parameter(Mandatory)][string]$Member,
        [Parameter(Mandatory)][string]$Role,
        [int]$MaxAttempts  = 8,
        [int]$DelaySeconds = 5
    )
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            Invoke-Gcloud projects add-iam-policy-binding $ProjectId `
                --member=$Member `
                --role=$Role `
                --condition=None `
                --quiet -Quiet | Out-Null
            return
        } catch {
            $message = $_.Exception.Message
            $transient = ($message -match 'does not exist') -or ($message -match 'ABORTED') `
                -or ($message -match 'concurrent')
            if (-not $transient -or $attempt -ge $MaxAttempts) { throw }
            Write-Host "    IAM has not caught up yet; retrying in ${DelaySeconds}s ($attempt/$MaxAttempts)" `
                -ForegroundColor DarkCyan
            Start-Sleep -Seconds $DelaySeconds
        }
    }
}

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
    'pubsub.googleapis.com', 'eventarc.googleapis.com', 'iamcredentials.googleapis.com',
    'storage.googleapis.com'
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
# Enabled unconditionally. `gcloud services enable` is idempotent - enabling an
# already-enabled API is a successful no-op - so a guard buys nothing here.
# The previous guard was worse than nothing: `services list` SUCCEEDS whether or
# not the API appears in its results, so Test-GcloudResource was always true and
# the condition read "if it is enabled, enable it".
$scanApi = "containerscanning.googleapis.com"
$enabledApis = @(Invoke-Gcloud services list --enabled --format="value(config.name)" --project=$ProjectId -Quiet)
if ($enabledApis -contains $scanApi) {
    Write-Skip "$scanApi"
} else {
    Invoke-Gcloud services enable $scanApi --project=$ProjectId --quiet -Quiet | Out-Null
    Write-Ok "$scanApi enabled - Artifact Registry will scan pushed images"
}

# ---------------------------------------------------------------------
Write-Step "Service accounts, one per service, least privilege"

# PROJECT-LEVEL ROLES ARE A LAST RESORT AND EACH ONE IS DELIBERATE.
#   roles/datastore.user   Firestore has no per-collection IAM. There is no
#                          narrower grant that lets the agent write its own
#                          decision log, so this is the floor, not a shortcut.
#   roles/aiplatform.user  Vertex AI predictions are a project-level surface.
#   roles/eventarc.eventReceiver  What lets the trigger identity receive an
#                          event at all. It is NOT what lets it call the agent -
#                          that is roles/run.invoker on one service, granted in
#                          deploy-all.ps1.

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
        Roles   = @('roles/logging.logWriter', 'roles/datastore.user', 'roles/aiplatform.user')
    },
    @{
        Id      = "rinne-reconstruction-sa"
        Display = "Rinne reconstruction (TripoSR on GPU)"
        Roles   = @('roles/logging.logWriter')
    },
    @{
        Id      = "rinne-eventarc-sa"
        Display = "Rinne Eventarc trigger (scan queue to agent)"
        Roles   = @('roles/eventarc.eventReceiver')
    }
)

foreach ($sa in $serviceAccounts) {
    $email = "$($sa.Id)@$ProjectId.iam.gserviceaccount.com"

    if (Test-GcloudResource iam service-accounts describe $email --project=$ProjectId --format="value(email)") {
        Write-Skip "service account $($sa.Id)"
    } else {
        Invoke-Gcloud iam service-accounts create $sa.Id `
            --display-name="$($sa.Display)" `
            --project=$ProjectId --quiet | Out-Null
        Write-Ok "Created $email"
    }

    foreach ($role in $sa.Roles) {
        Add-ProjectRole -ProjectId $ProjectId -Member "serviceAccount:$email" -Role $role
        Write-Ok "  $($sa.Id) -> $role"
    }
}

# ---------------------------------------------------------------------
Write-Step "Firestore database"

# Enabling firestore.googleapis.com does NOT create a database. The default
# database's location is FIXED at creation and cannot be changed afterwards
# without deleting it, so the guard below matters more than most.
$dbFlag = '--database=(default)'
if (Test-GcloudResource firestore databases describe $dbFlag --project=$ProjectId --format="value(name)") {
    $dbLocation = ((Invoke-Gcloud firestore databases describe $dbFlag `
        --project=$ProjectId --format="value(locationId)" -Quiet) -join '').Trim()
    Write-Skip "Firestore database (default) in $dbLocation"
    if ($dbLocation -and $dbLocation -ne $Region) {
        Write-Warning "Firestore (default) is in '$dbLocation', not '$Region'. The location is immutable."
    }
} else {
    # Native mode, not Datastore mode. The agent writes documents and reads them
    # back by key; Datastore mode would work and would also close the door on
    # the cockpit's realtime listeners on Day 6 for nothing.
    Invoke-Gcloud firestore databases create `
        --location=$Region `
        --type=firestore-native `
        --project=$ProjectId `
        --quiet | Out-Null
    Write-Ok "Created Firestore (default), Native mode, in $Region"
}

# ---------------------------------------------------------------------
Write-Step "Buckets"

# TWO BUCKETS, AND THE SPLIT IS LOAD-BEARING.
#   rinne-artifacts-*  reconstruction WRITES meshes here.
#   rinne-scans-*      the agent's ingest queue, and the ONLY bucket with an
#                      Eventarc trigger on it.
# Eventarc cannot filter a storage trigger by object prefix - only by bucket -
# so a trigger on the artifacts bucket would fire on every mesh the system
# itself writes and the agent would process its own output. A separate bucket
# removes that class of bug rather than guarding against it.
$artifactsBucket = "rinne-artifacts-$ProjectId"
$scansBucket     = "rinne-scans-$ProjectId"

$lifecyclePath = Join-Path $PSScriptRoot "..\policies\bucket-lifecycle.json"
if (-not (Test-Path $lifecyclePath)) { throw "Missing $lifecyclePath" }

foreach ($bucket in @($artifactsBucket, $scansBucket)) {
    # Uniform bucket-level access and enforced public access prevention: a mesh
    # URI is model-shaped output, so per-object ACLs must not be reachable at all.
    if (Test-GcloudResource storage buckets describe "gs://$bucket" --project=$ProjectId --format="value(name)") {
        Write-Skip "bucket gs://$bucket"
    } else {
        Invoke-Gcloud storage buckets create "gs://$bucket" `
            --project=$ProjectId `
            --location=$Region `
            --uniform-bucket-level-access `
            --public-access-prevention `
            --no-enable-autoclass `
            --quiet | Out-Null
        Write-Ok "Created gs://$bucket in $Region"
    }

    # Soft-delete off. It is billable storage for objects a 14-day lifecycle is
    # already deleting on purpose.
    Invoke-Gcloud storage buckets update "gs://$bucket" `
        --project=$ProjectId `
        --clear-soft-delete `
        --quiet -Quiet | Out-Null

    Invoke-Gcloud storage buckets update "gs://$bucket" `
        --project=$ProjectId `
        --lifecycle-file=$lifecyclePath `
        --quiet -Quiet | Out-Null
    Write-Ok "  gs://$bucket - soft-delete off, objects deleted after 14 days"
}

# ---------------------------------------------------------------------
Write-Step "Bucket IAM - deliberately asymmetric"

# reconstruction WRITES artifacts and never reads; web and physics READ them.
# The agent READS scans and never writes anything anywhere. Nobody holds
# objectAdmin, and every binding is on one bucket, never on the project.
$bucketBindings = @(
    @{ Bucket = $artifactsBucket; Sa = "rinne-reconstruction-sa"; Role = "roles/storage.objectCreator" },
    @{ Bucket = $artifactsBucket; Sa = "rinne-web-sa";            Role = "roles/storage.objectViewer" },
    @{ Bucket = $artifactsBucket; Sa = "rinne-physics-sa";        Role = "roles/storage.objectViewer" },
    @{ Bucket = $scansBucket;     Sa = "rinne-agent-sa";          Role = "roles/storage.objectViewer" }
)
foreach ($binding in $bucketBindings) {
    $member = "serviceAccount:$($binding.Sa)@$ProjectId.iam.gserviceaccount.com"
    Invoke-Gcloud storage buckets add-iam-policy-binding "gs://$($binding.Bucket)" `
        --project=$ProjectId `
        --member=$member `
        --role="$($binding.Role)" `
        --quiet -Quiet | Out-Null
    Write-Ok "  $($binding.Sa) -> $($binding.Role) on gs://$($binding.Bucket)"
}

# ---------------------------------------------------------------------
Write-Step "Cloud Storage service agent may publish to Pub/Sub"

# THIS IS THE ONE EVENTARC PREREQUISITE THAT IS NOT AUTOMATIC. An Eventarc
# storage trigger is a Pub/Sub notification underneath, published by the GCS
# service agent. Without roles/pubsub.publisher the trigger CREATES SUCCESSFULLY
# and then never delivers anything, which is the worst possible failure shape:
# no error, no event, nothing to read.
#
# `gcloud storage service-agent` also PROVISIONS the agent if it does not exist
# yet, which on a project that has never used notifications it may not.
$gcsAgent = ((Invoke-Gcloud storage service-agent --project=$ProjectId -Quiet) -join '').Trim()
if (-not $gcsAgent) { throw "Could not resolve the Cloud Storage service agent for $ProjectId" }
Add-ProjectRole -ProjectId $ProjectId -Member "serviceAccount:$gcsAgent" -Role "roles/pubsub.publisher"
Write-Ok "$gcsAgent -> roles/pubsub.publisher"

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
Write-Host "  Artifacts bucket  : gs://$artifactsBucket (14-day lifecycle, UBLA, PAP enforced)" -ForegroundColor White
Write-Host "  Scan queue bucket : gs://$scansBucket (agent ingest, Eventarc source)" -ForegroundColor White
Write-Host "  Firestore         : (default), Native mode, $Region" -ForegroundColor White
Write-Host "  Service accounts  : rinne-{web,physics,agent,reconstruction,eventarc}-sa" -ForegroundColor White
Write-Host ""
Write-Host "  Next:  pwsh .\infra\scripts\deploy-all.ps1" -ForegroundColor White
Write-Host ""
