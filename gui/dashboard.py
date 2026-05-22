import logging
import threading
import time
from datetime import datetime
from typing import Callable, Optional

import customtkinter as ctk
from PIL import Image

logger = logging.getLogger(__name__)


class DashboardTab(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        adb=None,
        state_machine=None,
        on_start: Optional[Callable] = None,
        on_pause: Optional[Callable] = None,
        on_stop: Optional[Callable] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.adb = adb
        self.state_machine = state_machine
        self._on_start = on_start
        self._on_pause = on_pause
        self._on_stop = on_stop

        self._session_start: Optional[float] = None
        self._attacks = 0
        self._gold = 0

        self._build_ui()
        self._start_refresh()

    def _build_ui(self) -> None:
        # Left: screenshot feed
        left = ctk.CTkFrame(self)
        left.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        self._screenshot_label = ctk.CTkLabel(left, text="No screenshot yet", width=640, height=400)
        self._screenshot_label.pack(pady=10)

        self._state_label = ctk.CTkLabel(left, text="State: IDLE", font=ctk.CTkFont(size=14))
        self._state_label.pack(pady=4)

        # Right: controls + stats
        right = ctk.CTkFrame(self, width=300)
        right.pack(side="right", fill="y", padx=10, pady=10)

        ctk.CTkLabel(right, text="Session Stats", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=8)

        self._stats_attacks = ctk.CTkLabel(right, text="Attacks: 0")
        self._stats_attacks.pack(pady=2)
        self._stats_gold = ctk.CTkLabel(right, text="Gold collected: 0")
        self._stats_gold.pack(pady=2)
        self._stats_time = ctk.CTkLabel(right, text="Time running: 0s")
        self._stats_time.pack(pady=2)

        # Status dot
        self._status_dot = ctk.CTkLabel(right, text="●", text_color="red", font=ctk.CTkFont(size=22))
        self._status_dot.pack(pady=8)

        ctk.CTkLabel(right, text="Controls", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=8)

        self._btn_start = ctk.CTkButton(right, text="Start", command=self._start, fg_color="#1a7a1a")
        self._btn_start.pack(fill="x", padx=10, pady=4)

        self._btn_pause = ctk.CTkButton(right, text="Pause", command=self._pause, fg_color="#7a7a1a")
        self._btn_pause.pack(fill="x", padx=10, pady=4)

        self._btn_stop = ctk.CTkButton(right, text="Stop", command=self._stop, fg_color="#7a1a1a")
        self._btn_stop.pack(fill="x", padx=10, pady=4)

    def _start(self) -> None:
        self._session_start = time.time()
        self._attacks = 0
        self._gold = 0
        self._status_dot.configure(text_color="#00ff88")
        if self._on_start:
            self._on_start()

    def _pause(self) -> None:
        self._status_dot.configure(text_color="#ffcc00")
        if self._on_pause:
            self._on_pause()

    def _stop(self) -> None:
        self._session_start = None
        self._status_dot.configure(text_color="red")
        if self._on_stop:
            self._on_stop()

    def _start_refresh(self) -> None:
        self._refresh_screenshot()
        self._refresh_stats()

    def _refresh_screenshot(self) -> None:
        def _fetch():
            if self.adb is None:
                return
            try:
                frame = self.adb.screenshot()
                h, w = frame.shape[:2]
                rgb = frame[:, :, ::-1]
                pil_img = Image.fromarray(rgb.astype("uint8")).resize((640, 360))
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(640, 360))
                self.after(0, lambda: self._screenshot_label.configure(image=ctk_img, text=""))
                if self.state_machine:
                    state_name = self.state_machine.current.name
                    self.after(0, lambda: self._state_label.configure(text=f"State: {state_name}"))
            except Exception as exc:
                logger.debug("Screenshot refresh failed: %s", exc)

        threading.Thread(target=_fetch, daemon=True).start()
        self.after(2000, self._refresh_screenshot)

    def _refresh_stats(self) -> None:
        if self._session_start:
            elapsed = int(time.time() - self._session_start)
            self._stats_time.configure(text=f"Time running: {elapsed}s")
        self._stats_attacks.configure(text=f"Attacks: {self._attacks}")
        self._stats_gold.configure(text=f"Gold collected: {self._gold:,}")
        self.after(5000, self._refresh_stats)

    def update_stats(self, attacks: int, gold: int) -> None:
        self._attacks = attacks
        self._gold = gold
