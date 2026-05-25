"""
Main application window — plain tkinter + ttk.

System title bar handles drag/resize natively.
F9 (configurable) toggles visibility.
"""

from __future__ import annotations

import ctypes
import threading
import time
from pathlib import Path

import tkinter as tk
from tkinter import ttk, simpledialog

from pynput import keyboard as pynput_kb

from core.config import AppConfig
from core.screen import GameScreen
from core.vision import Vision
from ui.theme import (
    BG, DARK, MID, PANEL, TEXT, DIM,
    RED, BLUE, GREEN, TEAL, ORANGE,
    F_BASE, F_BOLD, F_BIG, F_TITLE, F_SMALL, F_TINY, F_MONO, F_MONO_S,
    configure_styles,
)


class GoblinApp:
    """
    Top-level application.  Owns config / screen / vision and the tk window.
    Tabs receive a reference to `self` and call app.log(), app.hide(), etc.
    """

    def __init__(self):
        root_dir    = Path(__file__).resolve().parent.parent
        self.config = AppConfig(root_dir)
        self.screen = GameScreen(self.config)
        self.vision = Vision(self.screen, self.config)

        self.root   = tk.Tk()
        self.root.title("G.O.B.L.I.N  Toolkit")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(860, 580)
        self.root.geometry("1040x760+60+40")
        self.root.attributes("-topmost", True)

        configure_styles(self.root)

        self._visible         = True
        self._hotkey_listener = None
        self._log_text:  tk.Text   | None = None
        self._status_var: tk.StringVar    = tk.StringVar(value="  Ready")
        self._win_var:    tk.StringVar    = tk.StringVar(
            value=self.config.settings.get("window_title", "")
        )
        self._settings_open = False
        self._settings_frame: tk.Frame | None = None

    # ── Build ─────────────────────────────────────────────────────────────

    def build(self):
        r = self.root
        r.columnconfigure(0, weight=1)
        r.rowconfigure(1, weight=1)   # notebook expands

        self._build_window_bar(r).grid(row=0, column=0, sticky="ew")
        self._nb = self._build_tabs(r)
        self._nb.grid(row=1, column=0, sticky="nsew", padx=4, pady=(2, 0))
        self._build_settings_toggle(r).grid(row=2, column=0, sticky="ew")
        self._settings_frame = self._build_settings_body(r)
        self._settings_frame.grid(row=3, column=0, sticky="ew")
        self._settings_frame.grid_remove()
        self._build_statusbar(r).grid(row=4, column=0, sticky="ew")

    # ── Window selector bar ───────────────────────────────────────────────

    def _build_window_bar(self, parent) -> tk.Frame:
        bar = tk.Frame(parent, bg=MID, height=46)
        bar.pack_propagate(False)

        tk.Label(bar, text="Game window:", bg=MID, fg=DIM,
                 font=F_SMALL).pack(side="left", padx=(10, 4))

        ent = ttk.Entry(bar, textvariable=self._win_var, width=28, font=F_SMALL)
        ent.pack(side="left", padx=2, pady=8)

        ttk.Button(bar, text="Pick Window", style="Blue.TButton",
                   command=self._pick_window).pack(side="left", padx=4)
        ttk.Button(bar, text="Confirm", style="Sm.TButton",
                   command=self._confirm_window).pack(side="left", padx=2)

        tk.Label(bar, text="Screenshots & clicks target this window",
                 bg=MID, fg=DIM, font=F_TINY).pack(side="left", padx=8)
        return bar

    def _pick_window(self):
        wins = self.screen.list_windows()
        dlg  = tk.Toplevel(self.root)
        dlg.title("Pick Game Window")
        dlg.geometry("480x360")
        dlg.configure(bg=BG)
        dlg.attributes("-topmost", True)
        dlg.grab_set()

        tk.Label(dlg, text="Select the game window:", bg=BG, fg=TEXT,
                 font=F_BASE).pack(anchor="w", padx=10, pady=(10, 2))

        filt_var = tk.StringVar()
        filt     = ttk.Entry(dlg, textvariable=filt_var, font=F_SMALL)
        filt.pack(fill="x", padx=10, pady=2)

        lb_frame = tk.Frame(dlg, bg=BG)
        lb_frame.pack(fill="both", expand=True, padx=10, pady=4)
        sb  = ttk.Scrollbar(lb_frame)
        sb.pack(side="right", fill="y")
        lb  = tk.Listbox(lb_frame, yscrollcommand=sb.set, bg=PANEL, fg=TEXT,
                         selectbackground=BLUE, selectforeground="white",
                         font=F_SMALL, activestyle="none", bd=0, relief="flat")
        lb.pack(side="left", fill="both", expand=True)
        sb.configure(command=lb.yview)

        def _populate(*_):
            q = filt_var.get().lower()
            lb.delete(0, "end")
            for _, title in wins:
                if q in title.lower():
                    lb.insert("end", title)
        filt_var.trace_add("write", _populate)
        _populate()

        def _select(event=None):
            sel = lb.curselection()
            if not sel:
                return
            t = lb.get(sel[0])
            self._win_var.set(t)
            self.config.settings["window_title"] = t
            self.config.save_settings()
            dlg.destroy()
            self._confirm_window()

        lb.bind("<Double-1>", _select)
        ttk.Button(dlg, text="Select", style="Blue.TButton",
                   command=_select).pack(side="left", padx=10, pady=6)
        ttk.Button(dlg, text="Cancel", style="Sm.TButton",
                   command=dlg.destroy).pack(side="left", pady=6)

    def _confirm_window(self):
        title = self._win_var.get().strip()
        if not title:
            self.log("No window selected.")
            return
        self.config.settings["window_title"] = title
        self.config.save_settings()
        rect = self.screen.game_rect()
        if rect:
            self.log(f"✓ Game: '{title}'  {rect[2]}×{rect[3]} @ ({rect[0]},{rect[1]})")
        else:
            self.log(f"✗ Window not found: '{title}'")

    # ── Tabs ──────────────────────────────────────────────────────────────

    def _build_tabs(self, parent) -> ttk.Notebook:
        from ui.configure_tab import ConfigureTab
        from ui.flow_tab import FlowTab

        nb = ttk.Notebook(parent)

        cfg_frame = ttk.Frame(nb)
        nb.add(cfg_frame, text="  Configure  ")
        self._configure = ConfigureTab(cfg_frame, self)
        self._configure.build()

        flow_frame = ttk.Frame(nb)
        nb.add(flow_frame, text="  Bot Flow  ")
        self._flow = FlowTab(flow_frame, self)
        self._flow.build()

        log_frame = ttk.Frame(nb)
        nb.add(log_frame, text="  Log  ")
        self._build_log_tab(log_frame)

        return nb

    def _build_log_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        hdr = tk.Frame(parent, bg=MID, height=40)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        tk.Label(hdr, text="Session log", bg=MID, fg="#5555cc",
                 font=F_BIG).pack(side="left", padx=10)
        ttk.Button(hdr, text="Clear", style="SmRed.TButton",
                   command=self._clear_log).pack(side="right", padx=8, pady=6)

        txt_frame = tk.Frame(parent, bg=BG)
        txt_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        txt_frame.columnconfigure(0, weight=1)
        txt_frame.rowconfigure(0, weight=1)

        self._log_text = tk.Text(
            txt_frame, bg="#111111", fg=TEXT, font=F_MONO_S,
            wrap="word", state="disabled", bd=0, relief="flat",
            insertbackground=TEXT,
        )
        vsb = ttk.Scrollbar(txt_frame, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=vsb.set)
        self._log_text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

    def _clear_log(self):
        if self._log_text:
            self._log_text.configure(state="normal")
            self._log_text.delete("1.0", "end")
            self._log_text.configure(state="disabled")

    # ── Settings ──────────────────────────────────────────────────────────

    def _build_settings_toggle(self, parent) -> tk.Frame:
        bar = tk.Frame(parent, bg=DARK, height=28)
        bar.pack_propagate(False)
        self._stg_btn_var = tk.StringVar(value="▶  Settings")
        btn = tk.Button(
            bar, textvariable=self._stg_btn_var,
            bg=DARK, fg=DIM, activebackground=DARK, activeforeground=TEXT,
            font=F_SMALL, bd=0, relief="flat", anchor="w",
            command=self._toggle_settings,
        )
        btn.pack(side="left", fill="x", padx=8)
        return bar

    def _build_settings_body(self, parent) -> tk.Frame:
        body = tk.Frame(parent, bg=PANEL)

        def _row(label, key, lo, hi, step_size):
            r = tk.Frame(body, bg=PANEL)
            r.pack(fill="x", padx=14, pady=2)
            tk.Label(r, text=label, bg=PANEL, fg="#8888bb",
                     font=F_SMALL, width=22, anchor="w").pack(side="left")
            val = float(self.config.settings.get(key, self.config.DEFAULTS[key]))
            n   = max(1, round((hi - lo) / step_size))
            val_var = tk.StringVar(value=f"{val:.2f}")
            tk.Label(r, textvariable=val_var, bg=PANEL, fg="#ccccff",
                     font=F_SMALL, width=5).pack(side="right")
            sld = ttk.Scale(r, from_=0, to=n, orient="horizontal", length=180)
            sld.set(round((val - lo) / step_size))
            sld.pack(side="left", padx=4)
            def _cb(v, k=key, l=lo, s=step_size, lv=val_var):
                fv = round(l + float(v) * s, 4)
                lv.set(f"{fv:.2f}")
                self.config.settings[k] = fv
                self.config.save_settings()
                if k == "opacity":
                    self.root.attributes("-alpha", fv)
            sld.configure(command=_cb)

        _row("Click delay (ms)",  "click_delay_ms",  50,   1000, 10)
        _row("Match threshold",   "match_threshold", 0.5,  1.0,  0.01)

        # Click mode
        cm_row = tk.Frame(body, bg=PANEL)
        cm_row.pack(fill="x", padx=14, pady=2)
        tk.Label(cm_row, text="Click mode", bg=PANEL, fg="#8888bb",
                 font=F_SMALL, width=22, anchor="w").pack(side="left")
        mode_var = tk.StringVar(
            value=self.config.settings.get("click_mode", "foreground")
        )
        for m in ("foreground", "background"):
            tk.Radiobutton(
                cm_row, text=m, variable=mode_var, value=m,
                bg=PANEL, fg=TEXT, selectcolor=DARK, activebackground=PANEL,
                font=F_SMALL,
                command=lambda m=m: (
                    self.config.settings.update(click_mode=m),
                    self.config.save_settings()
                ),
            ).pack(side="left", padx=4)

        # Hotkey
        hk_row = tk.Frame(body, bg=PANEL)
        hk_row.pack(fill="x", padx=14, pady=(2, 8))
        tk.Label(hk_row, text="Toggle hotkey", bg=PANEL, fg="#8888bb",
                 font=F_SMALL, width=22, anchor="w").pack(side="left")
        hk_var = tk.StringVar(value=self.config.settings.get("toggle_hotkey", "<f9>"))
        ttk.Entry(hk_row, textvariable=hk_var, width=14,
                  font=F_SMALL).pack(side="left", padx=4)
        def _apply_hk():
            self.config.settings["toggle_hotkey"] = hk_var.get().strip()
            self.config.save_settings()
            self._setup_hotkey()
        ttk.Button(hk_row, text="Apply", style="SmBlue.TButton",
                   command=_apply_hk).pack(side="left", padx=4)

        return body

    def _toggle_settings(self):
        self._settings_open = not self._settings_open
        if self._settings_open:
            self._settings_frame.grid()
            self._stg_btn_var.set("▼  Settings")
        else:
            self._settings_frame.grid_remove()
            self._stg_btn_var.set("▶  Settings")

    # ── Status bar ────────────────────────────────────────────────────────

    def _build_statusbar(self, parent) -> tk.Frame:
        bar = tk.Frame(parent, bg=DARK, height=26)
        bar.pack_propagate(False)
        tk.Label(bar, textvariable=self._status_var,
                 bg=DARK, fg="#4a9a6a", font=F_MONO_S).pack(side="left", padx=6)
        return bar

    # ── Logging ───────────────────────────────────────────────────────────

    def log(self, msg: str):
        line = f"[{time.strftime('%H:%M:%S')}]  {msg}"
        print(line)
        def _do():
            self._status_var.set(f"  {msg[:120]}")
            if self._log_text:
                self._log_text.configure(state="normal")
                self._log_text.insert("end", line + "\n")
                self._log_text.see("end")
                self._log_text.configure(state="disabled")
        self.root.after(0, _do)

    # ── Visibility ────────────────────────────────────────────────────────

    def hide(self):
        self._visible = False
        self.root.withdraw()

    def show(self):
        self._visible = True
        self.root.deiconify()
        self.root.lift()

    def toggle(self):
        if self._visible:
            self.hide()
        else:
            self.show()

    def quit(self):
        self.root.destroy()

    # ── Hotkey ────────────────────────────────────────────────────────────

    def _setup_hotkey(self):
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
        hk = self.config.settings.get("toggle_hotkey", "<f9>")
        try:
            self._hotkey_listener = pynput_kb.GlobalHotKeys(
                {hk: lambda: self.root.after(0, self.toggle)}
            )
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
            self.log(f"Hotkey: {hk} = toggle overlay")
        except Exception as e:
            self.log(f"Hotkey failed: {e}")

    # ── Capture exclusion ─────────────────────────────────────────────────

    def _apply_capture_exclusion(self):
        try:
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            hwnd = self.root.winfo_id()
            ok   = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            if ok:
                self.log("✓ Overlay hidden from game screenshots (WDA_EXCLUDEFROMCAPTURE)")
            else:
                err = ctypes.windll.kernel32.GetLastError()
                self.log(f"⚠ Capture exclusion failed (err {err})")
        except Exception as e:
            self.log(f"⚠ Capture exclusion unavailable: {e}")

    # ── Run ───────────────────────────────────────────────────────────────

    def run(self):
        self.build()
        self.root.after(200,  self._setup_hotkey)
        self.root.after(350,  self._apply_capture_exclusion)
        self.root.after(500,  lambda: self.log(
            "Ready  ▸  Pick Window  ▸  Configure buttons  ▸  Run bot"
        ))
        self.root.mainloop()
