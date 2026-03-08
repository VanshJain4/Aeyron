#!/bin/bash
# Kills whatever is using the ESP32 serial port, then starts the bridge.
# Usage: ./run_aeyron_bridge.sh

PORT="${SERIAL_PORT:-/dev/cu.usbmodem1101}"
cd "$(dirname "$0")"

echo "Checking for process using $PORT..."
PIDS=$(lsof -t "$PORT" 2>/dev/null)
if [ -n "$PIDS" ]; then
  echo "Killing process(es) using the port: $PIDS"
  kill $PIDS 2>/dev/null
  sleep 2
  # Force kill if still alive
  PIDS=$(lsof -t "$PORT" 2>/dev/null)
  [ -n "$PIDS" ] && kill -9 $PIDS 2>/dev/null
  sleep 1
  echo "Port released."
else
  echo "Port is free."
fi

if [ ! -e "$PORT" ]; then
  echo ""
  echo "Port $PORT not found. Is the ESP32 plugged in?"
  echo "Available USB serial ports:"
  ls /dev/cu.usb* 2>/dev/null || echo "  (none)"
  echo ""
  echo "If you see a different port (e.g. /dev/cu.usbmodem1102), run:"
  echo "  SERIAL_PORT=/dev/cu.usbmodem1102 ./run_aeyron_bridge.sh"
  exit 1
fi

echo "Starting bridge..."
export SERIAL_PORT="$PORT"
exec python3 aeyron_bridge.py
