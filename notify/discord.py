import io
import logging
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import requests
from PIL import Image

logger = logging.getLogger(__name__)

_EMBED_COLOR = 0x00AA44

# Event → human-readable title mapping
_TITLES = {
    "TASK_STARTED":     "Task Started",
    "TASK_COMPLETED":   "Task Completed",
    "UPGRADE_STARTED":  "Upgrade Started",
    "INSUFFICIENT_LOOT": "Insufficient Loot",
    "ERROR":            "Bot Error",
    "BOT_STOPPED":      "Bot Stopped",
}

_ERROR_COLOR = 0xFF4444
_WARN_COLOR = 0xFFCC00


class DiscordNotifier:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def send(
        self,
        event: str,
        data: dict,
        screenshot: Optional[np.ndarray] = None,
    ) -> None:
        if not self.webhook_url:
            return

        title = _TITLES.get(event, event)
        color = _ERROR_COLOR if event == "ERROR" else (_WARN_COLOR if event == "INSUFFICIENT_LOOT" else _EMBED_COLOR)

        embed = {
            "title": title,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fields": [{"name": str(k), "value": str(v), "inline": True} for k, v in data.items()],
            "footer": {"text": "G.O.B.L.I.N AutoLoot CoC v3"},
        }

        try:
            if screenshot is not None:
                png_bytes = self._encode_png(screenshot)
                resp = requests.post(
                    self.webhook_url,
                    data={"payload_json": __import__("json").dumps({"embeds": [embed]})},
                    files={"file": ("screenshot.png", png_bytes, "image/png")},
                    timeout=10,
                )
            else:
                resp = requests.post(
                    self.webhook_url,
                    json={"embeds": [embed]},
                    timeout=10,
                )
            resp.raise_for_status()
            logger.debug("Discord notification sent: %s", event)
        except Exception as exc:
            logger.error("Discord send failed: %s", exc)

    def _encode_png(self, frame: np.ndarray) -> bytes:
        bgr = frame if frame.shape[2] == 3 else frame[:, :, :3]
        rgb = bgr[:, :, ::-1]
        img = Image.fromarray(rgb.astype("uint8"))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
