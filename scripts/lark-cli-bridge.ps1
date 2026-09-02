param(
    [int]$Port = 8765,
    [string]$Prefix = "http://127.0.0.1:8765/"
)

$ErrorActionPreference = "Stop"

function Invoke-LocalCli {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $false)][string[]]$Arguments = @()
    )
    # Invoke the native npm shim directly. Running the PowerShell wrapper as a
    # child process can normalize escaped newlines inside JSON cell values into
    # literal newlines before the HTTP response is written.
    $command = (Get-Command "$Name.cmd" -CommandType Application -ErrorAction Stop).Source
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    if ($Name -eq "lark-cli") {
        # Avoid the PowerShell/cmd shim entirely: the shim's child-process
        # output is not stable for multiline Feishu cell values.
        $node = Get-Command node -CommandType Application -ErrorAction Stop |
            Where-Object { $_.Source -match '\\node\.exe$' } |
            Select-Object -First 1
        if (-not $node) { throw "node.exe was not found" }
        $startInfo.FileName = $node.Source
        $startInfo.ArgumentList.Add((Join-Path (Split-Path $command -Parent) "node_modules\@larksuite\cli\scripts\run.js"))
    } else {
        $startInfo.FileName = $command
    }
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $startInfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    foreach ($argument in $Arguments) { $startInfo.ArgumentList.Add([string]$argument) }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    $process.Start() | Out-Null
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    return [pscustomobject]@{
        returncode = $process.ExitCode
        stdout = $stdout
        stderr = $stderr
    }
}

$listener = [System.Net.HttpListener]::new()
$listener.Prefixes.Add($Prefix)
$listener.Start()

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        $response = $context.Response
        try {
            $path = $context.Request.Url.AbsolutePath
            if ($context.Request.HttpMethod -ne "POST" -or $path -notin @("/feishu/records", "/doubao")) {
                $response.StatusCode = 404
                $body = @{ error = "not_found" } | ConvertTo-Json -Compress
            } elseif (($env:LARK_CLI_BRIDGE_TOKEN ?? "") -and
                $context.Request.Headers["X-Lark-CLI-Bridge-Token"] -ne $env:LARK_CLI_BRIDGE_TOKEN) {
                $response.StatusCode = 401
                $body = @{ error = "unauthorized" } | ConvertTo-Json -Compress
            } else {
                $reader = [System.IO.StreamReader]::new($context.Request.InputStream)
                try { $request = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
                if ($path -eq "/doubao") {
                    $command = [string]$request.command
                    if ($command -notin @("ask", "read", "status", "whoami")) {
                        throw "unsupported doubao command"
                    }
                    $args = @("doubao", $command)
                    if ($request.args) { $args += @($request.args | ForEach-Object { [string]$_ }) }
                    if ($command -eq "ask") {
                        $question = [string]$request.args[0]
                        if (-not $question) { throw "doubao ask requires a question" }
                        $open = Invoke-LocalCli -Name "opencli" -Arguments @(
                            "browser", "doubao-workflow", "open", "https://www.doubao.com/chat", "--window", "background"
                        )
                        if ($open.returncode -ne 0) { throw "could not open Doubao browser session" }
                        $wait = Invoke-LocalCli -Name "opencli" -Arguments @(
                            "browser", "doubao-workflow", "wait", "time", "3"
                        )
                        if ($wait.returncode -ne 0) { throw "Doubao browser session did not become ready" }
                        $fill = Invoke-LocalCli -Name "opencli" -Arguments @(
                            "browser", "doubao-workflow", "fill", '[contenteditable="true"]', $question
                        )
                        if ($fill.returncode -ne 0) { throw "could not fill the Doubao question" }
                        $send = Invoke-LocalCli -Name "opencli" -Arguments @(
                            "browser", "doubao-workflow", "click", "#flow-end-msg-send"
                        )
                        if ($send.returncode -ne 0) { throw "could not send the Doubao question" }
                        $settle = Invoke-LocalCli -Name "opencli" -Arguments @(
                            "browser", "doubao-workflow", "wait", "time", "25"
                        )
                        if ($settle.returncode -ne 0) { throw "Doubao response wait failed" }
                        $extract = Invoke-LocalCli -Name "opencli" -Arguments @(
                            "browser", "doubao-workflow", "extract", "--selector", "main", "--chunk-size", "20000"
                        )
                        if ($extract.returncode -ne 0) { throw "could not read the Doubao answer" }
                        $page = $extract.stdout | ConvertFrom-Json
                        $assistantText = [string]$page.content
                        if (-not $assistantText) { throw "Doubao returned no visible answer" }
                        $stdout = @(
                            @{ Role = "User"; Text = $question },
                            @{ Role = "Assistant"; Text = $assistantText },
                            @{ Role = "System"; Text = "Doubao browser conversation"; Url = [string]$page.url }
                        ) | ConvertTo-Json -Compress
                        $body = @{ returncode = 0; stdout = $stdout; stderr = "" } | ConvertTo-Json -Compress
                    } else {
                        $run = Invoke-LocalCli -Name "opencli" -Arguments $args
                        if ($run.returncode -ne 0) { throw "opencli doubao failed with exit code $($run.returncode)" }
                        $body = $run | ConvertTo-Json -Compress
                    }
                } else {
                    $appToken = [string]$request.app_token
                    $tableId = [string]$request.table_id
                    if (-not $appToken -or -not $tableId) { throw "app_token and table_id are required" }
                    $limit = [Math]::Min([Math]::Max([int]$request.limit, 1), 200)
                    $offset = [Math]::Max([int]$request.offset, 0)
                    $args = @(
                        "base", "+record-list", "--base-token", $appToken,
                        "--table-id", $tableId, "--limit", "$limit", "--format", "json"
                    )
                    if ($request.view_id) { $args += @("--view-id", [string]$request.view_id) }
                    if ($request.profile) { $args += @("--profile", [string]$request.profile) }
                    if ($offset -gt 0) { $args += @("--offset", "$offset") }
                    $run = Invoke-LocalCli -Name "lark-cli" -Arguments $args
                    if ($run.returncode -ne 0) {
                        throw "lark-cli failed with exit code $($run.returncode): $($run.stderr.ToString().Trim())"
                    }
                    $body = [string]$run.stdout
                }
            }
        } catch {
            $response.StatusCode = 500
            $body = @{ error = "bridge_error"; message = $_.Exception.Message } | ConvertTo-Json -Compress
        }
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
        $response.ContentType = "application/json; charset=utf-8"
        $response.ContentLength64 = $bytes.Length
        $response.OutputStream.Write($bytes, 0, $bytes.Length)
        $response.Close()
    }
} finally {
    $listener.Stop()
    $listener.Close()
}
