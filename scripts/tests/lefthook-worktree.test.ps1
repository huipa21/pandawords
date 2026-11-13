#Requires -Version 7.0

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$env:NODE_TLS_REJECT_UNAUTHORIZED = '1'
$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE = 'never'
$env:LEFTHOOK = '1'

foreach ($name in @(
        'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_PREFIX',
        'GIT_CONFIG_COUNT', 'GIT_CONFIG_PARAMETERS', 'LEFTHOOK_EXCLUDE', 'LEFTHOOK_SKIP'
    )) {
    Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
}

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$sandbox = Join-Path (Join-Path $projectRoot '.dev') "lefthook-worktree-$([guid]::NewGuid().ToString('N'))"
$mainRoot = Join-Path $sandbox 'main'
$linkedRoot = Join-Path $sandbox 'linked'
$originalLocation = (Get-Location).Path
$originalPath = $env:PATH
$links = [System.Collections.Generic.List[string]]::new()

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
    param([Parameter(Mandatory)][string[]]$Arguments, [switch]$ExpectFailure)

    return Invoke-External -Executable 'git' -Arguments $Arguments -ExpectFailure:$ExpectFailure
}

function Write-Fixture {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Content
    )

    $destination = Join-Path $Root $Path
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    [System.IO.File]::WriteAllText($destination, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Set-DependencyLink {
    param([Parameter(Mandatory)][string]$Path)

    $link = Join-Path $linkedRoot $Path
    $target = (Resolve-Path -LiteralPath (Join-Path $projectRoot $Path)).Path
    $type = if ($IsWindows) { 'Junction' } else { 'SymbolicLink' }
    New-Item -ItemType $type -Path $link -Target $target | Out-Null
    $links.Add($link)
}

function Remove-DependencyLink {
    param([Parameter(Mandatory)][string]$Path)

    $link = Join-Path $linkedRoot $Path
    (Get-Item -LiteralPath $link -Force).Delete()
    [void]$links.Remove($link)
}

function Add-Fixture {
    param([Parameter(Mandatory)][string]$Path)

    [void](Invoke-Git -Arguments @('add', '-f', '--', $Path))
}

function Assert-Commit {
    param([Parameter(Mandatory)][string]$Description, [string]$FailureText = '')

    $output = Invoke-Git -Arguments @('commit', '--no-gpg-sign', '-m', $Description) `
        -ExpectFailure:($FailureText.Length -gt 0)
    if ($FailureText -and -not $output.Contains($FailureText)) {
        throw "Expected '$FailureText' for '$Description'.`n$output"
    }
    if (-not $output.Contains('lefthook')) {
        throw "The shared test hook did not run for '$Description'.`n$output"
    }
    if ($output.Contains('WORKTREE_SYNTHETIC=not-a-secret')) {
        throw "The hook printed synthetic environment-file contents for '$Description'."
    }
    Write-Host "PASS $Description"
}

