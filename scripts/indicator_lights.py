#!/usr/bin/env python3
"""
PicFrame indicator light overlay.

Two small colored dots rendered in the upper-right corner of the frame display
via a borderless always-on-top Tkinter/XWayland window.

  Left dot  — Sync: green = synced, amber = not synced or wifi down
  Right dot — WiFi: green = connected, red = disconnected

Polls /dashboard/status every 10 seconds. Keeps last known state on API error.
"""

import json
import time
import urllib.request
import tkinter as tk

API_URL   = "http://localhost:8000/dashboard/status"
POLL_MS   = 10_000   # 10 s
DOT_PX    = 12       # ~3 mm at 96 DPI (50% larger than original 8 px)
GAP_PX    = 5        # horizontal gap between dots
PAD_PX    = 2        # padding inside canvas
MARGIN_PX = 38       # ~10 mm at 96 DPI

AMBER = "#fbbf24"
GREEN = "#22c55e"
RED   = "#ef4444"
BG    = "black"      # punched out by -transparentcolor on compositing systems


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

        # Make the black background transparent on compositing systems.
        # Falls back gracefully (visible dark box) if not supported.
        try:
            self.root.wm_attributes("-transparentcolor", BG)
        except Exception:
            pass

        # Horizontal layout: [sync] [wifi]
        cw = DOT_PX * 2 + GAP_PX + PAD_PX * 2
        ch = DOT_PX + PAD_PX * 2

        self.canvas = tk.Canvas(
            self.root, width=cw, height=ch, bg=BG, highlightthickness=0
        )
        self.canvas.pack()

        p = PAD_PX
        # Left dot — sync
        self.dot_sync = self.canvas.create_oval(
            p, p, p + DOT_PX, p + DOT_PX, fill=AMBER, outline=""
        )
        # Right dot — wifi
        x = p + DOT_PX + GAP_PX
        self.dot_wifi = self.canvas.create_oval(
            x, p, x + DOT_PX, p + DOT_PX, fill=GREEN, outline=""
        )

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
