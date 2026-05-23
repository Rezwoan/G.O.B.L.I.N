import logging
import time

import numpy as np

from core.adb import ADBInterface
from core.state_machine import StateMachine, State
from core.vision import TemplateMatcher

logger = logging.getLogger(__name__)

_BACK_BUTTON = (0.050, 0.950)
_HOME_BUTTON = (0.050, 0.950)


class Navigator:
    def __init__(
        self,
        adb: ADBInterface,
        state_machine: StateMachine,
        matcher: TemplateMatcher,
    ) -> None:
        self.adb = adb
        self.state_machine = state_machine
        self.matcher = matcher

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
        center = self.matcher.find(frame, "home_screen_attack_button")
        if center is None:
            logger.warning("go_to_matchmaking: home_screen_attack_button not found")
            return False
        self.adb.tap(*center)
        time.sleep(1.5)
        frame = self.adb.screenshot()
        state = self.state_machine.update(frame)
        if state == State.SEARCHING:
            return True
        # Try Find a Match button if still on attack menu
        center = self.matcher.find(frame, "multiplayer_find_a_match_button")
        if center:
            self.adb.tap(*center)
            time.sleep(1.5)
            return True
        logger.warning("go_to_matchmaking: did not reach SEARCHING state")
        return False

    def open_upgrade_panel(self) -> bool:
        frame = self.adb.screenshot()
        center = self.matcher.find(frame, "home_screen_upgrade_window_button")
        if center is None:
            logger.warning("open_upgrade_panel: home_screen_upgrade_window_button not found")
            return False
        self.adb.tap(*center)
        time.sleep(1.0)
        return True

    def close_upgrade_panel(self) -> bool:
        self.adb.tap(*_BACK_BUTTON)
        time.sleep(0.8)
        return True

    def dismiss_popups(self, frame: np.ndarray) -> bool:
        """Check for known popups and dismiss. Returns True if something was dismissed."""
        center = self.matcher.find(frame, "connection_lost_reload_button")
        if center:
            logger.info("Dismissing connection lost popup")
            self.adb.tap(*center)
            time.sleep(0.8)
            return True
        return False

    def move_camera_to_corner(self) -> None:
        """Push camera to top-left corner and zoom in for upgrade panel stability."""
        for _ in range(3):
            self.adb.swipe(0.5, 0.5, 0.9, 0.9, duration_ms=400)
            time.sleep(0.2)
        self.adb.pinch_in(0.5, 0.5, spread=0.35)
        self.adb.pinch_in(0.5, 0.5, spread=0.35)
        time.sleep(0.5)
