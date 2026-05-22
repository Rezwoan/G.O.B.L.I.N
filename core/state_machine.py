import logging
from enum import Enum, auto

import numpy as np

from core.vision import YOLODetector

logger = logging.getLogger(__name__)

# YOLO class signatures that identify each state
_STATE_SIGNATURES: dict[str, list[str]] = {
    "HOME_VILLAGE": ["btn_attack", "builder_idle", "mine_full"],
    "SEARCHING":    ["btn_next", "enemy_gold"],
    "ATTACKING":    ["troop_icon"],
    "POST_BATTLE":  ["loot_bag"],
    "UPGRADING":    ["upgrade_panel"],
    "COLLECTING":   ["btn_collect"],
}


class State(Enum):
    IDLE = auto()
    HOME_VILLAGE = auto()
    SEARCHING = auto()
    ATTACKING = auto()
    POST_BATTLE = auto()
    UPGRADING = auto()
    COLLECTING = auto()
    ERROR_RECOVERY = auto()


class StateMachine:
    def __init__(self, detector: YOLODetector) -> None:
        self._detector = detector
        self._current = State.IDLE
        self.retry_count: int = 0

    @property
    def current(self) -> State:
        return self._current

    def detect_state(self, frame: np.ndarray) -> State:
        detections = self._detector.detect(frame)
        detected_labels = {d.label for d in detections}

        for state_name, required_labels in _STATE_SIGNATURES.items():
            if any(label in detected_labels for label in required_labels):
                self.retry_count = 0
                return State[state_name]

        self.retry_count += 1
        logger.debug("State unknown (retry %d), detected labels: %s", self.retry_count, detected_labels)
        if self.retry_count > 3:
            return State.ERROR_RECOVERY
        return State.IDLE

    def transition(self, new_state: State) -> None:
        if new_state != self._current:
            logger.info("State transition: %s → %s", self._current.name, new_state.name)
            self._current = new_state

    def update(self, frame: np.ndarray) -> State:
        new_state = self.detect_state(frame)
        self.transition(new_state)
        return self._current
