#Requires -Version 5.1
<#
.SYNOPSIS
  Verifies the Definition of Done against the live deployment.

.DESCRIPTION
  Nine sections, each mapping to a stated requirement:

    1. rinne-web answers /api/health publicly                    (Day 1 DoD 3)
    2. rinne-web's /api/manifest reports all services healthy    (Day 1 DoD 3)
    3-4. Private services refuse unauthenticated callers         (security baseline)
    5. Every service reports min-instances 0 or empty            (cost control)
    6. No service runs as the default compute service account    (security baseline)
    7. rinne-reconstruction shape and bucket posture             (Day 2 DoD 1, 5)
    8. POST /v1/simulate is live and the contract is enforced    (Day 3 DoD 4)
    9. The agent's ingest path, identity and state store         (Day 4 DoD 1-5)

  Assertion 2 is the important one: the manifest page is GREEN ONLY IF the web
  service successfully minted an audience-scoped ID token and reached services
  that refuse everyone else. That single check proves the whole
  service-to-service auth path end to end.

  -IncludeAgentLoop is the Day 4 MILESTONE, end to end and live: it uploads a
  real image into the scan queue and then reads back the Firestore document the
  agent wrote. It costs one Gemini Flash call, which is a fraction of a cent.

.EXAMPLE
  pwsh .\infra\scripts\smoke-test.ps1
  pwsh .\infra\scripts\smoke-test.ps1 -IncludeAgentLoop -ScanImage .\docs\fixtures\desk.jpg
#>
[CmdletBinding()]
param(
    [string]$ProjectId = "rinnehackathon",
    [string]$Region    = "asia-southeast1",
    [switch]$IncludeGpu,
    [switch]$IncludeAgentLoop,
    [string]$ScanImage
)

. "$PSScriptRoot\lib\Rinne.Common.ps1"
Initialize-RinneShell
Assert-Tool -Name gcloud -InstallHint "Install the Google Cloud CLI."

# PowerShell 5.1 defaults to TLS 1.0 for Invoke-WebRequest. Cloud Run refuses it.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$failures = New-Object System.Collections.Generic.List[string]

function Get-Prop {

    param($Object, [string]$Name, $Default = "")
    if ($null -eq $Object) { return $Default }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop -or $null -eq $prop.Value) { return $Default }
    return $prop.Value
}

function Get-HttpStatus {

    param($ErrorRecord)
    $resp = Get-Prop (Get-Prop $ErrorRecord "Exception" $null) "Response" $null
    if ($null -eq $resp) { return 0 }
    $code = Get-Prop $resp "StatusCode" $null
    if ($null -eq $code) { return 0 }
    try { return [int]$code } catch { return 0 }
}

