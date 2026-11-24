# MQEL Revival - allow incoming TCP 8081 (launcher/patcher), 8443 (game, HTTPS)
# 5222 (chat) and 8088 (website) in the Windows firewall. Run as administrator.
#   powershell -ExecutionPolicy Bypass -File tools\open_firewall.ps1 [-Remove]
param([switch]$Remove)
$rules = @(
    @{ Name = "MQEL Launcher+Patcher (TCP 8081)"; Port = 8081 },
    @{ Name = "MQEL Game HTTPS (TCP 8443)"; Port = 8443 },
    @{ Name = "MQEL Chat XMPP (TCP 5222)"; Port = 5222 },
    @{ Name = "MQEL Website (TCP 8088)"; Port = 8088 }
)
foreach ($r in $rules) {
    Get-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    if (-not $Remove) {
        New-NetFirewallRule -DisplayName $r.Name -Direction Inbound -Protocol TCP -LocalPort $r.Port `
            -Action Allow -Profile Any | Out-Null
        Write-Host "allowed: $($r.Name)"
    } else { Write-Host "removed: $($r.Name)" }
}
Start-Sleep -Seconds 2
