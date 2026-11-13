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

function Show-Help {
    @'
PandaWords development commands

Usage: ./scripts/dev.ps1 <command>

Commands:
  help    Show this help
  setup   Check tools, sync projects, install Git hooks, and create .env.dev
'@ | Write-Host
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
    default {
        throw "Unknown command '$Command'. Run './scripts/dev.ps1 help' for available commands."
    }
}
