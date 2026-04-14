# DevForgeAI Stop Script
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidsFile = Join-Path $root ".devforgeai.pids"

if (Test-Path $pidsFile) {
    $pids = Get-Content $pidsFile | ConvertFrom-Json
    foreach ($p in @($pids.backend, $pids.frontend)) {
        try { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } catch {}
    }
    Remove-Item $pidsFile -Force
}

# Also kill by port as fallback
function Kill-Port($port) {
    $pids = netstat -ano | Select-String ":$port\s" | Select-String "LISTENING" |
        ForEach-Object { ($_ -split '\s+')[-1] } | Select-Object -Unique
    foreach ($p in $pids) {
        try { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } catch {}
    }
}
Kill-Port 19000
Kill-Port 19001
Kill-Port 3001

Write-Host "DevForgeAI stopped."
