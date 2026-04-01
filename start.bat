@echo off
echo Starting DevForgeAI...
echo.

:: Clean stale Next.js cache — prevents blank page after code changes
if exist "G:\Model_Mesh\frontend\.next\cache" (
    echo Cleaning stale frontend cache...
    rmdir /s /q "G:\Model_Mesh\frontend\.next\cache" 2>nul
)

:: Check if backend is already running on port 19000
netstat -ano | findstr ":19000 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% == 0 (
    echo [WARN] Port 19000 already in use - backend already running, skipping.
) else (
    echo Starting backend...
    start "DevForgeAI Backend" cmd /k "cd /d "G:\Model_Mesh\backend" && "G:\Model_Mesh\backend\venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 19000"
)

:: Check if frontend is already running on port 3001
netstat -ano | findstr ":3001 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% == 0 (
    echo [WARN] Port 3001 already in use - frontend already running, skipping.
) else (
    echo Starting frontend...
    timeout /t 3 /nobreak >nul
    start "DevForgeAI Frontend" cmd /k "cd /d "G:\Model_Mesh\frontend" && npm run dev"
)

echo.
echo Backend:  http://localhost:19000
echo Frontend: http://localhost:3001
echo API Docs: http://localhost:19000/docs
echo.
pause
