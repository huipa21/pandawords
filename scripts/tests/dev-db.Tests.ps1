#Requires -Version 7.0

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$devScript = Join-Path $root 'scripts\dev.ps1'
$runId = [guid]::NewGuid().ToString('N').Substring(0, 12)
$project = "pw131-$runId"
$volume = "$project-db"
$network = "${project}_default"
$guardName = "$project-guard"
$guardId = $null

$env:COMPOSE_PROJECT_NAME = $project
$env:PANDAWORDS_DEV_VOLUME = $volume
$env:PANDAWORDS_DEV_PORT = '8100'
$env:PANDAWORDS_TEST_PORT = '8101'
$env:SURREAL_USER = "test_$runId"
$env:SURREAL_PASS = [guid]::NewGuid().ToString('N') + '!$'

. $devScript help

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        throw $Message
    }
}

function Test-PodmanExists {
    param([string]$Kind, [string]$Name)
    $result = Invoke-Captured -Executable 'podman' -Arguments @($Kind, 'exists', $Name)
    if ($result.ExitCode -notin @(0, 1)) {
        throw "Could not check $Kind '$Name' (exit $($result.ExitCode))."
    }
    return $result.ExitCode -eq 0
}

function Get-TestContainer {
    param([string]$Service)
    $ids = @(Invoke-Quiet -Executable 'podman' -Arguments @(
        'ps', '--all', '--no-trunc', '--filter', "label=com.docker.compose.project=$project",
        '--filter', "label=com.docker.compose.service=$Service", '--format', '{{.ID}}'))
    Assert-True ($ids.Count -eq 1) "Expected exactly one $Service container."
    return [string]$ids[0]
}

function Assert-Healthy {
    param([string]$Container)
    $status = Invoke-Quiet -Executable 'podman' -Arguments @(
        'inspect', '--format', '{{.State.Health.Status}}', $Container)
    Assert-True (($status -join '').Trim() -eq 'healthy') "Container $Container is not healthy."
}

function Assert-WebSocket {
    param([int]$Port)
    $socket = [System.Net.WebSockets.ClientWebSocket]::new()
    $socket.Options.Proxy = $null
    $socket.Options.AddSubProtocol('json')
    $timeout = [Threading.CancellationTokenSource]::new([TimeSpan]::FromSeconds(10))
    try {
        [void]$socket.ConnectAsync([Uri]"ws://127.0.0.1:$Port/rpc", $timeout.Token).GetAwaiter().GetResult()
        Assert-True ($socket.State -eq [System.Net.WebSockets.WebSocketState]::Open) "WebSocket on port $Port is not open."
    }
    finally {
        $socket.Dispose()
        $timeout.Dispose()
    }
}

function Invoke-RecordRequest {
    param([int]$Port, [string]$Method, [string]$Marker = '', [switch]$AllowMissing)
    $basic = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(
            "$($env:SURREAL_USER):$($env:SURREAL_PASS)"))
    $headers = @{
        Authorization = "Basic $basic"
        Accept        = 'application/json'
        'Surreal-NS'  = 'main'
        'Surreal-DB'  = 'main'
    }
    $parameters = @{
        Uri                = "http://127.0.0.1:$Port/key/pw131_marker/sentinel"
        Method             = $Method
        Headers            = $headers
        TimeoutSec         = 10
        NoProxy            = $true
        SkipHttpErrorCheck = $true
    }
    if ($Method -eq 'POST') {
        $parameters.ContentType = 'application/json'
        $parameters.Body = @{ marker = $Marker } | ConvertTo-Json -Compress
    }
    $response = Invoke-WebRequest @parameters
    Assert-True ($response.StatusCode -eq 200) "Record request failed on port $Port (HTTP $($response.StatusCode))."
    $results = @(ConvertFrom-Json -InputObject $response.Content)
    if (@($results | Where-Object { $_.status -ne 'OK' }).Count -ne 0) {
        $missing = $AllowMissing -and $results.Count -eq 1 -and
            $results[0].kind -eq 'NotFound' -and $results[0].details.kind -in @('Table', 'Record')
        if (-not $missing) {
            $details = $response.Content.Replace($env:SURREAL_USER, '[redacted]')
            $details = $details.Replace($env:SURREAL_PASS, '[redacted]').Replace($basic, '[redacted]')
            throw "Record request failed on port ${Port}: $details"
        }
    }
    return $response.Content
}

