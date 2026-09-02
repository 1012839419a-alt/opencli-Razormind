# Sourceable restart-recovery helpers shared by install.ps1 and executable tests.
$script:OpenCliRestartStateFileName = ".opencli-restart-recovery-state.json"

function Test-OpenCliWsl {
    foreach ($path in @("/proc/sys/kernel/osrelease", "/proc/version")) {
        if (Test-Path -LiteralPath $path) {
            $kernelDescription = Get-Content -LiteralPath $path -Raw -ErrorAction SilentlyContinue
            if ($kernelDescription -match "(?i)microsoft") { return $true }
        }
    }
    return $false
}

function Test-OpenCliDockerBootPrerequisite {
    if ($env:OS -eq "Windows_NT" -or (Test-OpenCliWsl)) { return $false }
    $kernelName = & uname -s 2>$null
    if ($LASTEXITCODE -ne 0 -or "$kernelName".Trim() -ne "Linux") { return $false }
    if (-not [string]::IsNullOrEmpty($env:DOCKER_HOST)) { return $false }
    $dockerContext = & docker context show 2>$null
    if ($LASTEXITCODE -ne 0 -or "$dockerContext".Trim() -ne "default") { return $false }
    if (-not (Get-Command systemctl -ErrorAction SilentlyContinue)) { return $false }
    & systemctl is-enabled docker 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

function Get-OpenCliRecoveredContainer([string]$Service) {
    $containerId = docker compose ps -q $Service
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace("$containerId")) { throw "$Service container id is unavailable." }
    $state = docker inspect --format '{{.State.Status}}' $containerId
    if ($LASTEXITCODE -ne 0 -or "$state".Trim() -ne "running") { throw "$Service did not recover to running." }
    $health = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $containerId
    if ($LASTEXITCODE -ne 0 -or "$health".Trim() -ne "healthy") { throw "$Service did not recover to healthy." }
    return "$containerId".Trim()
}

function Test-OpenCliLocalAuthState([string]$ApiId) {
    docker exec $ApiId python -c 'import base64, hashlib; from pathlib import Path; from backend.security.local_auth import load_password_hash; state=Path("/data/local-admin-password.hash"); marker=state.with_name(f"{state.name}.initialized"); assert marker.read_text(encoding="utf-8") in {"opencli-local-auth-state-v1:initial\n", "opencli-local-auth-state-v1:changed\n"}; encoded=load_password_hash("", str(state)); assert encoded; scheme,n_text,r_text,p_text,salt_text,expected_text=encoded.split("$", 5); n,r,p=map(int, (n_text,r_text,p_text)); assert scheme == "scrypt" and n >= 2 and n & (n - 1) == 0 and 0 < r <= 32 and 0 < p <= 16; decode=lambda value: base64.b64decode(value.encode("ascii"), altchars=b"-_", validate=True); salt=decode(salt_text); expected=decode(expected_text); assert len(salt) >= 16 and len(expected) >= 32; probe=hashlib.scrypt(b"opencli-restart-state-validation", salt=salt, n=n, r=r, p=p, maxmem=64 * 1024 * 1024); assert len(probe) == len(expected)'
    if ($LASTEXITCODE -ne 0) { throw "Durable local authentication state is invalid." }
}

function New-OpenCliRestartState([string]$Directory, [string]$ComposeProjectName, [string]$Sentinel) {
    $apiId = Get-OpenCliRecoveredContainer "api"
    $null = Get-OpenCliRecoveredContainer "frontend"
    $agentId = Get-OpenCliRecoveredContainer "agent-1"
    $dbRevision = docker exec $apiId python -c 'import sqlite3; db=sqlite3.connect("/data/opencli_admin.db"); print(db.execute("SELECT version_num FROM alembic_version").fetchone()[0])'
    if ($LASTEXITCODE -ne 0) { throw "Could not read the database revision." }
    Test-OpenCliLocalAuthState $apiId
    $profileVolume = docker inspect --format '{{range .Mounts}}{{if eq .Destination "/home/chrome/.config/chromium"}}{{.Name}}{{end}}{{end}}' $agentId
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace("$profileVolume")) { throw "Agent profile volume is unavailable." }
    docker exec $apiId python -c 'from pathlib import Path; import sys; Path("/data/.opencli-host-restart-sentinel").write_text(sys.argv[1], encoding="utf-8")' $Sentinel
    if ($LASTEXITCODE -ne 0) { throw "Could not write the database-volume sentinel." }
    docker exec $agentId sh -c 'test -d /home/chrome/.config/chromium && test -r /home/chrome/.config/chromium && test -w /home/chrome/.config/chromium'
    if ($LASTEXITCODE -ne 0) { throw "Browser profile is not readable and writable." }
    docker exec $agentId sh -c 'printf %s "$1" > /home/chrome/.config/chromium/.opencli-host-restart-sentinel' sh $Sentinel
    if ($LASTEXITCODE -ne 0) { throw "Could not write the browser-profile sentinel." }

    $state = [ordered]@{
        compose_project_name = $ComposeProjectName
        db_revision = "$dbRevision".Trim()
        agent_profile_volume = "$profileVolume".Trim()
        sentinel = $Sentinel
    }
    $statePath = Join-Path $Directory $script:OpenCliRestartStateFileName
    [IO.File]::WriteAllText($statePath, ($state | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))
}

