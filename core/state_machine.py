import logging
from enum import Enum, auto

import numpy as np

from core.vision import TemplateMatcher

logger = logging.getLogger(__name__)

_STATE_MAP: dict[str, str] = {
    "loading":        "IDLE",
    "connection_lost": "ERROR_RECOVERY",
    "post_battle":    "POST_BATTLE",
    "attacking":      "ATTACKING",
    "searching":      "SEARCHING",
    "attack_menu":    "HOME_VILLAGE",
    "upgrading":      "UPGRADING",
    "home":           "HOME_VILLAGE",
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
    def __init__(self, matcher: TemplateMatcher) -> None:
        self.matcher = matcher
        self._current = State.IDLE
        self.retry_count: int = 0

    @property
    def current(self) -> State:
        return self._current

    def detect_state(self, frame: np.ndarray) -> State:
        state_str = self.matcher.detect_state(frame)
        if state_str == "unknown":
            self.retry_count += 1
            logger.debug("State unknown (retry %d)", self.retry_count)
            if self.retry_count >= 3:
                return State.ERROR_RECOVERY
            return State.IDLE
        self.retry_count = 0
        state_name = _STATE_MAP.get(state_str, "IDLE")
        return State[state_name]

    def transition(self, new_state: State) -> None:
        if new_state != self._current:
            logger.info("State transition: %s → %s", self._current.name, new_state.name)
            self._current = new_state

    def update(self, frame: np.ndarray) -> State:
        new_state = self.detect_state(frame)
        self.transition(new_state)
        return self._current
