param(
    [string]$Version = $(if ($env:OPENCLI_ADMIN_VERSION) { $env:OPENCLI_ADMIN_VERSION } else { "0.4.0" }),
    [string]$Repository = $(if ($env:OPENCLI_ADMIN_REPOSITORY) { $env:OPENCLI_ADMIN_REPOSITORY } else { "2233admin/opencli-Razormind" }),
    [string]$InstallDir = $(if ($env:OPENCLI_ADMIN_DIR) { $env:OPENCLI_ADMIN_DIR } else { Join-Path (Get-Location) "opencli-admin" })
)

$ErrorActionPreference = "Stop"

function Assert-NativeSuccess([string]$Message) {
    if ($LASTEXITCODE -ne 0) {
        throw $Message
    }
}

docker compose version | Out-Null
Assert-NativeSuccess "Docker Compose is required."
docker info | Out-Null
Assert-NativeSuccess "Docker is not running."

$resolvedInstallDir = [System.IO.Path]::GetFullPath($InstallDir)
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
    & curl.exe -fsSL --retry 3 --connect-timeout 20 -o $archive "https://codeload.github.com/$Repository/zip/refs/tags/v$Version"
    Assert-NativeSuccess "Failed to download the OpenCLI Admin release archive."
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

function New-DeviceClaimCode([int]$Length = 10) {
    $alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    return -join ((New-RandomBytes $Length) | ForEach-Object { $alphabet[$_ -band 31] })
}

function Get-LanIPv4Address {
    try {
        $candidates = foreach ($config in Get-NetIPConfiguration -ErrorAction Stop) {
            if ($config.NetAdapter.Status -ne "Up" -or -not $config.IPv4DefaultGateway) {
                continue
            }
            foreach ($address in @($config.IPv4Address)) {
                if (-not $address.IPAddress) {
                    continue
                }
                $bytes = ([Net.IPAddress]::Parse($address.IPAddress)).GetAddressBytes()
                $private =
                    $bytes[0] -eq 10 -or
                    ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or
                    ($bytes[0] -eq 192 -and $bytes[1] -eq 168)
                if ($private) {
                    [pscustomobject]@{
                        Address = $address.IPAddress
                        Metric = $config.NetIPv4Interface.InterfaceMetric
                    }
                }
            }
        }
        return ($candidates | Sort-Object Metric | Select-Object -First 1).Address
    } catch {
        return $null
    }
}

function Set-EnvValue([string]$Key, [string]$Value) {
    $content = [IO.File]::ReadAllText($envPath)
    $content = [Text.RegularExpressions.Regex]::Replace(
        $content,
        "(?m)^$([Text.RegularExpressions.Regex]::Escape($Key))=.*$",
        "$Key=$Value"
    )
    [IO.File]::WriteAllText($envPath, $content, [Text.UTF8Encoding]::new($false))
}

$apiToken = New-HexSecret 32
$bootstrapToken = New-HexSecret 32
$deviceClaimCode = New-DeviceClaimCode
Set-EnvValue "API_AUTH_TOKEN" $apiToken
Set-EnvValue "BOOTSTRAP_ADMIN_TOKEN" $bootstrapToken
Set-EnvValue "DEVICE_CLAIM_CODE" $deviceClaimCode
Set-EnvValue "SECRET_KEY" (New-HexSecret 32)
Set-EnvValue "CREDENTIAL_ENCRYPTION_KEY" (New-FernetKey)

Push-Location $resolvedInstallDir
try {
    docker compose pull api frontend agent-1
    Assert-NativeSuccess "Failed to pull OpenCLI Admin images."
    docker compose up -d
    Assert-NativeSuccess "Failed to start OpenCLI Admin."

    $frontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { "3010" }
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            Invoke-WebRequest "http://localhost:$frontendPort/login" -UseBasicParsing | Out-Null
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

Write-Host ""
Write-Host "opencli-Razormind $Version is ready."
Write-Host "Console URL: http://localhost:$frontendPort"
$lanAddress = Get-LanIPv4Address
if ($lanAddress) {
    Write-Host "LAN URL: http://${lanAddress}:$frontendPort"
}
Write-Host "Device claim code: $deviceClaimCode"
Write-Host "Open the console and use this one-time code to claim the device and create the local administrator."
Write-Host "BOOTSTRAP_ADMIN_TOKEN and API_AUTH_TOKEN were generated and stored only in $envPath for emergency recovery and machine access."
Write-Host "Keep $envPath private."
