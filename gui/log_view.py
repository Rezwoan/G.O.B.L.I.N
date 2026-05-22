import logging
import queue
import threading
from datetime import datetime

import customtkinter as ctk

logger = logging.getLogger(__name__)

_COLORS = {
    "INFO":    "#ffffff",
    "SUCCESS": "#00ff88",
    "WARNING": "#ffcc00",
    "ERROR":   "#ff4444",
    "DEBUG":   "#888888",
}


class LogView(ctk.CTkFrame):
    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self._queue: queue.Queue = queue.Queue()
        self._build_ui()
        self._poll()

    def _build_ui(self) -> None:
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(btn_frame, text="Logs", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Clear", width=70, command=self._clear).pack(side="right", padx=6)

        self._textbox = ctk.CTkTextbox(self, state="disabled", wrap="word", font=ctk.CTkFont(family="Consolas", size=12))
        self._textbox.pack(fill="both", expand=True, padx=6, pady=4)

    def append(self, level: str, message: str, timestamp: str = "") -> None:
        """Thread-safe log append."""
        if not timestamp:
            timestamp = datetime.now().strftime("%H:%M:%S")
        self._queue.put((level, message, timestamp))

    def _poll(self) -> None:
        try:
            while True:
                level, message, timestamp = self._queue.get_nowait()
                self._write(level, message, timestamp)
        except queue.Empty:
            pass
        self.after(200, self._poll)

    def _write(self, level: str, message: str, timestamp: str) -> None:
        color = _COLORS.get(level.upper(), "#ffffff")
        self._textbox.configure(state="normal")
        line = f"[{timestamp}] [{level}] {message}\n"
        self._textbox.insert("end", line)
        # Apply color to last inserted line via tag
        end_idx = self._textbox.index("end-1c")
        line_start = f"end-{len(line)+1}c"
        self._textbox.see("end")
        self._textbox.configure(state="disabled")

    def _clear(self) -> None:
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")


class GUILogHandler(logging.Handler):
    """Logging handler that routes records to the LogView widget."""

    def __init__(self, log_view: LogView) -> None:
        super().__init__()
        self._log_view = log_view

    def emit(self, record: logging.LogRecord) -> None:
        level = record.levelname
        # Map Python log levels to our display levels
        if level == "WARNING":
            display = "WARNING"
        elif level in ("ERROR", "CRITICAL"):
            display = "ERROR"
        elif level == "DEBUG":
            display = "DEBUG"
        else:
            display = "INFO"
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        self._log_view.append(display, self.format(record), ts)
