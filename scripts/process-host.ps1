#Requires -Version 7.0
param(
    [Parameter(Mandatory)][string]$Spec,
    [Parameter(Mandatory)][string]$Token
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# All descendants inherit this job, including cmd/pnpm and reload workers. Closing
# the last handle kills the tree even if a launcher exits before its children.
Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
public static class DevProcessJob {
    [StructLayout(LayoutKind.Sequential)]
    struct BasicLimits {
        public long PerProcessUserTime, PerJobUserTime;
        public uint Flags;
        public UIntPtr MinWorkingSet, MaxWorkingSet;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass, SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct IoCounters {
        public ulong ReadOperations, WriteOperations, OtherOperations;
        public ulong ReadBytes, WriteBytes, OtherBytes;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct ExtendedLimits {
        public BasicLimits Basic;
        public IoCounters Io;
        public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemory, PeakJobMemory;
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr CreateJobObject(IntPtr security, string name);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool SetInformationJobObject(IntPtr job, int kind, IntPtr info, uint size);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct StartupInfo {
        public uint Size;
        public string Reserved, Desktop, Title;
        public uint X, Y, XSize, YSize, XCountChars, YCountChars, FillAttribute, Flags;
        public ushort ShowWindow, ReservedSize;
        public IntPtr ReservedData, Input, Output, Error;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct ProcessInfo {
        public IntPtr Process, Thread;
        public uint ProcessId, ThreadId;
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool CreateProcess(string application, StringBuilder command,
        IntPtr processSecurity, IntPtr threadSecurity, bool inheritHandles, uint flags,
        IntPtr environment, string directory, ref StartupInfo startup, out ProcessInfo process);
    [DllImport("kernel32.dll")]
    static extern IntPtr GetStdHandle(int kind);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern uint ResumeThread(IntPtr thread);
    [DllImport("kernel32.dll")]
    static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetExitCodeProcess(IntPtr process, out uint code);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool TerminateProcess(IntPtr process, uint code);
    [DllImport("kernel32.dll")]
    static extern bool CloseHandle(IntPtr handle);
    // Deliberately retained for the entire host lifetime, never inherited by children.
    static IntPtr handle;
    public static void Attach(string token) {
        handle = CreateJobObject(IntPtr.Zero, "PandaWords-" + token);
        if (handle == IntPtr.Zero) throw new Win32Exception();
        var limits = new ExtendedLimits();
        limits.Basic.Flags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        int size = Marshal.SizeOf(limits);
        IntPtr buffer = Marshal.AllocHGlobal(size);
        try {
            Marshal.StructureToPtr(limits, buffer, false);
            if (!SetInformationJobObject(handle, 9, buffer, (uint)size))
                throw new Win32Exception();
        } finally { Marshal.FreeHGlobal(buffer); }
    }
    public static int Run(string executable, string command, string directory) {
        var startup = new StartupInfo();
        startup.Size = (uint)Marshal.SizeOf(startup);
        startup.Flags = 0x100; // STARTF_USESTDHANDLES
        startup.Input = GetStdHandle(-10);
        startup.Output = GetStdHandle(-11);
        startup.Error = GetStdHandle(-12);
        ProcessInfo process;
        // Assign the suspended root before any wrapper can launch descendants.
        if (!CreateProcess(executable, new StringBuilder(command), IntPtr.Zero, IntPtr.Zero,
                true, 0x08000004, IntPtr.Zero, directory, ref startup, out process))
            throw new Win32Exception();
        try {
            if (!AssignProcessToJobObject(handle, process.Process)) {
                TerminateProcess(process.Process, 1);
                throw new Win32Exception();
            }
            if (ResumeThread(process.Thread) == UInt32.MaxValue)
                throw new Win32Exception();
            WaitForSingleObject(process.Process, UInt32.MaxValue);
            uint code;
            if (!GetExitCodeProcess(process.Process, out code)) throw new Win32Exception();
            return (int)code;
        } finally {
            CloseHandle(process.Thread);
            CloseHandle(process.Process);
        }
    }
}
'@

[DevProcessJob]::Attach($Token)
$configuration = Get-Content -LiteralPath $Spec -Raw | ConvertFrom-Json
Set-Location -LiteralPath $configuration.Directory
@{
    Token = $Token
    Pid = $PID
    StartTicks = (Get-Process -Id $PID).StartTime.ToUniversalTime().Ticks
} | ConvertTo-Json -Compress | Set-Content -LiteralPath "$Spec.ready"
function Quote-NativeArgument {
    param([string]$Value)
    if ($Value -notmatch '[\s"]' -and $Value.Length -gt 0) { return $Value }
    return '"' + [regex]::Replace(
        [regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
}
$executable = [string]$configuration.Executable
$arguments = @($configuration.Arguments)
if ([IO.Path]::GetExtension($executable) -in @('.cmd', '.bat')) {
    $command = '"' + ((@($executable) + $arguments | ForEach-Object { Quote-NativeArgument $_ }) -join ' ') + '"'
    $executable = $env:ComSpec
    $command = "`"$executable`" /d /s /c $command"
}
else {
    $command = (@($executable) + $arguments | ForEach-Object { Quote-NativeArgument $_ }) -join ' '
}
exit ([DevProcessJob]::Run($executable, $command, $configuration.Directory))
