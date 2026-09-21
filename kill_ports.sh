#!/bin/bash

PORTS=(3000 4000 5050 8001 8010 8188 27017)

echo "Stopping processes on KONE ports..."

for PORT in "${PORTS[@]}"; do
    PIDS=$(lsof -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | sort -u)

    if [ -n "$PIDS" ]; then
        echo "Port $PORT -> killing PID(s): $PIDS"

        # Try graceful shutdown first
        kill -TERM $PIDS 2>/dev/null || true
    else
        echo "Port $PORT -> nothing running"
    fi
done

sleep 2

echo
echo "Force killing anything still running..."

for PORT in "${PORTS[@]}"; do
    PIDS=$(lsof -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | sort -u)

    if [ -n "$PIDS" ]; then
        echo "Port $PORT -> force killing PID(s): $PIDS"
        kill -9 $PIDS 2>/dev/null || true
    fi
done

echo
echo "Checking ports..."

for PORT in "${PORTS[@]}"; do
    if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "WARNING: Port $PORT is still in use"
        lsof -iTCP:"$PORT" -sTCP:LISTEN
    else
        echo "OK: Port $PORT is free"
    fi
done

echo
echo "Done."