try {
    New-Item -ItemType Directory -Path $mainRoot -Force | Out-Null
    $template = Join-Path $sandbox 'empty-template'
    New-Item -ItemType Directory -Path $template | Out-Null
    Write-Fixture -Root $sandbox -Path 'gitconfig' -Content "`n"
    $env:GIT_CONFIG_GLOBAL = Join-Path $sandbox 'gitconfig'
    $env:GIT_CONFIG_NOSYSTEM = '1'

    Set-Location $mainRoot
    [void](Invoke-Git -Arguments @('init', '--quiet', "--template=$template"))
    [void](Invoke-Git -Arguments @('config', '--local', 'core.autocrlf', 'false'))
    [void](Invoke-Git -Arguments @('config', '--local', 'user.name', 'Lefthook Worktree Test'))
    [void](Invoke-Git -Arguments @('config', '--local', 'user.email', 'worktree-test@example.invalid'))
    $commonDir = (Resolve-Path -LiteralPath (Invoke-Git -Arguments @(
                'rev-parse', '--path-format=absolute', '--git-common-dir'
            ))).Path
    $expectedGitDir = (Resolve-Path -LiteralPath (Join-Path $mainRoot '.git')).Path
    if ($commonDir -ne $expectedGitDir) { throw 'The test repository does not have its own Git directory.' }

    $projectFiles = @(
        'lefthook.yml',
        'package.json',
        'pnpm-workspace.yaml',
        (Join-Path 'backend' 'pyproject.toml'),
        (Join-Path 'backend' 'uv.lock'),
        (Join-Path 'frontend' 'eslint.config.mjs'),
        (Join-Path 'frontend' 'package.json')
        (Join-Path 'scripts' 'lint-staged.cjs')
    )
    foreach ($file in $projectFiles) {
        $destination = Join-Path $mainRoot $file
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $projectRoot $file) -Destination $destination
    }
    Write-Fixture -Root $mainRoot -Path '.gitignore' -Content "node_modules/`n.venv/`n.env*`n!.env.example`n"
    foreach ($file in ($projectFiles + @('.gitignore'))) { Add-Fixture -Path $file }
    [void](Invoke-Git -Arguments @('commit', '--no-gpg-sign', '-m', 'test baseline'))

    $module = Join-Path $projectRoot 'node_modules\lefthook\get-exe.js'
    $binary = Invoke-External -Executable 'node' -Arguments @(
        '-p', 'require(process.argv[1]).getExePath()', $module
    )
    $toolDir = Join-Path $sandbox 'tools'
    New-Item -ItemType Directory -Path $toolDir | Out-Null
    $launcher = Join-Path $toolDir $(if ($IsWindows) { 'lefthook.exe' } else { 'lefthook' })
    Copy-Item -LiteralPath $binary -Destination $launcher
    [void](Invoke-External -Executable $launcher -Arguments @('install'))
    $hook = Join-Path (Join-Path $expectedGitDir 'hooks') 'pre-commit'
    if (-not (Test-Path -LiteralPath $hook -PathType Leaf)) {
        throw 'Lefthook did not install in the disposable repository.'
    }
    [void](Invoke-Git -Arguments @('worktree', 'add', '--quiet', '-b', 'linked-test', $linkedRoot, 'HEAD'))
    Copy-Item -LiteralPath (Join-Path $projectRoot 'frontend\eslint-rules') `
        -Destination (Join-Path $linkedRoot 'frontend\eslint-rules') -Recurse
    Copy-Item -LiteralPath (Join-Path $projectRoot 'frontend\uno.config.ts') `
        -Destination (Join-Path $linkedRoot 'frontend\uno.config.ts')
    New-Item -ItemType Directory -Path (Join-Path $linkedRoot 'frontend\src') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $projectRoot 'frontend\src\design') `
        -Destination (Join-Path $linkedRoot 'frontend\src\design') -Recurse

    Set-Location $linkedRoot
    $linkedCommon = (Resolve-Path -LiteralPath (Invoke-Git -Arguments @(
                'rev-parse', '--path-format=absolute', '--git-common-dir'
            ))).Path
    if ($linkedCommon -ne $expectedGitDir) { throw 'The linked worktree is not using the disposable hooks.' }

    $frontendModules = Join-Path 'frontend' 'node_modules'
    $backendVenv = Join-Path 'backend' '.venv'
    Set-DependencyLink -Path 'node_modules'
    Set-DependencyLink -Path $frontendModules
    Set-DependencyLink -Path $backendVenv

    $pythonFile = Join-Path 'backend' 'linked.py'
    $badPython = "def sample( ):`n    return  1`n"
    $goodPython = "def sample() -> int:`n    return 1`n"
    Write-Fixture -Root $linkedRoot -Path $pythonFile -Content $badPython
    Add-Fixture -Path $pythonFile
    Assert-Commit -Description 'linked worktree invokes its Ruff formatter' -FailureText 'ruff-format failed'
    Write-Fixture -Root $linkedRoot -Path $pythonFile -Content $goodPython
    Add-Fixture -Path $pythonFile
    Assert-Commit -Description 'linked worktree accepts corrected Python'

    $tsFile = Join-Path (Join-Path 'frontend' 'src') 'linked.ts'
    $badTs = "export const value = 1;`n"
    $goodTs = "export const value = 1`n"
    Write-Fixture -Root $linkedRoot -Path $tsFile -Content $badTs
    Add-Fixture -Path $tsFile
    Assert-Commit -Description 'linked worktree invokes its ESLint' -FailureText 'style/semi'
    Write-Fixture -Root $linkedRoot -Path $tsFile -Content $goodTs
    Add-Fixture -Path $tsFile
    Assert-Commit -Description 'linked worktree accepts corrected TypeScript'

    Write-Fixture -Root $linkedRoot -Path '.env.dev' -Content "WORKTREE_SYNTHETIC=not-a-secret`n"
    Add-Fixture -Path '.env.dev'
    Assert-Commit -Description 'linked worktree blocks a synthetic environment file' -FailureText 'Blocked staged environment files'
    [void](Invoke-Git -Arguments @('rm', '--cached', '--quiet', '--', '.env.dev'))
    Remove-Item -LiteralPath (Join-Path $linkedRoot '.env.dev')

    $globalRuff = Join-Path $toolDir $(if ($IsWindows) { 'ruff.exe' } else { 'ruff' })
    $ruffPath = if ($IsWindows) {
        Join-Path $projectRoot 'backend\.venv\Scripts\ruff.exe'
    }
    else {
        Join-Path $projectRoot 'backend/.venv/bin/ruff'
    }
    Copy-Item -LiteralPath $ruffPath -Destination $globalRuff
    $env:PATH = $toolDir + [System.IO.Path]::PathSeparator + $originalPath
    Remove-DependencyLink -Path $backendVenv
    $missingPython = Join-Path 'backend' 'missing.py'
    Write-Fixture -Root $linkedRoot -Path $missingPython -Content $goodPython
    Add-Fixture -Path $missingPython
    Assert-Commit -Description 'missing local venv fails despite a global Ruff' `
        -FailureText 'Ruff is missing in this worktree'
    if (Test-Path -LiteralPath (Join-Path $linkedRoot $backendVenv)) {
        throw 'The hook unexpectedly created a local venv.'
    }
    New-Item -ItemType Directory -Path (Join-Path $linkedRoot $backendVenv) | Out-Null
    Assert-Commit -Description 'venv without Ruff fails despite a global Ruff' `
        -FailureText 'Ruff is missing in this worktree'
    Remove-Item -LiteralPath (Join-Path $linkedRoot $backendVenv) -Force
    Set-DependencyLink -Path $backendVenv
    Assert-Commit -Description 'restoring local Ruff permits the commit'
    $env:PATH = $originalPath

    Remove-DependencyLink -Path $frontendModules
    $missingTs = Join-Path (Join-Path 'frontend' 'src') 'missing.ts'
    Write-Fixture -Root $linkedRoot -Path $missingTs -Content $goodTs
    Add-Fixture -Path $missingTs
    Assert-Commit -Description 'missing local frontend node_modules fails' `
        -FailureText 'ESLint dependencies are missing in this worktree'
    Set-DependencyLink -Path $frontendModules
    Assert-Commit -Description 'restoring local ESLint permits the commit'

    Remove-DependencyLink -Path 'node_modules'
    $rootMissing = Join-Path (Join-Path 'frontend' 'src') 'root-missing.ts'
    Write-Fixture -Root $linkedRoot -Path $rootMissing -Content $goodTs
    Add-Fixture -Path $rootMissing
    Assert-Commit -Description 'missing local root node_modules fails' `
        -FailureText 'Lefthook dependencies are missing in this worktree'
    Set-DependencyLink -Path 'node_modules'
    Assert-Commit -Description 'restoring root dependencies permits the commit'
}
finally {
    Set-Location $originalLocation
    $env:PATH = $originalPath
    foreach ($link in $links) {
        if (Test-Path -LiteralPath $link) { (Get-Item -LiteralPath $link -Force).Delete() }
    }
    if (Test-Path -LiteralPath $sandbox) {
        Remove-Item -LiteralPath $sandbox -Recurse -Force
    }
}
