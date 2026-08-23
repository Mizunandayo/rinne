#Requires -Version 5.1
<#
.SYNOPSIS
  Verifies the Day 1 Definition of Done against the live deployment.

.DESCRIPTION
  Six assertions, each mapping to a stated requirement:

    1. rinne-web answers /api/health publicly                    (DoD 3)
    2. rinne-web's /api/manifest reports all three healthy       (DoD 3)
    3. rinne-physics returns 403 to an unauthenticated caller    (security baseline)
    4. rinne-agent   returns 403 to an unauthenticated caller    (security baseline)
    5. Every service reports min-instances 0 or empty            (cost control)
    6. No service runs as the default compute service account    (security baseline)

  Assertion 2 is the important one: the manifest page is GREEN ONLY IF the web
  service successfully minted an audience-scoped ID token and reached two
  services that refuse everyone else. That single check proves the whole
  service-to-service auth path end to end.

.EXAMPLE
  pwsh .\infra\scripts\smoke-test.ps1
#>
[CmdletBinding()]
param(
    [string]$ProjectId = "rinnehackathon",
    [string]$Region    = "asia-southeast1"
)

. "$PSScriptRoot\lib\Rinne.Common.ps1"
Initialize-RinneShell
Assert-Tool -Name gcloud -InstallHint "Install the Google Cloud CLI."

# PowerShell 5.1 defaults to TLS 1.0 for Invoke-WebRequest. Cloud Run refuses it.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$failures = New-Object System.Collections.Generic.List[string]

function Test-Assert {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][bool]$Condition,
        [string]$Detail = ""
    )
    if ($Condition) {
        Write-Host ("  PASS  {0}" -f $Name) -ForegroundColor Green
    } else {
        Write-Host ("  FAIL  {0}  {1}" -f $Name, $Detail) -ForegroundColor Red
        $script:failures.Add($Name)
    }
}

Write-Step "Resolving service URLs"
$urls = @{}
foreach ($name in @('rinne-web','rinne-physics','rinne-agent')) {
    $url = ((& gcloud run services describe $name --region=$Region --project=$ProjectId `
        --format="value(status.url)" 2>$null) -join '').Trim()
    if ($LASTEXITCODE -ne 0 -or -not $url) {
        $global:LASTEXITCODE = 0
        throw "$name is not deployed in $Region. Run deploy-all.ps1 first."
    }
    $global:LASTEXITCODE = 0
    $urls[$name] = $url
    Write-Ok "$name -> $url"
}

# -- 1. Public health -------------------------------------------------
Write-Step "1. rinne-web answers publicly"
try {
    $health = Invoke-RestMethod -Uri "$($urls['rinne-web'])/api/health" -TimeoutSec 30
    Test-Assert -Name "web /api/health returns a HealthReport" `
        -Condition ($health.service -eq 'web' -and $health.status -eq 'ok') `
        -Detail "got service=$($health.service) status=$($health.status)"
    Test-Assert -Name "web reports the expected region" `
        -Condition ($health.region -eq $Region) -Detail "got $($health.region)"
} catch {
    Test-Assert -Name "web /api/health reachable" -Condition $false -Detail $_.Exception.Message
}

# -- 2. Aggregated manifest - the real test ---------------------------
Write-Step "2. Authenticated service-to-service calls"
try {
    $response = Invoke-WebRequest -Uri "$($urls['rinne-web'])/api/manifest" `
        -TimeoutSec 45 -UseBasicParsing
    $manifest = $response.Content | ConvertFrom-Json

    Test-Assert -Name "manifest returns 200 (all services healthy)" `
        -Condition ($response.StatusCode -eq 200) -Detail "got $($response.StatusCode)"

    foreach ($entry in $manifest.services) {
        Test-Assert -Name "$($entry.service) reachable and ok" `
            -Condition ($entry.reachable -eq $true -and $entry.status -eq 'ok') `
            -Detail "reachable=$($entry.reachable) status=$($entry.status) reason=$($entry.reason)"
    }
} catch {
    $status = $_.Exception.Response.StatusCode.value__
    Test-Assert -Name "manifest reports all services healthy" -Condition $false `
        -Detail "HTTP $status - $($_.Exception.Message)"
}

# -- 3-4. Private services refuse anonymous callers -------------------
Write-Step "3-4. Private services reject unauthenticated callers"
foreach ($name in @('rinne-physics','rinne-agent')) {
    $status = 0
    try {
        $r = Invoke-WebRequest -Uri "$($urls[$name])/healthz" -TimeoutSec 20 -UseBasicParsing
        $status = $r.StatusCode
    } catch {
        $status = $_.Exception.Response.StatusCode.value__
    }
    # 403 is correct. 200 means the service is PUBLIC - a live credit-burn risk
    # and a security failure, not a cosmetic one.
    Test-Assert -Name "$name returns 403 without a token" `
        -Condition ($status -eq 403) `
        -Detail "got HTTP $status. 200 means the service is PUBLIC. Redeploy with --no-allow-unauthenticated."
}

# -- 5. Cost control --------------------------------------------------
Write-Step "5. Every service scales to zero"
$rows = & gcloud run services list --region=$Region --project=$ProjectId `
    --format="csv[no-heading](metadata.name,spec.template.metadata.annotations['autoscaling.knative.dev/minScale'])" 2>$null
$global:LASTEXITCODE = 0

foreach ($row in ($rows -split "`n" | Where-Object { $_.Trim() })) {
    $parts = $row -split ','
    $name  = $parts[0].Trim()
    $min   = if ($parts.Count -gt 1) { $parts[1].Trim() } else { '' }
    Test-Assert -Name "$name min-instances is 0" `
        -Condition ($min -eq '' -or $min -eq '0') `
        -Detail "min-instances=$min is actively burning credit. Revert it today."
}

# -- 6. No default compute service account ----------------------------
Write-Step "6. No service uses the default compute service account"
$defaultSa = ""
$projectNumber = ((& gcloud projects describe $ProjectId --format="value(projectNumber)" 2>$null) -join '').Trim()
$global:LASTEXITCODE = 0
if ($projectNumber) { $defaultSa = "$projectNumber-compute@developer.gserviceaccount.com" }

foreach ($name in @('rinne-web','rinne-physics','rinne-agent')) {
    $sa = ((& gcloud run services describe $name --region=$Region --project=$ProjectId `
        --format="value(spec.template.spec.serviceAccountName)" 2>$null) -join '').Trim()
    $global:LASTEXITCODE = 0
    Test-Assert -Name "$name uses a dedicated service account" `
        -Condition ($sa -ne $defaultSa -and $sa -like "rinne-*") `
        -Detail "got '$sa'. The default compute SA carries project Editor."
}

# -- Result -----------------------------------------------------------
Write-Host ""
if ($failures.Count -eq 0) {
    Write-Host "  Day 1 Definition of Done: ALL CHECKS PASSED" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Manifest page: $($urls['rinne-web'])/manifest" -ForegroundColor White
    Write-Host ""
    exit 0
}

Write-Host "  $($failures.Count) check(s) failed:" -ForegroundColor Red
$failures | ForEach-Object { Write-Host "    - $_" -ForegroundColor Red }
Write-Host ""
exit 1
