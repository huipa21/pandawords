#Requires -Version 7.0
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. (Join-Path $root 'scripts\dev.ps1') help
. (Join-Path $root 'scripts\test-backend.ps1')

$script:healthy = $true
$script:started = @()
$script:invocations = @()
$script:exitCode = 0
$originalUrl = [Environment]::GetEnvironmentVariable('SURREAL_TEST_URL')
$env:SURREAL_TEST_URL = 'ws://127.0.0.1:8101/rpc'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Invoke-WebRequest {
    param($Uri, [switch]$NoProxy, $TimeoutSec)
    Assert-True ($Uri.AbsoluteUri -eq 'http://127.0.0.1:8101/health') 'Wrong health endpoint.'
    if (-not $script:healthy) { throw 'Test service is down' }
    return @{ StatusCode = 200 }
}

function Start-Database {
    param([string]$Service)
    $script:started += $Service
}

function Invoke-Captured {
    param([string]$Executable, [string[]]$Arguments)
    $script:invocations += ,@($Executable, ($Arguments -join ' '))
    return @{ ExitCode = $script:exitCode; Output = @('pytest output') }
}

try {
    Invoke-BackendTests -Arguments @('-Backend', '-UpdateSnapshot')
    Assert-True ($script:started.Count -eq 0) 'A healthy shared server must not be restarted.'
    Assert-True ($script:invocations[0][1] -eq 'run --no-sync pytest -q --update-snapshot') 'Snapshot flag was not forwarded.'

    $script:healthy = $false
    Invoke-BackendTests -Arguments @('-Backend')
    Assert-True ($script:started.Count -eq 1 -and $script:started[0] -eq 'surreal-test') 'Only the test service should start.'
    Assert-True ($script:invocations[1][1] -eq 'run --no-sync pytest -q') 'Unexpected pytest command.'

    $script:exitCode = 3
    $failed = $false
    try { Invoke-BackendTests -Arguments @('-Backend') }
    catch { $failed = $_.Exception.Message -match 'exit code 3' }
    Assert-True $failed 'A pytest failure must propagate.'

    $failed = $false
    try { Invoke-BackendTests -Arguments @('-Frontend') }
    catch { $failed = $_.Exception.Message -match 'Unsupported test argument' }
    Assert-True $failed 'Unimplemented selectors must fail explicitly.'
    $failed = $false
    try { Invoke-BackendTests }
    catch { $failed = $_.Exception.Message -match 'Use test -Backend' }
    Assert-True $failed 'The default command must not pretend to run all layers.'
    Write-Host 'PASS: healthy reuse, test-only startup, snapshot forwarding, failure propagation, selector validation.'
}
finally {
    if ($null -eq $originalUrl) { Remove-Item Env:SURREAL_TEST_URL -ErrorAction SilentlyContinue }
    else { $env:SURREAL_TEST_URL = $originalUrl }
}
