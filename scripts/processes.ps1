function Test-OwnedProcess {
    param([Parameter(Mandatory)]$Entry)
    try {
        $process = Get-Process -Id $Entry.Pid -ErrorAction SilentlyContinue
        if ($null -eq $process -or $process.StartTime.ToUniversalTime().Ticks -ne $Entry.StartTicks) {
            return $false
        }
        $details = Get-CimInstance Win32_Process -Filter "ProcessId = $($Entry.Pid)"
        return $null -ne $details -and $null -ne $details.CommandLine -and
            $details.CommandLine.Contains($Entry.Token) -and
            $details.CommandLine.Contains($Entry.Spec) -and
            $details.CommandLine.Contains('process-host.ps1')
    }
    catch { return $false }
}

function Stop-OwnedProcess {
    param([Parameter(Mandatory)]$Entry)
    $owned = Test-OwnedProcess $Entry
    if ($owned) {
        # Hold the exact process handle, so a PID reuse between validation and stop
        # cannot redirect termination to a different process.
        $process = Get-Process -Id $Entry.Pid -ErrorAction SilentlyContinue
        if ($null -ne $process) {
            $null = $process.Handle
            if ($process.StartTime.ToUniversalTime().Ticks -eq $Entry.StartTicks) {
                $process.Kill()
                $process.WaitForExit()
            }
            if ($Entry.LauncherPid -ne $Entry.Pid) {
                $launcher = [pscustomobject]@{
                    Pid = $Entry.LauncherPid; StartTicks = $Entry.LauncherStartTicks
                    Token = $Entry.Token; Spec = $Entry.Spec
                }
                if (Test-OwnedProcess $launcher) {
                    $relay = Get-Process -Id $launcher.Pid -ErrorAction SilentlyContinue
                    if ($null -ne $relay) {
                        $null = $relay.Handle
                        if ($relay.StartTime.ToUniversalTime().Ticks -eq $launcher.StartTicks) {
                            $relay.Kill()
                            $relay.WaitForExit()
                        }
                    }
                }
            }
        }
    }
    if ($owned -or $null -eq (Get-Process -Id $Entry.Pid -ErrorAction SilentlyContinue)) {
        Remove-Item -LiteralPath $Entry.Spec, "$($Entry.Spec).ready" -Force -ErrorAction SilentlyContinue
    }
}

function Start-OwnedProcess {
    param(
        [string]$Name, [string]$Executable, [string[]]$Arguments,
        [string]$Directory, [string]$StateDirectory
    )
    if (-not $IsWindows) { throw 'The development process supervisor requires Windows.' }
    $token = [guid]::NewGuid().ToString('N')
    $spec = Join-Path $StateDirectory "$Name-$token.json"
    $logs = Join-Path $StateDirectory 'logs'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $resolved = (Get-Command $Executable -ErrorAction Stop).Source
    if ([IO.Path]::GetExtension($resolved) -eq '.ps1') {
        $cmd = [IO.Path]::ChangeExtension($resolved, '.cmd')
        if (-not (Test-Path -LiteralPath $cmd -PathType Leaf)) {
            throw "Background command '$Executable' needs a native executable or .cmd shim."
        }
        $resolved = $cmd
    }
    @{
        Executable = $resolved
        Arguments = @($Arguments)
        Directory = $Directory
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $spec
    $stdout = Join-Path $logs "$Name.log"
    $stderr = Join-Path $logs "$Name.error.log"
    $hostScript = Join-Path $PSScriptRoot 'process-host.ps1'
    # Windows App Execution Aliases can return a relay PID rather than the host
    # that owns the job. Launch the actual current PowerShell binary instead.
    $process = Start-Process (Join-Path $PSHOME 'pwsh.exe') -ArgumentList @(
        '-NoProfile', '-NonInteractive', '-File', "`"$hostScript`"",
        '-Spec', "`"$spec`"", '-Token', $token
    ) -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $entry = [pscustomobject]@{
        Pid = $process.Id
        StartTicks = $process.StartTime.ToUniversalTime().Ticks
        LauncherPid = $process.Id
        LauncherStartTicks = $process.StartTime.ToUniversalTime().Ticks
        Token = $token
        Spec = $spec
        Log = $stdout
        ErrorLog = $stderr
    }
    try {
        $deadline = [datetime]::UtcNow.AddSeconds(20)
        while (-not (Test-Path -LiteralPath "$spec.ready")) {
            if ($process.HasExited -or [datetime]::UtcNow -gt $deadline) {
                throw "Supervisor for $Name did not initialize."
            }
            Start-Sleep -Milliseconds 100
        }
        $ready = Get-Content -LiteralPath "$spec.ready" -Raw | ConvertFrom-Json
        $entry.Pid = $ready.Pid
        $entry.StartTicks = $ready.StartTicks
        if ($ready.Token -cne $token -or
            -not (Test-OwnedProcess $entry)) { throw "Supervisor identity mismatch for $Name." }
        return $entry
    }
    catch {
        Stop-OwnedProcess $entry
        Write-Host (Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue)
        throw
    }
}

function Wait-DevReady {
    param($Entry, [string]$Url = '', [string]$LogPattern = '', [int]$TimeoutSeconds = 60)
    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (-not (Test-OwnedProcess $Entry)) { break }
        if ($Url) {
            try {
                $response = Invoke-WebRequest -Uri $Url -NoProxy -TimeoutSec 2
                if ($response.StatusCode -eq 200) { return }
            }
            catch { }
        }
        elseif (Test-Path -LiteralPath $Entry.Log) {
            $log = Get-Content -LiteralPath $Entry.Log -Raw
            if ($log -match $LogPattern) {
                Start-Sleep -Seconds 1
                if ((Test-OwnedProcess $Entry) -and
                    (Get-Content -LiteralPath $Entry.Log -Raw) -notmatch 'worker_iteration_failed') { return }
            }
        }
        Start-Sleep -Milliseconds 200
    } while ([datetime]::UtcNow -lt $deadline)
    foreach ($path in @($Entry.Log, $Entry.ErrorLog)) {
        if (Test-Path -LiteralPath $path) { Write-Host (Get-Content -LiteralPath $path -Raw) }
    }
    throw "Readiness failed for PID $($Entry.Pid) ($Url$LogPattern)."
}
