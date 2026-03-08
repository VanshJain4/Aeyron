#!/usr/bin/env bash
# Quick check: is the API up and is the bridge able to POST?
cd "$(dirname "$0")"
echo "1. Checking API on port 8000..."
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/vitals
echo " (200 = OK)"
echo "2. Starting bridge for 5 seconds (you should see POST ok or an error)..."
timeout 5 python3 -u live_vitals_bridge.py --interval 1 2>&1 || true
echo ""
echo "3. Latest vitals:"
curl -s http://localhost:8000/vitals | python3 -m json.tool 2>/dev/null | head -20 || curl -s http://localhost:8000/vitals
