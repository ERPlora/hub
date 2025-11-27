@echo off
REM ERPlora Hub - Kiosk Mode Launcher for Windows
REM
REM This script launches the ERPlora Hub in kiosk mode (fullscreen, no browser UI)
REM Suitable for dedicated POS terminals, kiosks, and single-purpose devices.
REM
REM Usage:
REM   launch-kiosk.bat                    - Launch in kiosk mode (auto-detect)
REM   launch-kiosk.bat --web              - Launch web browser in kiosk mode
REM   launch-kiosk.bat --desktop          - Launch PyInstaller app in kiosk mode

setlocal enabledelayedexpansion

REM Default values
set MODE=auto
set PORT=8001
set URL=http://localhost:%PORT%

REM Parse arguments
:parse_args
if "%~1"=="" goto end_parse
if "%~1"=="--web" (
    set MODE=web
    shift
    goto parse_args
)
if "%~1"=="--desktop" (
    set MODE=desktop
    shift
    goto parse_args
)
if "%~1"=="--port" (
    set PORT=%~2
    set URL=http://localhost:!PORT!
    shift
    shift
    goto parse_args
)
if "%~1"=="--url" (
    set URL=%~2
    shift
    shift
    goto parse_args
)
if "%~1"=="--help" (
    echo ERPlora Hub - Kiosk Mode Launcher
    echo.
    echo Usage: %~nx0 [OPTIONS]
    echo.
    echo Options:
    echo   --web         Launch web browser in kiosk mode
    echo   --desktop     Launch PyInstaller app in kiosk mode
    echo   --port PORT   Django server port (default: 8001^)
    echo   --url URL     Custom URL to launch (default: http://localhost:8001^)
    echo   --help        Show this help message
    echo.
    echo Examples:
    echo   %~nx0                      # Auto-detect mode
    echo   %~nx0 --web                # Force web browser kiosk mode
    echo   %~nx0 --desktop            # Force desktop app kiosk mode
    echo   %~nx0 --web --url https://erplora.com
    exit /b 0
)
echo Unknown option: %~1
echo Use --help for usage information
exit /b 1

:end_parse

echo ╔════════════════════════════════════════════════╗
echo ║  ERPlora Hub - Kiosk Mode Launcher            ║
echo ╚════════════════════════════════════════════════╝
echo.
echo OS: Windows
echo Mode: %MODE%
echo URL: %URL%
echo.

REM Auto-detect mode if not specified
if "%MODE%"=="auto" (
    echo Auto-detecting mode...

    REM Check if desktop app exists
    if exist "%ProgramFiles%\ERPlora Hub\ERPloraHub.exe" (
        set MODE=desktop
        echo ^→ Found desktop app, using desktop mode
    ) else if exist "dist\ERPloraHub.exe" (
        set MODE=desktop
        echo ^→ Found desktop app in dist, using desktop mode
    ) else (
        set MODE=web
        echo ^→ Desktop app not found, using web mode
    )
    echo.
)

REM Launch based on mode
if "%MODE%"=="web" goto launch_web
if "%MODE%"=="desktop" goto launch_desktop

echo Invalid mode: %MODE%
exit /b 1

:launch_web
echo Launching web browser in kiosk mode...

REM Try browsers in order of preference
where chrome.exe >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Using Google Chrome
    start "" /min chrome.exe --kiosk --kiosk-printing --no-first-run --disable-infobars --disable-session-crashed-bubble --disable-pinch --overscroll-history-navigation=0 --disable-features=Translate --disable-notifications --disable-default-apps --no-default-browser-check --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding "%URL%" >nul 2>&1
    goto web_launched
)

where msedge.exe >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Using Microsoft Edge
    start "" /min msedge.exe --kiosk --kiosk-printing --no-first-run --disable-infobars --disable-session-crashed-bubble --disable-pinch --overscroll-history-navigation=0 --disable-notifications --disable-default-apps --no-default-browser-check --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding "%URL%" >nul 2>&1
    goto web_launched
)

REM Try program files locations
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    echo Using Google Chrome
    start "" /min "%ProgramFiles%\Google\Chrome\Application\chrome.exe" --kiosk --kiosk-printing --no-first-run --disable-infobars --disable-session-crashed-bubble --disable-pinch --overscroll-history-navigation=0 --disable-features=Translate --disable-notifications --disable-default-apps --no-default-browser-check --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding "%URL%" >nul 2>&1
    goto web_launched
)

if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    echo Using Google Chrome
    start "" /min "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" --kiosk --kiosk-printing --no-first-run --disable-infobars --disable-session-crashed-bubble --disable-pinch --overscroll-history-navigation=0 --disable-features=Translate --disable-notifications --disable-default-apps --no-default-browser-check --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding "%URL%" >nul 2>&1
    goto web_launched
)

if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
    echo Using Microsoft Edge
    start "" /min "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" --kiosk --kiosk-printing --no-first-run --disable-infobars --disable-session-crashed-bubble --disable-pinch --overscroll-history-navigation=0 --disable-notifications --disable-default-apps --no-default-browser-check --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding "%URL%" >nul 2>&1
    goto web_launched
)

echo No supported browser found!
echo Please install Chrome or Edge
exit /b 1

:web_launched
echo ✓ Browser launched in kiosk mode
echo.
echo Press Ctrl+C to stop the kiosk
pause >nul
exit /b 0

:launch_desktop
echo Launching desktop app in kiosk mode...

REM Find the desktop app
set APP_PATH=
if exist "%ProgramFiles%\ERPlora Hub\ERPloraHub.exe" (
    set "APP_PATH=%ProgramFiles%\ERPlora Hub\ERPloraHub.exe"
) else if exist "dist\ERPloraHub.exe" (
    set "APP_PATH=dist\ERPloraHub.exe"
)

if "!APP_PATH!"=="" (
    echo Desktop app not found!
    echo.
    echo Build the app first with: python build.py
    exit /b 1
)

echo Launching: !APP_PATH!
start "" "!APP_PATH!" --kiosk

echo ✓ Desktop app launched in kiosk mode
echo.
echo Press Ctrl+C to stop
pause >nul
exit /b 0
