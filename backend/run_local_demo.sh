#!/usr/bin/env bash
# Run full demo locally: free port 8000, start API, simulator, and serve demo.html.
# Open http://localhost:9080/demo.html in your browser. Ctrl+C stops all.
set -e
cd "$(dirname "$0")"

# Free port 8000
if lsof -i :8000 -t >/dev/null 2>&1; then
  echo "Freeing port 8000..."
  lsof -i :8000 -t | xargs kill -9 2>/dev/null || true
  sleep 2
fi

# Free port 9080 if in use
if lsof -i :9080 -t >/dev/null 2>&1; then
  lsof -i :9080 -t | xargs kill -9 2>/dev/null || true
  sleep 1
fi

API_PID=""
SIM_PID=""
HTTP_PID=""
cleanup() {
  [ -n "$API_PID" ] && kill $API_PID 2>/dev/null
  [ -n "$SIM_PID" ] && kill $SIM_PID 2>/dev/null
  [ -n "$HTTP_PID" ] && kill $HTTP_PID 2>/dev/null
  exit 0
}
trap cleanup INT TERM

echo "Starting API on http://localhost:8000 ..."
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 &
API_PID=$!
sleep 3

echo "Starting vitals simulator (patient B, 1s) ..."
python3 presage_simulator.py B --interval 1 &
SIM_PID=$!
sleep 1

echo "Serving demo page on http://localhost:9080 ..."
python3 -m http.server 9080 &
HTTP_PID=$!

echo ""
echo "  Open in browser:  http://localhost:9080/demo.html"
echo "  Then click 'Start camera' and allow when prompted."
echo "  Ctrl+C to stop."
echo ""
wait
