import logging
import time
from typing import Optional

import cv2
import numpy as np

from core.adb import ADBInterface, _jitter
from core.navigator import Navigator
from core.ocr import OCRReader
from core.state_machine import StateMachine
from core.vision import YOLODetector

logger = logging.getLogger(__name__)

# Panel bounding box (relative) — calibrate per resolution
_PANEL_BBOX = (0.05, 0.10, 0.95, 0.90)
_PANEL_SCROLL_FROM = (0.5, 0.70)
_PANEL_SCROLL_TO = (0.5, 0.30)
_BOTTOM_DIFF_THRESHOLD = 0.02


class UpgradeEngine:
    def __init__(
        self,
        adb: ADBInterface,
        navigator: Navigator,
        detector: YOLODetector,
        ocr: OCRReader,
        state_machine: StateMachine,
        config: dict,
        notifier,
        db=None,
    ) -> None:
        self.adb = adb
        self.navigator = navigator
        self.detector = detector
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

        seen_items: set[str] = set()
        max_scrolls = 30

        for scroll_num in range(max_scrolls):
            frame = self.adb.screenshot()
            panel_frame = self._crop_panel(frame)

            # CLAHE + adaptive threshold on panel region for better OCR
            processed = self._preprocess_panel(panel_frame)

            detections = self.detector.detect(frame)
            panel_items = [d for d in detections if d.label in ("upgrade_panel", "wall_segment", "btn_upgrade")]

            # Check if target is visible
            for d in detections:
                item_key = f"{d.label}_{d.center[0]:.2f}_{d.center[1]:.2f}"
                if item_key in seen_items:
                    continue
                seen_items.add(item_key)

                if d.label == target or self._label_matches(d.label, target):
                    logger.info("Found upgrade target '%s' at %s", target, d.center)
                    self.adb.tap(*d.center)
                    time.sleep(0.8)
                    success = self.upgrade_confirmation_flow()
                    self.navigator.close_upgrade_panel()
                    return success

            # Check if bottom reached
            time.sleep(0.3)
            frame2 = self.adb.screenshot()
            if self.check_bottom(frame, frame2, _PANEL_BBOX):
                logger.info("Reached bottom of upgrade panel — target '%s' not found", target)
                self.navigator.close_upgrade_panel()
                return False

            # Scroll up inside panel
            self.adb.swipe(*_PANEL_SCROLL_FROM, *_PANEL_SCROLL_TO, duration_ms=400)
            time.sleep(0.5)

        logger.warning("Max scrolls reached without finding '%s'", target)
        self.navigator.close_upgrade_panel()
        return False

    def upgrade_confirmation_flow(self) -> bool:
        """Tap upgrade, check cost vs loot, confirm if sufficient."""
        frame = self.adb.screenshot()
        detections = self.detector.detect(frame)
        upgrade_btn = next((d for d in detections if d.label == "btn_upgrade"), None)

        if upgrade_btn is None:
            logger.warning("upgrade_confirmation_flow: btn_upgrade not found")
            return False

        self.adb.tap(*upgrade_btn.center)
        time.sleep(0.8)

        frame = self.adb.screenshot()
        upgrade_cost = self.ocr.read_region(frame, "upgrade_cost")
        home_gold = self.ocr.read_region(frame, "home_gold")
        home_elixir = self.ocr.read_region(frame, "home_elixir")

        logger.info("Upgrade cost: %s | Home gold: %s | Home elixir: %s", upgrade_cost, home_gold, home_elixir)

        if upgrade_cost is None:
            logger.warning("Could not read upgrade cost")
            return False

        max_loot = max(home_gold or 0, home_elixir or 0)
        if max_loot < upgrade_cost:
            logger.info("Insufficient loot for upgrade (need %d, have %d)", upgrade_cost, max_loot)
            if self.notifier:
                self.notifier.notify("INSUFFICIENT_LOOT", {
                    "cost": upgrade_cost,
                    "gold": home_gold,
                    "elixir": home_elixir,
                })
            return False

        # Confirm upgrade
        detections = self.detector.detect(frame)
        confirm_btn = next((d for d in detections if d.label in ("btn_upgrade", "btn_confirm")), None)
        if confirm_btn:
            self.adb.tap(*confirm_btn.center)
            time.sleep(1.0)

        logger.info("Upgrade confirmed")
        if self.notifier:
            self.notifier.notify("UPGRADE_STARTED", {"cost": upgrade_cost})
        if self.db:
            self.db.log_upgrade(0, target="", cost_gold=upgrade_cost, cost_elixir=0, cost_dark=0, success=True)
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

    def _label_matches(self, detected: str, target: str) -> bool:
        return target.lower() in detected.lower() or detected.lower() in target.lower()
