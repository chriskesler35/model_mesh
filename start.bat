@echo off
setlocal

cd /d "%~dp0"
echo Starting DevForgeAI (hardened startup)...
echo.

python devforgeai.py start

if errorlevel 1 (
  echo.
  echo Startup failed. See output above for health check details.
  pause
)