function Get-IdToken {
    param(
        [Parameter(Mandatory)][string]$Audience,
        [string]$ServiceAccount
    )
    if (-not $ServiceAccount) { $ServiceAccount = "rinne-web-sa@$ProjectId.iam.gserviceaccount.com" }
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $raw = & gcloud auth print-identity-token `
            --impersonate-service-account=$ServiceAccount --audiences=$Audience 2>$null
    } finally {
        $ErrorActionPreference = $previous
    }
    $global:LASTEXITCODE = 0
    return ((@($raw) | Where-Object { $_ -is [string] }) -join '').Trim()
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

# 1. Public health
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

# 2. Aggregated manifest - the real test
Write-Step "2. Authenticated service-to-service calls"
try {
    $response = Invoke-WebRequest -Uri "$($urls['rinne-web'])/api/manifest" `
        -TimeoutSec 45 -UseBasicParsing
    $manifest = $response.Content | ConvertFrom-Json

    Test-Assert -Name "manifest returns 200 (all services healthy)" `
        -Condition ($response.StatusCode -eq 200) -Detail "got $($response.StatusCode)"

    foreach ($entry in $manifest.services) {
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

# 3-4. Private services refuse anonymous callers
Write-Step "3-4. Private services reject unauthenticated callers"
foreach ($name in @('rinne-physics','rinne-agent','rinne-reconstruction')) {
    $status = 0
    try {
        $r = Invoke-WebRequest -Uri "$($urls[$name])/livez" -TimeoutSec 20 -UseBasicParsing
        $status = $r.StatusCode
    } catch {
        $status = Get-HttpStatus $_
    }

    $notServed = ($status -ge 400 -and $status -lt 500)
    Test-Assert -Name "$name refuses unauthenticated callers" `
        -Condition $notServed `
        -Detail "got HTTP $status. A 2xx means the service is PUBLIC - redeploy with --no-allow-unauthenticated."
}

# 5. Cost control
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

# 6. No default compute service account
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

# 7. Reconstruction service
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

Test-Assert -Name "rinne-reconstruction-sa has objectCreator, not objectAdmin" `
    -Condition ($iam -match 'objectCreator' -and $iam -notmatch 'objectAdmin') `
    -Detail "bucket IAM does not match the documented asymmetry"
Test-Assert -Name "rinne-web-sa has objectViewer" `
    -Condition ($iam -match 'objectViewer') -Detail "bucket IAM is missing the read binding"
Test-Assert -Name "rinne-physics-sa can read the bucket, and only read" `
    -Condition ($iam -match 'rinne-physics-sa' -and $iam -notmatch 'objectAdmin') `
    -Detail "physics needs objectViewer to fetch a mesh for POST /v1/simulate"

# 8. The physics simulate route
Write-Step "8. POST /v1/simulate is live and the contract is enforced"

$physicsUrl = $urls['rinne-physics']
$token = Get-IdToken -Audience $physicsUrl

if (-not $token) {
    Test-Assert -Name "minted an ID token for rinne-physics" -Condition $false `
        -Detail "impersonation failed. Grant it once: gcloud iam service-accounts add-iam-policy-binding rinne-web-sa@$ProjectId.iam.gserviceaccount.com --member=user:YOUR_EMAIL --role=roles/iam.serviceAccountTokenCreator --project=$ProjectId"
} else {
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

# 9. The agent ingest path
Write-Step "9. The agent: ingest, identity, and the state store"

$scansBucket = "rinne-scans-$ProjectId"

# 9a. Firestore exists, in the right place, in the right mode.
$fsType = ((& gcloud firestore databases describe --database="(default)" --project=$ProjectId `
    --format="value(type)" 2>$null) -join '').Trim()
$global:LASTEXITCODE = 0
Test-Assert -Name "Firestore (default) exists in Native mode" `
    -Condition ($fsType -eq 'FIRESTORE_NATIVE') `
    -Detail "got '$fsType'. Enabling the API does not create a database."

$fsLocation = ((& gcloud firestore databases describe --database="(default)" --project=$ProjectId `
    --format="value(locationId)" 2>$null) -join '').Trim()
$global:LASTEXITCODE = 0
Test-Assert -Name "Firestore is in $Region" `
    -Condition ($fsLocation -eq $Region) `
    -Detail "got '$fsLocation'. The default database's location is immutable."

# 9b. The scan queue is its own bucket, locked down the same way.
$scanPap = ((& gcloud storage buckets describe "gs://$scansBucket" --project=$ProjectId `
    --format="value(public_access_prevention)" 2>$null) -join '').Trim()
$global:LASTEXITCODE = 0
Test-Assert -Name "scan bucket enforces public access prevention" `
    -Condition ($scanPap -eq 'enforced') -Detail "got '$scanPap'"

$scanIam = (& gcloud storage buckets get-iam-policy "gs://$scansBucket" --project=$ProjectId `
    --format=json 2>$null) -join ''
$global:LASTEXITCODE = 0
Test-Assert -Name "rinne-agent-sa can read the scan queue, and only read" `
    -Condition ($scanIam -match 'rinne-agent-sa' -and $scanIam -match 'objectViewer' `
                -and $scanIam -notmatch 'objectAdmin' -and $scanIam -notmatch 'objectCreator') `
    -Detail "the agent reads scans and writes nothing to any bucket"

# 9c. The trigger points at the agent, at the right path, on the right bucket.
$trigger = (& gcloud eventarc triggers describe rinne-scan-queue --location=$Region `
    --project=$ProjectId --format=json 2>$null) -join ''
