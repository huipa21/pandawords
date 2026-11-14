#Requires -Version 7.0

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$env:NODE_TLS_REJECT_UNAUTHORIZED = '1'
$env:LEFTHOOK = '1'

foreach ($name in @(
        'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_PREFIX',
        'GIT_CONFIG_COUNT', 'GIT_CONFIG_PARAMETERS', 'LEFTHOOK_EXCLUDE', 'LEFTHOOK_SKIP'
    )) {
    Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$testRoot = Join-Path (Join-Path $repoRoot '.dev') "lefthook-test-$([guid]::NewGuid().ToString('N'))"
$links = [System.Collections.Generic.List[string]]::new()
$pushed = $false
$synthetic = 'LEFTHOOK_SYNTHETIC=not-a-secret'

function Invoke-External {
    param(
        [Parameter(Mandatory)][string]$Executable,
        [Parameter()][string[]]$Arguments = @(),
        [switch]$ExpectFailure
    )

    $output = @(& $Executable @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    $text = $output -join "`n"
    if (($ExpectFailure -and $exitCode -eq 0) -or (-not $ExpectFailure -and $exitCode -ne 0)) {
        throw "'$Executable $($Arguments -join ' ')' returned $exitCode.`n$text"
    }

    return $text
}

function Invoke-Git {
    param(
        [Parameter(Mandatory)][string[]]$Arguments,
        [switch]$ExpectFailure
    )

    return Invoke-External -Executable 'git' -Arguments $Arguments -ExpectFailure:$ExpectFailure
}

function Write-TestFile {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Content)

    $destination = Join-Path $testRoot $Path
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    [System.IO.File]::WriteAllText($destination, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Copy-ProjectFile {
    param([Parameter(Mandatory)][string]$Path)

    $destination = Join-Path $testRoot $Path
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $repoRoot $Path) -Destination $destination
}

function Add-TestLink {
    param([Parameter(Mandatory)][string]$Path)

    $link = Join-Path $testRoot $Path
    $target = (Resolve-Path -LiteralPath (Join-Path $repoRoot $Path)).Path
    $type = if ($IsWindows) { 'Junction' } else { 'SymbolicLink' }
    New-Item -ItemType $type -Path $link -Target $target | Out-Null
    $links.Add($link)
}

function Add-TestFile {
    param([Parameter(Mandatory)][string]$Path)

    [void](Invoke-Git -Arguments @('add', '-f', '--', $Path))
}

function Assert-Commit {
    param(
        [Parameter(Mandatory)][string]$Description,
        [string]$FailureText = ''
    )

    $output = Invoke-Git -Arguments @('commit', '--no-gpg-sign', '-m', $Description) `
        -ExpectFailure:($FailureText.Length -gt 0)
    if ($FailureText -and -not $output.Contains($FailureText)) {
        throw "Expected '$FailureText' for '$Description'.`n$output"
    }
    if ($output.Contains($synthetic)) {
        throw "The hook printed synthetic environment-file contents for '$Description'."
    }
    Write-Host "PASS $Description"
}

try {
    New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
    $template = Join-Path $testRoot 'empty-template'
    New-Item -ItemType Directory -Path $template | Out-Null
    Push-Location $testRoot
    $pushed = $true
    Write-TestFile -Path 'empty-gitconfig' -Content "`n"
    $env:GIT_CONFIG_GLOBAL = Join-Path $testRoot 'empty-gitconfig'
    $env:GIT_CONFIG_NOSYSTEM = '1'

    [void](Invoke-Git -Arguments @('init', '--quiet', "--template=$template"))
    $commonDir = (Resolve-Path -LiteralPath (Invoke-Git -Arguments @('rev-parse', '--git-common-dir'))).Path
    $expectedGitDir = (Resolve-Path -LiteralPath (Join-Path $testRoot '.git')).Path
    if ($commonDir -ne $expectedGitDir) {
        throw 'The test repository does not have its own Git directory.'
    }
    New-Item -ItemType Directory -Path (Join-Path $expectedGitDir 'hooks') -Force | Out-Null
    [void](Invoke-Git -Arguments @('config', '--local', 'core.autocrlf', 'false'))
    [void](Invoke-Git -Arguments @('config', '--local', 'user.name', 'Lefthook Test'))
    [void](Invoke-Git -Arguments @('config', '--local', 'user.email', 'lefthook-test@example.invalid'))

    $projectFiles = @(
        'lefthook.yml',
        'package.json',
        'pnpm-workspace.yaml',
        (Join-Path 'backend' 'pyproject.toml'),
        (Join-Path 'backend' 'uv.lock'),
        (Join-Path 'frontend' 'eslint.config.mjs'),
        (Join-Path 'frontend' 'package.json'),
        (Join-Path 'scripts' 'dev.ps1')
        (Join-Path 'scripts' 'setup.ps1')
        (Join-Path 'scripts' 'lint-staged.cjs')
    )
    foreach ($file in $projectFiles) { Copy-ProjectFile -Path $file }
    Copy-Item -LiteralPath (Join-Path $repoRoot 'frontend\eslint-rules') `
        -Destination (Join-Path $testRoot 'frontend\eslint-rules') -Recurse
    Copy-ProjectFile -Path 'frontend\uno.config.ts'
    New-Item -ItemType Directory -Path (Join-Path $testRoot 'frontend\src') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $repoRoot 'frontend\src\design') `
        -Destination (Join-Path $testRoot 'frontend\src\design') -Recurse
    Write-TestFile -Path '.gitignore' -Content "node_modules/`n.venv/`n.env*`n!.env.example`n"
    Write-TestFile -Path '.env.example' -Content "LEFTHOOK_SYNTHETIC=example`n"
    Add-TestLink -Path 'node_modules'
    Add-TestLink -Path (Join-Path 'backend' '.venv')
    Add-TestLink -Path (Join-Path 'frontend' 'node_modules')
    foreach ($file in ($projectFiles + @('.gitignore', '.env.example'))) { Add-TestFile -Path $file }
    [void](Invoke-Git -Arguments @('commit', '--no-gpg-sign', '-m', 'test baseline'))

    $mockSetup = @'
function uv {
    $global:LASTEXITCODE = 0
    if ($args[0] -eq '--version') { 'uv test stub' }
}
function podman {
    $global:LASTEXITCODE = 0
    'podman test stub'
}
function pnpm {
    $global:LASTEXITCODE = 0
    if ($env:NODE_TLS_REJECT_UNAUTHORIZED -ne '1') {
        throw 'Setup did not enable Node TLS verification.'
    }
    if ($args[0] -eq '--version') {
        'pnpm test stub'
    }
    elseif ($args[0] -eq 'install') {
        if ((Get-Location).Path -ne (Join-Path $env:LEFTHOOK_TEST_ROOT 'frontend')) {
            throw 'pnpm install did not run from the test frontend.'
        }
    }
    elseif (($args -join ' ') -eq 'exec lefthook install') {
        if ((Get-Location).Path -ne $env:LEFTHOOK_TEST_ROOT) {
            throw 'lefthook install did not run from the test repository root.'
        }
        $installOutput = @(& node $env:LEFTHOOK_TEST_CLI install 2>&1)
        if ($LASTEXITCODE -ne 0) {
            throw "lefthook installation failed: $($installOutput -join "`n")"
        }
        $installOutput
    }
    else {
        throw "Unexpected pnpm invocation: $args"
    }
}
Remove-Item -LiteralPath Env:NODE_TLS_REJECT_UNAUTHORIZED -ErrorAction SilentlyContinue
& (Join-Path $env:LEFTHOOK_TEST_ROOT (Join-Path 'scripts' 'dev.ps1')) setup
'@
    Write-TestFile -Path 'mock-setup.ps1' -Content $mockSetup
    $env:LEFTHOOK_TEST_ROOT = $testRoot
    $env:LEFTHOOK_TEST_CLI = Join-Path $repoRoot 'node_modules\lefthook\bin\index.js'
    [void](Invoke-External -Executable 'pwsh' -Arguments @('-NoProfile', '-File', (Join-Path $testRoot 'mock-setup.ps1')))
    $hook = Join-Path (Join-Path $expectedGitDir 'hooks') 'pre-commit'
    if (-not (Test-Path -LiteralPath $hook -PathType Leaf)) {
        throw 'Setup did not install the pre-commit hook in the test repository.'
    }
    Remove-Item -LiteralPath (Join-Path $testRoot '.env.dev') -Force
    Write-Host 'PASS setup installs hooks only in the disposable repository'

    $pythonFile = Join-Path 'backend' 'sample file.py'
    $badPython = "def sample( ):`n    return  1`n"
    $goodPython = "def sample() -> int:`n    return 1`n"
    Write-TestFile -Path $pythonFile -Content $badPython
    Add-TestFile -Path $pythonFile
    Assert-Commit -Description 'reject badly formatted Python' -FailureText 'ruff-format failed'
    Write-TestFile -Path $pythonFile -Content $goodPython
    Assert-Commit -Description 'reject badly formatted staged Python with a clean worktree' -FailureText 'ruff-format failed'
    Add-TestFile -Path $pythonFile
    Write-TestFile -Path $pythonFile -Content $badPython
    Assert-Commit -Description 'accept clean staged Python with an unformatted worktree'
    if ([System.IO.File]::ReadAllText((Join-Path $testRoot $pythonFile)) -ne $badPython) {
        throw 'The hook modified unstaged Python changes.'
    }
    Write-TestFile -Path $pythonFile -Content $goodPython

    $lintFile = Join-Path 'backend' 'lint.py'
    Write-TestFile -Path $lintFile -Content "import os`n"
    Add-TestFile -Path $lintFile
    Assert-Commit -Description 'reject Ruff lint errors' -FailureText 'F401'
    Write-TestFile -Path $lintFile -Content "import sys`n`nprint(sys.version)`n"
    Add-TestFile -Path $lintFile
    Assert-Commit -Description 'accept corrected Python'

    $tsFile = Join-Path (Join-Path 'frontend' 'src') 'sample.ts'
    $badTs = "export const value = 1;`n"
    $goodTs = "export const value = 1`n"
    Write-TestFile -Path $tsFile -Content $badTs
    Add-TestFile -Path $tsFile
    Assert-Commit -Description 'reject ESLint errors in staged TypeScript' -FailureText 'style/semi'
    Write-TestFile -Path $tsFile -Content $goodTs
    Assert-Commit -Description 'check staged TypeScript instead of the worktree' -FailureText 'style/semi'
    Add-TestFile -Path $tsFile
    Write-TestFile -Path $tsFile -Content $badTs
    Assert-Commit -Description 'accept clean staged TypeScript with unstaged lint errors'
    if ([System.IO.File]::ReadAllText((Join-Path $testRoot $tsFile)) -ne $badTs) {
        throw 'The hook modified unstaged TypeScript changes.'
    }
    Write-TestFile -Path $tsFile -Content $goodTs

    $vueFile = Join-Path (Join-Path 'frontend' 'src') 'Sample.vue'
    $vue = "<script setup lang=`"ts`">`nconst value: number = 1;`n</script>`n`n<template>`n  <div>{{ value }}</div>`n</template>`n"
    Write-TestFile -Path $vueFile -Content $vue
    Add-TestFile -Path $vueFile
    Assert-Commit -Description 'reject ESLint errors in staged Vue' -FailureText 'style/semi'
    Write-TestFile -Path $vueFile -Content $vue.Replace('1;', '1')
    Add-TestFile -Path $vueFile
    Assert-Commit -Description 'accept corrected Vue'

    $rootTs = 'odd $value''s file.ts'
    Write-TestFile -Path $rootTs -Content $badTs
    Add-TestFile -Path $rootTs
    Assert-Commit -Description 'lint root TypeScript with a shell-sensitive filename' -FailureText 'style/semi'
    Write-TestFile -Path $rootTs -Content $goodTs
    Add-TestFile -Path $rootTs
    Assert-Commit -Description 'accept corrected root TypeScript'

    Write-TestFile -Path '.env.dev' -Content "$synthetic`n"
    Add-TestFile -Path '.env.dev'
    Assert-Commit -Description 'block force-added synthetic .env.dev' -FailureText 'Blocked staged environment files'
    Remove-Item -LiteralPath (Join-Path $testRoot '.env.dev')
    Assert-Commit -Description 'block staged environment content absent from the worktree' -FailureText 'Blocked staged environment files'
    [void](Invoke-Git -Arguments @('rm', '--cached', '--force', '--quiet', '--', '.env.dev'))

    $nestedExample = Join-Path 'config' '.env.example'
    Write-TestFile -Path '.env.example' -Content "LEFTHOOK_SYNTHETIC=updated-example`n"
    Write-TestFile -Path $nestedExample -Content "LEFTHOOK_SYNTHETIC=nested-example`n"
    Add-TestFile -Path '.env.example'
    Add-TestFile -Path $nestedExample
    Assert-Commit -Description 'allow root and nested .env.example files'

    $nestedSecret = Join-Path 'config' '.env.example.local'
    Write-TestFile -Path $nestedSecret -Content "$synthetic`n"
    Add-TestFile -Path $nestedSecret
    Assert-Commit -Description 'block a nested .env.example suffix' -FailureText 'Blocked staged environment files'
    [void](Invoke-Git -Arguments @('rm', '--cached', '--quiet', '--', $nestedSecret))

    $envDirectory = Join-Path (Join-Path 'config' '.env.private') 'settings'
    Write-TestFile -Path $envDirectory -Content "$synthetic`n"
    Add-TestFile -Path $envDirectory
    Assert-Commit -Description 'block files in an .env-prefixed directory' -FailureText 'Blocked staged environment files'
    [void](Invoke-Git -Arguments @('rm', '--cached', '--quiet', '--', $envDirectory))

    Write-TestFile -Path '.env.dev' -Content "$synthetic`n"
    Add-TestFile -Path '.env.dev'
    [void](Invoke-Git -Arguments @('commit', '--no-verify', '--no-gpg-sign', '-m', 'seed synthetic environment file'))
    [void](Invoke-Git -Arguments @('rm', '--quiet', '--', '.env.dev'))
    Assert-Commit -Description 'allow removal of a previously tracked environment file'

    $renameSource = Join-Path 'config' 'ordinary.txt'
    $renameTarget = Join-Path 'config' '.env.renamed'
    Write-TestFile -Path $renameSource -Content "SYNTHETIC=renamed`n"
    Add-TestFile -Path $renameSource
    Assert-Commit -Description 'accept an ordinary configuration file'
    [void](Invoke-Git -Arguments @('mv', '--', $renameSource, $renameTarget))
    $rename = Invoke-Git -Arguments @('diff', '--cached', '--name-status', '-M', '--')
    if (-not $rename.StartsWith('R100')) { throw 'The rename fixture was not detected as a rename.' }
    Assert-Commit -Description 'block a file renamed to an environment file' -FailureText 'Blocked staged environment files'
}
finally {
    if ($pushed) { Pop-Location }
    foreach ($link in $links) {
        if (Test-Path -LiteralPath $link) { (Get-Item -LiteralPath $link -Force).Delete() }
    }
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