function Assert-Marker {
    param([int]$Port, [string]$Marker, [bool]$Present)
    $body = Invoke-RecordRequest -Port $Port -Method 'GET' -AllowMissing:(-not $Present)
    $found = $body -match ('"marker"\s*:\s*"' + [regex]::Escape($Marker) + '"')
    Assert-True ($found -eq $Present) "Unexpected sentinel state on port $Port."
}

function Invoke-Reset {
    $result = Invoke-Captured -Executable 'pwsh' -Arguments @('-NoProfile', '-File', $devScript, 'reset-db')
    $output = $result.Output -join "`n"
    $basic = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(
            "$($env:SURREAL_USER):$($env:SURREAL_PASS)"))
    Assert-True (-not $output.Contains($env:SURREAL_PASS) -and -not $output.Contains($basic)) 'Reset leaked credentials.'
    return $result
}

function Remove-Guard {
    if ($null -eq $script:guardId) {
        return
    }
    $format = '{{.Name}}|{{ index .Config.Labels "pandawords.test.run" }}'
    $details = Invoke-Quiet -Executable 'podman' -Arguments @('inspect', '--format', $format, $script:guardId)
    Assert-True (($details -join '').Trim().TrimStart('/') -ceq "$guardName|$project") 'Guard ownership mismatch.'
    Write-Host "Cleanup: guard $script:guardId"
    [void](Invoke-Quiet -Executable 'podman' -Arguments @('rm', $script:guardId))
    $script:guardId = $null
}

function Remove-TestResources {
    Remove-Guard
    $ids = @(Invoke-Quiet -Executable 'podman' -Arguments @(
        'ps', '--all', '--no-trunc', '--filter', "label=com.docker.compose.project=$project",
        '--format', '{{.ID}}'))
    foreach ($id in $ids) {
        $format = '{{ index .Config.Labels "com.docker.compose.project" }}|{{ index .Config.Labels "com.docker.compose.service" }}'
        $details = (Invoke-Quiet -Executable 'podman' -Arguments @('inspect', '--format', $format, $id)) -join ''
        Assert-True ($details.Trim() -cin @("$project|surreal-dev", "$project|surreal-test")) 'Container ownership mismatch.'
        Write-Host "Cleanup: container $id ($($details.Trim()))"
        [void](Invoke-Quiet -Executable 'podman' -Arguments @('stop', $id))
        [void](Invoke-Quiet -Executable 'podman' -Arguments @('rm', $id))
    }
    if (Test-PodmanExists -Kind 'volume' -Name $volume) {
        $format = '{{ index .Labels "com.docker.compose.project" }}|{{ index .Labels "com.docker.compose.volume" }}'
        $details = (Invoke-Quiet -Executable 'podman' -Arguments @('volume', 'inspect', '--format', $format, $volume)) -join ''
        Assert-True ($details.Trim() -ceq "$project|dev-data") 'Volume ownership mismatch.'
        $users = @(Invoke-Quiet -Executable 'podman' -Arguments @(
            'ps', '--all', '--filter', "volume=$volume", '--format', '{{.ID}}'))
        Assert-True ($users.Count -eq 0) 'Disposable volume is still in use.'
        Write-Host "Cleanup: volume $volume ($($details.Trim()))"
        [void](Invoke-Quiet -Executable 'podman' -Arguments @('volume', 'rm', $volume))
    }
    if (Test-PodmanExists -Kind 'network' -Name $network) {
        $format = '{{ index .Labels "com.docker.compose.project" }}'
        $details = (Invoke-Quiet -Executable 'podman' -Arguments @('network', 'inspect', '--format', $format, $network)) -join ''
        Assert-True ($details.Trim() -ceq $project) 'Network ownership mismatch.'
        Write-Host "Cleanup: network $network ($($details.Trim()))"
        [void](Invoke-Quiet -Executable 'podman' -Arguments @('network', 'rm', $network))
    }
}

