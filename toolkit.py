#!/usr/bin/env python3
"""
G.O.B.L.I.N Toolkit — CoC bot configurator.
Single file. mss + win32 + OpenCV. No ADB.

Run:  python toolkit.py
"""

import json
import time
import threading
from pathlib import Path

import tkinter as tk
from tkinter import simpledialog

import customtkinter as ctk
import cv2
import numpy as np
import mss
from PIL import Image, ImageTk
import win32api
import win32gui
import win32con
from pynput import keyboard as pynput_kb
from pynput import mouse  as pynput_mouse


# ══════════════════════════════════════════════════════════════════════════════
# PATHS & DEFAULTS
# ══════════════════════════════════════════════════════════════════════════════

ROOT          = Path(__file__).parent
BUTTONS_FILE  = ROOT / "buttons.json"
CONFIG_FILE   = ROOT / "config.json"
TEMPLATES_DIR = ROOT / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)

DEFAULT_CFG = {
    "click_delay_ms":  150,
    "match_threshold": 0.80,
    "toggle_hotkey":   "<f9>",
    "window_title":    "",
    "opacity":         0.92,
}

# Pre-seeded button slots for CoC auto-loot flow
SEED_BUTTONS = {
    "btn_attack_home":  {"mode": "IMAGE", "coord": None, "template": None, "configured": False},
    "btn_find_match":   {"mode": "IMAGE", "coord": None, "template": None, "configured": False},
    "btn_next_base":    {"mode": "IMAGE", "coord": None, "template": None, "configured": False},
    "btn_attack_now":   {"mode": "IMAGE", "coord": None, "template": None, "configured": False},
    "btn_surrender":    {"mode": "IMAGE", "coord": None, "template": None, "configured": False},
    "btn_return_home":  {"mode": "IMAGE", "coord": None, "template": None, "configured": False},
    "btn_ok_popup":     {"mode": "COORD", "coord": None, "template": None, "configured": False},
    "btn_reload":       {"mode": "IMAGE", "coord": None, "template": None, "configured": False},
}

# Mode explanations shown in the info bar when a row is hovered / selected
MODE_HELP = {
    "IMAGE": "IMAGE — captures a screenshot of the button; bot finds it by visual matching",
    "COORD": "COORD  — you click once to record exact screen position; bot always clicks there",
}


# ══════════════════════════════════════════════════════════════════════════════
# MODULE STATE
# ══════════════════════════════════════════════════════════════════════════════

buttons: dict = {}
cfg:     dict = {}

root:           ctk.CTk | None = None
_rows_frame:    ctk.CTkScrollableFrame | None = None
_log_box:       ctk.CTkTextbox | None = None
_settings_body: ctk.CTkFrame | None = None
_settings_btn:  ctk.CTkButton | None = None
_win_title_var: ctk.StringVar | None = None
_info_var:      ctk.StringVar | None = None

_row_frames:  list = []
_row_status:  dict = {}
_settings_visible = False
is_visible  = True
_hotkey_listener  = None


# ══════════════════════════════════════════════════════════════════════════════
# PERSISTENCE
# ══════════════════════════════════════════════════════════════════════════════

def load_all() -> None:
    global buttons, cfg
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}
    for k, v in DEFAULT_CFG.items():
        cfg.setdefault(k, v)
    save_config()

    buttons = json.loads(BUTTONS_FILE.read_text(encoding="utf-8")) if BUTTONS_FILE.exists() else {}
    for k, v in SEED_BUTTONS.items():
        buttons.setdefault(k, dict(v))
    save_buttons()


def save_buttons() -> None:
    BUTTONS_FILE.write_text(json.dumps(buttons, indent=2), encoding="utf-8")


def save_config() -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# WINDOW VISIBILITY
# ══════════════════════════════════════════════════════════════════════════════

def hide_window() -> None:
    global is_visible
    is_visible = False
    root.withdraw()


