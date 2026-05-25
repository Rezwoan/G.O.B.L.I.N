"""
Screen interaction: screenshots, clicks, scrolling, holding.

Uses mss for screenshots (fast, works on Windows without ADB).
Uses win32api/win32gui for input injection.

Two click modes:
  foreground — moves the real cursor, works for every app (default)
  background — PostMessage, doesn't move cursor, may not work for all games
"""

import time

import cv2
import mss
import numpy as np
import win32api
import win32con
import win32gui
from PIL import Image

from .config import AppConfig


class GameScreen:
    """Captures game screenshots and injects mouse input."""

    def __init__(self, config: AppConfig):
        self.config = config

    # ── Window ────────────────────────────────────────────────────────────

    def find_hwnd(self) -> int:
        """Find the game window handle by title.  Returns 0 if not found."""
        title = self.config.settings.get("window_title", "").strip()
        return win32gui.FindWindow(None, title) if title else 0

    def game_rect(self) -> tuple[int, int, int, int] | None:
        """Return (x, y, width, height) of the game window, or None."""
        hwnd = self.find_hwnd()
        if not hwnd:
            return None
        r = win32gui.GetWindowRect(hwnd)
        w, h = r[2] - r[0], r[3] - r[1]
        return (r[0], r[1], w, h) if w > 0 and h > 0 else None

    @staticmethod
    def list_windows() -> list[tuple[int, str]]:
        """Enumerate all visible windows.  Returns [(hwnd, title), …]."""
        results: list[tuple[int, str]] = []
        def _cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                if title:
                    results.append((hwnd, title))
        win32gui.EnumWindows(_cb, None)
        return sorted(results, key=lambda x: x[1].lower())

    # ── Screenshots ───────────────────────────────────────────────────────

    def grab_game(self) -> tuple[np.ndarray, int, int]:
        """
        Screenshot the game window region (full screen as fallback).

        Returns
        -------
        (bgr_image, offset_x, offset_y)
            All pixel coords in the image need +offset_x, +offset_y
            to become absolute screen coords.
        """
        rect = self.game_rect()
        if rect:
            gx, gy, gw, gh = rect
            with mss.mss() as sct:
                raw = sct.grab({"top": gy, "left": gx, "width": gw, "height": gh})
            pil = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR), gx, gy

        with mss.mss() as sct:
            raw = sct.grab(sct.monitors[0])
        pil = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR), 0, 0

    @staticmethod
    def grab_fullscreen_pil() -> Image.Image:
        """Full-screen PIL image (for the rubber-band capture overlay)."""
        with mss.mss() as sct:
            raw = sct.grab(sct.monitors[0])
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    # ── Input: click ──────────────────────────────────────────────────────

    def click(self, x: int, y: int):
        """
        Click at absolute screen coordinates.
        Mode is controlled by config.settings["click_mode"].
        """
        delay = self.config.settings.get("click_delay_ms", 150) / 1000.0
        mode  = self.config.settings.get("click_mode", "foreground")

        if mode == "background":
            hwnd = self.find_hwnd()
            if hwnd:
                try:
                    # ScreenToClient gives proper client-area coords
                    # (accounts for title bar, borders, etc.)
                    cx, cy = win32gui.ScreenToClient(hwnd, (x, y))
                    lp = (cy & 0xFFFF) << 16 | (cx & 0xFFFF)
                    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN,
                                          win32con.MK_LBUTTON, lp)
                    time.sleep(delay)
                    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lp)
                    return
                except Exception:
                    pass  # fall through to foreground

        # Foreground: move cursor + hardware mouse event (always works)
        win32api.SetCursorPos((x, y))
        time.sleep(0.03)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(delay)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    # ── Input: hold ───────────────────────────────────────────────────────

    def hold(self, x: int, y: int, duration_ms: int):
        """Press and hold at (x, y) for duration_ms milliseconds."""
        win32api.SetCursorPos((x, y))
        time.sleep(0.03)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(duration_ms / 1000.0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    # ── Input: scroll (zoom) ─────────────────────────────────────────────

    def scroll(self, x: int, y: int, clicks: int = -1):
        """
        Mouse wheel at (x, y).  Negative clicks = scroll down (zoom out in CoC).
        """
        win32api.SetCursorPos((x, y))
        time.sleep(0.03)
        win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, x, y, clicks * 120, 0)

    def ensure_game_focus(self):
        """
        Bring the game window to the foreground so it receives input events.

        Google Play Games and similar emulator containers sometimes require
        the window to be the active/focused window before they accept scroll
        (wheel) events.  Regular mouse clicks via mouse_event() work without
        focus, but wheel events may not — so always call this before zoom_out().
        """
        hwnd = self.find_hwnd()
        if not hwnd:
            return
        try:
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.08)   # small settle time after focus change
        except Exception:
            pass

    def zoom_out(self, ticks: int = 5):
        """
        Zoom out by scrolling down at the centre of the game window.
        Focuses the game window first so the scroll events are received.
        """
        self.ensure_game_focus()          # game must have focus for wheel events
        rect = self.game_rect()
        if rect:
            cx = rect[0] + rect[2] // 2
            cy = rect[1] + rect[3] // 2
        else:
            with mss.mss() as sct:
                mon = sct.monitors[0]
                cx, cy = mon["width"] // 2, mon["height"] // 2
        for _ in range(ticks):
            self.scroll(cx, cy, -1)
            time.sleep(0.08)

    # ── Input: click a configured slot ────────────────────────────────────

    def click_slot(self, slot: dict, vision=None) -> bool:
        """
        Click a configured slot.
        IMAGE mode: uses Vision to find position on screen, then clicks.
        COORD mode: clicks stored coordinates.
        Returns True if a click was actually performed.
        """
        if slot.get("mode") == "IMAGE" and vision:
            found, _, (ax, ay) = vision.match_slot(slot)
            if found:
                self.click(ax, ay)
                return True
        coord = slot.get("coord")
        if coord:
            self.click(int(coord[0]), int(coord[1]))
            return True
        return False
