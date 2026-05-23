#!/usr/bin/env python3
"""
G.O.B.L.I.N Template Capture Tool

Runs silently in the background.
Press F9  → frozen screenshot opens in an OpenCV window.
Drag corners to adjust the green selection rectangle.
Press Enter → type the template name inside the same window → Enter again to save.
Esc cancels the current step. Q closes the window.
Ctrl+C in the console to quit.
"""

import io
import os
import re
import subprocess
import sys
import tempfile
import threading
import tomllib
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

TEMPLATES_DIR = PROJECT_ROOT / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)
REGIONS_TOML = TEMPLATES_DIR / "regions.toml"

WINDOW = "GOBLIN Template Capture"

# BGR colors
C_GREEN  = (  0, 220,   0)
C_CYAN   = (255, 255,   0)   # #00FFFF in BGR
C_WHITE  = (255, 255, 255)
C_SHADOW = ( 30,  30,  30)
C_DIM    = (140, 140, 140)

# Crosshair handle geometry
_H_CIRCLE = 3
_H_LINE   = 8


# ── Config ────────────────────────────────────────────────────────────────────

def _load_adb_config() -> dict:
    cfg = PROJECT_ROOT / "config.toml"
    try:
        with open(cfg, "rb") as f:
            return tomllib.load(f).get("adb", {})
    except FileNotFoundError:
        print(f"Warning: config.toml not found at {cfg} — using defaults")
        return {}


# ── ADB screencap ─────────────────────────────────────────────────────────────

def _screencap(adb_path: str, device: str) -> np.ndarray | None:
    # Primary: exec-out pipe
    try:
        r = subprocess.run(
            [adb_path, "-s", device, "exec-out", "screencap", "-p"],
            capture_output=True, timeout=15,
        )
        if r.returncode == 0 and len(r.stdout) > 1024:
            img = Image.open(io.BytesIO(r.stdout)).convert("RGB")
            return np.array(img)[:, :, ::-1].copy()
    except Exception:
        pass

    # Fallback: save on device → pull
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(tmp_fd)
        try:
            subprocess.run(
                [adb_path, "-s", device, "shell", "screencap", "-p", "/sdcard/goblin_tmpl.png"],
                capture_output=True, timeout=10, check=True,
            )
            subprocess.run(
                [adb_path, "-s", device, "pull", "/sdcard/goblin_tmpl.png", tmp_path],
                capture_output=True, timeout=10, check=True,
            )
            img = Image.open(tmp_path).convert("RGB")
            return np.array(img)[:, :, ::-1].copy()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except Exception:
        pass

    return None


# ── Monitor size ──────────────────────────────────────────────────────────────

def _screen_size() -> tuple[int, int]:
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    w, h = root.winfo_screenwidth(), root.winfo_screenheight()
    root.destroy()
    return w, h


def _scale_frame(frame: np.ndarray, max_w: int, max_h: int) -> tuple[np.ndarray, float]:
    h, w = frame.shape[:2]
    scale = min(max_w / w, max_h / h, 1.0)
    if scale < 1.0:
        frame = cv2.resize(
            frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA
        )
    return frame, scale


# ── Selection state ───────────────────────────────────────────────────────────

class _Selection:
    def __init__(self):
        self.x1 = self.y1 = self.x2 = self.y2 = 0
        self._drag: str | None = None
        self._drag_start = (0, 0)
        self._drag_orig  = (0, 0, 0, 0)

    def activate(self, dw: int, dh: int):
        hw, hh = int(dw * 0.20), int(dh * 0.15)
        mx, my = dw // 2, dh // 2
        self.x1, self.y1 = mx - hw, my - hh
        self.x2, self.y2 = mx + hw, my + hh
        self._drag = None

    def norm(self) -> tuple[int, int, int, int]:
        return (
            min(self.x1, self.x2), min(self.y1, self.y2),
            max(self.x1, self.x2), max(self.y1, self.y2),
        )

    def corner_pts(self) -> dict[str, tuple[int, int]]:
        x1, y1, x2, y2 = self.norm()
        return {"tl": (x1, y1), "tr": (x2, y1), "bl": (x1, y2), "br": (x2, y2)}

    def _hit(self, mx: int, my: int) -> str | None:
        grab = _H_LINE + 4
        for name, (cx, cy) in self.corner_pts().items():
            if abs(mx - cx) <= grab and abs(my - cy) <= grab:
                return name
        return None

    def _inside(self, mx: int, my: int) -> bool:
        x1, y1, x2, y2 = self.norm()
        return x1 + _H_LINE < mx < x2 - _H_LINE and y1 + _H_LINE < my < y2 - _H_LINE

    def on_down(self, x: int, y: int):
        h = self._hit(x, y)
        if h:
            self._drag = h
        elif self._inside(x, y):
            self._drag = "body"
            self._drag_start = (x, y)
            self._drag_orig  = (self.x1, self.y1, self.x2, self.y2)

    def on_move(self, x: int, y: int):
        d = self._drag
        if   d == "tl": self.x1, self.y1 = x, y
        elif d == "tr": self.x2, self.y1 = x, y
        elif d == "bl": self.x1, self.y2 = x, y
        elif d == "br": self.x2, self.y2 = x, y
        elif d == "body":
            dx, dy = x - self._drag_start[0], y - self._drag_start[1]
            ox1, oy1, ox2, oy2 = self._drag_orig
            self.x1, self.y1 = ox1 + dx, oy1 + dy
            self.x2, self.y2 = ox2 + dx, oy2 + dy

    def on_up(self):
        self._drag = None


