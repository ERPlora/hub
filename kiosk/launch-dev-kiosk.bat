@echo off
REM ERPlora Hub - Development Kiosk Mode Launcher for Windows
REM
REM This script starts Django development server and launches browser in kiosk mode
REM Useful for testing kiosk mode during development without building the desktop app
REM
REM Usage:
REM   launch-dev-kiosk.bat                 - Start Django + browser kiosk
REM   launch-dev-kiosk.bat --port 8001     - Custom port

setlocal enabledelayedexpansion

REM Default values
set PORT=8001
set URL=http://localhost:%PORT%
set VENV_PATH=.venv

REM Parse arguments
:parse_args
if "%~1"=="" goto end_parse
if "%~1"=="--port" (
    set PORT=%~2
    set URL=http://localhost:!PORT!
    shift
    shift
    goto parse_args
)
if "%~1"=="--venv" (
    set VENV_PATH=%~2
    shift
    shift
    goto parse_args
)
if "%~1"=="--help" (
    echo ERPlora Hub - Development Kiosk Mode Launcher
    echo.
    echo Usage: %~nx0 [OPTIONS]
    echo.
    echo Options:
    echo   --port PORT   Django server port (default: 8001^)
    echo   --venv PATH   Virtual environment path (default: .venv^)
    echo   --help        Show this help message
    echo.
    echo Example:
    echo   %~nx0 --port 8002
    exit /b 0
)
echo Unknown option: %~1
echo Use --help for usage information
exit /b 1

:end_parse

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0
set HUB_DIR=%SCRIPT_DIR%..

echo ╔════════════════════════════════════════════════╗
echo ║  ERPlora Hub - Dev Kiosk Mode                 ║
echo ╚════════════════════════════════════════════════╝
echo.
echo Hub Directory: %HUB_DIR%
echo Port: %PORT%
echo URL: %URL%
echo.

REM Change to hub directory
cd /d "%HUB_DIR%"

REM Check if virtual environment exists
if not exist "%VENV_PATH%" (
    echo Virtual environment not found: %VENV_PATH%
    echo Create it first with: uv venv ^&^& uv pip install -e .
    exit /b 1
)

REM Activate virtual environment
echo Activating virtual environment...
call "%VENV_PATH%\Scripts\activate.bat"

REM Kill any existing process on this port
echo Checking for existing server on port %PORT%...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    echo Killing existing process: %%a
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Start Django development server in background
echo Starting Django development server...
start /B python manage.py runserver %PORT% > "%TEMP%\erplora-dev-kiosk.log" 2>&1

REM Wait for Django to start
echo Waiting for Django to start...
set MAX_WAIT=15
set WAITED=0

:wait_loop
if %WAITED% geq %MAX_WAIT% goto start_failed

REM Check if port is listening
netstat -an | findstr ":%PORT%" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo ✓ Django started successfully
    goto start_success
)

timeout /t 1 /nobreak >nul
set /a WAITED+=1
echo   Waiting... (!WAITED!/%MAX_WAIT%)
goto wait_loop

:start_failed
echo Django failed to start within %MAX_WAIT% seconds
echo Check logs: type "%TEMP%\erplora-dev-kiosk.log"
exit /b 1

:start_success
echo.
echo Launching browser in kiosk mode...

REM Try browsers in order of preference
where chrome.exe >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Using Google Chrome
    start "" /min chrome.exe --kiosk --kiosk-printing --no-first-run --disable-infobars --disable-session-crashed-bubble --disable-pinch --overscroll-history-navigation=0 --disable-features=Translate --disable-notifications --disable-default-apps --no-default-browser-check --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding "%URL%" >nul 2>&1
    goto browser_launched
)

where msedge.exe >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Using Microsoft Edge
    start "" /min msedge.exe --kiosk --kiosk-printing --no-first-run --disable-infobars --disable-session-crashed-bubble --disable-pinch --overscroll-history-navigation=0 --disable-notifications --disable-default-apps --no-default-browser-check --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding "%URL%" >nul 2>&1
    goto browser_launched
)

REM Try program files locations
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    echo Using Google Chrome
    start "" /min "%ProgramFiles%\Google\Chrome\Application\chrome.exe" --kiosk --kiosk-printing --no-first-run --disable-infobars --disable-session-crashed-bubble --disable-pinch --overscroll-history-navigation=0 --disable-features=Translate --disable-notifications --disable-default-apps --no-default-browser-check --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding "%URL%" >nul 2>&1
    goto browser_launched
)

if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    echo Using Google Chrome
    start "" /min "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" --kiosk --kiosk-printing --no-first-run --disable-infobars --disable-session-crashed-bubble --disable-pinch --overscroll-history-navigation=0 --disable-features=Translate --disable-notifications --disable-default-apps --no-default-browser-check --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding "%URL%" >nul 2>&1
    goto browser_launched
)

if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
    echo Using Microsoft Edge
    start "" /min "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" --kiosk --kiosk-printing --no-first-run --disable-infobars --disable-session-crashed-bubble --disable-pinch --overscroll-history-navigation=0 --disable-notifications --disable-default-apps --no-default-browser-check --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding "%URL%" >nul 2>&1
    goto browser_launched
)

echo No supported browser found!
echo Please install Chrome or Edge
exit /b 1

:browser_launched
echo ✓ Browser launched in kiosk mode
echo.
echo ╔════════════════════════════════════════════════╗
echo ║  Kiosk mode is running                         ║
echo ║  Press Ctrl+C to stop                          ║
echo ╚════════════════════════════════════════════════╝
echo.
echo Django logs: type "%TEMP%\erplora-dev-kiosk.log"

REM Wait for Ctrl+C
pause >nul

REM Cleanup on exit
echo.
echo Shutting down...

REM Kill Django server
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    echo Stopping Django server: %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo ✓ Cleanup complete
exit /b 0
