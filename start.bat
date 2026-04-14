@echo off
setlocal
echo Starting DevForgeAI...
echo.

set BACKEND_PORT=19001

call :is_listening 19001
if %errorlevel% == 0 (
    echo [WARN] Port 19001 already in use - falling back to port 19000.
    set BACKEND_PORT=19000
)

set NEXT_PUBLIC_API_URL=http://localhost:%BACKEND_PORT%
set DEVFORGEAI_BACKEND_PORT=%BACKEND_PORT%

:: Clean stale Next.js cache — prevents blank page after code changes
if exist "G:\Model_Mesh\frontend\.next\cache" (
    echo Cleaning stale frontend cache...
    rmdir /s /q "G:\Model_Mesh\frontend\.next\cache" 2>nul
)

:: Check if backend is already running on the selected port
call :is_listening %BACKEND_PORT%
if %errorlevel% == 0 (
    echo [WARN] Port %BACKEND_PORT% already in use - backend already running, skipping.
) else (
    echo Starting backend on port %BACKEND_PORT%...
    start "DevForgeAI Backend" cmd /k "cd /d "G:\Model_Mesh\backend" && set DEVFORGEAI_BACKEND_PORT=%BACKEND_PORT% && "G:\Model_Mesh\backend\venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT%"
)

:: Check if frontend is already running on port 3001
netstat -ano | findstr ":3001 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% == 0 (
    echo [WARN] Port 3001 already in use - frontend already running, skipping.
) else (
    echo Starting frontend...
    timeout /t 3 /nobreak >nul
    start "DevForgeAI Frontend" cmd /k "cd /d "G:\Model_Mesh\frontend" && set NEXT_PUBLIC_API_URL=%NEXT_PUBLIC_API_URL% && set DEVFORGEAI_BACKEND_PORT=%BACKEND_PORT% && npm run dev"
)

echo.
echo Backend:  http://localhost:%BACKEND_PORT%
echo Frontend: http://localhost:3001
echo API Docs: http://localhost:%BACKEND_PORT%/docs
echo.
pause
goto :eof

:is_listening
netstat -ano | findstr ":%~1 " | findstr "LISTENING" >nul 2>&1
exit /b %errorlevel%
