#Requires -Version 5.1
<#
.SYNOPSIS
  Builds, pushes, and deploys all four Rinne services to Cloud Run, then wires
  the scan-queue bucket to the agent through Eventarc.

.DESCRIPTION
  DEPLOY ORDER IS NOT ARBITRARY: physics -> reconstruction -> agent -> web.
  Web's PHYSICS_SERVICE_URL, AGENT_SERVICE_URL and RECONSTRUCTION_SERVICE_URL
  are outputs of the first three deploys, so it must go last.

  NETWORK MODEL, stated because it is the single most common way this goes
  wrong: physics, reconstruction and agent deploy --no-allow-unauthenticated
  with --ingress=all. Ingress stays "all" ON PURPOSE. Without a VPC connector a
  Cloud Run -> Cloud Run call egresses over the public path, so --ingress=internal
  BLOCKS it and produces a 403 indistinguishable from an IAM failure. IAM is
  the real control: rinne-web-sa gets roles/run.invoker on those services and
  rinne-eventarc-sa gets it on the agent alone.

  THE EVENTARC TRIGGER IS CREATED HERE, NOT IN BOOTSTRAP. It names a Cloud Run
  service and a request path, so it cannot exist before the service does.

.PARAMETER Tag
  Image tag. Defaults to the short git SHA, or a UTC timestamp outside a repo.

.EXAMPLE
  pwsh .\infra\scripts\deploy-all.ps1
  pwsh .\infra\scripts\deploy-all.ps1 -Services physics,agent
  pwsh .\infra\scripts\deploy-all.ps1 -UseCloudBuild
#>
[CmdletBinding()]
param(
    [string]$ProjectId     = "rinnehackathon",
    [string]$ProjectNumber = "900016126232",
    [string]$Region        = "asia-southeast1",
    [string]$RepoName      = "rinne",
    [string]$Tag,
    [ValidateSet('physics','reconstruction','agent','web')]
    [string[]]$Services    = @('physics','reconstruction','agent','web'),
    [switch]$UseCloudBuild,
    [switch]$SkipBuild,
    [switch]$SkipTrigger
)

. "$PSScriptRoot\lib\Rinne.Common.ps1"
Initialize-RinneShell

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Assert-Tool -Name gcloud -InstallHint "Install the Google Cloud CLI."
if (-not $UseCloudBuild -and -not $SkipBuild) {
    Assert-Tool -Name docker -InstallHint "Install Docker Desktop, or re-run with -UseCloudBuild."
}

