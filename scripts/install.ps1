param(
    [string]$Version = $(if ($env:OPENCLI_ADMIN_VERSION) { $env:OPENCLI_ADMIN_VERSION } else { "0.4.1" }),
    [string]$Repository = $(if ($env:OPENCLI_ADMIN_REPOSITORY) { $env:OPENCLI_ADMIN_REPOSITORY } else { "2233admin/opencli-Razormind" }),
    [string]$InstallDir = $(if ($env:OPENCLI_ADMIN_DIR) { $env:OPENCLI_ADMIN_DIR } else { Join-Path (Get-Location) "opencli-admin" }),
    [string]$FrontendPort = $(if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { "3010" }),
    [string]$ApiPort = $(if ($env:API_PORT) { $env:API_PORT } else { "8031" }),
    [switch]$VerifyRestartRecovery
)

$ErrorActionPreference = "Stop"

function Assert-NativeSuccess([string]$Message) {
    if ($LASTEXITCODE -ne 0) {
        throw $Message
    }
}

$resolvedInstallDir = [System.IO.Path]::GetFullPath($InstallDir)
if ($VerifyRestartRecovery) {
    . (Join-Path $resolvedInstallDir "scripts/install-recovery.ps1")
    Test-OpenCliRestartState -Directory $resolvedInstallDir -FrontendPort $FrontendPort -ApiPort $ApiPort
    return
}

docker compose version | Out-Null
Assert-NativeSuccess "Docker Compose is required."
docker info | Out-Null
Assert-NativeSuccess "Docker is not running."
if (Test-Path -LiteralPath $resolvedInstallDir) {
    $existing = Get-ChildItem -LiteralPath $resolvedInstallDir -Force
    if ($existing.Count -gt 0) {
        throw "Install directory is not empty: $resolvedInstallDir"
    }
} else {
    New-Item -ItemType Directory -Path $resolvedInstallDir | Out-Null
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("opencli-admin-" + [guid]::NewGuid())
$archive = "$tempRoot.zip"
$expanded = Join-Path $tempRoot "expanded"
New-Item -ItemType Directory -Path $expanded | Out-Null

try {
    Invoke-WebRequest "https://github.com/$Repository/archive/refs/tags/v$Version.zip" -OutFile $archive -UseBasicParsing
    Expand-Archive -LiteralPath $archive -DestinationPath $expanded
    $sourceRoot = Get-ChildItem -LiteralPath $expanded -Directory | Select-Object -First 1
    if (-not $sourceRoot) {
        throw "The release archive did not contain a project directory."
    }
    Get-ChildItem -LiteralPath $sourceRoot.FullName -Force | Move-Item -Destination $resolvedInstallDir
} finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}

$envPath = Join-Path $resolvedInstallDir ".env"
Copy-Item -LiteralPath (Join-Path $resolvedInstallDir ".env.docker.example") -Destination $envPath
. (Join-Path $resolvedInstallDir "scripts/install-recovery.ps1")

function New-RandomBytes([int]$Count) {
    $bytes = New-Object byte[] $Count
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        $rng.Dispose()
    }
    return ,$bytes
}

function New-HexSecret([int]$Bytes) {
    return -join ((New-RandomBytes $Bytes) | ForEach-Object { $_.ToString("x2") })
}

function New-FernetKey {
    return [Convert]::ToBase64String((New-RandomBytes 32)).Replace("+", "-").Replace("/", "_")
}

function Set-EnvValue([string]$Key, [string]$Value) {
    $content = [IO.File]::ReadAllText($envPath)
    $pattern = "(?m)^$([Text.RegularExpressions.Regex]::Escape($Key))=.*$"
    if ([Text.RegularExpressions.Regex]::IsMatch($content, $pattern)) {
        $content = [Text.RegularExpressions.Regex]::Replace($content, $pattern, "$Key=$Value")
    } else {
        $content = $content.TrimEnd("`r", "`n") + "`n$Key=$Value`n"
    }
    [IO.File]::WriteAllText($envPath, $content, [Text.UTF8Encoding]::new($false))
}

$apiToken = New-HexSecret 32
$localAdminPassword = New-HexSecret 24
$bootstrapToken = New-HexSecret 32
Set-EnvValue "API_AUTH_TOKEN" $apiToken
Set-EnvValue "BOOTSTRAP_ADMIN_TOKEN" $bootstrapToken
Set-EnvValue "SECRET_KEY" (New-HexSecret 32)
Set-EnvValue "CREDENTIAL_ENCRYPTION_KEY" (New-FernetKey)
$composeProjectName = if ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { "opencli-admin" }
Set-EnvValue "COMPOSE_PROJECT_NAME" $composeProjectName

Push-Location $resolvedInstallDir
try {
    docker compose pull api frontend agent-1
    Assert-NativeSuccess "Failed to pull OpenCLI Admin images."
    $localAdminPassword | docker compose run --rm -T --no-deps api python -c 'import sys; from backend.security.local_auth import hash_password, initialize_password_hash; initialize_password_hash(hash_password(sys.stdin.read().strip()), "/data/local-admin-password.hash")'
    Assert-NativeSuccess "Failed to initialize the local administrator password."
    docker compose up -d
    Assert-NativeSuccess "Failed to start OpenCLI Admin."

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            Invoke-WebRequest "http://localhost:$FrontendPort/login" -UseBasicParsing | Out-Null
            $ready = $true
            break
        } catch {
            Start-Sleep -Seconds 5
        }
    }
    if (-not $ready) {
        docker compose ps
        docker compose logs --tail=100 api frontend
        throw "OpenCLI Admin did not become healthy within 5 minutes."
    }
} finally {
    Pop-Location
}

$restartBaselineReady = $false
Push-Location $resolvedInstallDir
try {
    New-OpenCliRestartState -Directory $resolvedInstallDir -ComposeProjectName $composeProjectName -Sentinel (New-HexSecret 16)
    $restartBaselineReady = $true
} catch {
    Write-Warning "The pre-restart persistence baseline could not be created: $($_.Exception.Message)"
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "OpenCLI Admin $Version is ready."
Write-Host "URL: http://localhost:$FrontendPort"
Write-Host "Local login: admin / $localAdminPassword"
Write-Host "Emergency BOOTSTRAP_ADMIN_TOKEN and fleet API_AUTH_TOKEN are stored in $envPath; local login uses the random password shown above."
Write-OpenCliRestartStatus -Directory $resolvedInstallDir -FrontendPort $FrontendPort -ApiPort $ApiPort -BaselineReady $restartBaselineReady