def show_window() -> None:
    global is_visible
    is_visible = True
    root.deiconify()
    root.lift()
    root.attributes("-topmost", True)


def toggle_window() -> None:
    if is_visible:
        hide_window()
    else:
        show_window()


# ══════════════════════════════════════════════════════════════════════════════
# TARGET WINDOW
# ══════════════════════════════════════════════════════════════════════════════

def _target_title() -> str:
    return _win_title_var.get().strip() if _win_title_var else cfg.get("window_title", "")


def find_target_hwnd() -> int:
    return win32gui.FindWindow(None, _target_title())


def get_target_rect() -> tuple | None:
    hwnd = find_target_hwnd()
    return win32gui.GetWindowRect(hwnd) if hwnd else None


def list_visible_windows() -> list[tuple[int, str]]:
    """Return [(hwnd, title), ...] for every visible, titled window."""
    result = []

    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).strip()
            if title:
                result.append((hwnd, title))

    win32gui.EnumWindows(_cb, None)
    result.sort(key=lambda t: t[1].lower())
    return result


# ══════════════════════════════════════════════════════════════════════════════
# CLICK INJECTION
# ══════════════════════════════════════════════════════════════════════════════

def click_at(x: int, y: int) -> None:
    delay = cfg.get("click_delay_ms", 150) / 1000.0
    hwnd  = find_target_hwnd()

    if hwnd:
        rect   = win32gui.GetWindowRect(hwnd)
        lx     = x - rect[0]
        ly     = y - rect[1]
        lparam = (ly & 0xFFFF) << 16 | (lx & 0xFFFF)
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
        time.sleep(delay)
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)
    else:
        win32api.SetCursorPos((x, y))
        time.sleep(0.05)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(delay)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP,   0, 0, 0, 0)


# ══════════════════════════════════════════════════════════════════════════════
# SCREENSHOT  (mss — no ADB)
# ══════════════════════════════════════════════════════════════════════════════

def grab_screen_pil() -> Image.Image:
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[0])
    return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def grab_screen_bgr() -> np.ndarray:
    return cv2.cvtColor(np.array(grab_screen_pil()), cv2.COLOR_RGB2BGR)


# ══════════════════════════════════════════════════════════════════════════════
# LOG
# ══════════════════════════════════════════════════════════════════════════════

def log(msg: str) -> None:
    ts   = time.strftime("%H:%M:%S")
    line = f"[{ts}]  {msg}"
    print(line)
    if _log_box is None:
        return
    try:
        _log_box.configure(state="normal")
        _log_box.insert("end", line + "\n")
        _log_box.see("end")
        _log_box.configure(state="disabled")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# UI REFRESH
# ══════════════════════════════════════════════════════════════════════════════

def refresh_ui() -> None:
    if _rows_frame is None:
        return
    for f, _ in _row_frames:
        try:
            f.destroy()
        except Exception:
            pass
    _row_frames.clear()
    _row_status.clear()
    for i, name in enumerate(buttons):
        _make_row(_rows_frame, name, i)
    _fit_window()


# ══════════════════════════════════════════════════════════════════════════════
# ACTION — PICK WINDOW
# ══════════════════════════════════════════════════════════════════════════════

