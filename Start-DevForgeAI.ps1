# DevForgeAI Background Launcher — no windows, no redirection issues

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidsFile = Join-Path $root ".devforgeai.pids"
$logsDir  = Join-Path $root "logs"
if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir | Out-Null }

$preferredBackendPort = 19001
$fallbackBackendPort = 19000

function Kill-Port($port) {
    netstat -ano | Select-String ":$port\s" | Select-String "LISTENING" |
        ForEach-Object { ($_ -split '\s+')[-1] } | Select-Object -Unique |
        ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } catch {} }
}
function Test-PortListening($port) {
    return [bool](netstat -ano | Select-String ":$port\s" | Select-String "LISTENING")
}

Kill-Port $preferredBackendPort
Kill-Port 3001
Start-Sleep -Seconds 2

$backendPort = if (Test-PortListening $preferredBackendPort) { $fallbackBackendPort } else { $preferredBackendPort }
$backendUrl = "http://localhost:$backendPort"

# Clean stale Next.js cache to avoid chunk mismatch errors after restarts.
$nextCacheDir = Join-Path $root "frontend\.next\cache"
if (Test-Path $nextCacheDir) {
    try { Remove-Item $nextCacheDir -Recurse -Force -ErrorAction Stop } catch {}
}

# Backend
$backendProc = Start-Process `
    -FilePath (Join-Path $root "backend\venv\Scripts\python.exe") `
    -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port $backendPort --reload" `
    -WorkingDirectory (Join-Path $root "backend") `
    -WindowStyle Hidden `
    -PassThru

# Frontend
$nextBin = Join-Path $root "frontend\node_modules\next\dist\bin\next"
$frontendEnv = @{
    NEXT_PUBLIC_API_URL = $backendUrl
    DEVFORGEAI_BACKEND_PORT = "$backendPort"
}
$frontendProc = Start-Process `
    -FilePath "node.exe" `
    -ArgumentList "`"$nextBin`" dev -p 3001" `
    -WorkingDirectory (Join-Path $root "frontend") `
    -Environment $frontendEnv `
    -WindowStyle Hidden `
    -PassThru

@{ backend = $backendProc.Id; frontend = $frontendProc.Id; backend_port = $backendPort } |
    ConvertTo-Json | Set-Content $pidsFile

Write-Host "Started: backend=$($backendProc.Id) frontend=$($frontendProc.Id) backend_port=$backendPort"
