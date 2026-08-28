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
    [string]$Region    = "asia-southeast1",
    # OFF by default. Everything else here is free; this one wakes the L4 for
    # roughly 90 seconds and $0.18. Run it before a recording, not routinely.
    [switch]$IncludeGpu
)

. "$PSScriptRoot\lib\Rinne.Common.ps1"
Initialize-RinneShell
Assert-Tool -Name gcloud -InstallHint "Install the Google Cloud CLI."

# PowerShell 5.1 defaults to TLS 1.0 for Invoke-WebRequest. Cloud Run refuses it.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$failures = New-Object System.Collections.Generic.List[string]

function Get-Prop {
    <#
      Safely read an OPTIONAL property. Set-StrictMode -Version Latest turns a
      missing property into a terminating error, and several fields in
      /api/manifest are legitimately absent - `reason` only exists when a
      service is UNREACHABLE. Reading it on a healthy service killed this script.
    #>
    param($Object, [string]$Name, $Default = "")
    if ($null -eq $Object) { return $Default }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop -or $null -eq $prop.Value) { return $Default }
    return $prop.Value
}

function Get-HttpStatus {
    <#
      Extract an HTTP status from a caught error WITHOUT assuming its shape.
      Only a WebException carries .Response; a timeout, a DNS failure, or - as
      happened here - a StrictMode PropertyNotFoundException does not. Reaching
      blindly for .Response inside a catch turns a small failure into an
      uncaught one that hides the original cause.
    #>
    param($ErrorRecord)
    $resp = Get-Prop (Get-Prop $ErrorRecord "Exception" $null) "Response" $null
    if ($null -eq $resp) { return 0 }
    $code = Get-Prop $resp "StatusCode" $null
    if ($null -eq $code) { return 0 }
    try { return [int]$code } catch { return 0 }
}

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
foreach ($name in @('rinne-web','rinne-physics','rinne-agent','rinne-reconstruction')) {
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
        # A cold service was deliberately not probed, so it is neither healthy
        # nor broken. Section 7 checks its shape; -IncludeGpu wakes it.
        if ((Get-Prop $entry "probed" $true) -eq $false) {
            Write-Ok "$(Get-Prop $entry 'service' '?') not probed (cold, by design)"
            continue
        }
        $reason = Get-Prop $entry "reason" "-"
        Test-Assert -Name "$(Get-Prop $entry 'service' '?') reachable and ok" `
            -Condition ((Get-Prop $entry "reachable" $false) -eq $true -and (Get-Prop $entry "status" "") -eq 'ok') `
            -Detail "reachable=$(Get-Prop $entry 'reachable' $false) status=$(Get-Prop $entry 'status' '?') reason=$reason"
    }
} catch {
    $status = Get-HttpStatus $_
    Test-Assert -Name "manifest reports all services healthy" -Condition $false `
        -Detail "HTTP $status - $($_.Exception.Message)"
}

# -- 3-4. Private services refuse anonymous callers -------------------
Write-Step "3-4. Private services reject unauthenticated callers"
foreach ($name in @('rinne-physics','rinne-agent','rinne-reconstruction')) {
    $status = 0
    try {
        $r = Invoke-WebRequest -Uri "$($urls[$name])/livez" -TimeoutSec 20 -UseBasicParsing
        $status = $r.StatusCode
    } catch {
        $status = Get-HttpStatus $_
    }
    # WHAT MATTERS IS THAT IT IS NOT SERVED, not the precise status code.
    # Current Cloud Run answers an unauthenticated request to a private service
    # with 404, not 403 - it declines to confirm the service even exists, which
    # is the better behaviour. Older releases answered 403. Asserting one exact
    # code makes this check break on a platform change that is not a regression.
    #
    # A 2xx is the only genuine failure here: it means the service is PUBLIC,
    # which is a security hole AND an open door onto the credit balance.
    $notServed = ($status -ge 400 -and $status -lt 500)
    Test-Assert -Name "$name refuses unauthenticated callers" `
        -Condition $notServed `
        -Detail "got HTTP $status. A 2xx means the service is PUBLIC - redeploy with --no-allow-unauthenticated."
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

foreach ($name in @('rinne-web','rinne-physics','rinne-agent','rinne-reconstruction')) {
    $sa = ((& gcloud run services describe $name --region=$Region --project=$ProjectId `
        --format="value(spec.template.spec.serviceAccountName)" 2>$null) -join '').Trim()
    $global:LASTEXITCODE = 0
    Test-Assert -Name "$name uses a dedicated service account" `
        -Condition ($sa -ne $defaultSa -and $sa -like "rinne-*") `
        -Detail "got '$sa'. The default compute SA carries project Editor."
}