def _make_mouse_cb(sel: _Selection, enabled: list[bool]):
    """enabled is a one-element list so the callback can see live updates."""
    def cb(event, x, y, flags, param):
        if not enabled[0]:
            return
        if   event == cv2.EVENT_LBUTTONDOWN: sel.on_down(x, y)
        elif event == cv2.EVENT_MOUSEMOVE:   sel.on_move(x, y)
        elif event == cv2.EVENT_LBUTTONUP:   sel.on_up()
    return cb


# ── Drawing ───────────────────────────────────────────────────────────────────

def _puttext(img: np.ndarray, text: str, pos: tuple[int, int], scale: float = 0.55,
             color: tuple = C_WHITE, thickness: int = 1):
    x, y = pos
    cv2.putText(img, text, (x + 1, y + 1), cv2.FONT_HERSHEY_SIMPLEX, scale, C_SHADOW, 2)
    cv2.putText(img, text, (x,     y    ), cv2.FONT_HERSHEY_SIMPLEX, scale, color,    thickness)


def _draw_handle(img: np.ndarray, cx: int, cy: int):
    cv2.line(img,   (cx - _H_LINE, cy), (cx + _H_LINE, cy), C_CYAN, 1, cv2.LINE_AA)
    cv2.line(img,   (cx, cy - _H_LINE), (cx, cy + _H_LINE), C_CYAN, 1, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), _H_CIRCLE, C_CYAN, -1, cv2.LINE_AA)


def _draw_selection(base: np.ndarray, sel: _Selection) -> np.ndarray:
    out = base.copy()
    x1, y1, x2, y2 = sel.norm()

    cv2.rectangle(out, (x1, y1), (x2, y2), C_GREEN, 2, cv2.LINE_AA)
    for cx, cy in sel.corner_pts().values():
        _draw_handle(out, cx, cy)

    hint_y = max(14, y1 - 6)
    _puttext(out, f"{x2 - x1} x {y2 - y1} px", (x1, hint_y), 0.46, C_DIM)
    _puttext(out, "Drag corners/rect to adjust   Enter=name it   Esc/Q=cancel", (8, 22), 0.50)
    return out


def _draw_name_input(base: np.ndarray, sel: _Selection, typed: str) -> np.ndarray:
    """Overlay the selection + a name-input bar at the bottom."""
    out = _draw_selection(base, sel)
    h, w = out.shape[:2]
    bar_h = 74
    y0 = h - bar_h

    # Dark bar background
    cv2.rectangle(out, (0, y0), (w, h), (18, 18, 18), -1)
    cv2.line(out, (0, y0), (w, y0), C_GREEN, 1)

    sanitized = _sanitize(typed)

    # "Name: <input>|"
    _puttext(out, "Name:", (10, y0 + 26), 0.65, C_DIM)
    _puttext(out, typed + "|", (80, y0 + 26), 0.65, C_WHITE, 1)

    # Second line: validation hint
    if typed and not sanitized:
        hint = "Invalid — use a-z  0-9  _ only"
        hint_col = (0, 100, 255)
    elif sanitized and sanitized != typed.lower().replace(" ", "_").replace("-", "_"):
        hint = f"Will save as: {sanitized}"
        hint_col = C_DIM
    else:
        hint = "Enter=confirm   Esc=back to selection"
        hint_col = C_DIM
    _puttext(out, hint, (10, y0 + 56), 0.46, hint_col)

    return out


# ── Name sanitiser ────────────────────────────────────────────────────────────

def _sanitize(text: str) -> str:
    s = text.lower().replace(" ", "_").replace("-", "_")
    return re.sub(r"[^a-z0-9_]", "", s)


# ── TOML I/O ──────────────────────────────────────────────────────────────────

def _load_regions() -> dict:
    if not REGIONS_TOML.exists():
        return {}
    try:
        with open(REGIONS_TOML, "rb") as f:
            return tomllib.load(f).get("regions", {})
    except Exception:
        return {}


def _write_regions(regions: dict):
    lines = ["[regions]\n"]
    for name, r in regions.items():
        lines += [
            f"\n[regions.{name}]\n",
            f"x1 = {r['x1']}\n",
            f"y1 = {r['y1']}\n",
            f"x2 = {r['x2']}\n",
            f"y2 = {r['y2']}\n",
        ]
    with open(REGIONS_TOML, "w", encoding="utf-8") as f:
        f.writelines(lines)


# ── Save template ─────────────────────────────────────────────────────────────

