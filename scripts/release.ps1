#Requires -Version 7.3

function Compress-ReleaseFile {
    param([string]$Source, [string]$Destination)

    $inputStream = [IO.File]::OpenRead($Source)
    try {
        $outputStream = [IO.File]::Open($Destination, [IO.FileMode]::CreateNew)
        try {
            $gzip = [IO.Compression.GZipStream]::new(
                $outputStream, [IO.Compression.CompressionLevel]::Optimal, $true)
            try { $inputStream.CopyTo($gzip) }
            finally { $gzip.Dispose() }
        }
        finally { $outputStream.Dispose() }
    }
    finally { $inputStream.Dispose() }
}

function Invoke-Release {
    param(
        [Parameter(Mandatory)][string[]]$Arguments,
        [string]$Root = (Split-Path -Parent $PSScriptRoot)
    )

    if ($Arguments.Count -ne 2 -or $Arguments[0] -ine '-Version' -or
        $Arguments[1] -cnotmatch '\A(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\z' -or
        $Arguments[1].Length -gt 100) {
        throw 'Usage: release -Version x.y.z (nonnegative integers, no leading zeros).'
    }
    $version = $Arguments[1]
    $dist = Join-Path $Root 'dist'
    $names = @("pandawords-$version-images.tar.gz", "pandawords-$version-deploy.tar.gz", 'SHA256SUMS')
    $images = @("docker.io/library/pandawords-api:$version", "docker.io/library/pandawords-web:$version")
    $bundleFiles = [ordered]@{
        'compose.yml' = 'deploy\compose.yml'
        '.env.example' = '.env.example'
        'Caddyfile.snippet' = 'deploy\Caddyfile.snippet'
    }
    foreach ($name in $bundleFiles.Keys) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $bundleFiles[$name]) -PathType Leaf)) {
            throw "Missing deployment input: $name"
        }
    }
    New-Item -ItemType Directory -Force -Path $dist | Out-Null
    $lock = $null
    $stage = $null
    $published = [Collections.Generic.List[string]]::new()
    try {
        # A single dist lock also protects the shared checksum filename across versions.
        $lock = [IO.File]::Open((Join-Path $dist '.release.lock'), [IO.FileMode]::CreateNew)
        foreach ($name in $names) {
            if (Test-Path -LiteralPath (Join-Path $dist $name)) {
                throw "Release output already exists: $name. Move the previous release out of dist first."
            }
        }
        foreach ($image in $images) {
            $exists = Invoke-Captured -Executable podman -Arguments @('image', 'exists', $image)
            if ($exists.ExitCode -eq 0) { throw "Release image already exists: $image. Choose a new version." }
            if ($exists.ExitCode -ne 1) { throw "Could not check release image: $image" }
        }
        $stage = Join-Path $dist ".release-$([guid]::NewGuid().ToString('N'))"
        New-Item -ItemType Directory -Path $stage | Out-Null
        [void](Invoke-Quiet -Executable podman -Arguments @(
            'build', '--tls-verify=true', '--platform', 'linux/amd64',
            '--file', (Join-Path $Root 'backend\Dockerfile'), '--tag', $images[0], (Join-Path $Root 'backend')))
        [void](Invoke-Quiet -Executable podman -Arguments @(
            'build', '--tls-verify=true', '--platform', 'linux/amd64',
            '--file', (Join-Path $Root 'frontend\Dockerfile'), '--tag', $images[1], $Root))
        foreach ($image in $images) {
            $platform = Invoke-Quiet -Executable podman -Arguments @(
                'image', 'inspect', '--format', '{{.Os}}/{{.Architecture}}', $image)
            if (($platform -join '').Trim() -cne 'linux/amd64') {
                throw "Release image is not linux/amd64: $image"
            }
        }
        $imageTar = Join-Path $stage 'images.tar'
        [void](Invoke-Quiet -Executable podman -Arguments (
            @('save', '--format', 'docker-archive', '--multi-image-archive', '--output', $imageTar) + $images))
        Compress-ReleaseFile $imageTar (Join-Path $stage $names[0])
        Remove-Item -LiteralPath $imageTar

        $bundle = Join-Path $stage 'bundle'
        New-Item -ItemType Directory -Path $bundle | Out-Null
        foreach ($name in $bundleFiles.Keys) {
            Copy-Item -LiteralPath (Join-Path $Root $bundleFiles[$name]) -Destination (Join-Path $bundle $name)
        }
        [IO.File]::WriteAllText((Join-Path $bundle 'VERSION'), "$version`n")
        $deployTar = Join-Path $stage 'deploy.tar'
        [System.Formats.Tar.TarFile]::CreateFromDirectory($bundle, $deployTar, $false)
        Compress-ReleaseFile $deployTar (Join-Path $stage $names[1])

        $checksums = foreach ($name in $names[0..1]) {
            $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $stage $name)).Hash.ToLowerInvariant()
            "$hash  $name"
        }
        [IO.File]::WriteAllText((Join-Path $stage 'SHA256SUMS'), ($checksums -join "`n") + "`n")
        foreach ($name in $names) {
            $destination = Join-Path $dist $name
            [IO.File]::Move((Join-Path $stage $name), $destination, $false)
            $published.Add($destination)
        }
        Write-Host "Release $version written to $dist"
    }
    catch {
        foreach ($path in $published) { Remove-Item -LiteralPath $path }
        throw
    }
    finally {
        if ($null -ne $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
        if ($null -ne $lock) {
            $lock.Dispose()
            Remove-Item -LiteralPath (Join-Path $dist '.release.lock')
        }
    }
}