foreach ($resource in @(
        @('container', "$project-surreal-dev-1"), @('container', "$project-surreal-test-1"),
        @('container', $guardName), @('volume', $volume), @('network', $network))) {
    Assert-True (-not (Test-PodmanExists -Kind $resource[0] -Name $resource[1])) "Disposable resource already exists: $($resource[1])."
}
$existing = @(Invoke-Quiet -Executable 'podman' -Arguments @(
    'ps', '--all', '--filter', "label=com.docker.compose.project=$project", '--format', '{{.ID}}'))
Assert-True ($existing.Count -eq 0) 'Disposable Compose project already has containers.'
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8100, 8101 -ErrorAction SilentlyContinue)
Assert-True ($listeners.Count -eq 0) 'Ports 8100 and 8101 must be free before this test.'
$published = @(Invoke-Quiet -Executable 'podman' -Arguments @('ps', '--format', '{{.Ports}}'))
Assert-True (@($published | Where-Object { $_ -match ':(8100|8101)->' }).Count -eq 0) 'A Podman container already publishes a test port.'
foreach ($port in @(8100, 8101)) {
    $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
    $probe.ExclusiveAddressUse = $true
    try {
        $probe.Start()
    }
    catch {
        throw "Port $port cannot be bound; the disposable test was not started."
    }
    finally {
        $probe.Stop()
    }
}
Write-Host "Disposable project: $project; volume: $volume; ports: 8100, 8101"

