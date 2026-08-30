@echo off
REM Setup script - Run this ONCE to install Python and dependencies
REM This script will download and set up Python 3.11

setlocal enabledelayedexpansion

cd /d "%~dp0"

echo.
echo ========================================
echo MyfansDownloader - First Time Setup
echo ========================================
echo.
echo This will install Python and dependencies.
echo Please wait...
echo.

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 (
    echo Python 3.9+ is already installed.
    goto install_deps
)
echo Python 3.9+ was not found. Installing Python 3.11...

REM Download Python installer
echo Downloading Python 3.11...
powershell -Command "$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile 'python_installer.exe'"

if not exist "python_installer.exe" (
    echo.
    echo ERROR: Failed to download Python!
    echo Please install Python manually from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo.
echo Installing Python 3.11...
REM Run the installer silently and add Python to PATH
python_installer.exe /quiet InstallAllUsers=0 PrependPath=1

if errorlevel 1 (
    echo.
    echo ERROR: Python installation failed!
    pause
    exit /b 1
)

:install_deps
echo.
echo Installing dependencies...
python -m pip install -r requirements.txt -q

if errorlevel 1 (
    echo.
    echo ERROR: Dependency installation failed!
    pause
    exit /b 1
)

REM Clean up
if exist python_installer.exe del python_installer.exe

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo You can now run: MyfansDownloader.bat
pause