def pick_window_dialog() -> None:
    """Pop a window-picker dialog listing all visible OS windows."""
    wins = list_visible_windows()
    if not wins:
        log("No visible windows found.")
        return

    dlg = ctk.CTkToplevel(root)
    dlg.title("Pick target window")
    dlg.attributes("-topmost", True)
    dlg.resizable(False, False)
    dlg.grab_set()

    ctk.CTkLabel(
        dlg,
        text="Select the window the game is running in:",
        font=("Consolas", 12),
    ).pack(padx=16, pady=(14, 6))

    # Filter entry
    filter_var = ctk.StringVar()

    filter_entry = ctk.CTkEntry(
        dlg, textvariable=filter_var,
        placeholder_text="type to filter…",
        width=440, height=30, font=("Consolas", 11),
    )
    filter_entry.pack(padx=16, pady=(0, 6))

    listbox_frame = ctk.CTkScrollableFrame(dlg, width=440, height=300)
    listbox_frame.pack(padx=16, pady=(0, 10))

    btn_labels: list[ctk.CTkButton] = []
    all_titles = [t for _, t in wins]

    def _populate(query: str = "") -> None:
        for w in listbox_frame.winfo_children():
            w.destroy()
        btn_labels.clear()
        for _, title in wins:
            if query.lower() in title.lower():
                b = ctk.CTkButton(
                    listbox_frame,
                    text=title,
                    anchor="w",
                    font=("Consolas", 11),
                    fg_color="transparent",
                    hover_color="#1a1a40",
                    text_color="#c0c0ff",
                    height=30,
                    command=lambda t=title: _select(t),
                )
                b.pack(fill="x", pady=1)
                btn_labels.append(b)

    def _select(title: str) -> None:
        _win_title_var.set(title)
        cfg["window_title"] = title
        save_config()
        dlg.destroy()
        refresh_target()

    filter_var.trace_add("write", lambda *_: _populate(filter_var.get()))
    _populate()

    ctk.CTkButton(dlg, text="Cancel", width=100,
                   command=dlg.destroy).pack(pady=(0, 12))


# ══════════════════════════════════════════════════════════════════════════════
# ACTION — REFRESH TARGET
# ══════════════════════════════════════════════════════════════════════════════

def refresh_target() -> None:
    title = _target_title()
    if not title:
        log("No window selected. Click 'Pick Window'.")
        return
    cfg["window_title"] = title
    save_config()
    hwnd = win32gui.FindWindow(None, title)
    if hwnd:
        r = win32gui.GetWindowRect(hwnd)
        w, h = r[2] - r[0], r[3] - r[1]
        log(f"✓  Found '{title}'  —  {w}×{h}  @  ({r[0]}, {r[1]})")
    else:
        log(f"✗  Window not found: '{title}'")


# ══════════════════════════════════════════════════════════════════════════════
# ACTION — SET COORD
# ══════════════════════════════════════════════════════════════════════════════

