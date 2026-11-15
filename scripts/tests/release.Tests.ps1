#Requires -Version 7.3
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot '..\release.ps1')
$root = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) ".dev\release-test-$([guid]::NewGuid().ToString('N'))"
$script:calls = [Collections.Generic.List[object]]::new()
$script:failAt = ''
$script:imageExists = $false
$script:platform = 'linux/amd64'

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Assert-Fails([scriptblock]$Action, [string]$Pattern) {
    try { & $Action }
    catch {
        Assert-True ($_.Exception.Message -like $Pattern) "Unexpected error: $_"
        return
    }
    throw "Expected failure: $Pattern"
}

function Invoke-Captured {
    param([string]$Executable, [string[]]$Arguments)
    $script:calls.Add($Arguments)
    return @{ ExitCode = [int](-not $script:imageExists); Output = @() }
}

function Invoke-Quiet {
    param([string]$Executable, [string[]]$Arguments)
    $script:calls.Add($Arguments)
    if ($Arguments[0] -eq $script:failAt) { throw 'Synthetic Podman failure' }
    switch ($Arguments[0]) {
        'image' { return $script:platform }
        'save' { [IO.File]::WriteAllText($Arguments[5], 'synthetic image archive') }
    }
}

function Read-Bundle([string]$Path) {
    $file = [IO.File]::OpenRead($Path)
    $gzip = [IO.Compression.GZipStream]::new($file, [IO.Compression.CompressionMode]::Decompress)
    $reader = [System.Formats.Tar.TarReader]::new($gzip)
    $entries = @{}
    try {
        while ($null -ne ($entry = $reader.GetNextEntry())) {
            $text = [IO.StreamReader]::new($entry.DataStream)
            try { $entries[($entry.Name -replace '^\./', '')] = $text.ReadToEnd() }
            finally { $text.Dispose() }
        }
    }
    finally { $reader.Dispose(); $gzip.Dispose(); $file.Dispose() }
    return $entries
}

try {
    New-Item -ItemType Directory -Path (Join-Path $root 'deploy') -Force | Out-Null
    foreach ($name in @('compose.yml', 'Caddyfile.snippet')) {
        [IO.File]::WriteAllText((Join-Path $root "deploy\$name"), "synthetic $name`n")
    }
    [IO.File]::WriteAllText((Join-Path $root '.env.example'), "synthetic .env.example`n")
    foreach ($version in @('1.2', '../1.2.3', '1.2.3;echo injected', "1.2.3`n", '-1.2.3', '01.2.3', '1.2.3-rc1')) {
        Assert-Fails { Invoke-Release -Root $root -Arguments @('-Version', $version) } 'Usage:*'
    }
    Assert-Fails { Invoke-Release -Root $root -Arguments @('-Version', '1.2.3', '-Force') } 'Usage:*'
    Assert-True ($script:calls.Count -eq 0) 'Invalid arguments invoked Podman.'
    $script:imageExists = $true
    Assert-Fails { Invoke-Release -Root $root -Arguments @('-Version', '1.2.3') } 'Release image already exists:*'
    $script:imageExists = $false
    foreach ($step in @('build', 'save')) {
        $script:failAt = $step
        Assert-Fails { Invoke-Release -Root $root -Arguments @('-Version', '1.2.3') } 'Synthetic Podman failure'
        Assert-True (@(Get-ChildItem (Join-Path $root 'dist') -Force).Count -eq 0) 'Failure left partial artifacts or lock.'
    }
    $script:failAt = ''
    $script:platform = 'linux/arm64'
    Assert-Fails { Invoke-Release -Root $root -Arguments @('-Version', '1.2.3') } 'Release image is not linux/amd64:*'
    Assert-True (@(Get-ChildItem (Join-Path $root 'dist') -Force).Count -eq 0) 'Wrong-platform failure left artifacts.'
    $script:platform = 'linux/amd64'
    $script:calls.Clear()
    Invoke-Release -Root $root -Arguments @('-Version', '1.2.3')
    $builds = @($script:calls | Where-Object { $_[0] -eq 'build' })
    Assert-True ($builds.Count -eq 2) 'Expected both image builds.'
    foreach ($build in $builds) {
        Assert-True (($build -join ' ') -like '*--tls-verify=true --platform linux/amd64*') 'Missing platform/TLS flags.'
        Assert-True ('--build-arg' -notin $build) 'Default release unexpectedly enabled optimizer.'
    }
    $save = @($script:calls | Where-Object { $_[0] -eq 'save' })[0]
    Assert-True (($save[0..4] -join ' ') -eq 'save --format docker-archive --multi-image-archive --output') 'Wrong archive flags.'
    Assert-True (($save[-2..-1] -join ' ') -eq 'docker.io/library/pandawords-api:1.2.3 docker.io/library/pandawords-web:1.2.3') 'Wrong image tags.'
    $dist = Join-Path $root 'dist'
    $entries = Read-Bundle (Join-Path $dist 'pandawords-1.2.3-deploy.tar.gz')
    Assert-True (($entries.Keys | Sort-Object) -join ',' -eq '.env.example,Caddyfile.snippet,compose.yml,VERSION') 'Wrong deploy bundle members.'
    Assert-True ($entries.VERSION -ceq "1.2.3`n") 'Wrong VERSION content.'
    Assert-True ($entries['.env.example'] -ceq "synthetic .env.example`n") 'Wrong environment example.'
    foreach ($line in Get-Content (Join-Path $dist 'SHA256SUMS')) {
        $hash, $name = $line -split '  ', 2
        Assert-True ($hash -ceq (Get-FileHash (Join-Path $dist $name)).Hash.ToLowerInvariant()) 'Checksum mismatch.'
    }
    $before = (Get-FileHash (Join-Path $dist 'SHA256SUMS')).Hash
    $script:calls.Clear()
    Assert-Fails { Invoke-Release -Root $root -Arguments @('-Version', '1.2.3') } 'Release output already exists:*'
    Assert-Fails { Invoke-Release -Root $root -Arguments @('-Version', '2.0.0') } 'Release output already exists:*'
    Assert-True ($script:calls.Count -eq 0) 'Overwrite guard ran Podman.'
    Assert-True ($before -ceq (Get-FileHash (Join-Path $dist 'SHA256SUMS')).Hash) 'Overwrite changed checksums.'
    [IO.File]::WriteAllText((Join-Path $dist '.release.lock'), '')
    Assert-Fails { Invoke-Release -Root $root -Arguments @('-Version', '2.0.0') } '*already exists*'
    Assert-True (Test-Path (Join-Path $dist '.release.lock')) 'Removed another invocation lock.'
    Remove-Item -LiteralPath $dist -Recurse -Force
    $script:calls.Clear()
    Invoke-Release -Root $root -Arguments @('-Version', '1.2.4', '-FsrsOptimizer')
    $builds = @($script:calls | Where-Object { $_[0] -eq 'build' })
    Assert-True (($builds[0] -join ' ') -like '*--build-arg INSTALL_FSRS_OPTIMIZER=true*') 'Optimizer was not enabled in the API image.'
    Assert-True ('--build-arg' -notin $builds[1]) 'Optimizer flag leaked into the frontend build.'
    Write-Host 'Release focused tests passed.'
}
finally {
    Remove-Item -LiteralPath $root -Recurse -Force
}