if (-not $Tag) {
    $sha = (& git -C $repoRoot rev-parse --short HEAD 2>$null)
    $Tag = if ($LASTEXITCODE -eq 0 -and $sha) { "$sha".Trim() }
           else { (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss") }
    $global:LASTEXITCODE = 0
}

$registry     = "$Region-docker.pkg.dev/$ProjectId/$RepoName"
$scansBucket  = "rinne-scans-$ProjectId"
$scanPrefix   = "scan-queue/"
$triggerName  = "rinne-scan-queue"
$eventarcSa   = "rinne-eventarc-sa@$ProjectId.iam.gserviceaccount.com"

Write-Step "Deploy plan"
Write-Host "  project  : $ProjectId"
Write-Host "  region   : $Region"
Write-Host "  registry : $registry"
Write-Host "  tag      : $Tag"
Write-Host "  services : $($Services -join ', ')"

Assert-Project -ProjectId $ProjectId -ExpectedNumber $ProjectNumber

$config = @{
    physics = @{
        Name        = 'rinne-physics'
        ProbePath   = '/readyz'
        Dockerfile  = 'services/physics/Dockerfile'
        ServiceAcct = 'rinne-physics-sa'
        Public      = $false
        MaxInstances= 3
        Concurrency = 40
        TimeoutSec  = 60
        Memory      = '1Gi'
        Cpu         = '1'
        Env         = @{ NODE_ENV = 'production'; LOG_LEVEL = 'info'; GCS_ARTIFACTS_BUCKET = "rinne-artifacts-$ProjectId" }
    }
    reconstruction = @{
        Name        = 'rinne-reconstruction'
        ProbePath   = '/readyz'
        Dockerfile  = 'services/reconstruction/Dockerfile'
        ServiceAcct = 'rinne-reconstruction-sa'
        Public      = $false
        MaxInstances= 1
        Concurrency = 1
        TimeoutSec  = 300
        Memory      = '16Gi'
        Cpu         = '4'
        Gpu         = $true
        Env         = @{ APP_ENV = 'production'; LOG_LEVEL = 'INFO'; ENABLE_DOCS = 'false'; PIPELINE_NAME = 'triposr'; STORAGE_MODE = 'gcs' }
    }
    agent = @{
        Name        = 'rinne-agent'
        ProbePath   = '/readyz'
        Dockerfile  = 'services/agent/Dockerfile'
        ServiceAcct = 'rinne-agent-sa'
        Public      = $false
        MaxInstances= 3
        Concurrency = 20
        TimeoutSec  = 420
        Memory      = '1Gi'
        Cpu         = '1'
        Env         = @{
            APP_ENV             = 'production'
            LOG_LEVEL           = 'INFO'
            ENABLE_DOCS         = 'false'
            STORE_MODE          = 'firestore'
            OBJECT_MODE         = 'gcs'
            TRIAGE_MODE         = 'flash'
            TRIAGE_MODEL        = 'gemini-3.5-flash'
            VERTEX_LOCATION     = $Region
            FIRESTORE_COLLECTION= 'agent-jobs'
            SCAN_BUCKET         = "rinne-scans-$ProjectId"
            SCAN_PREFIX         = 'scan-queue/'
            MAX_ATTEMPTS        = '3'
            CLIENT_MODE         = 'http'
            RECONSTRUCTION_TIMEOUT_SECONDS = '280'
            PHYSICS_TIMEOUT_SECONDS        = '60'
            GATE_RECONSTRUCTION_CONFIDENCE = '0.70'
            GATE_MATERIAL_CONFIDENCE       = '0.50'
            SOLVER_SEED         = '42'
            SOLVER_MAX_STEPS    = '900'
            TIP_FORCE_RATIO     = '0.5'
        }
    }
    web = @{
        Name        = 'rinne-web'
        ProbePath   = '/api/health'
        Dockerfile  = 'services/web/Dockerfile'
        ServiceAcct = 'rinne-web-sa'
        Public      = $true
        MaxInstances= 5
        Concurrency = 80
        TimeoutSec  = 60
        Memory      = '1Gi'
        Cpu         = '1'
        Env         = @{ NODE_ENV = 'production' }
    }
}

if (-not $SkipBuild -and -not $UseCloudBuild) {
    Write-Step "Configuring Docker for Artifact Registry"
    Invoke-Gcloud auth configure-docker "$Region-docker.pkg.dev" --quiet | Out-Null
    Write-Ok "Credential helper configured"
}

$deployed = @{}

foreach ($key in @('physics','reconstruction','agent','web')) {
    if ($Services -notcontains $key) { continue }

    $svc   = $config[$key]
    $image = "$registry/$($svc.Name):$Tag"
    $email = "$($svc.ServiceAcct)@$ProjectId.iam.gserviceaccount.com"

    # Build and push
    if (-not $SkipBuild) {
        Write-Step "Building $($svc.Name)"
        Push-Location $repoRoot
        try {
            if ($UseCloudBuild) {
                $cfgPath = Join-Path ([System.IO.Path]::GetTempPath()) "rinne-cloudbuild-$($svc.Name).yaml"
                $cfg = @"
steps:
  - name: gcr.io/cloud-builders/docker
    # DOCKER_BUILDKIT=1 is REQUIRED. The cloud-builders/docker image runs the
    # legacy builder by default, and every Rinne Dockerfile uses
    # `RUN --mount=type=cache,...`, which is a BuildKit-only feature. Without
    # this the build dies with "the --mount option requires BuildKit".
    # Docker Desktop enables BuildKit by default, so local builds succeed and
    # only Cloud Build fails - which is exactly the kind of divergence that is
    # cheap to fix here and expensive to debug on a deadline.
    env: ['DOCKER_BUILDKIT=1']
    args: ['build', '-f', '$($svc.Dockerfile)', '-t', '$image', '.']
    timeout: '3600s'
images:
  - '$image'
# One hour, not the default ten minutes. The reconstruction image pulls ~2.8GB of
# wheels plus 1.7GB of weights and pushes ~8GB; ten minutes is not close.
timeout: '3600s'
options:
  logging: CLOUD_LOGGING_ONLY
"@
                [System.IO.File]::WriteAllText(
                    $cfgPath,
                    ($cfg -replace "`r`n", "`n"),
                    (New-Object System.Text.UTF8Encoding($false))
                )
                try {
                    Invoke-Gcloud builds submit `
                        --config=$cfgPath `
                        --project=$ProjectId `
                        --region=$Region `
                        --quiet | Out-Null
                } finally {
                    Remove-Item $cfgPath -Force -ErrorAction SilentlyContinue
                }
            } else {
                & docker build -f $svc.Dockerfile -t $image .
                if ($LASTEXITCODE -ne 0) { throw "docker build failed for $($svc.Name)" }
                & docker push $image
                if ($LASTEXITCODE -ne 0) { throw "docker push failed for $($svc.Name)" }
            }
        } finally {
            Pop-Location
        }
        Write-Ok "Pushed $image"
    }

    # Environment
    $envMap = @{} + $svc.Env
    $envMap['SERVICE_VERSION'] = $Tag
    $envMap['GCP_REGION']      = $Region
    $envMap['GCP_PROJECT_ID']  = $ProjectId

    # Recover the URLs of anything deployed earlier, so a single service can be
    # redeployed on its own without losing what it is wired to.
    $needs = @()
    if ($key -eq 'agent') { $needs = @('physics','reconstruction') }
    if ($key -eq 'web')   { $needs = @('physics','reconstruction','agent') }
    foreach ($dep in $needs) {
        if (-not $deployed.ContainsKey($dep)) {
            $url = (Invoke-Gcloud run services describe $config[$dep].Name `
                --region=$Region --project=$ProjectId `
                --format="value(status.url)" -Quiet) -join ''
            if (-not $url) { throw "$($config[$dep].Name) is not deployed. Deploy it before $($svc.Name)." }
            $deployed[$dep] = "$url".Trim()
        }
    }

    if ($key -eq 'agent') {
        $envMap['RECONSTRUCTION_SERVICE_URL'] = $deployed['reconstruction']
        $envMap['PHYSICS_SERVICE_URL']        = $deployed['physics']
    }

    if ($key -eq 'web') {
        $envMap['PHYSICS_SERVICE_URL']        = $deployed['physics']
        $envMap['AGENT_SERVICE_URL']          = $deployed['agent']
        $envMap['RECONSTRUCTION_SERVICE_URL'] = $deployed['reconstruction']
        $envMap['GCS_ARTIFACTS_BUCKET']       = "rinne-artifacts-$ProjectId"
    }


    $envArg = "^@^" + (($envMap.GetEnumerator() | Sort-Object Name |
        ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "@")

    # Deploy
    Write-Step "Deploying $($svc.Name)"

    $deployArgs = @(
        'run','deploy', $svc.Name,
        "--image=$image",
        "--region=$Region",
        "--project=$ProjectId",
        "--platform=managed",
        "--service-account=$email",
        "--port=8080",
        "--cpu=$($svc.Cpu)",
        "--memory=$($svc.Memory)",
        "--concurrency=$($svc.Concurrency)",
        "--timeout=$($svc.TimeoutSec)",
        "--min-instances=0",
        "--max-instances=$($svc.MaxInstances)",
        "--ingress=all",
        "--execution-environment=gen2",
        "--startup-probe=httpGet.path=$($svc.ProbePath),httpGet.port=8080,initialDelaySeconds=5,periodSeconds=5,timeoutSeconds=3,failureThreshold=6",
        "--set-env-vars=$envArg",
        '--quiet'
    )

    # L4 has a hard 4 CPU / 16GiB floor, and --no-cpu-throttling is mandatory for
    # GPU - which is what makes billing instance-based rather than request-based.
    if ($svc.ContainsKey('Gpu') -and $svc.Gpu) {
        $deployArgs = $deployArgs | Where-Object { $_ -notlike '--startup-probe=*' }
        # 23 x 10 = 230s, against a hard 240s ceiling on failureThreshold x periodSeconds.
        $deployArgs += @(
            '--gpu=1',
            '--gpu-type=nvidia-l4',
            '--no-gpu-zonal-redundancy',
            '--no-cpu-throttling',
            "--startup-probe=httpGet.path=$($svc.ProbePath),httpGet.port=8080,initialDelaySeconds=10,periodSeconds=10,timeoutSeconds=5,failureThreshold=23",
            "--liveness-probe=httpGet.path=/livez,httpGet.port=8080,periodSeconds=30,timeoutSeconds=5,failureThreshold=3"
        )
    }

    $deployArgs += if ($svc.Public) { '--allow-unauthenticated' } else { '--no-allow-unauthenticated' }

    Invoke-Gcloud @deployArgs | Out-Null

    $url = ((Invoke-Gcloud run services describe $svc.Name `
        --region=$Region --project=$ProjectId --format="value(status.url)" -Quiet) -join '').Trim()
    $deployed[$key] = $url
    Write-Ok "$($svc.Name) -> $url"

    # Per-service invoker binding
    if (-not $svc.Public) {
        $invokers = @('rinne-web-sa')
        if (@('reconstruction','physics') -contains $key) { $invokers += 'rinne-agent-sa' }
        if ($key -eq 'agent') { $invokers += 'rinne-eventarc-sa' }
        foreach ($invoker in $invokers) {
            Invoke-Gcloud run services add-iam-policy-binding $svc.Name `
                --region=$Region --project=$ProjectId `
                --member="serviceAccount:$invoker@$ProjectId.iam.gserviceaccount.com" `
                --role="roles/run.invoker" `
                --quiet -Quiet | Out-Null
            Write-Ok "  $invoker granted roles/run.invoker on $($svc.Name) only"
        }
    }
}

# Eventarc: gs://rinne-scans-* object finalize -> POST /v1/events/scan
if (-not $SkipTrigger -and $Services -contains 'agent') {
    Write-Step "Eventarc trigger for the scan queue"


    $triggerArgs = @(
        "--location=$Region",
        "--project=$ProjectId",
        "--destination-run-service=rinne-agent",
        "--destination-run-region=$Region",
        "--destination-run-path=/v1/events/scan",
        "--event-filters=type=google.cloud.storage.object.v1.finalized",
        "--event-filters=bucket=$scansBucket",
        "--service-account=$eventarcSa",
        '--quiet'
    )

    if (Test-GcloudResource eventarc triggers describe $triggerName --location=$Region --project=$ProjectId --format="value(name)") {

        Invoke-Gcloud eventarc triggers update $triggerName `
            --location=$Region --project=$ProjectId `
            --destination-run-service=rinne-agent `
            --destination-run-region=$Region `
            --destination-run-path=/v1/events/scan `
            --service-account=$eventarcSa `
            --quiet -Quiet | Out-Null
        Write-Ok "Updated trigger $triggerName"
    } else {
        # THE FIRST TRIGGER IN A PROJECT LAZILY PROVISIONS THE EVENTARC SERVICE
        # AGENT, and the create that provisions it usually fails: the agent is
        # granted roles/eventarc.serviceAgent, but Eventarc's control plane has
        # not seen the grant yet. Hit for real on Aug 30, 2026. The role really
        # is present at that moment - checked - so the only fix is to wait and
        # ask again, which is what Google's own error message says to do.
        $created = $false
        for ($attempt = 1; $attempt -le 12; $attempt++) {
            try {
                Invoke-Gcloud eventarc triggers create $triggerName @triggerArgs | Out-Null
                $created = $true
                break
            } catch {
                $message = $_.Exception.Message
                $propagating = ($message -match 'FAILED_PRECONDITION') `
                    -or ($message -match 'Service Agent') -or ($message -match 'propagated')
                if (-not $propagating -or $attempt -ge 12) { throw }
                Write-Host "    Eventarc service agent not ready yet; retrying in 15s ($attempt/12)" `
                    -ForegroundColor DarkCyan
                Start-Sleep -Seconds 15
            }
        }
        if ($created) {
            Write-Ok "Created trigger $triggerName on gs://$scansBucket"
            Write-Host "    First-time triggers can take a couple of minutes to start delivering." -ForegroundColor DarkCyan
        }
    }

    $transport = ((Invoke-Gcloud eventarc triggers describe $triggerName `
        --location=$Region --project=$ProjectId `
        --format="value(transport.pubsub.subscription)" -Quiet) -join '').Trim()

    if ($transport) {
        $subId = $transport.Split('/')[-1]
        try {
            Invoke-Gcloud pubsub subscriptions update $subId `
                --project=$ProjectId `
                --ack-deadline=600 `
                --quiet -Quiet | Out-Null
            Write-Ok "  transport subscription $subId ack-deadline=600s"
        } catch {
            Write-Warning "Could not set the ack deadline on $subId. Eventarc may have reclaimed it."
            Write-Warning $_.Exception.Message
        }
    } else {
        Write-Warning "Trigger has no transport subscription yet. Re-run after it finishes provisioning."
    }
}

Write-Step "Deployed"
$deployed.GetEnumerator() | Sort-Object Name | ForEach-Object {
    $public = if ($config[$_.Key].Public) { 'public' } else { 'IAM-private' }
    [pscustomobject]@{ service = $config[$_.Key].Name; access = $public; url = $_.Value }
} | Format-Table -AutoSize

Write-Host ""
Write-Host "  Scan queue:  gs://$scansBucket/$scanPrefix" -ForegroundColor White
Write-Host "  Verify:      pwsh .\infra\scripts\smoke-test.ps1" -ForegroundColor White
Write-Host ""