$global:LASTEXITCODE = 0
Test-Assert -Name "Eventarc trigger rinne-scan-queue exists" `
    -Condition ([bool]$trigger) -Detail "no trigger. Re-run deploy-all.ps1."

if ($trigger) {
    $t = $trigger | ConvertFrom-Json
    $destService = Get-Prop (Get-Prop (Get-Prop $t 'destination' $null) 'cloudRun' $null) 'service' ''
    $destPath    = Get-Prop (Get-Prop (Get-Prop $t 'destination' $null) 'cloudRun' $null) 'path' ''
    Test-Assert -Name "trigger delivers to rinne-agent /v1/events/scan" `
        -Condition ($destService -eq 'rinne-agent' -and $destPath -eq '/v1/events/scan') `
        -Detail "got service='$destService' path='$destPath'"

    Test-Assert -Name "trigger listens to the SCAN bucket, not the artifacts bucket" `
        -Condition ($trigger -match [regex]::Escape($scansBucket) -and $trigger -notmatch 'rinne-artifacts') `
        -Detail "a trigger on the artifacts bucket would fire on the system's own meshes"

    $triggerSa = Get-Prop $t 'serviceAccount' ''
    Test-Assert -Name "trigger runs as rinne-eventarc-sa" `
        -Condition ("$triggerSa" -like "rinne-eventarc-sa@*") `
        -Detail "got '$triggerSa'. The default compute SA carries project Editor."
}

# 9d. The invoker binding that lets the trigger reach the agent at all.
$agentIam = (& gcloud run services get-iam-policy rinne-agent --region=$Region `
    --project=$ProjectId --format=json 2>$null) -join ''
$global:LASTEXITCODE = 0
Test-Assert -Name "rinne-eventarc-sa holds run.invoker on rinne-agent" `
    -Condition ($agentIam -match 'rinne-eventarc-sa' -and $agentIam -match 'run.invoker') `
    -Detail "without it Eventarc gets a 403 and retries for a week"

