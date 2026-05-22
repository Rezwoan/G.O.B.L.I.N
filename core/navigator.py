import logging
import time

import numpy as np

from core.adb import ADBInterface
from core.state_machine import StateMachine, State
from core.vision import YOLODetector

logger = logging.getLogger(__name__)

# Known popup dismiss patterns: (label_to_check, tap_relative_x, tap_relative_y)
_POPUP_PATTERNS = [
    ("btn_ok",       0.500, 0.580),
    ("btn_close",    0.500, 0.580),
    ("btn_dismiss",  0.500, 0.580),
]

# Relative coordinates for common navigation targets
_BACK_BUTTON = (0.050, 0.950)
_HOME_BUTTON = (0.050, 0.950)


class Navigator:
    def __init__(
        self,
        adb: ADBInterface,
        state_machine: StateMachine,
        detector: YOLODetector,
    ) -> None:
        self.adb = adb
        self.state_machine = state_machine
        self.detector = detector

    def go_home(self) -> bool:
        """Tap back/home until HOME_VILLAGE state detected. Returns True on success."""
        for attempt in range(5):
            frame = self.adb.screenshot()
            state = self.state_machine.update(frame)
            if state == State.HOME_VILLAGE:
                return True
            self.adb.tap(*_HOME_BUTTON)
            time.sleep(1.0)
        logger.warning("go_home: failed to reach HOME_VILLAGE after 5 attempts")
        return False

    def go_to_matchmaking(self) -> bool:
        """From home village, tap the attack button to enter matchmaking."""
        frame = self.adb.screenshot()
        detections = self.detector.detect(frame)
        btn = next((d for d in detections if d.label == "btn_attack"), None)
        if btn is None:
            logger.warning("go_to_matchmaking: btn_attack not found")
            return False
        self.adb.tap(*btn.center)
        time.sleep(1.5)
        frame = self.adb.screenshot()
        state = self.state_machine.update(frame)
        if state == State.SEARCHING:
            return True
        # Try tapping Find a Match if still on home
        for d in self.detector.detect(frame):
            if d.label == "btn_find_match":
                self.adb.tap(*d.center)
                time.sleep(1.5)
                return True
        logger.warning("go_to_matchmaking: did not reach SEARCHING state")
        return False

    def open_upgrade_panel(self) -> bool:
        frame = self.adb.screenshot()
        detections = self.detector.detect(frame)
        panel_btn = next((d for d in detections if d.label == "upgrade_panel"), None)
        if panel_btn is None:
            logger.warning("open_upgrade_panel: upgrade_panel button not found")
            return False
        self.adb.tap(*panel_btn.center)
        time.sleep(1.0)
        return True

    def close_upgrade_panel(self) -> bool:
        frame = self.adb.screenshot()
        detections = self.detector.detect(frame)
        close_btn = next((d for d in detections if d.label in ("btn_close", "btn_back")), None)
        if close_btn:
            self.adb.tap(*close_btn.center)
            time.sleep(0.8)
            return True
        # Fallback: tap back button
        self.adb.tap(*_BACK_BUTTON)
        time.sleep(0.8)
        return True

    def dismiss_popups(self, frame: np.ndarray) -> bool:
        """Check for popup patterns and dismiss. Returns True if something was dismissed."""
        detections = self.detector.detect(frame)
        detected_labels = {d.label: d for d in detections}
        for label, tx, ty in _POPUP_PATTERNS:
            if label in detected_labels:
                logger.info("Dismissing popup: %s", label)
                self.adb.tap(*detected_labels[label].center)
                time.sleep(0.8)
                return True
        return False

    def move_camera_to_corner(self) -> None:
        """Push camera to top-left corner and zoom in for upgrade panel stability."""
        # Swipe sequence to push camera to corner
        for _ in range(3):
            self.adb.swipe(0.5, 0.5, 0.9, 0.9, duration_ms=400)
            time.sleep(0.2)
        # Max zoom via pinch in
        self.adb.pinch_in(0.5, 0.5, spread=0.35)
        self.adb.pinch_in(0.5, 0.5, spread=0.35)
        time.sleep(0.5)