def set_coord(name: str) -> None:
    """
    Hide overlay → wait for one left-click anywhere → save (x, y) → restore.
    Esc cancels.
    """
    log(f"[{name}]  Click anywhere on screen to set position  (Esc = cancel)…")
    hide_window()
    done = threading.Event()

    def _listen() -> None:
        time.sleep(0.2)

        def on_click(x, y, btn, pressed):
            if not pressed or btn != pynput_mouse.Button.left:
                return
            buttons[name]["coord"]      = [x, y]
            buttons[name]["configured"] = True
            save_buttons()
            log(f"[{name}]  Position saved  →  ({x},  {y})")
            done.set()
            return False

        def on_key(key):
            if key == pynput_kb.Key.esc:
                log(f"[{name}]  Cancelled.")
                done.set()
                return False

        ml = pynput_mouse.Listener(on_click=on_click)
        kl = pynput_kb.Listener(on_press=on_key)
        ml.start(); kl.start()
        done.wait(timeout=30)
        ml.stop(); kl.stop()
        root.after(0, show_window)
        root.after(80, refresh_ui)

    threading.Thread(target=_listen, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
# ACTION — CAPTURE TEMPLATE
# ══════════════════════════════════════════════════════════════════════════════

def capture_template(name: str) -> None:
    """
    Hide overlay → mss screenshot → fullscreen canvas → drag red rect →
    crop → save PNG → restore.
    """
    log(f"[{name}]  Drag a box around the button on screen  (Esc = cancel)…")
    hide_window()
    root.after(380, lambda: _open_capture_overlay(name))


def _open_capture_overlay(name: str) -> None:
    pil_img = grab_screen_pil()
    sw, sh  = pil_img.size

    ov = tk.Toplevel()
    ov.overrideredirect(True)
    ov.attributes("-topmost", True)
    ov.geometry(f"{sw}x{sh}+0+0")

    photo  = ImageTk.PhotoImage(pil_img)
    canvas = tk.Canvas(ov, width=sw, height=sh,
                        cursor="crosshair", highlightthickness=0, bd=0)
    canvas.pack(fill="both", expand=True)
    canvas.create_image(0, 0, anchor="nw", image=photo)
    canvas._photo = photo                                 # keep reference

    # Light dim so the red box stands out
    canvas.create_rectangle(0, 0, sw, sh,
                             fill="black", stipple="gray25", outline="")

    # Instruction text
    canvas.create_text(sw // 2, 40,
                        text="Draw a box around the button  —  Esc to cancel",
                        fill="white", font=("Arial", 16, "bold"))

    anchor  = {}
    rect_id = [None]

    def on_press(e):
        anchor["x"], anchor["y"] = e.x, e.y

    def on_drag(e):
        if rect_id[0]:
            canvas.delete(rect_id[0])
        rect_id[0] = canvas.create_rectangle(
            anchor.get("x", e.x), anchor.get("y", e.y), e.x, e.y,
            outline="#ff1744", width=3, fill="",
        )

    def on_release(e):
        x1 = min(anchor.get("x", e.x), e.x)
        y1 = min(anchor.get("y", e.y), e.y)
        x2 = max(anchor.get("x", e.x), e.x)
        y2 = max(anchor.get("y", e.y), e.y)
        ov.destroy()

        if x2 - x1 < 6 or y2 - y1 < 6:
            log(f"[{name}]  Box too small — try again.")
            root.after(0, show_window)
            return

        cropped  = pil_img.crop((x1, y1, x2, y2))
        out_path = TEMPLATES_DIR / f"{name}.png"
        cropped.save(out_path)

        buttons[name]["template"]   = str(out_path)
        buttons[name]["mode"]       = "IMAGE"
        buttons[name]["configured"] = True
        save_buttons()
        log(f"[{name}]  Saved  →  {out_path.name}  ({x2-x1}×{y2-y1} px)")
        root.after(0, show_window)
        root.after(80, refresh_ui)

    def on_esc(e):
        ov.destroy()
        log(f"[{name}]  Cancelled.")
        root.after(0, show_window)

    canvas.bind("<ButtonPress-1>",   on_press)
    canvas.bind("<B1-Motion>",       on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    ov.bind("<Escape>", on_esc)
    ov.focus_force()
    ov.grab_set()


# ══════════════════════════════════════════════════════════════════════════════
# ACTION — TEST
# ══════════════════════════════════════════════════════════════════════════════

def _do_test(name: str, silent: bool = False) -> bool:
    data    = buttons.get(name, {})
    mode    = data.get("mode", "COORD")
    img_bgr = grab_screen_bgr()
    found   = False

    if mode == "IMAGE":
        tpl_path = data.get("template", "")
        if not tpl_path or not Path(tpl_path).exists():
            log(f"[{name}]  No image captured yet.")
            return False

        template = cv2.imread(tpl_path)
        if template is None:
            log(f"[{name}]  Image file unreadable.")
            return False

        res = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        th, tw = template.shape[:2]
        threshold = cfg.get("match_threshold", 0.80)
        found     = max_val >= threshold

        if found:
            cx, cy = max_loc[0] + tw // 2, max_loc[1] + th // 2
            cv2.rectangle(img_bgr, max_loc,
                          (max_loc[0] + tw, max_loc[1] + th),
                          (0, 230, 118), 3)
            cv2.putText(img_bgr, f"FOUND  {max_val:.2f}",
                        (max_loc[0], max_loc[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 230, 118), 2)
            log(f"[{name}]  ✓  FOUND  conf={max_val:.3f}  @  ({cx}, {cy})")
        else:
            cv2.putText(img_bgr,
                        f"NOT FOUND  (best match: {max_val:.2f},  need >= {threshold:.2f})",
                        (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (60, 60, 255), 2)
            log(f"[{name}]  ✗  NOT FOUND  best={max_val:.3f}")

    elif mode == "COORD":
        coord = data.get("coord")
        if not coord:
            log(f"[{name}]  No position set yet.")
            return False
        x, y = int(coord[0]), int(coord[1])
        cv2.circle(img_bgr, (x, y), 22, (64, 180, 255), 3)
        cv2.circle(img_bgr, (x, y),  6, (64, 180, 255), -1)
        cv2.putText(img_bgr, f"COORD  ({x}, {y})",
                    (x + 28, y + 8), cv2.FONT_HERSHEY_SIMPLEX,
                    0.85, (64, 180, 255), 2)
        log(f"[{name}]  Fixed position  →  ({x}, {y})")
        found = True

    if not silent:
        preview = cv2.resize(img_bgr, (960, 540))

        def _show():
            title = f"Test — {name}"
            cv2.imshow(title, preview)
            cv2.waitKey(2000)
            try:
                cv2.destroyWindow(title)
            except Exception:
                pass

        threading.Thread(target=_show, daemon=True).start()

    return found


def test_button(name: str) -> None:
    threading.Thread(target=_do_test, args=(name,), daemon=True).start()


def run_test_all() -> None:
    log("━━━  Run Test All  ━━━")

    def _worker():
        for name, data in list(buttons.items()):
            if not data.get("configured"):
                log(f"[{name}]  SKIP (not configured yet)")
                continue
            ok = _do_test(name, silent=True)
            log(f"[{name}]  {'✓  PASS' if ok else '✗  FAIL'}")
            time.sleep(0.5)
        log("━━━  Done  ━━━")

    threading.Thread(target=_worker, daemon=True).start()


def add_button_dialog() -> None:
    name = simpledialog.askstring(
        "Add Button",
        "Enter a name for the new button\n(e.g.  btn_troop_camp):",
        parent=root,
    )
    if not name or not name.strip():
        return
    name = name.strip()
    if not name.startswith("btn_"):
        name = "btn_" + name
    if name in buttons:
        log(f"'{name}' already exists.")
        return
    buttons[name] = {"mode": "IMAGE", "coord": None, "template": None, "configured": False}
    save_buttons()
    log(f"Added:  {name}")
    refresh_ui()


# ══════════════════════════════════════════════════════════════════════════════
# HOTKEY
# ══════════════════════════════════════════════════════════════════════════════

def setup_hotkey() -> None:
    global _hotkey_listener
    hk = cfg.get("toggle_hotkey", "<f9>")
    try:
        _hotkey_listener = pynput_kb.GlobalHotKeys(
            {hk: lambda: root.after(0, toggle_window)}
        )
        _hotkey_listener.daemon = True
        _hotkey_listener.start()
        log(f"Hotkey active:  {hk}  →  toggle overlay")
    except Exception as exc:
        log(f"Hotkey setup failed: {exc}")


def restart_hotkey() -> None:
    global _hotkey_listener
    if _hotkey_listener:
        try:
            _hotkey_listener.stop()
        except Exception:
            pass
    setup_hotkey()


# ══════════════════════════════════════════════════════════════════════════════
# UI — ROW
# ══════════════════════════════════════════════════════════════════════════════

_COL_A = "#0f0f26"
_COL_B = "#131330"

def _make_row(parent, name: str, idx: int) -> None:
    bg    = _COL_A if idx % 2 == 0 else _COL_B
    data  = buttons[name]

    frame = ctk.CTkFrame(parent, fg_color=bg, corner_radius=4, height=40)
    frame.pack(fill="x", pady=2, padx=4)
    frame.pack_propagate(False)

    # ── button name ───────────────────────────────────────────────────────────
    ctk.CTkLabel(
        frame, text=name,
        anchor="w", font=("Consolas", 11), text_color="#a0a0d0",
        width=190,
    ).pack(side="left", padx=(10, 4))

    # ── mode toggle:  COORD  |  IMAGE ─────────────────────────────────────────
    mode_var = ctk.StringVar(value=data.get("mode", "IMAGE"))

    def _set_mode(val, n=name):
        buttons[n]["mode"] = val
        save_buttons()
        if _info_var:
            _info_var.set(MODE_HELP.get(val, ""))

    ctk.CTkSegmentedButton(
        frame,
        values=["COORD", "IMAGE"],
        variable=mode_var,
        command=_set_mode,
        width=120, height=28,
        font=("Consolas", 11, "bold"),
    ).pack(side="left", padx=6)

    # ── status icon ───────────────────────────────────────────────────────────
    ok  = data.get("configured", False)
    lbl = ctk.CTkLabel(
        frame,
        text="✓" if ok else "✗",
        text_color="#00e676" if ok else "#f44336",
        font=("Consolas", 16, "bold"), width=28,
    )
    lbl.pack(side="left", padx=(2, 6))
    _row_status[name] = lbl

    # ── action buttons ────────────────────────────────────────────────────────
    for label, cmd, color in (
        ("Set Coord", lambda n=name: set_coord(n),        "#1255a0"),
        ("Capture",   lambda n=name: capture_template(n), "#520080"),
        ("Test",      lambda n=name: test_button(n),      "#0a4a1a"),
    ):
        ctk.CTkButton(
            frame, text=label,
            width=88 if label != "Test" else 60,
            height=28, font=("Consolas", 11),
            fg_color=color, hover_color=color,
            command=cmd,
        ).pack(side="left", padx=3)

    _row_frames.append((frame, lbl))


# ══════════════════════════════════════════════════════════════════════════════
# UI — SETTINGS BODY
# ══════════════════════════════════════════════════════════════════════════════

def _build_settings_body(parent: ctk.CTkFrame) -> None:
    sliders = [
        ("Click delay  (ms)",  "click_delay_ms",   50,  1000, 10),
        ("Match threshold",    "match_threshold",  0.5, 1.0,  0.01),
        ("Opacity",            "opacity",          0.2, 1.0,  0.05),
    ]
    for label, key, lo, hi, step in sliders:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=4)

        ctk.CTkLabel(row, text=label, width=160, anchor="w",
                      font=("Consolas", 11), text_color="#8888bb").pack(side="left")

        val = float(cfg.get(key, DEFAULT_CFG[key]))
        vv  = ctk.DoubleVar(value=val)
        vl  = ctk.CTkLabel(row, text=f"{val:.2f}", width=50,
                             font=("Consolas", 11), text_color="#ccccff")
        vl.pack(side="right")

        def _cb(v, k=key, var=vv, lbl=vl):
            fv = round(float(v), 3)
            var.set(fv)
            lbl.configure(text=f"{fv:.2f}")
            cfg[k] = fv
            save_config()
            if k == "opacity":
                root.attributes("-alpha", fv)

        ctk.CTkSlider(row, variable=vv, from_=lo, to=hi,
                       number_of_steps=max(1, int((hi - lo) / step)),
                       command=_cb, width=170).pack(side="right", padx=8)

    # Hotkey
    hk_row = ctk.CTkFrame(parent, fg_color="transparent")
    hk_row.pack(fill="x", padx=14, pady=(4, 10))
    ctk.CTkLabel(hk_row, text="Toggle hotkey", width=160, anchor="w",
                  font=("Consolas", 11), text_color="#8888bb").pack(side="left")
    hk_var = ctk.StringVar(value=cfg.get("toggle_hotkey", "<f9>"))
    ctk.CTkEntry(hk_row, textvariable=hk_var,
                  width=120, font=("Consolas", 11), height=28).pack(side="left", padx=6)

    def _apply():
        cfg["toggle_hotkey"] = hk_var.get().strip()
        save_config()
        restart_hotkey()

    ctk.CTkButton(hk_row, text="Apply", width=70, height=28,
                   font=("Consolas", 11), fg_color="#222244",
                   command=_apply).pack(side="left")


# ══════════════════════════════════════════════════════════════════════════════
# UI — SETTINGS TOGGLE
# ══════════════════════════════════════════════════════════════════════════════

def _toggle_settings() -> None:
    global _settings_visible
    if _settings_visible:
        _settings_body.pack_forget()
        _settings_visible = False
        _settings_btn.configure(text="▶  Settings")
    else:
        _settings_body.pack(fill="x", padx=6, pady=2)
        _settings_visible = True
        _settings_btn.configure(text="▼  Settings")
    _fit_window()


# ══════════════════════════════════════════════════════════════════════════════
# UI — FIT WINDOW
# ══════════════════════════════════════════════════════════════════════════════

def _fit_window() -> None:
    root.update_idletasks()
    h = root.winfo_reqheight()
    root.geometry(f"680x{h}+{root.winfo_x()}+{root.winfo_y()}")


# ══════════════════════════════════════════════════════════════════════════════
# UI — BUILD
# ══════════════════════════════════════════════════════════════════════════════

def build_ui() -> None:
    global root, _rows_frame, _log_box, _settings_body, _settings_btn
    global _win_title_var, _info_var

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("G.O.B.L.I.N")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", cfg.get("opacity", 0.92))
    root.configure(fg_color="#090920")
    root.geometry("680x600+60+60")

    # ── drag ──────────────────────────────────────────────────────────────────
    _d: dict = {}

    def _ds(e):
        _d["ox"] = e.x_root - root.winfo_x()
        _d["oy"] = e.y_root - root.winfo_y()

    def _dm(e):
        if "ox" in _d:
            root.geometry(f"+{e.x_root-_d['ox']}+{e.y_root-_d['oy']}")

    # ── TITLE BAR ─────────────────────────────────────────────────────────────
    tbar = ctk.CTkFrame(root, fg_color="#060618", corner_radius=0, height=36)
    tbar.pack(fill="x")
    tbar.pack_propagate(False)

    title_lbl = ctk.CTkLabel(
        tbar, text="⚙  G.O.B.L.I.N  Toolkit",
        font=("Consolas", 13, "bold"), text_color="#7c4dff",
    )
    title_lbl.pack(side="left", padx=12)

    ctk.CTkLabel(tbar, text="F9 = show/hide",
                  font=("Consolas", 10), text_color="#333366").pack(side="left", padx=4)

    ctk.CTkButton(tbar, text="✕", width=32, height=26,
                   font=("Consolas", 12, "bold"),
                   fg_color="#6a0000", hover_color="#b71c1c",
                   command=root.destroy).pack(side="right", padx=(2, 6), pady=4)

    ctk.CTkButton(tbar, text="—", width=32, height=26,
                   font=("Consolas", 12),
                   fg_color="#1a1a38", hover_color="#2a2a55",
                   command=hide_window).pack(side="right", padx=2, pady=4)

    for w in (tbar, title_lbl):
        w.bind("<ButtonPress-1>", _ds)
        w.bind("<B1-Motion>",     _dm)

    # ── MODE EXPLANATION BAR ──────────────────────────────────────────────────
    _info_var = ctk.StringVar(
        value="COORD = click once to set a fixed position  |  "
              "IMAGE = screenshot the button, bot finds it visually"
    )
    ctk.CTkLabel(
        root, textvariable=_info_var,
        font=("Consolas", 10), text_color="#555577",
        fg_color="#07071a", anchor="w", height=22,
    ).pack(fill="x", padx=10, pady=(2, 0))

    # ── TARGET WINDOW BAR ─────────────────────────────────────────────────────
    wbar = ctk.CTkFrame(root, fg_color="#0c0c24", corner_radius=0, height=42)
    wbar.pack(fill="x", pady=(4, 0))
    wbar.pack_propagate(False)

    ctk.CTkLabel(wbar, text="Game window:",
                  font=("Consolas", 11), text_color="#7777aa").pack(side="left", padx=(10, 4))

    _win_title_var = ctk.StringVar(value=cfg.get("window_title", ""))
    ctk.CTkEntry(
        wbar, textvariable=_win_title_var,
        width=210, height=28, font=("Consolas", 11),
    ).pack(side="left", padx=2)

    ctk.CTkButton(wbar, text="Pick Window", width=110, height=28,
                   font=("Consolas", 11), fg_color="#1a0050",
                   command=pick_window_dialog).pack(side="left", padx=6)

    ctk.CTkButton(wbar, text="Confirm", width=80, height=28,
                   font=("Consolas", 11), fg_color="#133060",
                   command=refresh_target).pack(side="left", padx=2)

    ctk.CTkButton(wbar, text="Test All", width=80, height=28,
                   font=("Consolas", 11), fg_color="#0d3020",
                   command=run_test_all).pack(side="right", padx=6)

    ctk.CTkButton(wbar, text="＋ Add", width=72, height=28,
                   font=("Consolas", 11), fg_color="#1a0838",
                   command=add_button_dialog).pack(side="right", padx=2)

    # ── COLUMN HEADERS ────────────────────────────────────────────────────────
    hdr = ctk.CTkFrame(root, fg_color="#08081e", corner_radius=0, height=24)
    hdr.pack(fill="x", pady=(6, 0))
    hdr.pack_propagate(False)

    for txt, w, side in (
        ("Button name",  190, "left"),
        ("Mode",         120, "left"),
        ("OK",            28, "left"),
        ("Set Coord",     88, "left"),
        ("Capture",       88, "left"),
        ("Test",          60, "left"),
    ):
        ctk.CTkLabel(hdr, text=txt, width=w, anchor="w",
                      font=("Consolas", 9, "bold"),
                      text_color="#333355").pack(side="left", padx=(10 if txt == "Button name" else 3, 0))

    # ── SCROLLABLE BUTTON LIST ────────────────────────────────────────────────
    _rows_frame = ctk.CTkScrollableFrame(
        root, fg_color="#0b0b22", height=280, corner_radius=0,
    )
    _rows_frame.pack(fill="x")

    for i, name in enumerate(buttons):
        _make_row(_rows_frame, name, i)

    # ── SETTINGS ──────────────────────────────────────────────────────────────
    st_bar = ctk.CTkFrame(root, fg_color="#08081e", corner_radius=0, height=32)
    st_bar.pack(fill="x", pady=(4, 0))
    st_bar.pack_propagate(False)

    _settings_btn = ctk.CTkButton(
        st_bar, text="▶  Settings",
        anchor="w", font=("Consolas", 11, "bold"),
        text_color="#444466", fg_color="transparent",
        hover_color="#101030", height=30,
        command=_toggle_settings,
    )
    _settings_btn.pack(fill="x", padx=8)

    _settings_body = ctk.CTkFrame(root, fg_color="#0d0d28", corner_radius=4)
    _build_settings_body(_settings_body)
    # not packed until user opens it

    # ── LOG ───────────────────────────────────────────────────────────────────
    ctk.CTkFrame(root, fg_color="#07071a", height=1).pack(fill="x")

    _log_box = ctk.CTkTextbox(
        root, height=130,
        font=("Consolas", 10),
        fg_color="#05050f",
        text_color="#3a9a5a",
        corner_radius=0,
        state="disabled",
    )
    _log_box.pack(fill="x")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    load_all()
    build_ui()
    _fit_window()
    root.after(200, setup_hotkey)
    root.after(400, lambda: log(
        "Ready.  ①  Click 'Pick Window' to select your game window.  "
        "②  Use 'Capture' to screenshot each button.  "
        "③  Use 'Test' to verify."
    ))
    root.mainloop()


if __name__ == "__main__":
    main()
