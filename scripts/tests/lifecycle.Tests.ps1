#Requires -Version 7.0
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. (Join-Path $root 'scripts\dev.ps1') help
. (Join-Path $root 'scripts\lifecycle.ps1')
$directory = Join-Path $root ".dev\process test-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory $directory -Force | Out-Null
$owned = @()
$unrelated = $null

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}
function Wait-File {
    param([string]$Path)
    $deadline = [datetime]::UtcNow.AddSeconds(20)
    while (-not (Test-Path -LiteralPath $Path)) {
        if ([datetime]::UtcNow -gt $deadline) { throw "Missing fixture output $Path" }
        Start-Sleep -Milliseconds 100
    }
}
function Assert-Gone {
    param([int[]]$Ids)
    $deadline = [datetime]::UtcNow.AddSeconds(10)
    do {
        $remaining = @($Ids | Where-Object { $null -ne (Get-Process -Id $_ -ErrorAction SilentlyContinue) })
        if ($remaining.Count -eq 0) { return }
        Start-Sleep -Milliseconds 100
    } while ([datetime]::UtcNow -lt $deadline)
    throw "Owned child processes survived: $($remaining -join ', ')"
}

try {
    $leaf = Join-Path $directory 'leaf.cjs'
    $wrapper = Join-Path $directory 'wrapper.cjs'
    @'
require('node:fs').writeFileSync(process.argv[2], String(process.pid));
setTimeout(() => {}, 120000);
'@ | Set-Content -LiteralPath $leaf
    @'
const [leaf, output, parentOutput, exitEarly] = process.argv.slice(2);
require('node:child_process').spawn(process.execPath, [leaf, output], {stdio: 'inherit'});
require('node:fs').writeFileSync(parentOutput, String(process.pid));
if (exitEarly) setTimeout(() => process.exit(0), 1000);
'@ | Set-Content -LiteralPath $wrapper
    $leafOutput = Join-Path $directory 'leaf.pid'
    $parentOutput = Join-Path $directory 'wrapper.pid'
    $entry = Start-OwnedProcess fixture node @($wrapper, $leaf, $leafOutput, $parentOutput) $directory $directory
    $owned += $entry
    Wait-File $leafOutput
    Wait-File $parentOutput
    $ids = @($entry.Pid, [int](Get-Content $parentOutput), [int](Get-Content $leafOutput))
    Assert-True (Test-OwnedProcess $entry) 'Supervisor ownership was not recognized.'
    $stale = $entry.PSObject.Copy()
    $stale.StartTicks--
    Stop-OwnedProcess $stale
    Assert-True (Test-OwnedProcess $entry) 'A stale timestamp stopped a live process.'
    $wrongToken = $entry.PSObject.Copy()
    $wrongToken.Token = [guid]::NewGuid().ToString('N')
    Assert-True (-not (Test-OwnedProcess $wrongToken)) 'A wrong ownership token was accepted.'
    $unrelated = Start-Process node -ArgumentList @('-e', '"setTimeout(() => {}, 120000)"') -PassThru
    $reused = $entry.PSObject.Copy()
    $reused.Pid = $unrelated.Id
    $reused.StartTicks = $unrelated.StartTime.ToUniversalTime().Ticks
    Stop-OwnedProcess $reused
    Assert-True (-not $unrelated.HasExited) 'An unrelated process with a reused PID was stopped.'
    Stop-OwnedProcess $entry
    Assert-Gone $ids
    Stop-OwnedProcess $entry

    # A wrapper exiting on its own must also close its job and kill the orphan leaf.
    $leafOutput = Join-Path $directory 'early-leaf.pid'
    $parentOutput = Join-Path $directory 'early-wrapper.pid'
    $entry = Start-OwnedProcess early node @($wrapper, $leaf, $leafOutput, $parentOutput, 'true') $directory $directory
    $owned += $entry
    Wait-File $parentOutput
    Assert-Gone @($entry.Pid, [int](Get-Content $parentOutput))
    if (Test-Path $leafOutput) { Assert-Gone @([int](Get-Content $leafOutput)) }

    $cmd = Join-Path $directory 'wrapper.cmd'
    [IO.File]::WriteAllText($cmd, "@echo off`r`n`"$((Get-Command node).Source)`" `"%~dp0leaf.cjs`" `"%~dp0cmd-leaf.pid`"`r`n")
    $entry = Start-OwnedProcess cmd $cmd @() $directory $directory
    $owned += $entry
    $cmdLeaf = Join-Path $directory 'cmd-leaf.pid'
    Wait-File $cmdLeaf
    $cmdIds = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($entry.Pid)" |
        ForEach-Object { [int]$_.ProcessId })
    Stop-OwnedProcess $entry
    Assert-Gone (@($entry.Pid, [int](Get-Content $cmdLeaf)) + $cmdIds)

    $leafOutput = Join-Path $directory 'shim-leaf.pid'
    $parentOutput = Join-Path $directory 'shim-wrapper.pid'
    $entry = Start-OwnedProcess shim pnpm @('exec', 'node', $wrapper, $leaf, $leafOutput, $parentOutput) (Join-Path $root 'frontend') $directory
    $owned += $entry
    Wait-File $leafOutput
    Wait-File $parentOutput
    $snapshot = @(Get-CimInstance Win32_Process)
    $tree = @([int]$entry.Pid)
    do {
        $children = @($snapshot | Where-Object { [int]$_.ParentProcessId -in $tree -and [int]$_.ProcessId -notin $tree } |
            ForEach-Object { [int]$_.ProcessId })
        $tree += $children
    } while ($children.Count -gt 0)
    Stop-OwnedProcess $entry
    Assert-Gone ($tree + @([int](Get-Content $leafOutput), [int](Get-Content $parentOutput)))

    $entry = Start-OwnedProcess failure node @('-e', "setTimeout(() => { console.error('fixture_failure'); process.exit(7); }, 1000)") $directory $directory
    $owned += $entry
    $failed = $false
    try { Wait-DevReady $entry -LogPattern 'never-ready' -TimeoutSeconds 5 }
    catch { Write-Host $_; $failed = $_.Exception.Message -match 'Readiness failed' }
    Assert-True $failed 'A crashing launcher was reported as ready.'
    Assert-Gone @($entry.Pid)
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        $failed = $false
        try { Assert-FreePort $listener.LocalEndpoint.Port }
        catch { $failed = $_.Exception.Message -match 'occupied' }
        Assert-True $failed 'An occupied port was taken over.'
    }
    finally { $listener.Stop() }
    $failed = $false
    try { Assert-MainLifecycle }
    catch { $failed = $_.Exception.Message -match 'main-worktree only' }
    if ($root -ne $script:MainRoot) { Assert-True $failed 'Linked-worktree lifecycle was allowed.' }

    # Exercise the real orchestration and persistence with real owned processes,
    # but fake DB/readiness interfaces: never bind or start the shared dev stack.
    $script:MainRoot = $directory
    New-Item -ItemType Directory -Path (Join-Path $directory 'backend'), (Join-Path $directory 'frontend') -Force | Out-Null
    $script:databaseStopped = @()
    $script:databaseRunning = $false
    $script:launches = @()
    $script:failOn = 'worker'
    $script:realStart = (Get-Command Start-OwnedProcess).ScriptBlock
    function Assert-MainLifecycle { }
    function Assert-FreePort { param([int]$Port) }
    function Start-Database { param([string]$Service) }
    function Get-OwnedDevDatabase { return 'fixture-owned-container' }
    function Stop-OwnedDevDatabase { param([string]$Id); if ($Id) { $script:databaseStopped += $Id } }
    function Invoke-Quiet {
        param([string]$Executable, [string[]]$Arguments)
        if ($Arguments -contains 'inspect') { return [string]$script:databaseRunning }
    }
    function Start-OwnedProcess {
        param([string]$Name, [string]$Executable, [string[]]$Arguments, [string]$Directory, [string]$StateDirectory)
        $entry = & $script:realStart $Name node @('-e', 'setTimeout(() => {}, 120000)') $Directory $StateDirectory
        $script:launches += $entry
        return $entry
    }
    function Wait-DevReady {
        param($Entry, [string]$Url = '', [string]$LogPattern = '')
        if ($script:failOn -and (Split-Path -Leaf $Entry.Log) -eq "$($script:failOn).log") {
            throw 'fixture readiness failure'
        }
        Assert-True (Test-OwnedProcess $Entry) 'Readiness checked an unowned fixture process.'
    }
    $originalEnv = @{}
    foreach ($name in @('APP_ENV', 'API_PORT', 'WEB_DEV_PORT', 'PANDAWORDS_DEV_PORT', 'SURREAL_URL')) {
        $originalEnv[$name] = [Environment]::GetEnvironmentVariable($name)
        [Environment]::SetEnvironmentVariable($name, $null)
    }
    try {
        $failed = $false
        try { Invoke-DevLifecycle up } catch { $failed = $_.Exception.Message -match 'fixture readiness failure' }
        Assert-True $failed 'Partial startup failure was lost.'
        Assert-Gone @($script:launches | ForEach-Object Pid)
        Assert-True ($script:databaseStopped.Count -eq 1) 'Rollback did not stop the newly started DB.'
        Assert-True (-not (Test-Path (Join-Path $directory '.dev\pids.json'))) 'Failed startup left active PID state.'
        $script:databaseRunning = $true
        try { Invoke-DevLifecycle up } catch { }
        Assert-Gone @($script:launches | ForEach-Object Pid)
        Assert-True ($script:databaseStopped.Count -eq 1) 'Rollback stopped a pre-existing DB.'
        $script:failOn = ''
        Invoke-DevLifecycle up
        $count = $script:launches.Count
        Invoke-DevLifecycle up
        Assert-True ($script:launches.Count -eq $count) 'Repeated up duplicated processes.'
        Invoke-DevLifecycle down
        Invoke-DevLifecycle down
        Assert-Gone @($script:launches | ForEach-Object Pid)
        Assert-True ($script:databaseStopped.Count -eq 2) 'Repeated down stopped a non-recorded DB.'
    }
    finally {
        foreach ($entry in $script:launches) { Stop-OwnedProcess $entry }
        foreach ($name in $originalEnv.Keys) { [Environment]::SetEnvironmentVariable($name, $originalEnv[$name]) }
        Remove-Item -LiteralPath (Join-Path $directory '.dev\pids.json') -Force -ErrorAction SilentlyContinue
    }
    Write-Host 'PASS: owned tree cleanup, orphan cleanup, stale/reused PID guard, readiness failure, occupied port, main-worktree guard.'
    Write-Host 'PASS: persisted PID state, partial startup rollback, pre-existing DB preservation, idempotent up/down (isolated fake services).'
}
catch { Write-Host $_; Write-Host $_.ScriptStackTrace; throw }
finally {
    foreach ($entry in $owned) { Stop-OwnedProcess $entry }
    if ($null -ne $unrelated -and -not $unrelated.HasExited) { $unrelated.Kill(); $unrelated.WaitForExit() }
    $deadline = [datetime]::UtcNow.AddSeconds(5)
    while (Test-Path -LiteralPath $directory) {
        try { Remove-Item -LiteralPath $directory -Recurse -Force }
        catch {
            if ([datetime]::UtcNow -gt $deadline) { throw }
            Start-Sleep -Milliseconds 100
        }
    }
}
