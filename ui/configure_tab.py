"""
Configure tab — register every button / slot the bot needs.

Sub-tabs: Home | Attack | Post-Attack | Upgrade | Troops & Deploy
"""

from __future__ import annotations

import threading
import time
import uuid

import tkinter as tk
from tkinter import ttk, simpledialog
import cv2

from pynput import keyboard as pynput_kb, mouse as pynput_mouse
from PIL import ImageTk

from ui.theme import (
    BG, DARK, MID, PANEL, ROW_A, ROW_B,
    BLUE, GREEN, RED, TEAL, ORANGE, TEXT, DIM, OK, FAIL,
    F_BASE, F_BOLD, F_BIG, F_SMALL, F_TINY, F_MONO, F_MONO_S,
    row_bg, make_scrollable,
)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ui.app import GoblinApp

_CAP_COL = "#1e3a5a"


class ConfigureTab:
    """Builds and manages the Configure tab."""

    def __init__(self, parent: tk.Frame, app: "GoblinApp"):
        self.parent = parent
        self.app    = app
        self.cfg    = app.config
        self.screen = app.screen
        self.vision = app.vision

        # Inner frame refs for in-place rebuilds
        self._slot_inners: dict[str, tk.Frame] = {}
        self._troop_inner:  tk.Frame | None = None
        self._hero_inner:   tk.Frame | None = None
        self._deploy_inner: tk.Frame | None = None

        # Debounce
        self._army_after_id = None

    # ── Debounce ──────────────────────────────────────────────────────────

    def _debounce_save_army(self):
        if self._army_after_id:
            self.app.root.after_cancel(self._army_after_id)
        self._army_after_id = self.app.root.after(400, self.cfg.save_army)

    # ── Build ─────────────────────────────────────────────────────────────

    def build(self):
        self.parent.columnconfigure(0, weight=1)
        self.parent.rowconfigure(0, weight=1)

        nb = ttk.Notebook(self.parent)
        nb.grid(row=0, column=0, sticky="nsew")

        for name, ctx in [("Home", "home"), ("Attack", "attack"),
                          ("Post-Attack", "post_attack"), ("Upgrade", "upgrade")]:
            f = ttk.Frame(nb)
            nb.add(f, text=f"  {name}  ")
            self._build_button_subtab(f, ctx)

        td = ttk.Frame(nb)
        nb.add(td, text="  Troops & Deploy  ")
        self._build_troops_subtab(td)

    # ── Generic button sub-tab ────────────────────────────────────────────

    def _build_button_subtab(self, parent: ttk.Frame, context: str):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        # Toolbar
        tb = tk.Frame(parent, bg=MID, height=42)
        tb.grid(row=0, column=0, sticky="ew")
        tb.grid_propagate(False)
        ttk.Button(tb, text="＋  Add Button", style="SmBlue.TButton",
                   command=lambda: self._add_button(context)).pack(side="left", padx=8, pady=6)
        tk.Label(tb, text="COORD = fixed position  │  IMAGE = visual match",
                 bg=MID, fg=DIM, font=F_TINY).pack(side="left", padx=6)

        # Column headers
        hdr = tk.Frame(parent, bg=DARK, height=24)
        hdr.grid(row=1, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.pack_propagate(False)
        for txt, w in [("Name", 190), ("Mode", 136), ("OK", 32),
                       ("Set Coord", 88), ("Capture", 88), ("Test", 88), ("", 36)]:
            tk.Label(hdr, text=txt, bg=DARK, fg="#555555",
                     font=F_TINY, width=0).pack(side="left", padx=(6, 0))
            tk.Frame(hdr, bg=DARK, width=w).pack(side="left")

        # Scrollable list
        outer, inner = make_scrollable(parent, bg=BG)
        outer.grid(row=2, column=0, sticky="nsew", padx=2, pady=2)
        self._slot_inners[context] = inner
        self._rebuild_button_list(context)

    def _rebuild_button_list(self, context: str):
        inner = self._slot_inners.get(context)
        if inner is None:
            return
        for w in inner.winfo_children():
            w.destroy()

        slots = self.cfg.buttons.get(context, {})
        if not slots:
            tk.Label(inner, text="  No buttons configured — click ＋ Add Button",
                     bg=BG, fg=DIM, font=F_SMALL).pack(anchor="w", padx=8, pady=6)
            return

        for i, (name, data) in enumerate(slots.items()):
            self._make_slot_row(inner, context, name, data, i)

    def _make_slot_row(self, parent, context: str, name: str, data: dict, idx: int):
        bg  = row_bg(idx)
        row = tk.Frame(parent, bg=bg, height=46)
        row.pack(fill="x", padx=2, pady=1)
        row.pack_propagate(False)

        # Name
        tk.Label(row, text=name, bg=bg, fg=TEXT, font=F_MONO,
                 width=18, anchor="w").pack(side="left", padx=(8, 2))

        # Mode toggle
        mode_var = tk.StringVar(value=data.get("mode", "IMAGE"))
        for m in ("COORD", "IMAGE"):
            tk.Radiobutton(
                row, text=m, variable=mode_var, value=m,
                bg=bg, fg=TEXT, selectcolor=DARK, activebackground=bg,
                font=F_TINY,
                command=lambda m=m, n=name, c=context: (
                    self.cfg.buttons[c][n].update(mode=m),
                    self.cfg.save_buttons(),
                ),
            ).pack(side="left", padx=2)

        # Configured indicator
        ok_flag = data.get("configured", False)
        tk.Label(row, text="✓" if ok_flag else "✗", bg=bg,
                 fg=OK if ok_flag else FAIL, font=F_BOLD,
                 width=2).pack(side="left", padx=4)

        save_rb = lambda c=context: (self.cfg.save_buttons(), self._rebuild_button_list(c))

        for lbl, fn, col, sty in [
            ("Set Coord", lambda c=context, n=name: self._set_coord(c, n, lambda c=context: save_rb(c)), BLUE,  "SmBlue.TButton"),
            ("Capture",   lambda c=context, n=name: self._capture(c, n, lambda c=context: save_rb(c)),   _CAP_COL, "SmTeal.TButton"),
            ("Test",      lambda c=context, n=name: self._test(c, n),                                    GREEN, "SmGreen.TButton"),
        ]:
            ttk.Button(row, text=lbl, style=sty,
                       command=fn).pack(side="left", padx=2, pady=6)

        ttk.Button(row, text="✕", style="SmRed.TButton",
                   command=lambda c=context, n=name: self._del_button(c, n)
                   ).pack(side="left", padx=(4, 6))

    # ── Button CRUD ───────────────────────────────────────────────────────

    def _add_button(self, context: str):
        name = simpledialog.askstring("Add Button", "Button name:",
                                      parent=self.app.root)
        if not name or not name.strip():
            return
        name = name.strip().replace(" ", "_")
        if name in self.cfg.buttons.get(context, {}):
            self.app.log(f"'{name}' already exists in {context}")
            return
        self.cfg.buttons.setdefault(context, {})[name] = {
            "mode": "IMAGE", "coord": None, "template": None, "configured": False,
        }
        self.cfg.save_buttons()
        self._rebuild_button_list(context)
        self.app.log(f"Added: {context}.{name}")

    def _del_button(self, context: str, name: str):
        if name in self.cfg.buttons.get(context, {}):
            del self.cfg.buttons[context][name]
            self.cfg.save_buttons()
            self._rebuild_button_list(context)
            self.app.log(f"Deleted: {context}.{name}")

    def _set_coord(self, context: str, name: str, save_fn):
        slot  = self.cfg.buttons[context][name]
        label = f"{context}.{name}"
        self.app.log(f"[{label}]  Click anywhere to set position  (Esc = cancel)…")
        self.app.hide()
        done = threading.Event()

        def _listen():
            time.sleep(0.25)
            def on_click(x, y, btn, pressed):
                if not pressed or btn != pynput_mouse.Button.left:
                    return
                slot["coord"] = [x, y]
                slot["configured"] = True
                save_fn()
                self.app.log(f"[{label}]  Position → ({x},{y})")
                done.set()
                return False
            def on_key(key):
                if key == pynput_kb.Key.esc:
                    self.app.log(f"[{label}]  Cancelled.")
                    done.set()
                    return False
            ml = pynput_mouse.Listener(on_click=on_click)
            kl = pynput_kb.Listener(on_press=on_key)
            ml.start(); kl.start()
            done.wait(30)
            ml.stop(); kl.stop()
            self.app.root.after(0, self.app.show)

        threading.Thread(target=_listen, daemon=True).start()

    def _capture(self, context: str, name: str, save_fn):
        slot  = self.cfg.buttons[context][name]
        label = f"{context}.{name}"
        fkey  = f"{context}_{name}"
        self.app.log(f"[{label}]  Drag a box around the button  (Esc = cancel)…")
        self.app.hide()
        self.app.root.after(400, lambda: self._capture_overlay(slot, save_fn, label, fkey))

    def _test(self, context: str, name: str):
        slot  = self.cfg.buttons[context][name]
        label = f"{context}.{name}"
        def _run():
            img, result = self.vision.test_slot_preview(slot)
            self.app.log(f"[{label}]  {result}")
            prev = cv2.resize(img, (960, 540))
            def _show():
                cv2.imshow(f"Test — {label}", prev)
                cv2.waitKey(2500)
                try:   cv2.destroyWindow(f"Test — {label}")
                except: pass
            threading.Thread(target=_show, daemon=True).start()
        threading.Thread(target=_run, daemon=True).start()

    # ── Rubber-band capture overlay ────────────────────────────────────────

    def _capture_overlay(self, slot: dict, save_fn, label: str, file_key: str):
        pil    = self.screen.grab_fullscreen_pil()
        sw, sh = pil.size
        ov     = tk.Tk()
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        ov.geometry(f"{sw}x{sh}+0+0")
        photo  = ImageTk.PhotoImage(pil)
        canvas = tk.Canvas(ov, width=sw, height=sh,
                           cursor="crosshair", highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas._photo = photo
        canvas.create_rectangle(0, 0, sw, sh, fill="black", stipple="gray25", outline="")
        canvas.create_text(sw // 2, 44,
                           text="Draw a box around the button  —  Esc to cancel",
                           fill="white", font=("Consolas", 16, "bold"))

        anc = {}; rid = [None]

        def press(e):
            anc["x"], anc["y"] = e.x, e.y

        def drag(e):
            if rid[0]:
                canvas.delete(rid[0])
            rid[0] = canvas.create_rectangle(
                anc.get("x", e.x), anc.get("y", e.y), e.x, e.y,
                outline="#ff4444", width=3, fill="")

        def release(e):
            x1 = min(anc.get("x", e.x), e.x)
            y1 = min(anc.get("y", e.y), e.y)
            x2 = max(anc.get("x", e.x), e.x)
            y2 = max(anc.get("y", e.y), e.y)
            ov.destroy()
            if x2 - x1 < 6 or y2 - y1 < 6:
                self.app.log(f"[{label}]  Selection too small — try again.")
                self.app.root.after(0, self.app.show)
                return
            out = self.cfg.templates_dir / f"{file_key}.png"
            pil.crop((x1, y1, x2, y2)).save(out)
            slot["template"]   = str(out)
            slot["mode"]       = "IMAGE"
            slot["configured"] = True
            save_fn()
            self.app.log(f"[{label}]  Saved → {out.name}  ({x2-x1}×{y2-y1}px)")
            self.app.root.after(0, self.app.show)

        def esc(e):
            ov.destroy()
            self.app.log(f"[{label}]  Cancelled.")
            self.app.root.after(0, self.app.show)

        canvas.bind("<ButtonPress-1>",   press)
        canvas.bind("<B1-Motion>",       drag)
        canvas.bind("<ButtonRelease-1>", release)
        ov.bind("<Escape>", esc)
        ov.focus_force()
        ov.mainloop()

    # ══════════════════════════════════════════════════════════════════════
    # Troops & Deploy sub-tab
    # ══════════════════════════════════════════════════════════════════════

    def _build_troops_subtab(self, parent: ttk.Frame):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        outer, inner = make_scrollable(parent, bg=BG)
        outer.grid(row=0, column=0, sticky="nsew")

        # ── TROOPS ────────────────────────────────────────────────────────
        tk.Label(inner, text="TROOPS", bg=BG, fg=DIM,
                 font=F_TINY).pack(anchor="w", padx=8, pady=(8, 0))
        ttk.Button(inner, text="＋  Add Troop", style="SmBlue.TButton",
                   command=self._add_troop).pack(anchor="w", padx=8, pady=4)

        self._troop_inner = tk.Frame(inner, bg=BG)
        self._troop_inner.pack(fill="x", padx=4)

        # ── SIEGE ─────────────────────────────────────────────────────────
        tk.Frame(inner, bg="#2a2a2a", height=1).pack(fill="x", padx=8, pady=6)
        tk.Label(inner, text="SIEGE MACHINE", bg=BG, fg=DIM,
                 font=F_TINY).pack(anchor="w", padx=8)
        self._build_siege_row(inner)

        # ── HEROES ────────────────────────────────────────────────────────
        tk.Frame(inner, bg="#2a2a2a", height=1).pack(fill="x", padx=8, pady=6)
        tk.Label(inner, text="HEROES  (max 4)", bg=BG, fg=DIM,
                 font=F_TINY).pack(anchor="w", padx=8)
        ttk.Button(inner, text="＋  Add Hero", style="SmTeal.TButton",
                   command=self._add_hero).pack(anchor="w", padx=8, pady=4)

        self._hero_inner = tk.Frame(inner, bg=BG)
        self._hero_inner.pack(fill="x", padx=4)

        # ── DEPLOY POSITIONS ──────────────────────────────────────────────
        tk.Frame(inner, bg="#2a2a2a", height=1).pack(fill="x", padx=8, pady=6)
        tk.Label(inner, text="DEPLOY POSITIONS", bg=BG, fg=DIM,
                 font=F_TINY).pack(anchor="w", padx=8)

        dtb = tk.Frame(inner, bg=BG)
        dtb.pack(fill="x", padx=8, pady=4)
        tk.Label(dtb, text="Points:", bg=BG, fg=TEXT, font=F_SMALL).pack(side="left")
        nv = ttk.Entry(dtb, width=4, font=F_SMALL)
        nv.insert(0, "12")
        nv.pack(side="left", padx=4)
        ttk.Button(dtb, text="Auto-detect", style="SmRed.TButton",
                   command=lambda: self._detect_deploy(int(nv.get() or "12"))
                   ).pack(side="left", padx=2)
        ttk.Button(dtb, text="＋ Manual", style="SmBlue.TButton",
                   command=self._add_deploy_manual).pack(side="left", padx=2)
        ttk.Button(dtb, text="Preview", style="SmGreen.TButton",
                   command=self._preview_deploy).pack(side="left", padx=2)
        ttk.Button(dtb, text="Clear", style="SmRed.TButton",
                   command=self._clear_deploy).pack(side="left", padx=2)

        self._deploy_inner = tk.Frame(inner, bg=BG)
        self._deploy_inner.pack(fill="x", padx=4, pady=4)

        self._rebuild_troops()
        self._rebuild_heroes()
        self._rebuild_deploy()

    # ── Troop rows ────────────────────────────────────────────────────────

    def _rebuild_troops(self):
        if self._troop_inner is None:
            return
        for w in self._troop_inner.winfo_children():
            w.destroy()
        troops = self.cfg.army.get("troops", [])
        if not troops:
            tk.Label(self._troop_inner,
                     text="  No troops — click ＋ Add Troop",
                     bg=BG, fg=DIM, font=F_SMALL).pack(anchor="w", padx=8, pady=4)
            return
        for i, t in enumerate(troops):
            self._make_troop_row(self._troop_inner, t, i)

    def _make_troop_row(self, parent, troop: dict, idx: int):
        bg  = row_bg(idx)
        row = tk.Frame(parent, bg=bg, height=44)
        row.pack(fill="x", pady=1)
        row.pack_propagate(False)

        tk.Label(row, text=f"#{idx+1}", bg=bg, fg=DIM, font=F_SMALL).pack(side="left", padx=6)

        nm_var = tk.StringVar(value=troop.get("name", ""))
        nm_entry = ttk.Entry(row, textvariable=nm_var, width=14, font=F_SMALL)
        nm_entry.pack(side="left", padx=2, pady=8)
        nm_var.trace_add("write", lambda *_, t=troop, v=nm_var: (
            t.update(name=v.get()), self._debounce_save_army()
        ))

        tk.Label(row, text="×", bg=bg, fg=DIM, font=F_SMALL).pack(side="left")
        cnt_var = tk.StringVar(value=str(troop.get("count", 1)))
        ttk.Entry(row, textvariable=cnt_var, width=4, font=F_SMALL).pack(side="left", padx=2)
        def _set_count(*_, t=troop, v=cnt_var):
            try:
                t["count"] = int(v.get())
                self._debounce_save_army()
            except ValueError:
                pass
        cnt_var.trace_add("write", _set_count)

        tk.Label(row, text="→", bg=bg, fg=DIM, font=F_SMALL).pack(side="left")
        da_var = tk.StringVar(value=troop.get("deploy_at", "all"))
        ttk.Entry(row, textvariable=da_var, width=8, font=F_SMALL).pack(side="left", padx=2)
        da_var.trace_add("write", lambda *_, t=troop, v=da_var: (
            t.update(deploy_at=v.get()), self._debounce_save_army()
        ))

        ok_flag = troop.get("configured", False)
        tk.Label(row, text="✓" if ok_flag else "✗", bg=bg,
                 fg=OK if ok_flag else FAIL, font=F_BOLD).pack(side="left", padx=4)

        key = f"troops.slot_{idx+1}"
        save_rb = lambda: (self.cfg.save_army(), self._rebuild_troops())
        for lbl, fn, sty in [
            ("Coord",   lambda t=troop, k=key: self._set_coord_slot(t, k, save_rb), "SmBlue.TButton"),
            ("Capture", lambda t=troop, k=key: self._capture_slot(t, k, save_rb),   "SmTeal.TButton"),
            ("Test",    lambda t=troop, k=key: self._test_slot(t, k),               "SmGreen.TButton"),
        ]:
            ttk.Button(row, text=lbl, style=sty, command=fn).pack(side="left", padx=2, pady=8)

        ttk.Button(row, text="✕", style="SmRed.TButton",
                   command=lambda i=idx: self._del_troop(i)
                   ).pack(side="left", padx=(4, 6))

    def _add_troop(self):
        self.cfg.army["troops"].append({
            "id": str(uuid.uuid4())[:8], "name": "", "mode": "IMAGE",
            "coord": None, "template": None, "configured": False,
            "count": 1, "deploy_at": "all",
        })
        self.cfg.save_army()
        self._rebuild_troops()

    def _del_troop(self, idx: int):
        troops = self.cfg.army.get("troops", [])
        if 0 <= idx < len(troops):
            troops.pop(idx)
            self.cfg.save_army()
            self._rebuild_troops()

    # ── Siege row ─────────────────────────────────────────────────────────

    def _build_siege_row(self, parent):
        siege = self.cfg.army["siege"]
        row   = tk.Frame(parent, bg=ROW_A, height=46)
        row.pack(fill="x", padx=4, pady=2)
        row.pack_propagate(False)

        tk.Label(row, text="Name:", bg=ROW_A, fg=TEXT, font=F_SMALL).pack(side="left", padx=(10, 2))
        nv = tk.StringVar(value=siege.get("name", ""))
        ttk.Entry(row, textvariable=nv, width=18, font=F_SMALL).pack(side="left", padx=4, pady=8)
        nv.trace_add("write", lambda *_: (siege.update(name=nv.get()), self._debounce_save_army()))

        ok_flag = siege.get("configured", False)
        tk.Label(row, text="✓" if ok_flag else "✗", bg=ROW_A,
                 fg=OK if ok_flag else FAIL, font=F_BOLD).pack(side="left", padx=4)

        save_rb = lambda: self.cfg.save_army()
        for lbl, fn, sty in [
            ("Coord",   lambda: self._set_coord_slot(siege, "troops.siege", save_rb), "SmBlue.TButton"),
            ("Capture", lambda: self._capture_slot(siege, "troops.siege", save_rb),   "SmTeal.TButton"),
            ("Test",    lambda: self._test_slot(siege, "troops.siege"),               "SmGreen.TButton"),
        ]:
            ttk.Button(row, text=lbl, style=sty, command=fn).pack(side="left", padx=2, pady=8)

    # ── Hero rows ─────────────────────────────────────────────────────────

    def _rebuild_heroes(self):
        if self._hero_inner is None:
            return
        for w in self._hero_inner.winfo_children():
            w.destroy()
        heroes = self.cfg.army.get("heroes", [])
        if not heroes:
            tk.Label(self._hero_inner,
                     text="  No heroes — click ＋ Add Hero",
                     bg=BG, fg=DIM, font=F_SMALL).pack(anchor="w", padx=8, pady=4)
            return
        for i, h in enumerate(heroes):
            self._make_hero_row(self._hero_inner, h, i)

    def _make_hero_row(self, parent, hero: dict, idx: int):
        bg  = row_bg(idx)
        row = tk.Frame(parent, bg=bg, height=44)
        row.pack(fill="x", pady=1)
        row.pack_propagate(False)

        tk.Label(row, text=f"⚔{idx+1}", bg=bg, fg=DIM, font=F_SMALL).pack(side="left", padx=6)

        nv = tk.StringVar(value=hero.get("name", ""))
        ttk.Entry(row, textvariable=nv, width=18, font=F_SMALL).pack(side="left", padx=4, pady=8)
        nv.trace_add("write", lambda *_, h=hero, v=nv: (
            h.update(name=v.get()), self._debounce_save_army()
        ))

        ok_flag = hero.get("configured", False)
        tk.Label(row, text="✓" if ok_flag else "✗", bg=bg,
                 fg=OK if ok_flag else FAIL, font=F_BOLD).pack(side="left", padx=4)

        key = f"troops.hero_{idx+1}"
        save_rb = lambda: (self.cfg.save_army(), self._rebuild_heroes())
        for lbl, fn, sty in [
            ("Coord",   lambda h=hero, k=key: self._set_coord_slot(h, k, save_rb), "SmBlue.TButton"),
            ("Capture", lambda h=hero, k=key: self._capture_slot(h, k, save_rb),   "SmTeal.TButton"),
            ("Test",    lambda h=hero, k=key: self._test_slot(h, k),               "SmGreen.TButton"),
        ]:
            ttk.Button(row, text=lbl, style=sty, command=fn).pack(side="left", padx=2, pady=8)

        ttk.Button(row, text="✕", style="SmRed.TButton",
                   command=lambda i=idx: self._del_hero(i)
                   ).pack(side="left", padx=(4, 6))

    def _add_hero(self):
        if len(self.cfg.army.get("heroes", [])) >= 4:
            self.app.log("Max 4 heroes.")
            return
        self.cfg.army["heroes"].append({
            "id": str(uuid.uuid4())[:8], "name": "", "mode": "IMAGE",
            "coord": None, "template": None, "configured": False, "deploy_at": "all",
        })
        self.cfg.save_army()
        self._rebuild_heroes()

    def _del_hero(self, idx: int):
        heroes = self.cfg.army.get("heroes", [])
        if 0 <= idx < len(heroes):
            heroes.pop(idx)
            self.cfg.save_army()
            self._rebuild_heroes()

    # ── Deploy positions ──────────────────────────────────────────────────

    def _rebuild_deploy(self):
        if self._deploy_inner is None:
            return
        for w in self._deploy_inner.winfo_children():
            w.destroy()
        positions = self.cfg.army.get("deploy_positions", [])
        if not positions:
            tk.Label(self._deploy_inner,
                     text="  No positions — use Auto-detect or ＋ Manual",
                     bg=BG, fg=DIM, font=F_SMALL).pack(anchor="w", padx=8, pady=4)
            return
        for i, pos in enumerate(positions):
            row = tk.Frame(self._deploy_inner, bg=row_bg(i), height=28)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)
            tk.Label(row, text=f"#{i+1}   x={pos[0]:5d}   y={pos[1]:5d}",
                     bg=row_bg(i), fg=TEXT, font=F_MONO_S).pack(side="left", padx=8)
            ttk.Button(row, text="✕", style="SmRed.TButton",
                       command=lambda i=i: self._del_deploy(i)
                       ).pack(side="right", padx=4, pady=2)

    def _detect_deploy(self, n_points: int):
        self.app.hide()
        def _run():
            time.sleep(0.6)
            self.app.log("Scanning for red deploy border…")
            pts = self.vision.detect_deploy_zone(n_points)
            self.app.root.after(0, self.app.show)
            if not pts:
                self.app.log("✗ No deploy border found.")
                return
            self.cfg.army["deploy_positions"] = pts
            self.cfg.save_army()
            self.app.log(f"✓ {len(pts)} deploy positions saved.")
            self.app.root.after(0, self._rebuild_deploy)
        threading.Thread(target=_run, daemon=True).start()

    def _add_deploy_manual(self):
        self.app.log("Click anywhere to add a deploy position  (Esc = cancel)…")
        self.app.hide()
        done = threading.Event()
        def _listen():
            time.sleep(0.25)
            def on_click(x, y, btn, pressed):
                if not pressed or btn != pynput_mouse.Button.left:
                    return
                self.cfg.army.setdefault("deploy_positions", []).append([x, y])
                self.cfg.save_army()
                self.app.log(f"Deploy position added: ({x},{y})")
                done.set()
                return False
            def on_key(key):
                if key == pynput_kb.Key.esc:
                    self.app.log("Cancelled.")
                    done.set()
                    return False
            ml = pynput_mouse.Listener(on_click=on_click)
            kl = pynput_kb.Listener(on_press=on_key)
            ml.start(); kl.start()
            done.wait(30)
            ml.stop(); kl.stop()
            self.app.root.after(0, self.app.show)
            self.app.root.after(100, self._rebuild_deploy)
        threading.Thread(target=_listen, daemon=True).start()

    def _preview_deploy(self):
        positions = self.cfg.army.get("deploy_positions", [])
        if not positions:
            self.app.log("No positions to preview.")
            return
        def _show():
            img, ox, oy = self.screen.grab_game()
            for i, p in enumerate(positions):
                ix, iy = p[0] - ox, p[1] - oy
                cv2.circle(img, (ix, iy), 12, (0, 220, 110), -1)
                cv2.circle(img, (ix, iy), 14, (255, 255, 255), 2)
                cv2.putText(img, str(i+1), (ix-5, iy+5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
            prev = cv2.resize(img, (960, 540))
            cv2.imshow("Deploy Positions", prev)
            cv2.waitKey(3000)
            try:   cv2.destroyWindow("Deploy Positions")
            except: pass
        threading.Thread(target=_show, daemon=True).start()

    def _clear_deploy(self):
        self.cfg.army["deploy_positions"] = []
        self.cfg.save_army()
        self._rebuild_deploy()
        self.app.log("Deploy positions cleared.")

    def _del_deploy(self, idx: int):
        pos = self.cfg.army.get("deploy_positions", [])
        if 0 <= idx < len(pos):
            pos.pop(idx)
            self.cfg.save_army()
            self._rebuild_deploy()

    # ── Shared slot helpers ───────────────────────────────────────────────

    def _set_coord_slot(self, slot: dict, label: str, save_fn):
        self.app.log(f"[{label}]  Click anywhere to set position  (Esc = cancel)…")
        self.app.hide()
        done = threading.Event()
        def _listen():
            time.sleep(0.25)
            def on_click(x, y, btn, pressed):
                if not pressed or btn != pynput_mouse.Button.left:
                    return
                slot["coord"] = [x, y]
                slot["configured"] = True
                save_fn()
                self.app.log(f"[{label}]  Position → ({x},{y})")
                done.set()
                return False
            def on_key(key):
                if key == pynput_kb.Key.esc:
                    self.app.log(f"[{label}]  Cancelled.")
                    done.set()
                    return False
            ml = pynput_mouse.Listener(on_click=on_click)
            kl = pynput_kb.Listener(on_press=on_key)
            ml.start(); kl.start()
            done.wait(30)
            ml.stop(); kl.stop()
            self.app.root.after(0, self.app.show)
        threading.Thread(target=_listen, daemon=True).start()

    def _capture_slot(self, slot: dict, label: str, save_fn):
        fkey = label.replace(".", "_")
        self.app.log(f"[{label}]  Drag a box around the button  (Esc = cancel)…")
        self.app.hide()
        self.app.root.after(400, lambda: self._capture_overlay(slot, save_fn, label, fkey))

    def _test_slot(self, slot: dict, label: str):
        def _run():
            img, result = self.vision.test_slot_preview(slot)
            self.app.log(f"[{label}]  {result}")
            prev = cv2.resize(img, (960, 540))
            def _show():
                cv2.imshow(f"Test — {label}", prev)
                cv2.waitKey(2500)
                try:   cv2.destroyWindow(f"Test — {label}")
                except: pass
            threading.Thread(target=_show, daemon=True).start()
        threading.Thread(target=_run, daemon=True).start()