try {
    Start-Database -Service 'surreal-dev'
    Start-Database -Service 'surreal-test'
    $devContainer = Get-TestContainer -Service 'surreal-dev'
    $testContainer = Get-TestContainer -Service 'surreal-test'
    Assert-Healthy $devContainer
    Assert-Healthy $testContainer
    Assert-WebSocket -Port 8100
    Assert-WebSocket -Port 8101
    $devMounts = @((Invoke-Quiet -Executable 'podman' -Arguments @(
                'inspect', '--format', '{{json .Mounts}}', $devContainer)) | ConvertFrom-Json)
    $testMounts = @((Invoke-Quiet -Executable 'podman' -Arguments @(
                'inspect', '--format', '{{json .Mounts}}', $testContainer)) | ConvertFrom-Json)
    $devVolumes = @($devMounts | Where-Object { $null -ne $_ -and $_.Type -eq 'volume' })
    $testVolumes = @($testMounts | Where-Object { $null -ne $_ -and $_.Type -eq 'volume' })
    Assert-True ($devVolumes.Count -eq 1 -and $devVolumes[0].Name -ceq $volume) 'Unexpected dev volumes.'
    Assert-True ($testVolumes.Count -eq 0) 'The test service must not create persistent volumes.'
    Write-Host 'PASS: both Compose services are healthy on their default ports.'

    $devMarker = "dev_$runId"
    $testMarker = "test_$runId"
    [void](Invoke-RecordRequest -Port 8100 -Method 'POST' -Marker $devMarker)
    [void](Invoke-RecordRequest -Port 8101 -Method 'POST' -Marker $testMarker)
    Assert-Marker -Port 8100 -Marker $devMarker -Present $true
    Assert-Marker -Port 8101 -Marker $testMarker -Present $true

    Stop-Database -Service 'surreal-dev'
    Start-Database -Service 'surreal-dev'
    Assert-Marker -Port 8100 -Marker $devMarker -Present $true
    Stop-Database -Service 'surreal-test'
    Start-Database -Service 'surreal-test'
    Assert-Marker -Port 8101 -Marker $testMarker -Present $false
    [void](Invoke-RecordRequest -Port 8101 -Method 'POST' -Marker $testMarker)
    Write-Host 'PASS: RocksDB persists across restart; test storage is in memory.'

    $originalCompose = (Get-Item Function:\Invoke-DatabaseCompose).ScriptBlock
    try {
        $env:COMPOSE_PROJECT_NAME = "$project-other"
        Set-Item Function:\Invoke-DatabaseCompose -Value { throw 'Unexpected Compose start.' }
        $startRefused = $false
        try {
            Start-Database -Service 'surreal-dev'
        }
        catch {
            $startRefused = $_.Exception.Message -match 'does not belong'
        }
        Assert-True $startRefused 'Start must refuse a volume belonging to another project.'
        $refusal = Invoke-Reset
    }
    finally {
        $env:COMPOSE_PROJECT_NAME = $project
        Set-Item Function:\Invoke-DatabaseCompose -Value $originalCompose
    }
    Assert-True ($refusal.ExitCode -ne 0 -and ($refusal.Output -join "`n") -match 'does not belong') 'Reset must refuse a volume belonging to another project.'
    Assert-Marker -Port 8100 -Marker $devMarker -Present $true

    $guardId = (Invoke-Quiet -Executable 'podman' -Arguments @(
        'create', '--name', $guardName, '--label', "pandawords.test.run=$project", '--image-volume', 'ignore',
        '--mount', "type=volume,source=$volume,destination=/guard",
        'docker.io/surrealdb/surrealdb:v3.3.5', 'start', 'memory')) -join ''
    try {
        Set-Item Function:\Invoke-DatabaseCompose -Value { throw 'Unexpected Compose start.' }
        $startRefused = $false
        try {
            Start-Database -Service 'surreal-dev'
        }
        catch {
            $startRefused = $_.Exception.Message -match 'another container uses'
        }
        Assert-True $startRefused 'Start must refuse a volume used by another container.'
    }
    finally {
        Set-Item Function:\Invoke-DatabaseCompose -Value $originalCompose
    }
    $refusal = Invoke-Reset
    Assert-True ($refusal.ExitCode -ne 0 -and ($refusal.Output -join "`n") -match 'another container uses') 'Reset must refuse a volume used by another container.'
    Assert-Marker -Port 8100 -Marker $devMarker -Present $true
    Remove-Guard
    Write-Host 'PASS: start and reset reject foreign ownership and additional volume consumers.'

    $reset = Invoke-Reset
    if ($reset.ExitCode -ne 0) {
        Write-CapturedOutput -Output $reset.Output
        throw "Reset failed (exit $($reset.ExitCode))."
    }
    Assert-True (-not (Test-PodmanExists -Kind 'volume' -Name $volume)) 'Reset did not remove the dev volume.'
    Assert-True ((Get-TestContainer -Service 'surreal-test') -ceq $testContainer) 'Reset altered the test container.'
    Assert-Healthy $testContainer
    Assert-Marker -Port 8101 -Marker $testMarker -Present $true
    $resetAgain = Invoke-Reset
    Assert-True ($resetAgain.ExitCode -eq 0) 'Reset should succeed when the dev volume is absent.'

    Start-Database -Service 'surreal-dev'
    Assert-Marker -Port 8100 -Marker $devMarker -Present $false
    Assert-Marker -Port 8101 -Marker $testMarker -Present $true
    Write-Host 'PASS: reset removes persisted dev data without disturbing the test database.'
}
catch {
    $failure = $_
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8100, 8101 -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        Write-Host "Listener: $($listener.LocalAddress):$($listener.LocalPort)"
    }
    $ids = @(Invoke-Quiet -Executable 'podman' -Arguments @(
        'ps', '--all', '--no-trunc', '--filter', "label=com.docker.compose.project=$project",
        '--format', '{{.ID}}'))
    $basic = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(
            "$($env:SURREAL_USER):$($env:SURREAL_PASS)"))
    foreach ($id in $ids) {
        $bindings = Invoke-Captured -Executable 'podman' -Arguments @('port', $id)
        Write-CapturedOutput -Output $bindings.Output
        $logs = Invoke-Captured -Executable 'podman' -Arguments @('logs', $id)
        foreach ($line in $logs.Output) {
            $redacted = ([string]$line).Replace($env:SURREAL_USER, '[redacted]')
            $redacted = $redacted.Replace($env:SURREAL_PASS, '[redacted]').Replace($basic, '[redacted]')
            Write-Host $redacted
        }
    }
    throw $failure
}
finally {
    Remove-TestResources
}
