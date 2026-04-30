#!/usr/bin/env python3
"""
PicFrame indicator light overlay.

Two small colored dots rendered in the upper-right corner of the frame display
via a borderless always-on-top Tkinter/XWayland window.

  Top dot    — Sync: green = synced, amber = not synced or wifi down
  Bottom dot — WiFi: green = connected, red = disconnected

Polls /dashboard/status every 10 seconds. Keeps last known state on API error.
"""

import json
import sys
import time
import urllib.request
import tkinter as tk

API_URL   = "http://localhost:8000/dashboard/status"
POLL_MS   = 10_000   # 10 s
DOT_PX    = 8        # ~2 mm at 96 DPI
GAP_PX    = 4
PAD_PX    = 2
MARGIN_PX = 38       # ~10 mm at 96 DPI

AMBER = "#fbbf24"
GREEN = "#22c55e"
RED   = "#ef4444"
BG    = "#111111"


def fetch_status():
    try:
        with urllib.request.urlopen(API_URL, timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        return None


class IndicatorOverlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)

        cw = DOT_PX + PAD_PX * 2
        ch = DOT_PX * 2 + GAP_PX + PAD_PX * 2

        self.canvas = tk.Canvas(
            self.root, width=cw, height=ch, bg=BG, highlightthickness=0
        )
        self.canvas.pack()

        p = PAD_PX
        self.dot_sync = self.canvas.create_oval(p, p, p + DOT_PX, p + DOT_PX,
                                                fill=AMBER, outline="")
        y = p + DOT_PX + GAP_PX
        self.dot_wifi = self.canvas.create_oval(p, y, p + DOT_PX, y + DOT_PX,
                                                fill=GREEN, outline="")

        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"{cw}x{ch}+{sw - cw - MARGIN_PX}+{MARGIN_PX}")

        self.poll()
        self.root.mainloop()

    def poll(self):
        data = fetch_status()
        if data is not None:
            wifi_ok = data.get("wifi_connected", False)
            sync_ok = data.get("sync_status") == "match" and wifi_ok
            self.canvas.itemconfig(self.dot_sync, fill=GREEN if sync_ok else AMBER)
            self.canvas.itemconfig(self.dot_wifi, fill=GREEN if wifi_ok else RED)
        self.root.after(POLL_MS, self.poll)


if __name__ == "__main__":
    # Wait up to 30 s for the API to be ready before opening the window
    for _ in range(6):
        if fetch_status() is not None:
            break
        time.sleep(5)
    IndicatorOverlay()