def _save(name: str, orig: np.ndarray, sel: _Selection, scale: float):
    orig_h, orig_w = orig.shape[:2]
    x1d, y1d, x2d, y2d = sel.norm()

    ox1 = max(0,      int(x1d / scale))
    oy1 = max(0,      int(y1d / scale))
    ox2 = min(orig_w, int(x2d / scale))
    oy2 = min(orig_h, int(y2d / scale))

    if ox2 <= ox1 or oy2 <= oy1:
        print("  Selection too small — discarded.")
        return

    rx1 = round(ox1 / orig_w, 4)
    ry1 = round(oy1 / orig_h, 4)
    rx2 = round(ox2 / orig_w, 4)
    ry2 = round(oy2 / orig_h, 4)

    crop = orig[oy1:oy2, ox1:ox2]
    out_path = TEMPLATES_DIR / f"{name}.png"
    Image.fromarray(crop[:, :, ::-1].astype("uint8")).save(str(out_path))

    regions = _load_regions()
    if name in regions:
        print(f"  Warning: overwriting existing region '{name}'")
    regions[name] = {"x1": rx1, "y1": ry1, "x2": rx2, "y2": ry2}
    _write_regions(regions)

    print(f"  Saved templates/{name}.png  |  x1={rx1}  y1={ry1}  x2={rx2}  y2={ry2}")


# ── Selection session ─────────────────────────────────────────────────────────

def _run_selection(adb_path: str, device: str):
    # 1. Take screencap
    print("Capturing...", end=" ", flush=True)
    orig = _screencap(adb_path, device)
    if orig is None:
        print("FAILED — check ADB connection.")
        return
    print("OK")

    # 2. Scale to 90 % of monitor
    sw, sh = _screen_size()
    scaled, scale = _scale_frame(orig, int(sw * 0.9), int(sh * 0.9))
    dh, dw = scaled.shape[:2]

    # 3. Init selection rectangle
    sel = _Selection()
    sel.activate(dw, dh)

    # 4. Open window
    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_TOPMOST, 1)

    mouse_enabled = [True]   # mutable so callback can be toggled
    cv2.setMouseCallback(WINDOW, _make_mouse_cb(sel, mouse_enabled))

    cv2.imshow(WINDOW, _draw_selection(scaled, sel))
    cv2.moveWindow(WINDOW, max(0, (sw - dw) // 2), max(0, (sh - dh) // 2))

    # 5. Two-state loop: "select" → drag handles | "name" → type name
    state = "select"
    typed = ""

    while True:
        # Closed via window X button
        try:
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                print("  Window closed.")
                break
        except cv2.error:
            break

        # Render
        if state == "select":
            mouse_enabled[0] = True
            cv2.imshow(WINDOW, _draw_selection(scaled, sel))
        else:
            mouse_enabled[0] = False   # freeze rect while typing
            cv2.imshow(WINDOW, _draw_name_input(scaled, sel, typed))

        key = cv2.waitKeyEx(30)
        if key == -1:
            continue
        k = key & 0xFF

        # ── SELECT state keys ───────────────────────────────────────────
        if state == "select":
            if k == 13:                        # Enter → switch to name input
                state = "select->name"         # transition handled below
                typed = ""
                state = "name"
            elif k == 27 or k in (ord("q"), ord("Q")):
                print("  Selection discarded.")
                break

        # ── NAME state keys ──────────────────────────────────────────────
        elif state == "name":
            if k == 13:                        # Enter → confirm
                name = _sanitize(typed)
                if name:
                    _save(name, orig, sel, scale)
                    break
                # else: show nothing extra — the bar already shows "Invalid"

            elif k == 27:                      # Esc → back to selection
                state = "select"
                typed = ""

            elif k == 8:                       # Backspace
                typed = typed[:-1]

            elif 32 <= k <= 126:               # Printable ASCII
                typed += chr(k)

    # 6. Destroy window safely
    try:
        cv2.destroyWindow(WINDOW)
    except cv2.error:
        pass
    cv2.destroyAllWindows()
    cv2.waitKey(1)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    adb_cfg  = _load_adb_config()
    adb_path = adb_cfg.get("path", "adb")
    device   = "{}:{}".format(adb_cfg.get("host", "127.0.0.1"), adb_cfg.get("port", 5555))

    print("G.O.B.L.I.N Template Capture Tool")
    print(f"  ADB  : {device}  ({adb_path})")
    print(f"  Out  : {TEMPLATES_DIR}")
    print()

    try:
        import keyboard
    except ImportError:
        print("ERROR: 'keyboard' package not found. Run: pip install keyboard")
        sys.exit(1)

    f9 = threading.Event()
    keyboard.add_hotkey("F9", lambda: f9.set())

    print("Ready — press F9 to capture a region.  Ctrl+C to quit.\n")

    try:
        while True:
            f9.wait()
            f9.clear()
            _run_selection(adb_path, device)
            f9.clear()   # discard any F9 pressed while window was open
            print("Ready — press F9 to capture another region.\n")
    except KeyboardInterrupt:
        print("\nBye.")


if __name__ == "__main__":
    main()
