"""
Bot Flow tab — the automation plan (plain tkinter + ttk).

Attack + Upgrade step lists.  Action types:
  CLICK | HOLD | DETECT | ZOOM_OUT | DEPLOY | SCROLL_SEARCH
"""

from __future__ import annotations

import threading
import time
import uuid

import tkinter as tk
from tkinter import ttk

from core.alarm import AlarmManager
from ui.theme import (
    BG, DARK, MID, ROW_A, ROW_B,
    BLUE, GREEN, RED, TEAL, TEXT, DIM, OK, FAIL,
    F_BASE, F_BOLD, F_BIG, F_SMALL, F_TINY, F_MONO, F_MONO_S,
    row_bg, make_scrollable,
)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ui.app import GoblinApp


ACTION_TYPES = ["CLICK", "HOLD", "DETECT", "ZOOM_OUT", "DEPLOY", "SCROLL_SEARCH"]
ON_FAIL_OPTS = ["ALARM_WAIT", "SKIP", "STOP"]
SCROLL_DIRS  = ["DOWN", "UP", "LEFT", "RIGHT"]


class FlowTab:
    """Builds and manages the Bot Flow tab."""

    def __init__(self, parent: tk.Frame, app: "GoblinApp"):
        self.parent = parent
        self.app    = app
        self.cfg    = app.config
        self.screen = app.screen
        self.vision = app.vision

        self._alarm = AlarmManager()

        self._state        = "idle"
        self._stop_flag    = threading.Event()
        self._paused       = False
        self._attack_count = 0

        # Widget refs
        self._list_inners: dict[str, tk.Frame] = {}
        self._run_btn:    ttk.Button | None = None
        self._pause_btn:  ttk.Button | None = None
        self._stop_btn:   ttk.Button | None = None
        self._flow_status_var = tk.StringVar(value="  Idle")

        # Surgical update refs: which -> step_id -> {"pf": tk.Frame, "target_cb": ttk.Combobox}
        self._row_widgets: dict[str, dict[str, dict]] = {}

        # Debounce
        self._flow_after_id = None

    # ── Debounce ──────────────────────────────────────────────────────────

    def _debounce_save_flow(self):
        if self._flow_after_id:
            self.app.root.after_cancel(self._flow_after_id)
        self._flow_after_id = self.app.root.after(400, self.cfg.save_flow)

    # ══════════════════════════════════════════════════════════════════════
    # Build
    # ══════════════════════════════════════════════════════════════════════

    def build(self):
        self.parent.columnconfigure(0, weight=1)
        self.parent.rowconfigure(1, weight=1)

        self._build_control_bar(self.parent).grid(row=0, column=0, sticky="ew")
        self._build_step_tabs(self.parent).grid(row=1, column=0, sticky="nsew",
                                                padx=2, pady=2)

    # ── Control bar ───────────────────────────────────────────────────────

    def _build_control_bar(self, parent) -> tk.Frame:
        bar = tk.Frame(parent, bg=MID, height=54)
        bar.pack_propagate(False)

        tk.Label(bar, text="Attacks before upgrade:", bg=MID, fg=TEXT,
                 font=F_SMALL).pack(side="left", padx=(12, 2), pady=10)

        apu_var = tk.StringVar(value=str(self.cfg.flow_data.get("attacks_per_upgrade", 40)))
        apu_entry = ttk.Entry(bar, textvariable=apu_var, width=6, font=F_SMALL)
        apu_entry.pack(side="left", padx=4)
        apu_var.trace_add("write", lambda *_: self._on_apu_change(apu_var.get()))

        self._run_btn = ttk.Button(bar, text="▶  Run", style="Green.TButton",
                                   command=self._run)
        self._run_btn.pack(side="left", padx=6, pady=8)

        self._pause_btn = ttk.Button(bar, text="⏸  Pause", style="TButton",
                                     command=self._toggle_pause)
        self._pause_btn.pack(side="left", padx=2, pady=8)
        self._pause_btn.state(["disabled"])

        self._stop_btn = ttk.Button(bar, text="■  Stop", style="Red.TButton",
                                    command=self._stop)
        self._stop_btn.pack(side="left", padx=2, pady=8)
        self._stop_btn.state(["disabled"])

        ttk.Button(bar, text="↺  Reset Flows", style="Orange.TButton",
                   command=self._reset_flows).pack(side="left", padx=8)

        tk.Label(bar, textvariable=self._flow_status_var, bg=MID, fg=DIM,
                 font=F_SMALL).pack(side="left", padx=8)

        return bar

    def _on_apu_change(self, v: str):
        try:
            self.cfg.flow_data["attacks_per_upgrade"] = int(v)
            self._debounce_save_flow()
        except ValueError:
            pass

    # ── Step list tabs ────────────────────────────────────────────────────

    def _build_step_tabs(self, parent) -> ttk.Notebook:
        nb = ttk.Notebook(parent)
        for label, which in [("⚔  Attack", "attack_steps"),
                              ("⬆  Upgrade", "upgrade_steps")]:
            f = ttk.Frame(nb)
            nb.add(f, text=f"  {label}  ")
            self._build_step_list_tab(f, which)
        return nb

    def _build_step_list_tab(self, parent: ttk.Frame, which: str):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        # Toolbar
        tb = tk.Frame(parent, bg=MID, height=42)
        tb.grid(row=0, column=0, sticky="ew")
        tb.pack_propagate(False)
        ttk.Button(tb, text="＋  Add Step", style="SmBlue.TButton",
                   command=lambda: self._add_step(which)).pack(side="left", padx=8, pady=6)
        tk.Label(tb, text="DETECT / SCROLL_SEARCH = state gate  │  DEPLOY = full army",
                 bg=MID, fg=DIM, font=F_TINY).pack(side="left", padx=6)

        # Column headers
        hdr = tk.Frame(parent, bg=DARK, height=24)
        hdr.grid(row=1, column=0, sticky="ew")
        hdr.grid_propagate(False)
        for txt, w in [("#", 28), ("Action", 112), ("Target", 168),
                       ("Params", 244), ("Delay ms", 80), ("", 70)]:
            tk.Label(hdr, text=txt, bg=DARK, fg="#555555",
                     font=F_TINY, width=0).pack(side="left")
            tk.Frame(hdr, bg=DARK, width=w).pack(side="left")

        # Scrollable list
        outer, inner = make_scrollable(parent, bg=BG)
        outer.grid(row=2, column=0, sticky="nsew", padx=2, pady=2)
        self._list_inners[which] = inner
        self._rebuild(which)

    # ══════════════════════════════════════════════════════════════════════
    # Step list management
    # ══════════════════════════════════════════════════════════════════════

    def _rebuild(self, which: str):
        self._row_widgets[which] = {}
        inner = self._list_inners.get(which)
        if inner is None:
            return
        for w in inner.winfo_children():
            w.destroy()

        steps = self.cfg.flow_data.get(which, [])
        if not steps:
            tk.Label(inner, text="  No steps yet — click ＋ Add Step to build the plan",
                     bg=BG, fg=DIM, font=F_SMALL).pack(anchor="w", padx=8, pady=8)
            return
        for i, step in enumerate(steps):
            self._make_step_row(inner, step, i, which)

    def _make_step_row(self, parent: tk.Frame, step: dict, idx: int, which: str):
        bg  = row_bg(idx)
        row = tk.Frame(parent, bg=bg, height=52)
        row.pack(fill="x", pady=1)
        row.pack_propagate(False)

        action = step.get("action", "CLICK")
        sid    = step.get("id", str(id(step)))

        # Step number
        tk.Label(row, text=str(idx+1), bg=bg, fg=DIM,
                 font=F_TINY, width=3).pack(side="left", padx=(4, 0))

        # Action dropdown
        action_var = tk.StringVar(value=action)
        action_cb  = ttk.Combobox(row, textvariable=action_var,
                                  values=ACTION_TYPES, state="readonly",
                                  width=11, font=F_SMALL)
        action_cb.pack(side="left", padx=2, pady=10)
        action_var.trace_add("write", lambda *_, s=step, w=which, v=action_var:
                             self._on_action_change(s, v.get(), w))

        # Target dropdown
        keys      = self.cfg.all_slot_keys()
        target_var = tk.StringVar(value=step.get("target", keys[0] if keys else ""))
        target_cb  = ttk.Combobox(row, textvariable=target_var,
                                  values=keys, state="readonly",
                                  width=18, font=F_SMALL)
        target_cb.pack(side="left", padx=2)
        if action in ("ZOOM_OUT", "DEPLOY"):
            target_cb.state(["disabled"])
        target_var.trace_add("write", lambda *_, s=step, v=target_var:
                             self._on_field(s, "target", v.get()))

        # Params frame (surgical update target)
        pf = tk.Frame(row, bg=bg, width=244)
        pf.pack(side="left", padx=2)
        pf.pack_propagate(False)
        self._build_params(pf, step, action, bg)

        # Store refs
        self._row_widgets.setdefault(which, {})[sid] = {
            "pf": pf, "target_cb": target_cb, "bg": bg,
        }

        # Delay field
        delay_var = tk.StringVar(value=str(step.get("delay_ms", 500)))
        ttk.Entry(row, textvariable=delay_var, width=7,
                  font=F_SMALL).pack(side="left", padx=2)
        delay_var.trace_add("write", lambda *_, s=step, v=delay_var:
                            self._on_int_field(s, "delay_ms", v.get()))
        tk.Label(row, text="ms", bg=bg, fg=DIM, font=F_TINY).pack(side="left")

        # Move / delete buttons
        for sym, delta in (("▲", -1), ("▼", 1)):
            tk.Button(
                row, text=sym, bg=MID, fg=TEXT, font=F_TINY,
                bd=0, relief="flat", padx=2, pady=1,
                command=lambda i=idx, d=delta, w=which: self._move(i, d, w),
            ).pack(side="left", padx=1, pady=12)

        ttk.Button(row, text="✕", style="SmRed.TButton",
                   command=lambda i=idx, w=which: self._del_step(i, w)
                   ).pack(side="left", padx=(4, 6))

    def _build_params(self, pf: tk.Frame, step: dict, action: str, bg: str):
        for w in pf.winfo_children():
            w.destroy()

        def int_entry(key: str, default: int, width: int, suffix: str = ""):
            v = tk.StringVar(value=str(step.get(key, default)))
            e = ttk.Entry(pf, textvariable=v, width=width, font=F_SMALL)
            e.pack(side="left", padx=2, pady=10)
            v.trace_add("write", lambda *_, k=key, var=v:
                        self._on_int_field(step, k, var.get()))
            if suffix:
                tk.Label(pf, text=suffix, bg=bg, fg=DIM,
                         font=F_TINY).pack(side="left")

        def combo(key: str, values: list, width: int):
            v = tk.StringVar(value=step.get(key, values[0]))
            c = ttk.Combobox(pf, textvariable=v, values=values,
                             state="readonly", width=width, font=F_SMALL)
            c.pack(side="left", padx=2, pady=10)
            v.trace_add("write", lambda *_, k=key, var=v:
                        self._on_field(step, k, var.get()))

        if action == "CLICK":
            tk.Label(pf, text="×", bg=bg, fg=DIM, font=F_SMALL).pack(side="left", padx=2)
            int_entry("repeat", 1, 5, "times")

        elif action == "HOLD":
            int_entry("hold_ms", 1000, 7, "ms")

        elif action == "DETECT":
            int_entry("detect_timeout_ms", 30000, 7, "ms")
            combo("on_fail", ON_FAIL_OPTS, 12)

        elif action == "ZOOM_OUT":
            int_entry("repeat", 5, 5, "ticks")

        elif action == "DEPLOY":
            tk.Label(pf, text="[ Full Army ]", bg=bg, fg="#888888",
                     font=F_SMALL).pack(side="left", padx=4)

        elif action == "SCROLL_SEARCH":
            combo("scroll_direction", SCROLL_DIRS, 7)
            int_entry("max_scrolls", 10, 4, "×")
            combo("on_fail", ON_FAIL_OPTS, 10)

    # ── Field handlers ────────────────────────────────────────────────────

    def _on_action_change(self, step: dict, value: str, which: str):
        step["action"] = value
        if value in ("ZOOM_OUT", "DEPLOY"):
            step.pop("target", None)
        elif not step.get("target"):
            keys = self.cfg.all_slot_keys()
            if keys:
                step["target"] = keys[0]
        self.cfg.save_flow()

        sid  = step.get("id", str(id(step)))
        refs = self._row_widgets.get(which, {}).get(sid, {})
        pf   = refs.get("pf")
        bg   = refs.get("bg", BG)

        if pf is not None:
            try:
                self._build_params(pf, step, value, bg)
            except Exception:
                self._rebuild(which)
                return
        else:
            self._rebuild(which)
            return

        target_cb = refs.get("target_cb")
        if target_cb is not None:
            try:
                if value in ("ZOOM_OUT", "DEPLOY"):
                    target_cb.state(["disabled"])
                else:
                    target_cb.state(["!disabled"])
            except Exception:
                pass

    def _on_field(self, step: dict, key: str, value: str):
        step[key] = value
        self.cfg.save_flow()

    def _on_int_field(self, step: dict, key: str, value: str):
        try:
            step[key] = int(value)
            self._debounce_save_flow()
        except ValueError:
            pass

    # ── Add / Delete / Reorder ────────────────────────────────────────────

    def _add_step(self, which: str):
        keys = self.cfg.all_slot_keys()
        step: dict = {
            "id": str(uuid.uuid4())[:8],
            "action": "CLICK",
            "target": keys[0] if keys else "",
            "repeat": 1, "hold_ms": 1000,
            "detect_timeout_ms": 30000, "on_fail": "ALARM_WAIT",
            "delay_ms": 500, "scroll_direction": "DOWN", "max_scrolls": 10,
        }
        self.cfg.flow_data.setdefault(which, []).append(step)
        self.cfg.save_flow()
        self._rebuild(which)

    def _del_step(self, idx: int, which: str):
        steps = self.cfg.flow_data.get(which, [])
        if 0 <= idx < len(steps):
            steps.pop(idx)
            self.cfg.save_flow()
            self._rebuild(which)

    def _move(self, idx: int, direction: int, which: str):
        steps   = self.cfg.flow_data.get(which, [])
        new_idx = idx + direction
        if 0 <= new_idx < len(steps):
            steps[idx], steps[new_idx] = steps[new_idx], steps[idx]
            self.cfg.save_flow()
            self._rebuild(which)

    # ══════════════════════════════════════════════════════════════════════
    # Bot control
    # ══════════════════════════════════════════════════════════════════════

    def _reset_flows(self):
        if self._state != "idle":
            self.app.log("Stop the bot before resetting flows.")
            return
        self.cfg.reset_flow_to_defaults()
        for which in ("attack_steps", "upgrade_steps"):
            self._rebuild(which)
        self.app.log("↺ Flows reset to defaults.")

    def _run(self):
        if self._state != "idle":
            return
        self._state        = "running"
        self._paused       = False
        self._attack_count = 0
        self._stop_flag.clear()
        self._update_controls()
        atk = len(self.cfg.flow_data.get("attack_steps",  []))
        upg = len(self.cfg.flow_data.get("upgrade_steps", []))
        self.app.log(f"▶ Starting — {atk} attack / {upg} upgrade steps")
        self.app.hide()
        threading.Thread(target=self._execute, daemon=True).start()

    def _toggle_pause(self):
        if self._state == "running":
            self._paused = True
            self._state  = "paused"
            self.app.log("⏸ Paused — click Resume when ready.")
            self.app.root.after(0, self.app.show)
            self.app.root.after(0, self._update_controls)
        elif self._state == "paused":
            self._paused = False
            self._state  = "running"
            self.app.log("▶ Resumed.")
            self.app.root.after(0, self._update_controls)
            self.app.root.after(50, self.app.hide)

    def _stop(self):
        self._stop_flag.set()
        self._alarm.stop()
        self._paused = False
        self.app.log("■ Stop requested…")

    def _finish(self):
        self._state  = "idle"
        self._paused = False
        self.app.show()
        self._update_controls()

    def _update_controls(self):
        if self._run_btn is None:
            return
        s = self._state
        if s == "idle":
            self._run_btn.state(["!disabled"])
            self._pause_btn.state(["disabled"])
            self._pause_btn.configure(text="⏸  Pause", style="TButton")
            self._stop_btn.state(["disabled"])
            self._flow_status_var.set("  Idle")
        elif s == "running":
            self._run_btn.state(["disabled"])
            self._pause_btn.state(["!disabled"])
            self._pause_btn.configure(text="⏸  Pause", style="TButton")
            self._stop_btn.state(["!disabled"])
            self._flow_status_var.set(f"  ▶ Attack #{self._attack_count}")
        elif s == "paused":
            self._run_btn.state(["disabled"])
            self._pause_btn.state(["!disabled"])
            self._pause_btn.configure(text="▶  Resume", style="Green.TButton")
            self._stop_btn.state(["!disabled"])
            self._flow_status_var.set("  ⏸ Paused")

    # ══════════════════════════════════════════════════════════════════════
    # Execution engine  (unchanged logic — only UI calls updated)
    # ══════════════════════════════════════════════════════════════════════

    def _execute(self):
        try:
            apu = self.cfg.flow_data.get("attacks_per_upgrade", 40)
            while not self._stop_flag.is_set():
                ok = self._run_step_list("attack_steps", "Attack")
                if not ok:
                    break
                self._attack_count += 1
                self.app.root.after(0, self._update_controls)
                self.app.log(f"  ✓ Attack #{self._attack_count} complete")

                upg = self.cfg.flow_data.get("upgrade_steps", [])
                if upg and apu > 0 and self._attack_count % apu == 0:
                    self.app.log(f"  ⬆ Upgrade cycle (attack #{self._attack_count})")
                    ok = self._run_step_list("upgrade_steps", "Upgrade")
                    if not ok:
                        break
                    self.app.log("  ✓ Upgrade cycle complete")

            if not self._stop_flag.is_set():
                self.app.log("✓ Bot loop ended.")
            else:
                self.app.log("■ Bot stopped.")
        except Exception as e:
            self.app.log(f"✗ Unhandled error: {e}")
        finally:
            self.app.root.after(0, self._finish)

    def _run_step_list(self, which: str, label: str) -> bool:
        for i, step in enumerate(self.cfg.flow_data.get(which, [])):
            if self._stop_flag.is_set():
                return False
            self._wait_if_paused()
            if self._stop_flag.is_set():
                return False
            if not self._execute_step(step, i, label):
                return False
            delay = step.get("delay_ms", 500) / 1000.0
            if delay > 0:
                self._interruptible_sleep(delay)
        return True

    def _wait_if_paused(self):
        while self._paused and not self._stop_flag.is_set():
            time.sleep(0.1)

    def _interruptible_sleep(self, seconds: float):
        end = time.time() + seconds
        while time.time() < end:
            if self._stop_flag.is_set():
                return
            time.sleep(min(0.1, end - time.time()))

    def _execute_step(self, step: dict, idx: int, cycle: str) -> bool:
        action = step.get("action", "CLICK")
        target = step.get("target", "")
        slot   = self.cfg.resolve_slot(target) if target else None
        num    = idx + 1

        if action == "CLICK":
            repeat = step.get("repeat", 1)
            if slot:
                for r in range(repeat):
                    if self._stop_flag.is_set():
                        return False
                    self.screen.click_slot(slot, self.vision)
                    if r < repeat - 1:
                        time.sleep(0.06)
                self.app.log(f"  [{cycle} {num}] CLICK {target} ×{repeat}")
            else:
                self.app.log(f"  [{cycle} {num}] SKIP — '{target}' not configured")
            return True

        elif action == "HOLD":
            hold_ms = step.get("hold_ms", 1000)
            if slot:
                if slot.get("mode") == "IMAGE":
                    found, _, (ax, ay) = self.vision.match_slot(slot)
                    if found:
                        self.screen.hold(ax, ay, hold_ms)
                elif slot.get("coord"):
                    c = slot["coord"]
                    self.screen.hold(int(c[0]), int(c[1]), hold_ms)
                self.app.log(f"  [{cycle} {num}] HOLD {target} {hold_ms}ms")
            else:
                self.app.log(f"  [{cycle} {num}] SKIP — '{target}' not configured")
            return True

        elif action == "DETECT":
            if not slot or slot.get("mode") != "IMAGE":
                self.app.log(f"  [{cycle} {num}] SKIP — '{target}' needs IMAGE mode")
                return True
            timeout = step.get("detect_timeout_ms", 30000) / 1000.0
            self.app.log(f"  [{cycle} {num}] DETECT {target}  (timeout {timeout:.1f}s)")
            start = time.time()
            while time.time() - start < timeout:
                if self._stop_flag.is_set():
                    return False
                self._wait_if_paused()
                if self.vision.detect_on_screen(slot):
                    self.app.log("         → detected ✓")
                    return True
                time.sleep(0.35)
            self.app.log("         → timeout — not found")
            return self._handle_on_fail(step, f"{cycle} {num} DETECT")

        elif action == "ZOOM_OUT":
            ticks = step.get("repeat", 5)
            self.screen.zoom_out(ticks)
            self.app.log(f"  [{cycle} {num}] ZOOM OUT ×{ticks}")
            return True

        elif action == "DEPLOY":
            return self._execute_full_deploy(num, cycle)

        elif action == "SCROLL_SEARCH":
            if not slot or slot.get("mode") != "IMAGE":
                self.app.log(f"  [{cycle} {num}] SKIP — '{target}' needs IMAGE mode")
                return True
            direction   = step.get("scroll_direction", "DOWN")
            max_scrolls = step.get("max_scrolls", 10)
            self.app.log(f"  [{cycle} {num}] SCROLL_SEARCH {target} dir={direction}")
            found = self._do_scroll_search(slot, direction, max_scrolls)
            if found:
                self.app.log("         → found ✓")
                return True
            self.app.log(f"         → not found after {max_scrolls} scrolls")
            return self._handle_on_fail(step, f"{cycle} {num} SCROLL_SEARCH")

        return True

    def _handle_on_fail(self, step: dict, context: str) -> bool:
        on_fail = step.get("on_fail", "ALARM_WAIT")
        if on_fail == "SKIP":
            self.app.log("         → SKIP")
            return True
        if on_fail == "STOP":
            self.app.log("         → STOP")
            return False

        self.app.log("         → ⚠ ALARM  (move mouse to silence — then Resume)")
        self.app.root.after(0, self.app.show)
        time.sleep(0.15)
        self._alarm.trigger()
        self._alarm.wait(stop_signal=self._stop_flag)
        if self._stop_flag.is_set():
            return False

        self.app.log("         → alarm cleared — bot paused")
        self._paused = True
        self._state  = "paused"
        self.app.root.after(0, self._update_controls)
        self._wait_if_paused()
        if self._stop_flag.is_set():
            return False

        self.app.root.after(0, self.app.hide)
        time.sleep(0.15)
        return True

    def _do_scroll_search(self, slot: dict, direction: str, max_scrolls: int) -> bool:
        rect = self.screen.game_rect()
        if rect:
            cx = rect[0] + rect[2] // 2
            cy = rect[1] + rect[3] // 2
        else:
            import mss
            with mss.mss() as sct:
                mon = sct.monitors[0]
            cx, cy = mon["width"] // 2, mon["height"] // 2

        ticks = {"DOWN": -3, "UP": 3, "LEFT": -3, "RIGHT": 3}.get(direction, -3)
        for _ in range(max_scrolls):
            if self._stop_flag.is_set():
                return False
            if self.vision.detect_on_screen(slot):
                return True
            self.screen.scroll(cx, cy, ticks)
            time.sleep(0.5)
        return self.vision.detect_on_screen(slot)

    def _execute_full_deploy(self, num: int, cycle: str) -> bool:
        positions  = self.cfg.army.get("deploy_positions", [])
        tap_ms     = self.cfg.army.get("deploy_tap_delay_ms", 200) / 1000.0
        ability_ms = self.cfg.army.get("ability_delay_ms", 2500) / 1000.0

        if not positions:
            self.app.log(f"  [{cycle} {num}] DEPLOY skipped — no deploy positions")
            return True

        def get_pts(spec) -> list:
            s = str(spec or "all").strip().lower()
            if not s or s == "all":
                return positions
            pts = []
            for part in s.split(","):
                try:
                    i = int(part.strip()) - 1
                    if 0 <= i < len(positions):
                        pts.append(positions[i])
                except (ValueError, IndexError):
                    pass
            return pts if pts else positions

        self.app.log(f"  [{cycle} {num}] DEPLOY — siege → troops → heroes → abilities")

        siege = self.cfg.army.get("siege", {})
        if siege.get("configured"):
            if self._stop_flag.is_set():
                return True
            self.screen.click_slot(siege, self.vision)
            time.sleep(tap_ms * 3)
            pts = get_pts(siege.get("deploy_at", "all"))
            self.screen.click(pts[0][0], pts[0][1])
            time.sleep(tap_ms * 2)

        for troop in self.cfg.army.get("troops", []):
            if self._stop_flag.is_set():
                return True
            if not troop.get("configured"):
                continue
            self.screen.click_slot(troop, self.vision)
            time.sleep(tap_ms * 2)
            pts   = get_pts(troop.get("deploy_at", "all"))
            count = int(troop.get("count", 1))
            for j in range(count):
                if self._stop_flag.is_set():
                    return True
                p = pts[j % len(pts)]
                self.screen.click(p[0], p[1])
                time.sleep(tap_ms)

        heroes = [h for h in self.cfg.army.get("heroes", []) if h.get("configured")]
        for hero in heroes:
            if self._stop_flag.is_set():
                return True
            self.screen.click_slot(hero, self.vision)
            time.sleep(tap_ms * 2)
            pts = get_pts(hero.get("deploy_at", "all"))
            self.screen.click(pts[0][0], pts[0][1])
            time.sleep(tap_ms)

        if heroes:
            self._interruptible_sleep(ability_ms)
            for hero in heroes:
                if self._stop_flag.is_set():
                    return True
                self.screen.click_slot(hero, self.vision)
                time.sleep(0.5)
            self.app.log("         → hero abilities activated")

        return True
