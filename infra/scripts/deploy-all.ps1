#Requires -Version 5.1
<#
.SYNOPSIS
  Builds, pushes, and deploys all three Rinne services to Cloud Run.

.DESCRIPTION
  DEPLOY ORDER IS NOT ARBITRARY: physics -> agent -> web.
  Web's PHYSICS_SERVICE_URL and AGENT_SERVICE_URL are outputs of the first two
  deploys, so it must go last.

  NETWORK MODEL, stated because it is the single most common way this goes
  wrong: physics and agent deploy --no-allow-unauthenticated with
  --ingress=all. Ingress stays "all" ON PURPOSE. Without a VPC connector a
  Cloud Run -> Cloud Run call egresses over the public path, so --ingress=internal
  BLOCKS it and produces a 403 indistinguishable from an IAM failure. IAM is
  the real control: rinne-web-sa gets roles/run.invoker on those two specific
  services and nothing else on the planet can call them.

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
    [ValidateSet('physics','agent','web')]
    [string[]]$Services    = @('physics','agent','web'),
    [switch]$UseCloudBuild,
    [switch]$SkipBuild
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

$registry = "$Region-docker.pkg.dev/$ProjectId/$RepoName"

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
        Env         = @{ NODE_ENV = 'production'; LOG_LEVEL = 'info' }
    }
    agent = @{
        Name        = 'rinne-agent'
        ProbePath   = '/readyz'
        Dockerfile  = 'services/agent/Dockerfile'
        ServiceAcct = 'rinne-agent-sa'
        Public      = $false
        MaxInstances= 3
        Concurrency = 20
        TimeoutSec  = 300
        Memory      = '1Gi'
        Cpu         = '1'
        Env         = @{ APP_ENV = 'production'; LOG_LEVEL = 'INFO'; ENABLE_DOCS = 'false' }
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

foreach ($key in @('physics','agent','web')) {
    if ($Services -notcontains $key) { continue }

    $svc   = $config[$key]
    $image = "$registry/$($svc.Name):$Tag"
    $email = "$($svc.ServiceAcct)@$ProjectId.iam.gserviceaccount.com"

    # -- Build and push ------------------------------------------------
    if (-not $SkipBuild) {
        Write-Step "Building $($svc.Name)"
        Push-Location $repoRoot
        try {
            if ($UseCloudBuild) {
                # `gcloud builds submit --tag` requires a Dockerfile at the ROOT
                # of the uploaded context. Rinne's Dockerfiles live at
                # services/<svc>/Dockerfile and deliberately build FROM the repo
                # root (they need pnpm-lock.yaml, pnpm-workspace.yaml and
                # packages/contracts), so --tag cannot express this build and
                # fails with "Dockerfile required when specifying --tag".
                #
                # A generated build config can express it, and it runs the exact
                # same `docker build -f ... .` command as the local path below,
                # so the two build paths cannot drift apart.
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
images:
  - '$image'
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

    # -- Environment ---------------------------------------------------
    $envMap = @{} + $svc.Env
    $envMap['SERVICE_VERSION'] = $Tag
    $envMap['GCP_REGION']      = $Region
    $envMap['GCP_PROJECT_ID']  = $ProjectId

    if ($key -eq 'web') {
        if (-not $deployed.ContainsKey('physics') -or -not $deployed.ContainsKey('agent')) {
            # Recover the URLs when web is deployed on its own.
            foreach ($dep in @('physics','agent')) {
                if (-not $deployed.ContainsKey($dep)) {
                    $url = (Invoke-Gcloud run services describe $config[$dep].Name `
                        --region=$Region --project=$ProjectId `
                        --format="value(status.url)" -Quiet) -join ''
                    if (-not $url) { throw "$($config[$dep].Name) is not deployed. Deploy it before web." }
                    $deployed[$dep] = "$url".Trim()
                }
            }
        }
        $envMap['PHYSICS_SERVICE_URL'] = $deployed['physics']
        $envMap['AGENT_SERVICE_URL']   = $deployed['agent']
    }


    $envArg = "^@^" + (($envMap.GetEnumerator() | Sort-Object Name |
        ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "@")

    # -- Deploy --------------------------------------------------------
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
        # STARTUP PROBE, not the default TCP check.
        # Cloud Run's default startup check only opens a TCP connection to the
        # port. A revision that is listening but broken therefore passes, gets
        # promoted, and fails every request. physics and agent probe /readyz,
        # which for physics returns 503 until Rapier has actually initialised
        # and passed its self-test - so a revision whose WASM failed to load
        # never receives traffic. web probes /api/health.
        "--startup-probe=httpGet.path=$($svc.ProbePath),httpGet.port=8080,initialDelaySeconds=5,periodSeconds=5,timeoutSeconds=3,failureThreshold=6",
        "--set-env-vars=$envArg",
        '--quiet'
    )

    $deployArgs += if ($svc.Public) { '--allow-unauthenticated' } else { '--no-allow-unauthenticated' }

    Invoke-Gcloud @deployArgs | Out-Null

    $url = ((Invoke-Gcloud run services describe $svc.Name `
        --region=$Region --project=$ProjectId --format="value(status.url)" -Quiet) -join '').Trim()
    $deployed[$key] = $url
    Write-Ok "$($svc.Name) -> $url"

    # -- Per-service invoker binding -----------------------------------
    if (-not $svc.Public) {
        Invoke-Gcloud run services add-iam-policy-binding $svc.Name `
            --region=$Region --project=$ProjectId `
            --member="serviceAccount:rinne-web-sa@$ProjectId.iam.gserviceaccount.com" `
            --role="roles/run.invoker" `
            --quiet -Quiet | Out-Null
        Write-Ok "  rinne-web-sa granted roles/run.invoker on $($svc.Name) only"
    }
}

Write-Step "Deployed"
$deployed.GetEnumerator() | Sort-Object Name | ForEach-Object {
    $public = if ($config[$_.Key].Public) { 'public' } else { 'IAM-private' }
    [pscustomobject]@{ service = $config[$_.Key].Name; access = $public; url = $_.Value }
} | Format-Table -AutoSize

Write-Host ""
Write-Host "  Verify:  pwsh .\infra\scripts\smoke-test.ps1" -ForegroundColor White
Write-Host ""
