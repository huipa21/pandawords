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
