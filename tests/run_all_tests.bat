@echo off
setlocal enabledelayedexpansion

:: ============================================
::  DevForgeAI Complete Test Suite
::  Outputs: tests\reports\test_report_YYYY-MM-DD_HHMMSS.md
:: ============================================

:: Timestamp for filenames
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set TIMESTAMP=%datetime:~0,4%-%datetime:~4,2%-%datetime:~6,2%_%datetime:~8,2%%datetime:~10,2%%datetime:~12,2%
set REPORT_DIR=G:\Model_Mesh\tests\reports
set REPORT_FILE=%REPORT_DIR%\test_report_%TIMESTAMP%.md
set PYTEST_JSON=%REPORT_DIR%\pytest_results_%TIMESTAMP%.json
set PYTEST_LOG=%REPORT_DIR%\pytest_output_%TIMESTAMP%.txt
set E2E_JSON=%REPORT_DIR%\e2e_results_%TIMESTAMP%.json
set E2E_LOG=%REPORT_DIR%\e2e_output_%TIMESTAMP%.txt
set BACKEND_URL=

:: Create reports dir
if not exist "%REPORT_DIR%" mkdir "%REPORT_DIR%"

echo ============================================
echo  DevForgeAI Complete Test Suite
echo  Report: %REPORT_FILE%
echo ============================================
echo.

:: ---- Pre-flight checks ----
set BACKEND_OK=0
set FRONTEND_OK=0

curl -s http://localhost:19001/v1/health >nul 2>&1
if %errorlevel% equ 0 (
    set BACKEND_OK=1
    set BACKEND_URL=http://localhost:19001
    echo [OK] Backend is healthy at %BACKEND_URL%
) else (
    curl -s http://localhost:19000/v1/health >nul 2>&1
)

if %BACKEND_OK% equ 0 if %errorlevel% equ 0 (
    set BACKEND_OK=1
    set BACKEND_URL=http://localhost:19000
    echo [OK] Backend is healthy
) else (
    echo [ERROR] Backend is not running at localhost:19001 or localhost:19000
    echo Please start DevForgeAI first: devforgeai_startup.bat
    exit /b 1
)

curl -s http://localhost:3001 >nul 2>&1
if %errorlevel% equ 0 (
    set FRONTEND_OK=1
    echo [OK] Frontend is healthy
) else (
    echo [WARN] Frontend not detected at localhost:3001 — E2E tests will be skipped
)

echo.
echo ============================================
echo  PART 1: Backend API Tests (pytest)
echo ============================================
echo.

cd /d G:\Model_Mesh

:: Install pytest-json-report if missing
python -c "import pytest_jsonreport" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing pytest-json-report...
    pip install pytest-json-report >nul 2>&1
)

if exist tests\conftest.py (
    echo Running pytest... (output: %PYTEST_LOG%)
    set DEVFORGEAI_URL=%BACKEND_URL%
    set DEVFORGEAI_API_URL=%BACKEND_URL%
    python -m pytest tests\ -v --tb=long --ignore=tests\e2e --ignore=tests\manual --json-report --json-report-file="%PYTEST_JSON%" >"!PYTEST_LOG!" 2>&1
    set PYTEST_EXIT=!errorlevel!
    :: Show summary on console
    echo.
    findstr /R "passed failed error skipped" "!PYTEST_LOG!"
    echo.
    echo [pytest exit code: !PYTEST_EXIT!  — full output: !PYTEST_LOG!]
) else (
    echo [SKIP] No pytest tests found
    set PYTEST_EXIT=-1
)

echo.
echo ============================================
echo  PART 2: Frontend E2E Tests (Playwright)
echo ============================================
echo.

if %FRONTEND_OK% equ 0 (
    echo [SKIP] Frontend not running — skipping E2E tests
    set PW_EXIT=-1
    goto :generate_report
)

cd /d G:\Model_Mesh\tests\e2e
if not exist node_modules (
    echo Installing Playwright...
    npm install >nul 2>&1
    npx playwright install chromium >nul 2>&1
)

echo Running Playwright... (output: %E2E_LOG%)
npx playwright test --reporter=json >"%E2E_JSON%" 2>"%E2E_LOG%"
set PW_EXIT=!errorlevel!

:: Also capture list output for readability
npx playwright test --reporter=list >>"%E2E_LOG%" 2>&1
echo.
echo [Playwright exit code: !PW_EXIT!]

:generate_report
echo.
echo ============================================
echo  Generating Report...
echo ============================================
echo.

cd /d G:\Model_Mesh

:: Generate the markdown report using Python
python tests\generate_report.py "%PYTEST_JSON%" "%E2E_JSON%" "%PYTEST_LOG%" "%E2E_LOG%" "%REPORT_FILE%" "%TIMESTAMP%"

if exist "%REPORT_FILE%" (
    echo.
    echo ============================================
    echo  REPORT GENERATED
    echo  %REPORT_FILE%
    echo ============================================
    echo.
    type "%REPORT_FILE%"
    echo.
) else (
    echo [ERROR] Report generation failed — raw logs available:
    echo   %PYTEST_LOG%
    echo   %E2E_LOG%
)

pause
