#!/usr/bin/env bash
# Live data demo: API + webcam bridge (real pulse from camera). No simulator.
# Open http://localhost:9080/demo.html — vitals are from your webcam.
# If you had many terminals running, run:  ./stop_all.sh   first, then this.
set -e
cd "$(dirname "$0")"

for port in 8000 9080; do
  if lsof -i :$port -t >/dev/null 2>&1; then
    echo "Freeing port $port..."
    lsof -i :$port -t | xargs kill -9 2>/dev/null || true
    sleep 2
  fi
done

API_PID=""
HTTP_PID=""
cleanup() {
  [ -n "$API_PID" ] && kill $API_PID 2>/dev/null
  [ -n "$HTTP_PID" ] && kill $HTTP_PID 2>/dev/null
  exit 0
}
trap cleanup INT TERM

echo "Starting API on http://localhost:8000 ..."
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 &
API_PID=$!
sleep 3

echo "Serving demo page on http://localhost:9080 ..."
python3 -m http.server 9080 &
HTTP_PID=$!

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
echo ""
echo "  Open:  http://localhost:9080/demo.html"
echo ""
echo "  --- LIVE VITALS: use a SECOND terminal ---"
echo "  In another terminal run:"
echo "    cd $DEMO_DIR"
echo "    python3 -u live_vitals_bridge.py --interval 1"
echo "  Keep it open. You should see 'Bridge: POST ok' every second."
echo "  Then face the camera in the browser and wait ~30 sec."
echo "  Ctrl+C here stops API and demo server."
echo ""
wait
