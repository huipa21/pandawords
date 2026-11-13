function Invoke-BackendTests {
    param([Parameter()][string[]]$Arguments = @())

    $updateSnapshot = $false
    foreach ($argument in $Arguments) {
        switch ($argument.ToLowerInvariant()) {
            '-backend' { }
            '-updatesnapshot' { $updateSnapshot = $true }
            default { throw "Unsupported test argument '$argument'. Only -Backend and -UpdateSnapshot are implemented." }
        }
    }
    if ('-Backend' -notin $Arguments) {
        throw 'Use test -Backend; combined and frontend test orchestration is not implemented yet.'
    }

    $url = [Environment]::GetEnvironmentVariable('SURREAL_TEST_URL')
    if ([string]::IsNullOrWhiteSpace($url)) {
        $url = 'ws://127.0.0.1:8101/rpc'
    }
    $endpoint = [Uri]$url
    if ($endpoint.Host -notin @('localhost', '127.0.0.1', '[::1]') -or
        $endpoint.Port -ne 8101 -or $endpoint.Scheme -notin @('ws', 'wss')) {
        throw 'Backend tests require the loopback test server on port 8101.'
    }
    $health = [UriBuilder]::new($endpoint)
    $health.Scheme = if ($endpoint.Scheme -eq 'wss') { 'https' } else { 'http' }
    $health.Host = if ($endpoint.Host -eq 'localhost') { '127.0.0.1' } else { $endpoint.Host }
    $health.Path = '/health'
    try {
        $response = Invoke-WebRequest -Uri $health.Uri -NoProxy -TimeoutSec 2
        $running = $response.StatusCode -eq 200
    }
    catch {
        $running = $false
    }
    if (-not $running) {
        Start-Database -Service 'surreal-test'
    }

    $root = Split-Path -Parent $PSScriptRoot
    Push-Location (Join-Path $root 'backend')
    try {
        $pytestArguments = @('run', '--no-sync', 'pytest', '-q')
        if ($updateSnapshot) {
            $pytestArguments += '--update-snapshot'
        }
        $result = Invoke-Captured -Executable 'uv' -Arguments $pytestArguments
        Write-CapturedOutput -Output $result.Output
        if ($result.ExitCode -ne 0) {
            throw "Backend tests failed with exit code $($result.ExitCode)."
        }
    }
    finally {
        Pop-Location
    }
}
