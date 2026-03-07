#!/usr/bin/env bash
# Kill simulator + anything on 8000/9080 so only live data runs.
echo "Stopping simulator (patient A/B/C) and freeing ports 8000, 9080..."
pkill -f "presage_simulator.py" 2>/dev/null && echo "  Killed simulator" || true
for port in 8000 9080; do
  if lsof -i :$port -t >/dev/null 2>&1; then
    lsof -i :$port -t | xargs kill -9 2>/dev/null || true
    echo "  Killed process on port $port"
  fi
done
sleep 2
echo "Done. Now run:  ./run_live_demo.sh   (in this folder)"
