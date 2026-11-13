#Requires -Version 7.0

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Command = 'help',

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-MainWorktreeRoot {
    $gitCommand = Get-Command git -ErrorAction SilentlyContinue
    if ($null -eq $gitCommand) {
        throw 'Git is required to locate the main worktree.'
    }

    $commonDirOutput = @(& git -C $PSScriptRoot rev-parse --path-format=absolute --git-common-dir 2>&1)
    if ($LASTEXITCODE -ne 0 -or $commonDirOutput.Count -eq 0) {
        throw "Could not resolve the main worktree root from '$PSScriptRoot'."
    }

    $commonDir = [System.IO.Path]::GetFullPath([string]$commonDirOutput[-1])
    $root = Split-Path -Parent $commonDir
    if (-not (Test-Path -LiteralPath (Join-Path $root '.env.example') -PathType Leaf)) {
        throw "The resolved main worktree '$root' does not contain .env.example."
    }

    return $root
}

function Import-EnvironmentFile {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            $name = $Matches[1]
            $value = $Matches[2]
            if ($value.Length -ge 2 -and
                (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                    ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }

            if (-not (Test-Path -LiteralPath "Env:$name")) {
                Set-Item -Path "Env:$name" -Value $value
            }
        }
    }
}

function Ensure-LogsDirectory {
    $logsDirectory = Join-Path (Join-Path $script:MainRoot '.dev') 'logs'
    New-Item -ItemType Directory -Path $logsDirectory -Force | Out-Null
    return $logsDirectory
}

