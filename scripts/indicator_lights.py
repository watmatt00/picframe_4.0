#!/usr/bin/env python3
"""
PicFrame indicator light overlay.

Two small colored dots rendered in the upper-right corner of the frame display
via a borderless always-on-top GTK3 window with RGBA transparency.

  Left dot  — Sync: green = synced, amber = not synced or wifi down
  Right dot — WiFi: green = connected, red = disconnected

Polls /dashboard/status every 10 seconds. Keeps last known state on API error.
"""

import json
import math
import time
import urllib.request

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
import cairo

API_URL   = "http://localhost:8000/dashboard/status"
POLL_MS   = 10_000   # 10 s
DOT_R     = 9        # dot radius px (diameter 18 px ≈ 4.5 mm at 96 DPI)
GAP_PX    = 6        # gap between dot edges
PAD_PX    = 4        # padding around dots
MARGIN_PX = 38       # distance from right/top screen edge (~10 mm)
DOT_ALPHA = 0.5      # dot opacity

AMBER = (0.98, 0.75, 0.14)
GREEN = (0.13, 0.77, 0.37)
RED   = (0.94, 0.27, 0.27)


def fetch_status():
    try:
        with urllib.request.urlopen(API_URL, timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        return None


class IndicatorOverlay(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)

        self.sync_color = AMBER
        self.wifi_color = GREEN

        d = DOT_R * 2
        self._cw = d * 2 + GAP_PX + PAD_PX * 2
        self._ch = d + PAD_PX * 2

        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_app_paintable(True)
        self.set_size_request(self._cw, self._ch)

        # RGBA visual for transparent background
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self.connect("draw", self._on_draw)
        self.connect("destroy", Gtk.main_quit)

        # Realize window so we can access the underlying GDK window
        self.realize()

        # override_redirect bypasses the WM entirely — same as Tkinter's
        # overrideredirect(True). This lets us force position and stay on top
        # of fullscreen windows (like Pi3D) without WM interference.
        self.get_window().set_override_redirect(True)

        # Position: upper-right corner
        display = Gdk.Display.get_default()
        monitor = display.get_monitor(0)
        geo = monitor.get_geometry()
        x = geo.x + geo.width - self._cw - MARGIN_PX
        self.move(x, geo.y + MARGIN_PX)

        self.show_all()
        GLib.timeout_add(POLL_MS, self._poll)

    def _on_draw(self, widget, cr):
        # Clear to fully transparent
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()

        cr.set_operator(cairo.OPERATOR_OVER)
        self._draw_dot(cr, PAD_PX + DOT_R, PAD_PX + DOT_R, self.sync_color)
        self._draw_dot(cr, PAD_PX + DOT_R * 3 + GAP_PX, PAD_PX + DOT_R, self.wifi_color)

    def _draw_dot(self, cr, cx, cy, color):
        r, g, b = color
        cr.set_source_rgba(r, g, b, DOT_ALPHA)
        cr.arc(cx, cy, DOT_R, 0, 2 * math.pi)
        cr.fill()

    def _poll(self):
        data = fetch_status()
        if data is not None:
            wifi_ok = data.get("wifi_connected", False)
            sync_ok = data.get("sync_status") == "match" and wifi_ok
            self.sync_color = GREEN if sync_ok else AMBER
            self.wifi_color = GREEN if wifi_ok else RED
            self.queue_draw()
        return True  # keep GLib timer alive


def main():
    for _ in range(6):
        if fetch_status() is not None:
            break
        time.sleep(5)

    overlay = IndicatorOverlay()
    overlay._poll()
    Gtk.main()


if __name__ == "__main__":
    main()
