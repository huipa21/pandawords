. (Join-Path $PSScriptRoot 'processes.ps1')

function Assert-MainLifecycle {
    $root = Split-Path -Parent $PSScriptRoot
    if ([IO.Path]::GetFullPath($root) -ne [IO.Path]::GetFullPath($script:MainRoot)) {
        throw 'up/down/E2E are main-worktree only; shared ports must not be used from a linked worktree.'
    }
}

function Assert-FreePort {
    param([int]$Port)
    if (@([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
        Where-Object Port -eq $Port).Count -ne 0) {
        throw "Port $Port is occupied; refusing to take over an unrelated service."
    }
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Any, $Port)
    $listener.ExclusiveAddressUse = $true
    try { $listener.Start() }
    catch { throw "Port $Port is occupied; refusing to take over an unrelated service." }
    finally { $listener.Stop() }
}

function Get-OwnedDevDatabase {
    $context = Get-DatabaseContext
    $ids = @(Invoke-Quiet podman @(
        'ps', '--all', '--no-trunc',
        '--filter', "label=com.docker.compose.project=$($context.Project)",
        '--filter', 'label=com.docker.compose.service=surreal-dev', '--format', '{{.ID}}'))
    if ($ids.Count -gt 1) { throw 'Multiple dev database containers; refusing ambiguous ownership.' }
    if ($ids.Count -eq 0) { return $null }
    return [string]$ids[0]
}

function Stop-OwnedDevDatabase {
    param([string]$Id)
    if (-not $Id) { return }
    $context = Get-DatabaseContext
    $result = Invoke-Captured podman @('inspect', '--format',
        '{{ index .Config.Labels "com.docker.compose.project" }}|{{ index .Config.Labels "com.docker.compose.service" }}', $Id)
    if ($result.ExitCode -ne 0) { return }
    if (($result.Output -join '').Trim() -cne "$($context.Project)|surreal-dev") {
        throw 'Database ownership mismatch; refusing to stop it.'
    }
    [void](Invoke-Quiet podman @('stop', $Id))
}

function Save-DevState {
    param($State, [string]$Path)
    $State | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath "$Path.new"
    Move-Item -LiteralPath "$Path.new" -Destination $Path -Force
}

function Stop-DevState {
    param($State, [switch]$KeepDatabase)
    foreach ($name in @('vite', 'worker', 'api')) {
        if ($State.Processes.Contains($name)) { Stop-OwnedProcess $State.Processes[$name] }
    }
    if (-not $KeepDatabase) { Stop-OwnedDevDatabase $State.Database }
}

function Invoke-DevLifecycle {
    param([ValidateSet('up', 'down')][string]$Action)
    Assert-MainLifecycle
    $directory = Join-Path $script:MainRoot '.dev'
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $path = Join-Path $directory 'pids.json'
    try {
        $lock = [IO.File]::Open((Join-Path $directory 'lifecycle.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    }
    catch { throw 'Another up/down operation is in progress.' }
    try {
        $state = if (Test-Path -LiteralPath $path) {
            Get-Content -LiteralPath $path -Raw | ConvertFrom-Json -AsHashtable
        } else { @{ Database = ''; Processes = @{} } }
        if ($Action -eq 'down') {
            Stop-DevState $state
            Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
            Write-Host 'Development stack stopped.'
            return
        }
        if ($state.Processes.Count -gt 0) {
            if ($state.Processes.Count -eq 3 -and
                @($state.Processes.Values | Where-Object { -not (Test-OwnedProcess $_) }).Count -eq 0) {
                Wait-DevReady $state.Processes.api -Url 'http://127.0.0.1:8000/api/readyz'
                Wait-DevReady $state.Processes.vite -Url 'http://127.0.0.1:5173/'
                Wait-DevReady $state.Processes.worker -LogPattern 'database_connected'
                Write-DevUrls
                return
            }
            Stop-DevState $state -KeepDatabase
            $state.Processes = @{}
            Save-DevState $state $path
        }
        Assert-FreePort 8000
        Assert-FreePort 5173
        $existing = Get-OwnedDevDatabase
        $wasRunning = $false
        if ($existing) {
            $wasRunning = ((Invoke-Quiet podman @('inspect', '--format', '{{.State.Running}}', $existing)) -join '').Trim() -eq 'true'
        }
        if (-not $wasRunning) { Assert-FreePort 8100 }
        if ($env:APP_ENV -and $env:APP_ENV -ne 'development') { throw 'up requires APP_ENV=development.' }
        foreach ($setting in @(@('API_PORT', '8000'), @('WEB_DEV_PORT', '5173'), @('PANDAWORDS_DEV_PORT', '8100'))) {
            $value = [Environment]::GetEnvironmentVariable($setting[0])
            if ($value -and $value -ne $setting[1]) { throw "up requires $($setting[0])=$($setting[1])." }
        }
        if ($env:SURREAL_URL -and $env:SURREAL_URL -notmatch '^ws://(localhost|127\.0\.0\.1):8100/rpc$') {
            throw 'up requires the loopback development database on port 8100.'
        }
        $state = @{ Database = ''; Processes = @{} }
        try {
            Start-Database surreal-dev
            $state.Database = Get-OwnedDevDatabase
            if (-not $state.Database) { throw 'Started database has no owned container.' }
            Save-DevState $state $path
            $backend = Join-Path $script:MainRoot 'backend'
            Push-Location $backend
            try {
                [void](Invoke-Quiet uv @('run', '--no-sync', 'python', '-m', 'app.db.migrate'))
                [void](Invoke-Quiet uv @('run', '--no-sync', 'python', '-m', 'app.db.seed'))
            }
            finally { Pop-Location }
            $state.Processes.api = Start-OwnedProcess api uv @(
                'run', '--no-sync', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', '8000', '--no-proxy-headers', '--no-access-log'
            ) $backend $directory
            Save-DevState $state $path
            Wait-DevReady $state.Processes.api -Url 'http://127.0.0.1:8000/api/readyz'
            $state.Processes.worker = Start-OwnedProcess worker uv @(
                'run', '--no-sync', 'python', '-u', '-m', 'app.worker'
            ) $backend $directory
            Save-DevState $state $path
            Wait-DevReady $state.Processes.worker -LogPattern 'database_connected'
            $state.Processes.vite = Start-OwnedProcess vite pnpm @(
                'exec', 'vite', '--host', '127.0.0.1', '--port', '5173', '--strictPort'
            ) (Join-Path $script:MainRoot 'frontend') $directory
            Save-DevState $state $path
            Wait-DevReady $state.Processes.vite -Url 'http://127.0.0.1:5173/'
            Write-DevUrls
        }
        catch {
            $failure = $_
            # Compose can fail its health wait after starting the container.
            if (-not $state.Database) { $state.Database = Get-OwnedDevDatabase }
            Stop-DevState $state -KeepDatabase:$wasRunning
            Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
            throw $failure
        }
    }
    finally { $lock.Dispose() }
}

function Write-DevUrls {
    Write-Host 'Web: http://localhost:5173'
    Write-Host 'API: http://localhost:8000/docs'
    Write-Host 'Database: http://localhost:8100'
}
