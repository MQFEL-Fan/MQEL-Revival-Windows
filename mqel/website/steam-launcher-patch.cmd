<# : batch part, PowerShell sees this as a comment
@echo off
set "MQ_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((Get-Content -LiteralPath '%~f0') -join [char]10)"
exit /b
#>
# Lets the 2015 launcher (PublicLauncher.exe 276072) install our updates when
# started from Steam. In Steam mode its state machine sends "version old"
# (game, launcher, repair) straight to TaskExit, and the version checks show
# "Update needed / Please update via the Steam client". The patch removes the
# three Steam branches in the state machine setup (jne -> nop at VA 0x4e10a7,
# 0x4e1135, 0x4e1225) and turns the dialog (VA 0x4def05) into a plain "ret".
# Put this file into the game's installation folder and double-click it.

$ErrorActionPreference = "Stop"
$exe = Join-Path $env:MQ_DIR "Launcher\PublicLauncher.exe"
if (-not (Test-Path $exe)) { $exe = Join-Path $env:MQ_DIR "PublicLauncher.exe" }

# file offset, original bytes, patched bytes
$patches = @(
    @(0xE04A7, [byte[]](0x75, 0x05), [byte[]](0x90, 0x90)),
    @(0xE0535, [byte[]](0x75, 0x11), [byte[]](0x90, 0x90)),
    @(0xE0625, [byte[]](0x0f, 0x85, 0x86, 0x00, 0x00, 0x00), [byte[]](0x90, 0x90, 0x90, 0x90, 0x90, 0x90)),
    @(0xDE305, [byte[]](0x6a), [byte[]](0xc3))
)

function Matches($data, $offset, $bytes) {
    if ($data.Length -lt $offset + $bytes.Length) { return $false }
    for ($i = 0; $i -lt $bytes.Length; $i++) {
        if ($data[$offset + $i] -ne $bytes[$i]) { return $false }
    }
    return $true
}

try {
    if (-not (Test-Path $exe)) { throw "PublicLauncher.exe not found next to this script or in Launcher\." }
    $data = [IO.File]::ReadAllBytes($exe)
    $todo = 0
    foreach ($p in $patches) {
        if (Matches $data $p[0] $p[1]) { $todo++ }
        elseif (-not (Matches $data $p[0] $p[2])) { throw "Unknown PublicLauncher.exe version, nothing changed." }
    }
    if ($todo -eq 0) {
        Write-Host "Already patched: $exe"
    } else {
        if (-not (Test-Path "$exe.bak")) { Copy-Item $exe "$exe.bak" }
        foreach ($p in $patches) { [Array]::Copy($p[2], 0, $data, $p[0], $p[2].Length) }
        [IO.File]::WriteAllBytes($exe, $data)
        Write-Host "Patched: $exe (backup: PublicLauncher.exe.bak)"
    }
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
}
Read-Host "Press Enter to close"
