@echo off
echo Stopping DevForgeAI...
echo.

:: Kill backend (port 19000)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":19000 " ^| findstr "LISTENING"') do (
    echo Killing backend PID %%a
    taskkill /PID %%a /F >nul 2>&1
)

:: Kill frontend (port 3001)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3001 " ^| findstr "LISTENING"') do (
    echo Killing frontend PID %%a
    taskkill /PID %%a /F >nul 2>&1
)

:: Also kill any orphaned node processes running next dev for this project
for /f "tokens=2" %%a in ('wmic process where "CommandLine like '%%Model_Mesh%%frontend%%next%%'" get ProcessId /format:value 2^>nul ^| findstr "="') do (
    echo Killing orphan node PID %%a
    taskkill /PID %%a /F >nul 2>&1
)

echo.
echo DevForgeAI stopped.
pause
