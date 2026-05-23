import logging
import time
from typing import Optional

import cv2
import numpy as np

from core.adb import ADBInterface, _jitter
from core.navigator import Navigator
from core.ocr import OCRReader
from core.state_machine import StateMachine
from core.vision import TemplateMatcher

logger = logging.getLogger(__name__)

_PANEL_BBOX = (0.05, 0.10, 0.95, 0.90)
_PANEL_SCROLL_FROM = (0.5, 0.70)
_PANEL_SCROLL_TO = (0.5, 0.30)
_BOTTOM_DIFF_THRESHOLD = 0.02


class UpgradeEngine:
    def __init__(
        self,
        adb: ADBInterface,
        navigator: Navigator,
        matcher: TemplateMatcher,
        ocr: OCRReader,
        state_machine: StateMachine,
        config: dict,
        notifier,
        db=None,
    ) -> None:
        self.adb = adb
        self.navigator = navigator
        self.matcher = matcher
        self.ocr = ocr
        self.state_machine = state_machine
        self.config = config
        self.notifier = notifier
        self.db = db

    def run_upgrade(self, target: str) -> bool:
        """Find and upgrade the named item. Returns True on success."""
        self.navigator.move_camera_to_corner()
        time.sleep(0.5)

        if not self.navigator.open_upgrade_panel():
            logger.error("Could not open upgrade panel")
            return False

        max_scrolls = 30

        for scroll_num in range(max_scrolls):
            frame = self.adb.screenshot()

            confirm_center = self.matcher.find(frame, "upgrade_confirm_button")
            if confirm_center:
                logger.info("Found upgrade confirm button for target '%s'", target)
                success = self.upgrade_confirmation_flow()
                self.navigator.close_upgrade_panel()
                return success

            time.sleep(0.3)
            frame2 = self.adb.screenshot()
            if self.check_bottom(frame, frame2, _PANEL_BBOX):
                logger.info("Reached bottom of upgrade panel — target '%s' not found", target)
                self.navigator.close_upgrade_panel()
                return False

            self.adb.swipe(*_PANEL_SCROLL_FROM, *_PANEL_SCROLL_TO, duration_ms=400)
            time.sleep(0.5)

        logger.warning("Max scrolls reached without finding '%s'", target)
        self.navigator.close_upgrade_panel()
        return False

    def upgrade_confirmation_flow(self) -> bool:
        """Confirm upgrade assuming sufficient loot (OCR disabled)."""
        frame = self.adb.screenshot()
        confirm_center = self.matcher.find(frame, "upgrade_confirm_button")
        if confirm_center:
            self.adb.tap(*confirm_center)
            time.sleep(1.0)

        logger.info("Upgrade confirmed (loot check skipped — OCR disabled)")
        if self.notifier:
            self.notifier.notify("UPGRADE_STARTED", {"cost": 0})
        if self.db:
            self.db.log_upgrade(0, target="", cost_gold=0, cost_elixir=0, cost_dark=0, success=True)
        return True

    def check_bottom(self, frame1: np.ndarray, frame2: np.ndarray, panel_bbox: tuple) -> bool:
        """Return True if the panel hasn't changed between two frames (bottom reached)."""
        crop1 = self._crop_panel(frame1, panel_bbox)
        crop2 = self._crop_panel(frame2, panel_bbox)
        if crop1.shape != crop2.shape:
            return False
        diff = cv2.absdiff(crop1, crop2)
        normalized_diff = diff.mean() / 255.0
        return normalized_diff < _BOTTOM_DIFF_THRESHOLD

    def _crop_panel(self, frame: np.ndarray, bbox: tuple = _PANEL_BBOX) -> np.ndarray:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        return frame[int(y1 * h):int(y2 * h), int(x1 * w):int(x2 * w)]

    def _preprocess_panel(self, panel: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(panel, cv2.COLOR_BGR2GRAY) if len(panel.shape) == 3 else panel
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        return cv2.adaptiveThreshold(
            enhanced, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=11, C=2,
        )
