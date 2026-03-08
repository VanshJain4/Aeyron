#!/usr/bin/env python3
"""
AEYRON Health — ESP32 Serial → WebSocket Bridge
Reads MR60BHA2 sensor data from ESP32-C6 over USB serial,
parses it, and broadcasts JSON over WebSocket so the iOS app clip can consume it.

Requirements:
    pip install pyserial websockets

Usage:
    python3 aeyron_bridge.py

Then in your Swift app connect to:
    ws://<YOUR_LAPTOP_IP>:8765
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import serial
import serial.tools.list_ports
import websockets
from datetime import datetime
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────
SERIAL_BAUD   = 115200
WS_HOST       = "0.0.0.0"   # listen on all interfaces so iPhone can reach it
WS_PORT       = 8765
# Set to your ESP32 port if auto-detect fails. Env SERIAL_PORT overrides this.
SERIAL_PORT   = os.environ.get("SERIAL_PORT") or None  # e.g. "/dev/cu.usbmodem1101"
# ─────────────────────────────────────────────────────────────────────────────

# Shared latest sensor state (updated by serial reader, sent to every WS client)
latest = {
    "heart_rate":    0.0,
    "breath_rate":   0.0,
    "distance":      0.0,
    "total_phase":   0.0,
    "breath_phase":  0.0,
    "heart_phase":   0.0,
    "timestamp":     "",
}

connected_clients: set = set()
_ws_push_count: int = 0


def auto_detect_port() -> Optional[str]:
    """Return the first USB serial port that looks like an ESP32. Skip simulator/debug ports."""
    skip = ("debug-console", "bluetooth", "bluetooth-incoming", "wireless", "iphone", "ipad")
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        name = (p.device or "").lower()
        if any(s in desc or s in name for s in skip):
            continue
        if any(k in desc for k in ["cp210", "ch340", "ftdi", "esp32", "usb serial", "usb"]):
            print(f"[serial] auto-detected: {p.device}  ({p.description})")
            return p.device
    # No ESP32-like port; list what we have
    ports = list(serial.tools.list_ports.comports())
    if ports:
        print("[serial] No ESP32-like port found. Available ports:")
        for p in ports:
            print(f"         {p.device}  —  {p.description}")
        print("         Plug in the ESP32, then run again. Or set SERIAL_PORT in script or:")
        print("         SERIAL_PORT=/dev/cu.usbmodem1101 python3 aeyron_bridge.py")
    return None


def parse_line(line: str):
    """
    Parse a line like:
        total_phase: 1.23   breath_phase: 0.45   heart_phase: 0.67
        breath_rate: 14.50
        heart_rate: 72.00
        distance: 0.80
    Updates the `latest` dict in-place.
    """
    patterns = {
        "heart_rate":   r"heart_rate:\s*([\d.]+)",
        "breath_rate":  r"breath_rate:\s*([\d.]+)",
        "distance":     r"distance:\s*([\d.]+)",
        "total_phase":  r"total_phase:\s*([\d.]+)",
        "breath_phase": r"breath_phase:\s*([\d.]+)",
        "heart_phase":  r"heart_phase:\s*([\d.]+)",
    }
    updated = False
    for key, pattern in patterns.items():
        m = re.search(pattern, line)
        if m:
            latest[key] = float(m.group(1))
            updated = True
    if updated:
        latest["timestamp"] = datetime.utcnow().isoformat() + "Z"
    return updated


async def serial_reader(port: str):
    """Background task: read serial lines and update `latest`."""
    print(f"[serial] opening {port} @ {SERIAL_BAUD} baud")
    loop = asyncio.get_event_loop()
    try:
        ser = serial.Serial(port, SERIAL_BAUD, timeout=1)
    except serial.SerialException as e:
        print(f"[serial] ERROR: {e}")
        return

    print("[serial] connected — waiting for sensor data…")
    while True:
        try:
            raw = await loop.run_in_executor(None, ser.readline)
            line = raw.decode("utf-8", errors="ignore").strip()
            if line:
                parsed = parse_line(line)
                if parsed:
                    print(f"[sensor] {latest}")
                    # Push to all connected WebSocket clients immediately
                    n = len(connected_clients)
                    if n:
                        msg = json.dumps(latest)
                        await asyncio.gather(
                            *[client.send(msg) for client in connected_clients],
                            return_exceptions=True,
                        )
                        global _ws_push_count
                        _ws_push_count += 1
                        if _ws_push_count % 20 == 1:
                            print(f"[ws] pushed to {n} client(s)")
        except Exception as e:
            print(f"[serial] read error: {e}")
            await asyncio.sleep(0.5)


async def ws_handler(websocket):
    """Handle an incoming WebSocket connection from the iOS app."""
    addr = websocket.remote_address
    print(f"[ws] client connected: {addr}")
    connected_clients.add(websocket)
    try:
        # Send current snapshot immediately on connect
        await websocket.send(json.dumps(latest))
        print(f"[ws] sent initial snapshot to client (heart_rate={latest['heart_rate']}, breath_rate={latest['breath_rate']})")
        # Keep connection alive; data is pushed from serial_reader
        await websocket.wait_closed()
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.discard(websocket)
        print(f"[ws] client disconnected: {addr}")


async def heartbeat_loop():
    """Send latest to all connected clients every 2s so the app gets updates even without new serial data."""
    while True:
        await asyncio.sleep(2.0)
        if connected_clients:
            msg = json.dumps(latest)
            await asyncio.gather(
                *[c.send(msg) for c in connected_clients],
                return_exceptions=True,
            )


async def main():
    port = SERIAL_PORT or auto_detect_port()
    if not port:
        print("[ERROR] No serial port found.")
        print("        1. Plug in the ESP32 via USB.")
        print("        2. In Arduino IDE: Tools → Port — note the port (e.g. /dev/cu.usbmodem1101).")
        print("        3. Close Serial Monitor, then run: SERIAL_PORT=/dev/cu.usbmodem1101 python3 aeyron_bridge.py")
        return

    print(f"[ws] starting WebSocket server on ws://0.0.0.0:{WS_PORT}")
    print("     Connect your iPhone to the same WiFi, then in the app use ws://<MAC_IP>:8765")
    print("     Get Mac IP: ipconfig getifaddr en0")
    print("     Bridge running. If no [sensor] lines appear below, ESP32 may not be sending or wrong port.\n")

    async with websockets.serve(ws_handler, WS_HOST, WS_PORT):
        await asyncio.gather(serial_reader(port), heartbeat_loop())


if __name__ == "__main__":
    asyncio.run(main())
