#Requires -Version 5.1
<#
.SYNOPSIS
  Workload Identity Federation so GitHub Actions can deploy without any key.

.DESCRIPTION
  Leaked service-account keys are the single most common GCP compromise vector,
  and a key in a GitHub secret is a long-lived credential with no expiry that
  every workflow run can read. WIF replaces it with a short-lived token,
  cryptographically bound to one repository.

  THE ATTRIBUTE CONDITION IS THE WHOLE SECURITY CONTROL. Without it, any GitHub
  repository on the planet can present an OIDC token to this pool and
  impersonate the deployer. gcloud now refuses to create a provider that maps
  assertion.repository without one; that refusal is a feature.

  Run once. Idempotent.

.EXAMPLE
  pwsh .\infra\scripts\bootstrap-wif.ps1
#>
[CmdletBinding()]
param(
    [string]$ProjectId     = "rinnehackathon",
    [string]$ProjectNumber = "900016126232",
    [string]$Region        = "asia-southeast1",
    [string]$GitHubOwner   = "Mizunandayo",
    [string]$GitHubRepo    = "rinne",
    [string]$PoolId        = "github",
    [string]$ProviderId    = "github-oidc",
    [string]$DeployerSa    = "rinne-deployer"
)

. "$PSScriptRoot\lib\Rinne.Common.ps1"
Initialize-RinneShell
Assert-Tool -Name gcloud -InstallHint "Install the Google Cloud CLI."
Assert-Project -ProjectId $ProjectId -ExpectedNumber $ProjectNumber

$fullRepo     = "$GitHubOwner/$GitHubRepo"
$deployerMail = "$DeployerSa@$ProjectId.iam.gserviceaccount.com"

Write-Step "Workload identity pool"
if (Test-GcloudResource iam workload-identity-pools describe $PoolId `
        --location=global --project=$ProjectId --format="value(name)") {
    Write-Skip "pool '$PoolId'"
} else {
    Invoke-Gcloud iam workload-identity-pools create $PoolId `
        --location=global --project=$ProjectId `
        --display-name="GitHub Actions" `
        --description="Keyless CI for $fullRepo" --quiet | Out-Null
    Write-Ok "Created pool '$PoolId'"
}

Write-Step "OIDC provider (repository-scoped)"
if (Test-GcloudResource iam workload-identity-pools providers describe $ProviderId `
        --location=global --workload-identity-pool=$PoolId `
        --project=$ProjectId --format="value(name)") {
    Write-Skip "provider '$ProviderId'"
} else {
    Invoke-Gcloud iam workload-identity-pools providers create-oidc $ProviderId `
        --location=global `
        --workload-identity-pool=$PoolId `
        --project=$ProjectId `
        --display-name="GitHub OIDC" `
        --issuer-uri="https://token.actions.githubusercontent.com" `
        --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner,attribute.ref=assertion.ref" `
        --attribute-condition="assertion.repository_owner == '$GitHubOwner' && assertion.repository == '$fullRepo'" `
        --quiet | Out-Null
    Write-Ok "Created provider, restricted to $fullRepo"
}

Write-Step "Deployer service account"
if (Test-GcloudResource iam service-accounts describe $deployerMail --project=$ProjectId --format="value(email)") {
    Write-Skip "service account '$DeployerSa'"
} else {
    Invoke-Gcloud iam service-accounts create $DeployerSa `
        --display-name="Rinne CI deployer (WIF, no key)" `
        --project=$ProjectId --quiet | Out-Null
    Write-Ok "Created $deployerMail"
}

Write-Step "Deployer roles"
foreach ($role in @('roles/run.admin','roles/artifactregistry.writer')) {
    Invoke-Gcloud projects add-iam-policy-binding $ProjectId `
        --member="serviceAccount:$deployerMail" --role=$role `
        --condition=None --quiet -Quiet | Out-Null
    Write-Ok "  $role"
}


Write-Step "Act-as permission, scoped to the four runtime service accounts"
foreach ($runtime in @('rinne-web-sa','rinne-physics-sa','rinne-agent-sa','rinne-reconstruction-sa')) {
    $mail = "$runtime@$ProjectId.iam.gserviceaccount.com"
    if (-not (Test-GcloudResource iam service-accounts describe $mail --project=$ProjectId --format="value(email)")) {
        Write-Warning "  $runtime does not exist yet. Run bootstrap-gcp.ps1 first."
        continue
    }
    Invoke-Gcloud iam service-accounts add-iam-policy-binding $mail `
        --member="serviceAccount:$deployerMail" `
        --role="roles/iam.serviceAccountUser" `
        --project=$ProjectId --quiet -Quiet | Out-Null
    Write-Ok "  deployer may act as $runtime"
}

Write-Step "Binding the repository to the deployer"
$principal = "principalSet://iam.googleapis.com/projects/$ProjectNumber/locations/global/workloadIdentityPools/$PoolId/attribute.repository/$fullRepo"
Invoke-Gcloud iam service-accounts add-iam-policy-binding $deployerMail `
    --project=$ProjectId `
    --role="roles/iam.workloadIdentityUser" `
    --member=$principal --quiet -Quiet | Out-Null
Write-Ok "Only $fullRepo may impersonate the deployer"

$provider = "projects/$ProjectNumber/locations/global/workloadIdentityPools/$PoolId/providers/$ProviderId"

Write-Step "Add these as GitHub repository VARIABLES (not secrets - neither is sensitive)"
Write-Host ""
Write-Host "  GCP_WORKLOAD_IDENTITY_PROVIDER = $provider" -ForegroundColor White
Write-Host "  GCP_DEPLOYER_SERVICE_ACCOUNT   = $deployerMail" -ForegroundColor White
Write-Host ""
Write-Host "  gh variable set GCP_WORKLOAD_IDENTITY_PROVIDER --body `"$provider`"" -ForegroundColor DarkGray
Write-Host "  gh variable set GCP_DEPLOYER_SERVICE_ACCOUNT   --body `"$deployerMail`"" -ForegroundColor DarkGray
Write-Host ""
