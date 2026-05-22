import io
import logging
import threading
import time
from typing import Callable, Optional

import numpy as np
import requests
from PIL import Image

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org/bot{token}/{method}"

_TITLES = {
    "TASK_STARTED":      "Task Started",
    "TASK_COMPLETED":    "Task Completed",
    "UPGRADE_STARTED":   "Upgrade Started",
    "INSUFFICIENT_LOOT": "Insufficient Loot",
    "ERROR":             "Bot Error",
    "BOT_STOPPED":       "Bot Stopped",
}


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str) -> None:
        self.token = token
        self.chat_id = chat_id
        self._polling = False
        self._poll_thread: Optional[threading.Thread] = None
        self._last_update_id: int = 0
        self._on_status: Optional[Callable] = None
        self._on_stop: Optional[Callable] = None

    def send(
        self,
        event: str,
        data: dict,
        screenshot: Optional[np.ndarray] = None,
    ) -> None:
        if not self.token or not self.chat_id:
            return
        title = _TITLES.get(event, event)
        lines = [f"*{title}*"]
        for k, v in data.items():
            lines.append(f"  {k}: `{v}`")
        text = "\n".join(lines)

        try:
            if screenshot is not None:
                self._send_photo(text, screenshot)
            else:
                self._send_message(text)
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)

    def _send_message(self, text: str) -> None:
        url = _API_BASE.format(token=self.token, method="sendMessage")
        resp = requests.post(url, json={"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
        resp.raise_for_status()

    def _send_photo(self, caption: str, frame: np.ndarray) -> None:
        bgr = frame if frame.shape[2] == 3 else frame[:, :, :3]
        rgb = bgr[:, :, ::-1]
        img = Image.fromarray(rgb.astype("uint8"))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        url = _API_BASE.format(token=self.token, method="sendPhoto")
        resp = requests.post(
            url,
            data={"chat_id": self.chat_id, "caption": caption, "parse_mode": "Markdown"},
            files={"photo": ("screenshot.png", buf, "image/png")},
            timeout=15,
        )
        resp.raise_for_status()

    def start_polling(self) -> None:
        if self._polling or not self.token:
            return
        self._polling = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True, name="TelegramPoller")
        self._poll_thread.start()
        logger.info("Telegram polling started")

    def stop_polling(self) -> None:
        self._polling = False
        logger.info("Telegram polling stopped")

    def on_status(self, callback: Callable) -> None:
        self._on_status = callback

    def on_stop(self, callback: Callable) -> None:
        self._on_stop = callback

    def _poll_loop(self) -> None:
        while self._polling:
            try:
                url = _API_BASE.format(token=self.token, method="getUpdates")
                resp = requests.get(
                    url,
                    params={"offset": self._last_update_id + 1, "timeout": 5},
                    timeout=10,
                )
                resp.raise_for_status()
                updates = resp.json().get("result", [])
                for update in updates:
                    self._last_update_id = update["update_id"]
                    self._handle_update(update)
            except Exception as exc:
                logger.debug("Telegram poll error: %s", exc)
            time.sleep(2.0)

    def _handle_update(self, update: dict) -> None:
        msg = update.get("message", {})
        text = msg.get("text", "").strip()
        if text == "/status" and self._on_status:
            self._on_status()
        elif text == "/stop" and self._on_stop:
            self._on_stop()
