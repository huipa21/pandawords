#Requires -Version 7.0
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$fixture = Join-Path $root "backend\lifecycle_lint_fixture_$([guid]::NewGuid().ToString('N')).py"
try {
    # A private, new fixture: never alter an existing user source file.
    [IO.File]::WriteAllText($fixture, "print(undefined_lifecycle_fixture)`n")
    $output = @(& pwsh -NoProfile -File (Join-Path $root 'scripts\dev.ps1') check 2>&1)
    if ($LASTEXITCODE -eq 0 -or ($output -join "`n") -notmatch 'F821' -or
        ($output -join "`n") -notmatch 'undefined_lifecycle_fixture') {
        Write-Host ($output -join "`n")
        throw 'check did not propagate the actual Ruff failure with full diagnostics.'
    }
    Write-Host 'PASS: actual check exits nonzero and prints Ruff F821 diagnostics; fixture removed.'
}
finally { Remove-Item -LiteralPath $fixture -Force -ErrorAction SilentlyContinue }
