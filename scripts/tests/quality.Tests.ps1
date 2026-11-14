#Requires -Version 7.0
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. (Join-Path $root 'scripts\dev.ps1') help
. (Join-Path $root 'scripts\quality.ps1')
function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}
$script:invocations = @()
$script:failCommand = ''
function Invoke-Quiet {
    param([string]$Executable, [string[]]$Arguments)
    $command = "$Executable $($Arguments -join ' ')"
    $script:invocations += $command
    if ($command -match $script:failCommand -and $script:failCommand) { throw 'fixture exit code 7' }
}
function Invoke-BackendTests {
    param([string[]]$Arguments)
    $script:invocations += "backend $($Arguments -join ' ')"
}
# The backend dot-source defines its runner, so test orchestration with its underlying
# capture and health interfaces, preserving the real selector/pytest implementation.
function Invoke-Captured {
    param([string]$Executable, [string[]]$Arguments)
    $script:invocations += "$Executable $($Arguments -join ' ')"
    return @{ ExitCode = 0; Output = @() }
}
function Invoke-WebRequest { return @{ StatusCode = 200 } }
$originalUrl = $env:SURREAL_TEST_URL
$env:SURREAL_TEST_URL = 'ws://127.0.0.1:8101/rpc'
try {
    Invoke-Checks
    Assert-True ($script:invocations.Count -eq 5) 'check must run all five tools.'
    Assert-True ($script:invocations[0] -match 'ruff format --check') 'Format check was skipped.'
    $script:invocations = @()
    Invoke-Tests
    Assert-True ($script:invocations.Count -eq 2) 'Default tests must run both unit layers.'
    Assert-True ($script:invocations[0] -match 'pytest -q') 'Default omitted backend.'
    Assert-True ($script:invocations[1] -match 'vitest run --reporter=dot') 'Default omitted frontend.'
    $script:invocations = @()
    Invoke-Tests @('-Frontend', '-Backend', '-UpdateSnapshot', '-Frontend')
    Assert-True ($script:invocations.Count -eq 2 -and $script:invocations[0] -match '--update-snapshot') 'Combined selectors or snapshot forwarding failed.'
    $script:failCommand = 'vitest'
    $failed = $false
    try { Invoke-Tests @('-Frontend') } catch { $failed = $_.Exception.Message -match 'exit code 7' }
    Assert-True $failed 'Frontend failures must propagate.'
    foreach ($arguments in @(@('-bogus'), @('-Frontend', '-UpdateSnapshot'))) {
        $failed = $false
        try { Invoke-Tests $arguments } catch { $failed = $true }
        Assert-True $failed 'An invalid selector was accepted.'
    }
    $failed = $false
    try { Invoke-Tests @('-E2E') } catch { $failed = $true }
    Assert-True $failed 'Unconfigured/worktree E2E must fail, not silently skip.'
    Write-Host 'PASS: five checks, default/combined selectors, snapshot flag, failure propagation, E2E guard.'
}
finally {
    if ($null -eq $originalUrl) { Remove-Item Env:SURREAL_TEST_URL -ErrorAction SilentlyContinue }
    else { $env:SURREAL_TEST_URL = $originalUrl }
}
