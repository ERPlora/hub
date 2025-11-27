#!/bin/bash
# ERPlora Hub - Kiosk Mode Launcher for macOS/Linux
#
# This script launches the ERPlora Hub in kiosk mode (fullscreen, no browser UI)
# Suitable for dedicated POS terminals, kiosks, and single-purpose devices.
#
# Usage:
#   ./launch-kiosk.sh                    # Launch in kiosk mode
#   ./launch-kiosk.sh --web              # Launch web browser in kiosk mode
#   ./launch-kiosk.sh --desktop          # Launch PyInstaller app in kiosk mode

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
MODE="auto"
PORT=8001
URL="http://localhost:${PORT}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --web)
            MODE="web"
            shift
            ;;
        --desktop)
            MODE="desktop"
            shift
            ;;
        --port)
            PORT="$2"
            URL="http://localhost:${PORT}"
            shift 2
            ;;
        --url)
            URL="$2"
            shift 2
            ;;
        --help)
            echo "ERPlora Hub - Kiosk Mode Launcher"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --web         Launch web browser in kiosk mode"
            echo "  --desktop     Launch PyInstaller app in kiosk mode"
            echo "  --port PORT   Django server port (default: 8001)"
            echo "  --url URL     Custom URL to launch (default: http://localhost:8001)"
            echo "  --help        Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                      # Auto-detect mode"
            echo "  $0 --web                # Force web browser kiosk mode"
            echo "  $0 --desktop            # Force desktop app kiosk mode"
            echo "  $0 --web --url https://erplora.com"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
else
    echo -e "${RED}Unsupported OS: $OSTYPE${NC}"
    echo "This script only supports macOS and Linux"
    exit 1
fi

echo -e "${BLUE}╔════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  ERPlora Hub - Kiosk Mode Launcher            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}OS:${NC} $OS"
echo -e "${GREEN}Mode:${NC} $MODE"
echo -e "${GREEN}URL:${NC} $URL"
echo ""

# Function to launch web browser in kiosk mode
launch_web_kiosk() {
    echo -e "${YELLOW}Launching web browser in kiosk mode...${NC}"

    if [[ "$OS" == "macos" ]]; then
        # macOS: Try browsers in order of preference
        if command -v /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome &> /dev/null; then
            echo "Using Google Chrome"
            /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
                --kiosk \
                --kiosk-printing \
                --no-first-run \
                --disable-infobars \
                --disable-session-crashed-bubble \
                --disable-pinch \
                --overscroll-history-navigation=0 \
                --disable-features=Translate \
                --disable-notifications \
                --disable-default-apps \
                --no-default-browser-check \
                --silent-launch \
                --disable-background-timer-throttling \
                --disable-backgrounding-occluded-windows \
                --disable-renderer-backgrounding \
                "$URL" > /dev/null 2>&1 &
        elif command -v /Applications/Microsoft\ Edge.app/Contents/MacOS/Microsoft\ Edge &> /dev/null; then
            echo "Using Microsoft Edge"
            /Applications/Microsoft\ Edge.app/Contents/MacOS/Microsoft\ Edge \
                --kiosk \
                --kiosk-printing \
                --no-first-run \
                --disable-infobars \
                --disable-session-crashed-bubble \
                --disable-pinch \
                --overscroll-history-navigation=0 \
                --disable-notifications \
                --disable-default-apps \
                --no-default-browser-check \
                --silent-launch \
                --disable-background-timer-throttling \
                --disable-backgrounding-occluded-windows \
                --disable-renderer-backgrounding \
                "$URL" > /dev/null 2>&1 &
        elif command -v /Applications/Safari.app/Contents/MacOS/Safari &> /dev/null; then
            echo "Using Safari (fullscreen mode)"
            echo -e "${YELLOW}Note: Safari doesn't support true kiosk mode. Press Cmd+Ctrl+F for fullscreen.${NC}"
            open -a Safari "$URL"
        else
            echo -e "${RED}No supported browser found!${NC}"
            echo "Please install Chrome, Edge, or Safari"
            exit 1
        fi

    elif [[ "$OS" == "linux" ]]; then
        # Linux: Try browsers in order of preference
        if command -v google-chrome &> /dev/null; then
            echo "Using Google Chrome"
            google-chrome \
                --kiosk \
                --kiosk-printing \
                --no-first-run \
                --disable-infobars \
                --disable-session-crashed-bubble \
                --disable-pinch \
                --overscroll-history-navigation=0 \
                --disable-features=Translate \
                --disable-notifications \
                --disable-default-apps \
                --no-default-browser-check \
                --disable-background-timer-throttling \
                --disable-backgrounding-occluded-windows \
                --disable-renderer-backgrounding \
                "$URL" > /dev/null 2>&1 &
        elif command -v chromium-browser &> /dev/null; then
            echo "Using Chromium"
            chromium-browser \
                --kiosk \
                --kiosk-printing \
                --no-first-run \
                --disable-infobars \
                --disable-session-crashed-bubble \
                --disable-pinch \
                --overscroll-history-navigation=0 \
                --disable-notifications \
                --disable-default-apps \
                --no-default-browser-check \
                --disable-background-timer-throttling \
                --disable-backgrounding-occluded-windows \
                --disable-renderer-backgrounding \
                "$URL" > /dev/null 2>&1 &
        elif command -v firefox &> /dev/null; then
            echo "Using Firefox"
            firefox --kiosk "$URL" > /dev/null 2>&1 &
        else
            echo -e "${RED}No supported browser found!${NC}"
            echo "Please install Chrome, Chromium, or Firefox"
            exit 1
        fi
    fi

    echo -e "${GREEN}✓ Browser launched in kiosk mode${NC}"
    echo ""
    echo "Press Ctrl+C to stop the kiosk"

    # Wait for Ctrl+C
    trap "echo ''; echo 'Stopping kiosk mode...'; exit 0" INT
    while true; do
        sleep 1
    done
}

