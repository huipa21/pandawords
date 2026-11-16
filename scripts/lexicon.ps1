#Requires -Version 7.0

function Invoke-Lexicon {
    param([string[]]$Arguments = @())

    $options = @{
        '-rawdir' = '--raw-dir'
        '-output' = '--output'
        '-distdir' = '--dist-dir'
        '-date' = '--date'
    }
    $cli = @('run', '--no-sync', 'python', '-X', 'utf8', '-m', 'scripts.lexicon_release')
    for ($index = 0; $index -lt $Arguments.Count; $index += 2) {
        $key = $Arguments[$index].ToLowerInvariant()
        if (-not $options.ContainsKey($key) -or $index + 1 -ge $Arguments.Count -or
            [string]::IsNullOrWhiteSpace($Arguments[$index + 1])) {
            throw 'lexicon prepare failed: usage: lexicon [-RawDir path] [-Output path] [-DistDir path] [-Date yyyy-MM-dd]'
        }
        $cli += @($options[$key], $Arguments[$index + 1])
    }
    Push-Location (Join-Path (Split-Path -Parent $PSScriptRoot) 'backend')
    try {
        $result = Invoke-Captured -Executable uv -Arguments $cli
        Write-CapturedOutput -Output $result.Output
        if ($result.ExitCode -ne 0) {
            throw "lexicon command failed with exit code $($result.ExitCode)."
        }
    }
    catch {
        throw "lexicon invocation failed: $_"
    }
    finally { Pop-Location }
}
