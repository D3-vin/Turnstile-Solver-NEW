#!/bin/bash

# Default values
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-5072}"
BROWSER_TYPE="${BROWSER_TYPE:-chromium}"
DEBUG="${DEBUG:-false}"
PROXY="${PROXY:-false}"
IPV6="${IPV6:-false}"
THREAD="${THREAD:-4}"
USERAGENT="${USERAGENT:-}"
NO_HEADLESS="${NO_HEADLESS:-false}"

# Build command array
CMD=("python" "api_solver.py")

# Add arguments based on environment variables
if [ "$NO_HEADLESS" = "true" ]; then
    CMD+=("--no-headless")
fi

if [ "$DEBUG" = "true" ]; then
    CMD+=("--debug")
fi

CMD+=("--browser_type" "$BROWSER_TYPE")
CMD+=("--thread" "$THREAD")

if [ "$PROXY" = "true" ]; then
    CMD+=("--proxy")
fi

if [ "$IPV6" = "true" ]; then
    CMD+=("--ipv6")
fi

if [ -n "$USERAGENT" ]; then
    CMD+=("--useragent" "$USERAGENT")
fi

CMD+=("--host" "$HOST")
CMD+=("--port" "$PORT")

# Execute the command
echo "Starting Turnstile Solver with command: ${CMD[*]}"
exec "${CMD[@]}"