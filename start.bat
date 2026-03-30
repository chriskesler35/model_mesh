@echo off
echo Starting DevForgeAI...
cd /d "%~dp0"

echo Clearing ports 19000 and 3001...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":19000 " ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3001 " ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)

timeout /t 2 /nobreak >nul

echo Starting PM2 processes...
pm2 start ecosystem.config.js

echo.
echo DevForgeAI is running in the background.
echo   Frontend: http://localhost:3001
echo   Backend:  http://localhost:19000
echo.
echo To stop:    double-click stop.bat  or  pm2 stop all
echo To restart: pm2 restart all
echo To view logs: pm2 logs
pause
