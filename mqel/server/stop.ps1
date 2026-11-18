# Beendet alle MQEL-Server (Spielserver/XMPP) anhand ihrer Kommandozeile.
# Funktioniert aus jedem Terminal (PowerShell/CMD/VS Code/...), auch wenn
# Strg+C den Prozess nicht erreicht (z. B. Git-Bash/mintty leitet Strg+C
# nicht an native Windows-Programme weiter).
#
# Gebrauch:  powershell -ExecutionPolicy Bypass -File server/stop.ps1

$patterns = @('*game_server*', '*logging_server*', '*xmpp_server*')
$killed = 0
foreach ($p in Get-CimInstance Win32_Process -Filter "Name LIKE 'python%.exe'") {
    $cmd = $p.CommandLine
    if (-not $cmd) { continue }
    foreach ($pat in $patterns) {
        if ($cmd -like $pat) {
            try {
                Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
                Write-Host "beendet: PID $($p.ProcessId) [$cmd]"
                $killed++
            } catch {
                Write-Warning ("PID $($p.ProcessId) nicht beendbar " +
                    "(Admin-Terminal nötig?): [$cmd]")
            }
            break
        }
    }
}
if ($killed -eq 0) { Write-Host 'Keine MQEL-Server gefunden.' }
