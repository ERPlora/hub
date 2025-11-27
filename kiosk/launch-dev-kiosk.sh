#!/bin/bash
# ERPlora Hub - Development Kiosk Mode Launcher
#
# This script starts Django development server and launches browser in kiosk mode
# Useful for testing kiosk mode during development without building the desktop app
#
# Usage:
#   ./launch-dev-kiosk.sh                 # Start Django + browser kiosk
#   ./launch-dev-kiosk.sh --port 8001     # Custom port

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
PORT=8001
URL="http://localhost:${PORT}"
VENV_PATH=".venv"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --port)
            PORT="$2"
            URL="http://localhost:${PORT}"
            shift 2
            ;;
        --venv)
            VENV_PATH="$2"
            shift 2
            ;;
        --help)
            echo "ERPlora Hub - Development Kiosk Mode Launcher"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --port PORT   Django server port (default: 8001)"
            echo "  --venv PATH   Virtual environment path (default: .venv)"
            echo "  --help        Show this help message"
            echo ""
            echo "Example:"
            echo "  $0 --port 8002"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
HUB_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

echo -e "${BLUE}╔════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  ERPlora Hub - Dev Kiosk Mode                 ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Hub Directory:${NC} $HUB_DIR"
echo -e "${GREEN}Port:${NC} $PORT"
echo -e "${GREEN}URL:${NC} $URL"
echo ""

# Change to hub directory
cd "$HUB_DIR"

# Check if virtual environment exists
if [[ ! -d "$VENV_PATH" ]]; then
    echo -e "${RED}Virtual environment not found: $VENV_PATH${NC}"
    echo "Create it first with: uv venv && uv pip install -e ."
    exit 1
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source "$VENV_PATH/bin/activate"

# Kill any existing Django server on this port
echo -e "${YELLOW}Checking for existing server on port $PORT...${NC}"
if lsof -ti:$PORT > /dev/null 2>&1; then
    echo "Killing existing server on port $PORT"
    lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# Start Django development server in background
echo -e "${YELLOW}Starting Django development server...${NC}"
python manage.py runserver $PORT > /tmp/erplora-dev-kiosk.log 2>&1 &
DJANGO_PID=$!

echo "Django PID: $DJANGO_PID"
echo "Logs: /tmp/erplora-dev-kiosk.log"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"

    # Kill Django server
    if kill -0 $DJANGO_PID 2>/dev/null; then
        echo "Stopping Django server (PID: $DJANGO_PID)"
        kill $DJANGO_PID 2>/dev/null || true
    fi

    # Kill any remaining processes on the port
    if lsof -ti:$PORT > /dev/null 2>&1; then
        echo "Cleaning up port $PORT"
        lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
    fi

    echo -e "${GREEN}✓ Cleanup complete${NC}"
    exit 0
}

trap cleanup INT TERM

# Wait for Django to start
echo -e "${YELLOW}Waiting for Django to start...${NC}"
MAX_WAIT=15
WAITED=0
while [[ $WAITED -lt $MAX_WAIT ]]; do
    if curl -s http://localhost:$PORT > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Django started successfully${NC}"
        break
    fi
    sleep 1
    WAITED=$((WAITED + 1))
    echo "  Waiting... ($WAITED/$MAX_WAIT)"
done

if [[ $WAITED -eq $MAX_WAIT ]]; then
    echo -e "${RED}Django failed to start within $MAX_WAIT seconds${NC}"
    echo "Check logs: tail -f /tmp/erplora-dev-kiosk.log"
    cleanup
    exit 1
fi

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
else
    echo -e "${RED}Unsupported OS: $OSTYPE${NC}"
    cleanup
    exit 1
fi

# Launch browser in kiosk mode
echo ""
echo -e "${YELLOW}Launching browser in kiosk mode...${NC}"

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
        cleanup
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
        cleanup
        exit 1
    fi
fi

echo -e "${GREEN}✓ Browser launched in kiosk mode${NC}"
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Kiosk mode is running                         ║${NC}"
echo -e "${GREEN}║  Press Ctrl+C to stop                          ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
echo ""
echo "Django logs: tail -f /tmp/erplora-dev-kiosk.log"

# Wait for Ctrl+C
while true; do
    # Check if Django is still running
    if ! kill -0 $DJANGO_PID 2>/dev/null; then
        echo -e "${RED}Django server stopped unexpectedly${NC}"
        cleanup
        exit 1
    fi
    sleep 2
done