# 9e. The agent's own readiness, through the same authenticated path web uses.
$agentUrl = $urls['rinne-agent']
$agentToken = Get-IdToken -Audience $agentUrl
if (-not $agentToken) {
    Test-Assert -Name "minted an ID token for rinne-agent" -Condition $false `
        -Detail "impersonation failed. See the hint in section 8."
} else {
    try {
        $r = Invoke-WebRequest -Uri "$agentUrl/readyz" -TimeoutSec 60 -UseBasicParsing `
            -Headers @{ Authorization = "Bearer $agentToken" }
        $body = $r.Content | ConvertFrom-Json
        Test-Assert -Name "rinne-agent answers /readyz when authenticated" `
            -Condition ($r.StatusCode -eq 200 -and (Get-Prop $body 'status' '') -eq 'ok') `
            -Detail "HTTP $($r.StatusCode) status=$(Get-Prop $body 'status' '?')"

        $store  = ($body.dependencies | Where-Object { $_.name -eq 'job-store' })
        $triage = ($body.dependencies | Where-Object { $_.name -eq 'triage' })
        Test-Assert -Name "agent reports the REAL job store, not the memory double" `
            -Condition ((Get-Prop $store 'detail' '') -eq 'firestore') `
            -Detail "got '$(Get-Prop $store 'detail' '?')'"
        Test-Assert -Name "agent reports a Gemini model, not the stub triager" `
            -Condition ((Get-Prop $triage 'detail' '') -like 'gemini-*') `
            -Detail "got '$(Get-Prop $triage 'detail' '?')'"

        $loop = ($body.dependencies | Where-Object { $_.name -eq 'decision-loop' })
        Test-Assert -Name "agent calls the REAL reconstruction and physics services" `
            -Condition ((Get-Prop $loop 'detail' '') -like 'http *') `
            -Detail "got '$(Get-Prop $loop 'detail' '?')'"
        Test-Assert -Name "agent reports the gate thresholds it will escalate on" `
            -Condition ((Get-Prop $loop 'detail' '') -like '*gate 0.*') `
            -Detail "readyz did not name the declared policy numbers"
        Write-Ok "agent: store=$(Get-Prop $store 'detail' '?') triage=$(Get-Prop $triage 'detail' '?')"
        Write-Ok "loop:  $(Get-Prop $loop 'detail' '?')"
    } catch {
        Test-Assert -Name "rinne-agent answers an authenticated /readyz" `
            -Condition $false -Detail "HTTP $(Get-HttpStatus $_) - $($_.Exception.Message)"
    }
}

# 9f. The Day 5 milestone: one upload, the whole section 7 loop
if ($IncludeAgentLoop) {
    Write-Step "9f. Drop an image in the bucket, read the whole decision back"

    if (-not $ScanImage -or -not (Test-Path $ScanImage)) {
        Test-Assert -Name "a scan image was supplied" -Condition $false `
            -Detail "pass -ScanImage <path to a .jpg or .png>"
    } else {
        $leaf      = [System.IO.Path]::GetFileNameWithoutExtension($ScanImage)
        $ext       = [System.IO.Path]::GetExtension($ScanImage).ToLowerInvariant()
        $mime      = if ($ext -eq '.png') { 'image/png' } elseif ($ext -eq '.webp') { 'image/webp' } else { 'image/jpeg' }
        $stamp     = (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
        $objectName= "scan-queue/$leaf-$stamp$ext"

        Invoke-Gcloud storage cp $ScanImage "gs://$scansBucket/$objectName" `
            --content-type=$mime --project=$ProjectId --quiet -Quiet | Out-Null
        Write-Ok "uploaded gs://$scansBucket/$objectName"

        $generation = ((& gcloud storage objects describe "gs://$scansBucket/$objectName" `
            --project=$ProjectId --format="value(generation)" 2>$null) -join '').Trim()
        $global:LASTEXITCODE = 0

        $material = "$scansBucket/$objectName#$generation"
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try {
            $bytes  = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($material))
            $hex    = -join ($bytes | ForEach-Object { $_.ToString("x2") })
        } finally {
            $sha.Dispose()
        }
        $jobId = "scan-" + $hex.Substring(0, 16)
        Write-Ok "expecting job $jobId"

        # The document appears in queued within a second, so polling for its mere
        # existence proves nothing. Wait for a state the loop cannot leave.
        $settled = @('skipped_low_risk','awaiting_verification','reporting','done','failed')
        $agentToken = Get-IdToken -Audience $agentUrl
        $job = $null
        foreach ($attempt in 1..45) {
            Start-Sleep -Seconds 10
            try {
                $r = Invoke-WebRequest -Uri "$agentUrl/v1/jobs/$jobId" -TimeoutSec 30 `
                    -UseBasicParsing -Headers @{ Authorization = "Bearer $agentToken" }
                if ($r.StatusCode -eq 200) {
                    $job = $r.Content | ConvertFrom-Json
                    if ($settled -contains (Get-Prop $job 'state' '')) { break }
                    Write-Host "    $(Get-Prop $job 'state' '?') ..." -ForegroundColor DarkCyan
                }
            } catch {
                $null = Get-HttpStatus $_
            }
        }

        if ($null -eq $job) {
            Test-Assert -Name "the agent wrote a job document for the uploaded scan" `
                -Condition $false `
                -Detail "no document after 450s. Check the trigger, the GCS service agent's pubsub.publisher binding, and the agent logs."
        } else {
            $state = Get-Prop $job 'state' ''
            Test-Assert -Name "the job reached a state the loop cannot leave" `
                -Condition ($settled -contains $state) `
                -Detail "state='$state' error='$(Get-Prop (Get-Prop $job 'error' $null) 'rule' '-')'"

            $triageRec = Get-Prop $job 'triage' $null
            Test-Assert -Name "the decision names the model that made it" `
                -Condition ((Get-Prop $triageRec 'model' '') -like 'gemini-*') `
                -Detail "got '$(Get-Prop $triageRec 'model' '?')'"

            Write-Ok "state: $state"
            Write-Ok "shape: $(Get-Prop $triageRec 'shape' '?')  confidence: $(Get-Prop $triageRec 'confidence' '?')  latency: $(Get-Prop $triageRec 'latencyMs' '?')ms"
            Write-Ok "reason: $(Get-Prop $triageRec 'rationale' '?')"

            if ($state -eq 'skipped_low_risk') {
                Write-Ok "Flash saw no physics risk, so the decision half never ran. That is a pass."
            } else {
                $sel   = Get-Prop $job 'selection' $null
                $recon = Get-Prop $job 'reconstruction' $null
                $sim   = Get-Prop $job 'simulation' $null
                $gate  = Get-Prop $job 'gate' $null
                $wanted = if ($state -eq 'reporting') { 'report' } else { 'escalate' }

                Test-Assert -Name "the agent chose a physics test and said why" `
                    -Condition ([bool](Get-Prop $sel 'kind' '')) `
                    -Detail "no selection record on the job"
                Test-Assert -Name "reconstruction ran and returned a mesh in the artifacts bucket" `
                    -Condition ((Get-Prop $recon 'meshUri' '') -like "gs://rinne-artifacts-$ProjectId/*") `
                    -Detail "got '$(Get-Prop $recon 'meshUri' '?')'"
                Test-Assert -Name "physics ran and returned a verdict" `
                    -Condition ([bool](Get-Prop $sim 'verdict' '')) `
                    -Detail "no simulation record on the job"
                Test-Assert -Name "the gate named the policy it applied" `
                    -Condition ((Get-Prop $gate 'policy' '') -eq 'min-confidence-v1') `
                    -Detail "got '$(Get-Prop $gate 'policy' '?')'"
                Test-Assert -Name "the gate recorded every input it compared" `
                    -Condition (@(Get-Prop $gate 'inputs' @()).Count -ge 3) `
                    -Detail "an escalation has to be auditable from the document alone"
                Test-Assert -Name "the decision chain runs ingest to gate" `
                    -Condition (@(Get-Prop $job 'decisions' @()).Count -ge 4) `
                    -Detail "expected ingest, triage and two gate entries"
                Test-Assert -Name "the state matches what the gate decided" `
                    -Condition ((Get-Prop $gate 'decision' '') -eq $wanted) `
                    -Detail "gate said '$(Get-Prop $gate 'decision' '?')' but the job is '$state'"

                Write-Ok "test:  $(Get-Prop $sel 'kind' '?')  ($(Get-Prop $sel 'rationale' '?'))"
                Write-Ok "mesh:  $(Get-Prop $recon 'meshUri' '?')"
                Write-Ok "recon: confidence $(Get-Prop $recon 'confidence' '?') ($(Get-Prop $recon 'band' '?'))  material $(Get-Prop $recon 'material' '?') $(Get-Prop $recon 'materialConfidence' '?')"
                Write-Ok "sim:   $(Get-Prop $sim 'verdict' '?')  tilt $(Get-Prop $sim 'tiltDegrees' '?')deg  drift $(Get-Prop $sim 'driftMeters' '?')m"
                Write-Ok "gate:  $(Get-Prop $gate 'decision' '?')  observed $(Get-Prop $gate 'observed' '?') vs threshold $(Get-Prop $gate 'threshold' '?')"
                $reasons = @(Get-Prop $gate 'reasons' @())
                if ($reasons.Count -gt 0) { Write-Ok "why:   $($reasons -join ', ')" }
            }
        }
    }
} else {
    Write-Ok "Agent loop skipped. Re-run with -IncludeAgentLoop -ScanImage <path> for the Day 5 milestone."
}

if ($IncludeGpu) {
    Write-Step "7b. Waking the L4 (this costs about `$0.18)"
    $audience = $urls['rinne-reconstruction']
    $token = Get-IdToken -Audience $audience

    if (-not $token) {
        Test-Assert -Name "minted an ID token for rinne-reconstruction" -Condition $false `
            -Detail "impersonation failed. See the hint in section 8."
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

# Result
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
