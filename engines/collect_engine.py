import logging
import time

from core.adb import ADBInterface, _jitter
from core.state_machine import StateMachine
from core.vision import YOLODetector

logger = logging.getLogger(__name__)


class CollectEngine:
    def __init__(
        self,
        adb: ADBInterface,
        detector: YOLODetector,
        state_machine: StateMachine,
    ) -> None:
        self.adb = adb
        self.detector = detector
        self.state_machine = state_machine

    def collect_all(self) -> int:
        """Detect and tap all full mines/collectors. Returns count tapped."""
        frame = self.adb.screenshot()
        detections = self.detector.detect(frame)
        mines = [d for d in detections if d.label == "mine_full"]

        logger.info("collect_all: found %d ready collectors", len(mines))
        for mine in mines:
            self.adb.tap(*mine.center)
            time.sleep(_jitter(400) / 1000.0)

        return len(mines)
