# DevForgeAI startup wrapper (delegates to hardened Python CLI)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "Starting DevForgeAI (hardened startup)..."
python .\devforgeai.py start
