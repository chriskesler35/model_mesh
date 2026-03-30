@echo off
echo Starting DevForgeAI...
cd /d "%~dp0"
pm2 start ecosystem.config.js
echo.
echo DevForgeAI is running in the background.
echo   Frontend: http://localhost:3001
echo   Backend:  http://localhost:19000
echo.
echo To stop:   pm2 stop all
echo To restart: pm2 restart all
echo To view logs: pm2 logs
pause
