# DevForgeAI Background Launcher — no windows, no redirection issues

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidsFile = Join-Path $root ".devforgeai.pids"
$logsDir  = Join-Path $root "logs"
if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir | Out-Null }

function Kill-Port($port) {
    netstat -ano | Select-String ":$port\s" | Select-String "LISTENING" |
        ForEach-Object { ($_ -split '\s+')[-1] } | Select-Object -Unique |
        ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } catch {} }
}
Kill-Port 19000
Kill-Port 3001
Start-Sleep -Seconds 2

# Backend
$backendProc = Start-Process `
    -FilePath (Join-Path $root "backend\venv\Scripts\python.exe") `
    -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port 19000 --reload" `
    -WorkingDirectory (Join-Path $root "backend") `
    -WindowStyle Hidden `
    -PassThru

# Frontend
$nextBin = Join-Path $root "frontend\node_modules\next\dist\bin\next"
$frontendProc = Start-Process `
    -FilePath "node.exe" `
    -ArgumentList "`"$nextBin`" dev -p 3001" `
    -WorkingDirectory (Join-Path $root "frontend") `
    -WindowStyle Hidden `
    -PassThru

@{ backend = $backendProc.Id; frontend = $frontendProc.Id } |
    ConvertTo-Json | Set-Content $pidsFile

Write-Host "Started: backend=$($backendProc.Id) frontend=$($frontendProc.Id)"
