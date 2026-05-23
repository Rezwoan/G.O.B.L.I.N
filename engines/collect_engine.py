import logging
import time

from core.adb import ADBInterface, _jitter
from core.state_machine import StateMachine
from core.vision import TemplateMatcher

logger = logging.getLogger(__name__)


class CollectEngine:
    def __init__(
        self,
        adb: ADBInterface,
        matcher: TemplateMatcher,
        state_machine: StateMachine,
    ) -> None:
        self.adb = adb
        self.matcher = matcher
        self.state_machine = state_machine

    def collect_all(self) -> int:
        """Detect and tap all full mines/collectors. Returns count tapped."""
        frame = self.adb.screenshot()
        mines = self.matcher.find_all(frame, "mine_full")

        logger.info("collect_all: found %d ready collectors", len(mines))
        for center in mines:
            self.adb.tap(*center)
            time.sleep(_jitter(400) / 1000.0)

        return len(mines)