function Invoke-Captured {
    param(
        [Parameter(Mandatory)][string]$Executable,
        [Parameter()][string[]]$Arguments = @()
    )

    $output = @(& $Executable @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    return [pscustomobject]@{
        ExitCode = $exitCode
        Output   = $output
    }
}

function Write-CapturedOutput {
    param([Parameter()][object[]]$Output = @())

    foreach ($line in $Output) {
        Write-Host $line
    }
}

function Invoke-Quiet {
    param(
        [Parameter(Mandatory)][string]$Executable,
        [Parameter()][string[]]$Arguments = @()
    )

    $result = Invoke-Captured -Executable $Executable -Arguments $Arguments
    if ($result.ExitCode -ne 0) {
        Write-CapturedOutput -Output $result.Output
        throw "'$Executable $($Arguments -join ' ')' failed with exit code $($result.ExitCode)."
    }

    return $result.Output
}

function Invoke-WithFallback {
    param(
        [Parameter(Mandatory)][string]$Executable,
        [Parameter()][string[]]$Arguments = @(),
        [Parameter(Mandatory)][AllowEmptyString()][string]$FallbackSource,
        [Parameter(Mandatory)][string]$FallbackName,
        [Parameter(Mandatory)][string[]]$FallbackArguments
    )

    $officialResult = Invoke-Captured -Executable $Executable -Arguments $Arguments
    if ($officialResult.ExitCode -eq 0) {
        return $officialResult.Output
    }

    if ([string]::IsNullOrWhiteSpace($FallbackSource)) {
        Write-CapturedOutput -Output $officialResult.Output
        throw "'$Executable $($Arguments -join ' ')' failed with exit code $($officialResult.ExitCode); no fallback source is configured."
    }

    Write-Host "Official source failed; retrying with $FallbackName."
    $fallbackResult = Invoke-Captured -Executable $Executable -Arguments $FallbackArguments
    if ($fallbackResult.ExitCode -ne 0) {
        Write-Host 'Official source output:'
        Write-CapturedOutput -Output $officialResult.Output
        Write-Host 'Fallback source output:'
        Write-CapturedOutput -Output $fallbackResult.Output
        throw "Fallback command '$Executable $($FallbackArguments -join ' ')' failed with exit code $($fallbackResult.ExitCode)."
    }

    return $fallbackResult.Output
}

function Get-DatabaseContext {
    $project = [Environment]::GetEnvironmentVariable('COMPOSE_PROJECT_NAME')
    if ([string]::IsNullOrEmpty($project)) {
        $project = 'pandawords'
    }
    $volume = [Environment]::GetEnvironmentVariable('PANDAWORDS_DEV_VOLUME')
    if ([string]::IsNullOrEmpty($volume)) {
        $volume = 'pandawords-dev-db'
    }
    if ($project -cnotmatch '^[a-z0-9][a-z0-9_-]*$' -or
        $volume -cnotmatch '^[a-zA-Z0-9][a-zA-Z0-9_.-]*$') {
        throw 'Invalid Compose project or dev volume name.'
    }
    return @{
        Project = $project
        Volume  = $volume
        File    = Join-Path (Split-Path -Parent $PSScriptRoot) 'deploy\compose.dev.yml'
    }
}

function Invoke-DatabaseCompose {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $context = Get-DatabaseContext
    $composeArguments = @('compose', '--project-name', $context.Project, '--file', $context.File)
    [void](Invoke-Quiet -Executable 'podman' -Arguments ($composeArguments + $Arguments))
}

function Test-DevVolumeOwnership {
    param([Parameter(Mandatory)][hashtable]$Context)

    $exists = Invoke-Captured -Executable 'podman' -Arguments @('volume', 'exists', $Context.Volume)
    if ($exists.ExitCode -eq 1) {
        return $false
    }
    if ($exists.ExitCode -ne 0) {
        Write-CapturedOutput -Output $exists.Output
        throw 'Could not check the dev database volume.'
    }

    $format = '{{ index .Labels "com.docker.compose.project" }}|{{ index .Labels "com.docker.compose.volume" }}'
    $labels = Invoke-Quiet -Executable 'podman' -Arguments @('volume', 'inspect', '--format', $format, $Context.Volume)
    if (($labels -join '').Trim() -cne "$($Context.Project)|dev-data") {
        throw "Volume '$($Context.Volume)' does not belong to this Compose project; refusing database operation."
    }
    return $true
}

function Get-DevVolumeContainers {
    param([Parameter(Mandatory)][hashtable]$Context)

    $volumeFilter = "volume=$($Context.Volume)"
    $idFormat = '{{.ID}}'
    $users = @(Invoke-Quiet -Executable 'podman' -Arguments @(
        'ps', '--all', '--no-trunc', '--filter', $volumeFilter, '--format', $idFormat))
    $devUsers = @(Invoke-Quiet -Executable 'podman' -Arguments @(
        'ps', '--all', '--no-trunc', '--filter', $volumeFilter,
        '--filter', "label=com.docker.compose.project=$($Context.Project)",
        '--filter', 'label=com.docker.compose.service=surreal-dev', '--format', $idFormat))
    foreach ($container in $users) {
        if ($container -cnotin $devUsers) {
            throw "Refusing to use volume '$($Context.Volume)': another container uses it."
        }
    }
    return $users
}

function Start-Database {
    param([Parameter(Mandatory)][ValidateSet('surreal-dev', 'surreal-test')][string]$Service)
    if ($Service -eq 'surreal-dev') {
        $context = Get-DatabaseContext
        if (Test-DevVolumeOwnership -Context $context) {
            [void](Get-DevVolumeContainers -Context $context)
        }
    }
    Invoke-DatabaseCompose -Arguments @('up', '--detach', '--wait', '--wait-timeout', '90', $Service)
}

function Stop-Database {
    param([Parameter(Mandatory)][ValidateSet('surreal-dev', 'surreal-test')][string]$Service)
    Invoke-DatabaseCompose -Arguments @('stop', $Service)
}

function Reset-Database {
    $context = Get-DatabaseContext
    if (-not (Test-DevVolumeOwnership -Context $context)) {
        Write-Host "Dev database volume '$($context.Volume)' is already absent."
        return
    }

    $users = @(Get-DevVolumeContainers -Context $context)
    foreach ($container in $users) {
        [void](Invoke-Quiet -Executable 'podman' -Arguments @('stop', $container))
        [void](Invoke-Quiet -Executable 'podman' -Arguments @('rm', $container))
    }
    [void](Invoke-Quiet -Executable 'podman' -Arguments @('volume', 'rm', $context.Volume))
    Write-Host "Removed dev database volume '$($context.Volume)'; the dev database is stopped."
}

function Show-Help {
    @'
PandaWords development commands

Usage: ./scripts/dev.ps1 <command>

Commands:
  help      Show this help
  setup     Check tools, sync projects, install Git hooks, and create .env.dev
  reset-db  Stop the dev database and delete its data volume
  gen-api   Export OpenAPI offline and regenerate frontend API types in this worktree
  test -Backend [-UpdateSnapshot]  Run backend tests against the isolated test server
'@ | Write-Host
}

function Export-ApiTypes {
    $worktreeRoot = Split-Path -Parent $PSScriptRoot
    $apiDirectory = Join-Path $worktreeRoot 'frontend\src\api'
    Push-Location (Join-Path $worktreeRoot 'backend')
    try {
        $schema = @(& uv run --offline python -m app.openapi)
        if ($LASTEXITCODE -ne 0) {
            throw 'Offline OpenAPI export failed. Restore backend dependencies with uv sync first.'
        }
        $json = $schema -join "`n"
        $null = $json | ConvertFrom-Json
        New-Item -ItemType Directory -Force -Path $apiDirectory | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $apiDirectory 'openapi.json'), "$json`n")
    }
    finally {
        Pop-Location
    }

    Push-Location (Join-Path $worktreeRoot 'frontend')
    try {
        & pnpm exec openapi-typescript src/api/openapi.json -o src/api/schema.d.ts
        if ($LASTEXITCODE -ne 0) {
            throw 'OpenAPI TypeScript generation failed.'
        }
        & pnpm exec eslint src/api/openapi.json src/api/schema.d.ts --fix
        if ($LASTEXITCODE -ne 0) {
            throw 'Generated API contract formatting failed.'
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-Setup {
    $env:NODE_TLS_REJECT_UNAUTHORIZED = '1'

    if (-not (Test-Path -LiteralPath (Join-Path $script:MainRoot '.env.dev') -PathType Leaf)) {
        $examplePath = Join-Path $script:MainRoot '.env.example'
        Copy-Item -LiteralPath $examplePath -Destination (Join-Path $script:MainRoot '.env.dev')
        Import-EnvironmentFile -Path (Join-Path $script:MainRoot '.env.dev')
        Write-Host 'Created .env.dev from .env.example.'
    }

    $toolVersions = @(
        @{ Name = 'git'; Arguments = @('--version') },
        @{ Name = 'uv'; Arguments = @('--version') },
        @{ Name = 'node'; Arguments = @('--version') },
        @{ Name = 'pnpm'; Arguments = @('--version') },
        @{ Name = 'podman'; Arguments = @('--version') }
    )
    foreach ($tool in $toolVersions) {
        if ($null -eq (Get-Command $tool.Name -ErrorAction SilentlyContinue)) {
            throw "Required setup tool '$($tool.Name)' was not found on PATH."
        }

        $versionOutput = Invoke-Quiet -Executable $tool.Name -Arguments $tool.Arguments
        Write-Host "$($tool.Name) $($versionOutput -join ' ')"
    }

    [void](Ensure-LogsDirectory)
    [void](Invoke-Quiet -Executable 'uv' -Arguments @('python', 'install', '3.14'))

    $backendDirectory = Join-Path $script:MainRoot 'backend'
    if (Test-Path -LiteralPath $backendDirectory -PathType Container) {
        Push-Location $backendDirectory
        try {
            $pipFallback = [Environment]::GetEnvironmentVariable('PIP_FALLBACK_INDEX_URL')
            $uvArguments = @('sync')
            $uvFallbackArguments = @('sync')
            if (-not [string]::IsNullOrWhiteSpace($pipFallback)) {
                $uvFallbackArguments += @('--default-index', $pipFallback)
            }
            [void](Invoke-WithFallback -Executable 'uv' -Arguments $uvArguments `
                -FallbackSource $pipFallback -FallbackName 'PIP_FALLBACK_INDEX_URL' `
                -FallbackArguments $uvFallbackArguments)
        }
        finally {
            Pop-Location
        }
    }
    else {
        Write-Host 'backend/ not found; skipping uv sync.'
    }

    $frontendDirectory = Join-Path $script:MainRoot 'frontend'
    if (Test-Path -LiteralPath $frontendDirectory -PathType Container) {
        Push-Location $frontendDirectory
        try {
            $npmFallback = [Environment]::GetEnvironmentVariable('NPM_FALLBACK_REGISTRY')
            $pnpmFallbackArguments = @('install')
            if (-not [string]::IsNullOrWhiteSpace($npmFallback)) {
                $pnpmFallbackArguments += "--registry=$npmFallback"
            }
            [void](Invoke-WithFallback -Executable 'pnpm' -Arguments @('install') `
                -FallbackSource $npmFallback -FallbackName 'NPM_FALLBACK_REGISTRY' `
                -FallbackArguments $pnpmFallbackArguments)
        }
        finally {
            Pop-Location
        }

        Push-Location $script:MainRoot
        try {
            [void](Invoke-Quiet -Executable 'pnpm' -Arguments @('exec', 'lefthook', 'install'))
        }
        finally {
            Pop-Location
        }
    }
    else {
        Write-Host 'frontend/ not found; skipping pnpm install.'
    }

    Write-Host "Setup complete. Main worktree: $script:MainRoot"
}

$script:MainRoot = Get-MainWorktreeRoot
Import-EnvironmentFile -Path (Join-Path $script:MainRoot '.env.dev')

switch ($Command.ToLowerInvariant()) {
    'test' {
        . (Join-Path $PSScriptRoot 'test-backend.ps1')
        Invoke-BackendTests -Arguments $CommandArgs
    }
    'gen-api' {
        if ($CommandArgs.Count -ne 0) {
            throw 'The gen-api command does not accept additional arguments.'
        }
        Export-ApiTypes
    }
    'help' {
        if ($CommandArgs.Count -ne 0) {
            throw 'The help command does not accept additional arguments.'
        }
        Show-Help
    }
    'setup' {
        if ($CommandArgs.Count -ne 0) {
            throw 'The setup command does not accept additional arguments.'
        }
        Invoke-Setup
    }
    'reset-db' {
        if ($CommandArgs.Count -ne 0) {
            throw 'The reset-db command does not accept additional arguments.'
        }
        Reset-Database
    }
    default {
        throw "Unknown command '$Command'. Run './scripts/dev.ps1 help' for available commands."
    }
}
