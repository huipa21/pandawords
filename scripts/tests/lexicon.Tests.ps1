#Requires -Version 7.0
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. (Join-Path $root 'scripts\dev.ps1') help
. (Join-Path $root 'scripts\lexicon.ps1')
$script:calls = @()
$script:exitCode = 0

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Invoke-Captured {
    param([string]$Executable, [string[]]$Arguments)
    $script:calls += ,@($Executable, (Get-Location).Path, $Arguments)
    return @{ ExitCode = $script:exitCode; Output = @('synthetic lexicon build failed') }
}

$originalLocation = (Get-Location).Path
Invoke-Lexicon
$call = $script:calls[-1]
Assert-True ($call[0] -eq 'uv') 'lexicon did not invoke uv.'
Assert-True ($call[1] -eq (Join-Path $root 'backend')) 'lexicon used the wrong worktree backend.'
Assert-True (($call[2] -join ' ') -eq 'run --no-sync python -X utf8 -m scripts.lexicon_release') 'Wrong release entrypoint.'
Assert-True ((Get-Location).Path -eq $originalLocation) 'lexicon changed caller location.'
Invoke-Lexicon @('-RawDir', 'C:\fixture source\raw', '-Output', 'C:\fixture source\lexicon.sqlite',
    '-DistDir', 'C:\fixture source\dist', '-Date', '2026-11-14')
$cli = $script:calls[-1][2]
Assert-True ($cli[7] -eq '--raw-dir' -and $cli[8] -eq 'C:\fixture source\raw') 'Raw path was split/lost.'
Assert-True ($cli[9] -eq '--output' -and $cli[11] -eq '--dist-dir' -and $cli[13] -eq '--date') 'Flags were not forwarded.'
foreach ($invalid in @(@('-Bogus', 'x'), @('-RawDir'), @('-Date', ''))) {
    $failed = $false
    try { Invoke-Lexicon $invalid }
    catch { $failed = $_.Exception.Message -like 'lexicon prepare failed:*' }
    Assert-True $failed 'Invalid arguments were accepted.'
}
foreach ($code in @(1, 7)) {
    $script:exitCode = $code
    $failed = $false
    try { Invoke-Lexicon }
    catch { $failed = $_.Exception.Message -like "*exit code $code*" }
    Assert-True $failed 'Release failure did not propagate.'
    Assert-True ((Get-Location).Path -eq $originalLocation) 'Failure changed caller location.'
}
Write-Host 'PASS: lexicon dispatch, explicit path/date flags, argument guards, failure exit and location restoration.'