# -- 7. Reconstruction service ----------------------------------------
Write-Step "7. rinne-reconstruction shape and storage"

$reconRaw = & gcloud run services describe rinne-reconstruction --region=$Region --project=$ProjectId `
    --format="value(spec.template.spec.containers[0].resources.limits)" 2>$null
$global:LASTEXITCODE = 0
Test-Assert -Name "rinne-reconstruction requests an nvidia-l4" `
    -Condition ("$reconRaw" -match 'nvidia.com/gpu') `
    -Detail "resource limits read '$reconRaw'. No GPU attached means the L4 flags were dropped."

$reconMax = ((& gcloud run services describe rinne-reconstruction --region=$Region --project=$ProjectId `
    --format="value(spec.template.metadata.annotations['autoscaling.knative.dev/maxScale'])" 2>$null) -join '').Trim()
$global:LASTEXITCODE = 0
# The approved quota is exactly 1. A higher value deploys and then fails at scale.
Test-Assert -Name "rinne-reconstruction max-instances is 1" `
    -Condition ($reconMax -eq '1') -Detail "got '$reconMax'; approved L4 quota is 1"

$bucket = "rinne-artifacts-$ProjectId"
$pap = ((& gcloud storage buckets describe "gs://$bucket" --project=$ProjectId `
    --format="value(public_access_prevention)" 2>$null) -join '').Trim()
$global:LASTEXITCODE = 0
Test-Assert -Name "artifacts bucket enforces public access prevention" `
    -Condition ($pap -eq 'enforced') -Detail "got '$pap'"

$ubla = ((& gcloud storage buckets describe "gs://$bucket" --project=$ProjectId `
    --format="value(uniform_bucket_level_access)" 2>$null) -join '').Trim()
$global:LASTEXITCODE = 0
Test-Assert -Name "artifacts bucket uses uniform bucket-level access" `
    -Condition ($ubla -eq 'True') -Detail "got '$ubla'"

$iam = (& gcloud storage buckets get-iam-policy "gs://$bucket" --project=$ProjectId `
    --format=json 2>$null) -join ''
$global:LASTEXITCODE = 0
# Asymmetric on purpose: reconstruction writes and never reads, web reads and
# never writes. objectAdmin on either one is the failure this catches.
Test-Assert -Name "rinne-reconstruction-sa has objectCreator, not objectAdmin" `
    -Condition ($iam -match 'objectCreator' -and $iam -notmatch 'objectAdmin') `
    -Detail "bucket IAM does not match the documented asymmetry"
Test-Assert -Name "rinne-web-sa has objectViewer" `
    -Condition ($iam -match 'objectViewer') -Detail "bucket IAM is missing the read binding"
Test-Assert -Name "rinne-physics-sa can read the bucket, and only read" `
    -Condition ($iam -match 'rinne-physics-sa' -and $iam -notmatch 'objectAdmin') `
    -Detail "physics needs objectViewer to fetch a mesh for POST /v1/simulate"

# -- 8. The physics simulate route ------------------------------------
# CPU only. Waking physics costs nothing measurable, unlike the L4.
Write-Step "8. POST /v1/simulate is live and the contract is enforced"

$physicsUrl = $urls['rinne-physics']
$sa = "rinne-web-sa@$ProjectId.iam.gserviceaccount.com"
$previous = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $raw = & gcloud auth print-identity-token `
        --impersonate-service-account=$sa --audiences=$physicsUrl 2>$null
} finally {
    $ErrorActionPreference = $previous
}
$global:LASTEXITCODE = 0
$token = ((@($raw) | Where-Object { $_ -is [string] }) -join '').Trim()

