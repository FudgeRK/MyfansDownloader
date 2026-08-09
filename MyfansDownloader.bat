@echo off
cd /d "%~dp0"
echo.
echo ========================================
echo MyfansDownloader
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed!
    echo.
    echo Run SETUP.bat first to install Python and dependencies.
    echo.
    pause
    exit /b 1
)

echo Running MyfansDownloader...
echo.

python MyfansDownloader_unified.py

echo.
echo Program finished.
pause



