#!/usr/bin/env bash
# Start API + simulator for live-feel demo. Ctrl+C stops both.
set -e
cd "$(dirname "$0")"
API_PID=""
SIM_PID=""
cleanup() { [ -n "$API_PID" ] && kill $API_PID 2>/dev/null; [ -n "$SIM_PID" ] && kill $SIM_PID 2>/dev/null; exit 0; }
trap cleanup INT TERM

# Free port 8000 so bind succeeds
if lsof -i :8000 -t >/dev/null 2>&1; then
  echo "Freeing port 8000..."
  lsof -i :8000 -t | xargs kill -9 2>/dev/null || true
  sleep 2
fi

echo "Starting API on port 8000..."
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 &
API_PID=$!
sleep 3
echo "Starting vitals simulator (patient B, 1s interval)..."
python3 presage_simulator.py B --interval 1 &
SIM_PID=$!
echo "Demo running. Camera + VitalsPanel in browser. Ctrl+C to stop."
wait
