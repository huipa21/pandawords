function Invoke-ProjectCommand {
    param([string]$Project, [string]$Executable, [string[]]$Arguments)
    Push-Location (Join-Path (Split-Path -Parent $PSScriptRoot) $Project)
    try { [void](Invoke-Quiet $Executable $Arguments) }
    finally { Pop-Location }
}

function Invoke-Checks {
    param([string[]]$Arguments = @())
    if ($Arguments.Count -ne 0) { throw 'check does not accept additional arguments.' }
    Invoke-ProjectCommand backend uv @('run', '--no-sync', 'ruff', 'format', '--check', '.')
    Invoke-ProjectCommand backend uv @('run', '--no-sync', 'ruff', 'check', '.')
    Invoke-ProjectCommand backend uv @('run', '--no-sync', 'basedpyright')
    Invoke-ProjectCommand frontend pnpm @('exec', 'eslint', '.')
    Invoke-ProjectCommand frontend pnpm @('exec', 'vue-tsc', '-b', '--noEmit')
    Write-Host 'Checks passed.'
}

function Invoke-Tests {
    param([string[]]$Arguments = @())
    $selectors = @()
    $snapshot = $false
    foreach ($argument in $Arguments) {
        switch ($argument.ToLowerInvariant()) {
            '-backend' { $selectors += 'Backend' }
            '-frontend' { $selectors += 'Frontend' }
            '-e2e' { $selectors += 'E2E' }
            '-updatesnapshot' { $snapshot = $true }
            default { throw "Unsupported test argument '$argument'." }
        }
    }
    if ($selectors.Count -eq 0) { $selectors = @('Backend', 'Frontend') }
    if ($snapshot -and 'Backend' -notin $selectors) { throw '-UpdateSnapshot requires -Backend.' }
    if ('E2E' -in $selectors) {
        . (Join-Path $PSScriptRoot 'lifecycle.ps1')
        Assert-MainLifecycle
        $frontend = Join-Path (Split-Path -Parent $PSScriptRoot) 'frontend'
        if (@(Get-ChildItem -LiteralPath $frontend -Filter 'playwright.config.*' -File).Count -ne 1) {
            throw 'E2E requires a Playwright config (task 1.6.6); no tests were run.'
        }
        try { [void](Invoke-WebRequest 'http://127.0.0.1:5173/' -NoProxy -TimeoutSec 2) }
        catch { throw 'E2E requires the ready main-worktree dev stack on port 5173. Run up first.' }
    }
    if ('Backend' -in $selectors) {
        . (Join-Path $PSScriptRoot 'test-backend.ps1')
        $backendArguments = @('-Backend')
        if ($snapshot) { $backendArguments += '-UpdateSnapshot' }
        Invoke-BackendTests $backendArguments
    }
    if ('Frontend' -in $selectors) {
        Invoke-ProjectCommand frontend pnpm @('exec', 'vitest', 'run', '--reporter=dot')
    }
    if ('E2E' -in $selectors) {
        Invoke-ProjectCommand frontend pnpm @('exec', 'playwright', 'test')
    }
    Write-Host 'Selected tests passed.'
}
