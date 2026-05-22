from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Event constants
TASK_STARTED = "TASK_STARTED"
TASK_COMPLETED = "TASK_COMPLETED"
UPGRADE_STARTED = "UPGRADE_STARTED"
INSUFFICIENT_LOOT = "INSUFFICIENT_LOOT"
ERROR = "ERROR"
BOT_STOPPED = "BOT_STOPPED"


class Notifier:
    """Facade that broadcasts to Discord and/or Telegram."""

    def __init__(self, discord=None, telegram=None) -> None:
        self._discord = discord
        self._telegram = telegram

    def notify(
        self,
        event: str,
        data: dict,
        screenshot: Optional[np.ndarray] = None,
    ) -> None:
        if self._discord:
            try:
                self._discord.send(event, data, screenshot)
            except Exception as exc:
                logger.error("Discord notify failed: %s", exc)
        if self._telegram:
            try:
                self._telegram.send(event, data, screenshot)
            except Exception as exc:
                logger.error("Telegram notify failed: %s", exc)