function Test-OpenCliRestartState([string]$Directory, [string]$FrontendPort, [string]$ApiPort) {
    $statePath = Join-Path $Directory $script:OpenCliRestartStateFileName
    if (-not (Test-Path -LiteralPath $statePath)) { throw "Restart baseline is unavailable: $statePath" }
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace($state.compose_project_name)) { throw "Restart baseline has no Compose project name." }
    $env:COMPOSE_PROJECT_NAME = $state.compose_project_name

    Push-Location $Directory
    try {
        docker info | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Docker daemon is unavailable." }
        $apiId = Get-OpenCliRecoveredContainer "api"
        $null = Get-OpenCliRecoveredContainer "frontend"
        $agentId = Get-OpenCliRecoveredContainer "agent-1"
        $dbRevision = docker exec $apiId python -c 'import sqlite3; db=sqlite3.connect("file:/data/opencli_admin.db?mode=ro", uri=True); assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"; print(db.execute("SELECT version_num FROM alembic_version").fetchone()[0])'
        if ($LASTEXITCODE -ne 0 -or "$dbRevision".Trim() -ne $state.db_revision) { throw "Database revision or quick_check changed." }
        $dbSentinel = docker exec $apiId python -c 'from pathlib import Path; print(Path("/data/.opencli-host-restart-sentinel").read_text(encoding="utf-8"))'
        if ($LASTEXITCODE -ne 0 -or "$dbSentinel".Trim() -ne $state.sentinel) { throw "Database-volume sentinel changed." }
        Test-OpenCliLocalAuthState $apiId
        $profileVolume = docker inspect --format '{{range .Mounts}}{{if eq .Destination "/home/chrome/.config/chromium"}}{{.Name}}{{end}}{{end}}' $agentId
        if ($LASTEXITCODE -ne 0 -or "$profileVolume".Trim() -ne $state.agent_profile_volume) { throw "Agent profile volume changed." }
        $profileSentinel = docker exec $agentId sh -c 'cat /home/chrome/.config/chromium/.opencli-host-restart-sentinel'
        if ($LASTEXITCODE -ne 0 -or "$profileSentinel".Trim() -ne $state.sentinel) { throw "Browser-profile sentinel changed." }
        docker exec $apiId python -c 'import json, os, urllib.request; request=urllib.request.Request("http://localhost:8000/api/v1/auth/me", headers={"Authorization": f"Bearer {os.environ[\"BOOTSTRAP_ADMIN_TOKEN\"]}", "X-API-Token": os.environ["API_AUTH_TOKEN"]}); payload=json.load(urllib.request.urlopen(request, timeout=5)); assert payload["data"]["subject"] == "bootstrap-admin"'
        if ($LASTEXITCODE -ne 0) { throw "Authenticated identity check failed." }
        Invoke-WebRequest "http://localhost:$FrontendPort/login" -UseBasicParsing | Out-Null
        Invoke-WebRequest "http://localhost:$ApiPort/health" -UseBasicParsing | Out-Null
    } finally {
        Pop-Location
    }
    Write-Host "Restart recovery verified for project $($state.compose_project_name): services, database, authentication, and browser profile persisted."
}

function Write-OpenCliRestartStatus([string]$Directory, [string]$FrontendPort, [string]$ApiPort, [bool]$BaselineReady) {
    if (Test-OpenCliDockerBootPrerequisite) {
        Write-Host ""
        Write-Host "Restart prerequisite verified: native Linux uses the default Docker context, DOCKER_HOST is unset, and the Docker systemd unit is enabled."
        Write-Host "This confirms boot prerequisites only; the installer has not tested a host restart."
    } else {
        Write-Warning "Restart recovery unverified. OpenCLI is ready now, but its host-restart recovery has not been tested."
        if (Test-OpenCliWsl) {
            Write-Host "Action: WSL is development-only for this recovery contract; no production host-restart claim is made."
        } elseif ($env:OS -eq "Windows_NT") {
            $automaticDockerService = Get-Service -Name "com.docker.service", "docker" -ErrorAction SilentlyContinue |
                Where-Object { $_.StartType -eq "Automatic" } | Select-Object -First 1
            if ($automaticDockerService) { Write-Host "Docker service startup is Automatic, but full Docker Desktop recovery still requires the post-restart check." }
            Write-Host 'Action: enable "Start Docker Desktop when you sign in" in Docker Desktop settings.'
            Write-Host "Inspect startup registration: Get-CimInstance Win32_StartupCommand | Where-Object { `$_.Name -match 'Docker' }"
        } else {
            $kernelName = & uname -s 2>$null
            if ($LASTEXITCODE -eq 0 -and "$kernelName".Trim() -eq "Darwin") { Write-Host 'Action: enable "Start Docker Desktop when you sign in" in Docker Desktop settings.' }
            else { Write-Host "Action: use the default Docker context, unset DOCKER_HOST, and, if appropriate, enable Docker yourself with: sudo systemctl enable docker" }
        }
    }

    if ($BaselineReady) {
        $escapedDirectory = $Directory.Replace("'", "''")
        $escapedFrontendPort = $FrontendPort.Replace("'", "''")
        $escapedApiPort = $ApiPort.Replace("'", "''")
        Write-Host "A non-secret pre-restart baseline was saved in $(Join-Path $Directory $script:OpenCliRestartStateFileName)."
        Write-Host "After the next host restart, verify without docker compose up/start/restart:"
        Write-Host "  Set-Location -LiteralPath '$escapedDirectory'"
        Write-Host "  .\scripts\install.ps1 -InstallDir '$escapedDirectory' -VerifyRestartRecovery -FrontendPort '$escapedFrontendPort' -ApiPort '$escapedApiPort'"
    } else {
        Write-Warning "The pre-restart persistence baseline could not be created; recovery remains unverified."
    }
}