if (-not $token) {
    Test-Assert -Name "minted an ID token for rinne-physics" -Condition $false `
        -Detail "impersonation failed. Grant it once: gcloud iam service-accounts add-iam-policy-binding $sa --member=user:YOUR_EMAIL --role=roles/iam.serviceAccountTokenCreator --project=$ProjectId"
} else {
    # A scene whose mesh uri points at the metadata server. The contract must
    # refuse it BEFORE the handler runs, so this asserts the SSRF control in
    # production rather than only in a unit test.
    $hostile = @{
        schemaVersion = 1
        sceneId       = "smoke-000001"
        units         = @{ length = "m"; mass = "kg" }
        gravity       = @{ x = 0; y = -9.81; z = 0 }
        ground        = @{ friction = 0.6; restitution = 0.1 }
        body          = @{
            mesh               = @{ uri = "http://metadata.google.internal/computeMetadata/v1/"; format = "glb" }
            massKilograms      = 2.4
            friction           = 0.55
            restitution        = 0.05
            initialTranslation = @{ x = 0; y = 0.02; z = 0 }
        }
        test          = @{ kind = "tip"; pushHeightRatio = 0.9; forceNewtons = 18; directionDegrees = 0 }
        solver        = @{ timestepSeconds = 0.0166667; maxSteps = 900; seed = 42 }
    } | ConvertTo-Json -Depth 6 -Compress

    $status = 0
    try {
        $r = Invoke-WebRequest -Uri "$physicsUrl/v1/simulate" -Method POST -TimeoutSec 60 `
            -UseBasicParsing -ContentType "application/json" -Body $hostile `
            -Headers @{ Authorization = "Bearer $token" }
        $status = $r.StatusCode
    } catch {
        $status = Get-HttpStatus $_
    }
    Test-Assert -Name "/v1/simulate REFUSES a non-gs:// mesh uri" `
        -Condition ($status -eq 400) -Detail "expected 400, got $status"
}

if ($IncludeGpu) {
    Write-Step "7b. Waking the L4 (this costs about `$0.18)"
    $audience = $urls['rinne-reconstruction']
    # gcloud is authenticated as a USER account here, and --audiences requires a
    # service account, so impersonate the identity web actually uses.
    $sa = "rinne-web-sa@$ProjectId.iam.gserviceaccount.com"
    # Impersonation prints a WARNING to stderr, and 5.1 turns redirected native
    # stderr into ErrorRecords that $ErrorActionPreference=Stop makes terminating.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $raw = & gcloud auth print-identity-token `
            --impersonate-service-account=$sa --audiences=$audience 2>$null
    } finally {
        $ErrorActionPreference = $previous
    }
    $global:LASTEXITCODE = 0
    $token = ((@($raw) | Where-Object { $_ -is [string] }) -join '').Trim()

    if (-not $token) {
        Test-Assert -Name "minted an ID token for rinne-reconstruction" -Condition $false `
            -Detail "impersonation failed. Grant it once: gcloud iam service-accounts add-iam-policy-binding $sa --member=user:YOUR_EMAIL --role=roles/iam.serviceAccountTokenCreator --project=$ProjectId"
    } else {
        try {
            $r = Invoke-WebRequest -Uri "$audience/readyz" -TimeoutSec 240 -UseBasicParsing `
                -Headers @{ Authorization = "Bearer $token" }
            $body = $r.Content | ConvertFrom-Json
            Test-Assert -Name "rinne-reconstruction answers /readyz when authenticated" `
                -Condition ($r.StatusCode -eq 200 -and (Get-Prop $body 'status' '') -eq 'ok') `
                -Detail "HTTP $($r.StatusCode) status=$(Get-Prop $body 'status' '?')"
            $pipeline = ($body.dependencies | Where-Object { $_.name -eq 'pipeline' })
            Test-Assert -Name "reconstruction reports which pipeline is loaded" `
                -Condition ([bool](Get-Prop $pipeline 'detail' '')) `
                -Detail "readyz did not report a pipeline dependency"
            Write-Ok "pipeline: $(Get-Prop $pipeline 'detail' 'unknown')"
        } catch {
            Test-Assert -Name "rinne-reconstruction answers an authenticated /readyz" `
                -Condition $false -Detail "HTTP $(Get-HttpStatus $_) - $($_.Exception.Message)"
        }
    }
} else {
    Write-Ok "GPU wake skipped. Re-run with -IncludeGpu before a recording."
}

# -- Result -----------------------------------------------------------
Write-Host ""
if ($failures.Count -eq 0) {
    Write-Host "  Definition of Done: ALL CHECKS PASSED" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Manifest page: $($urls['rinne-web'])/manifest" -ForegroundColor White
    Write-Host ""
    exit 0
}

Write-Host "  $($failures.Count) check(s) failed:" -ForegroundColor Red
$failures | ForEach-Object { Write-Host "    - $_" -ForegroundColor Red }
Write-Host ""
exit 1