# Function to launch desktop app in kiosk mode
launch_desktop_kiosk() {
    echo -e "${YELLOW}Launching desktop app in kiosk mode...${NC}"

    # Find the desktop app
    if [[ "$OS" == "macos" ]]; then
        APP_PATH="/Applications/ERPlora Hub.app/Contents/MacOS/ERPlora Hub"
        if [[ ! -f "$APP_PATH" ]]; then
            # Try local build
            APP_PATH="./dist/ERPlora Hub.app/Contents/MacOS/ERPlora Hub"
        fi
    elif [[ "$OS" == "linux" ]]; then
        APP_PATH="./dist/ERPloraHub"
        if [[ ! -f "$APP_PATH" ]]; then
            APP_PATH="/opt/erplora-hub/ERPloraHub"
        fi
    fi

    if [[ ! -f "$APP_PATH" ]]; then
        echo -e "${RED}Desktop app not found!${NC}"
        echo "Searched for: $APP_PATH"
        echo ""
        echo "Build the app first with: python build.py"
        exit 1
    fi

    echo "Launching: $APP_PATH"
    "$APP_PATH" --kiosk &

    echo -e "${GREEN}✓ Desktop app launched in kiosk mode${NC}"
    echo ""
    echo "Press Ctrl+C to stop"

    # Wait for Ctrl+C
    trap "echo ''; echo 'Stopping...'; exit 0" INT
    while true; do
        sleep 1
    done
}

# Auto-detect mode if not specified
if [[ "$MODE" == "auto" ]]; then
    echo -e "${YELLOW}Auto-detecting mode...${NC}"

    # Check if desktop app exists
    if [[ "$OS" == "macos" ]]; then
        if [[ -f "/Applications/ERPlora Hub.app/Contents/MacOS/ERPlora Hub" ]] ||
           [[ -f "./dist/ERPlora Hub.app/Contents/MacOS/ERPlora Hub" ]]; then
            MODE="desktop"
            echo -e "${GREEN}→ Found desktop app, using desktop mode${NC}"
        else
            MODE="web"
            echo -e "${GREEN}→ Desktop app not found, using web mode${NC}"
        fi
    elif [[ "$OS" == "linux" ]]; then
        if [[ -f "./dist/ERPloraHub" ]] || [[ -f "/opt/erplora-hub/ERPloraHub" ]]; then
            MODE="desktop"
            echo -e "${GREEN}→ Found desktop app, using desktop mode${NC}"
        else
            MODE="web"
            echo -e "${GREEN}→ Desktop app not found, using web mode${NC}"
        fi
    fi
    echo ""
fi

# Launch based on mode
if [[ "$MODE" == "web" ]]; then
    launch_web_kiosk
elif [[ "$MODE" == "desktop" ]]; then
    launch_desktop_kiosk
else
    echo -e "${RED}Invalid mode: $MODE${NC}"
    exit 1
fi
