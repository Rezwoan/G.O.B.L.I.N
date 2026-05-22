import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

from core.adb import ADBInterface, _jitter
from core.navigator import Navigator
from core.ocr import OCRReader
from core.state_machine import StateMachine, State
from core.vision import YOLODetector, DeploymentZoneDetector
from strategies import STRATEGIES

logger = logging.getLogger(__name__)

# Fallback deployment ring: 8% inset border, 20 points
_FALLBACK_RING_INSET = 0.08
_FALLBACK_N = 20


def _fallback_ring() -> list[tuple[float, float]]:
    pts = []
    n = _FALLBACK_N
    ins = _FALLBACK_RING_INSET
    for i in range(n):
        t = i / n
        if t < 0.25:
            x = ins + (t / 0.25) * (1 - 2 * ins)
            y = ins
        elif t < 0.5:
            x = 1 - ins
            y = ins + ((t - 0.25) / 0.25) * (1 - 2 * ins)
        elif t < 0.75:
            x = (1 - ins) - ((t - 0.5) / 0.25) * (1 - 2 * ins)
            y = 1 - ins
        else:
            x = ins
            y = (1 - ins) - ((t - 0.75) / 0.25) * (1 - 2 * ins)
        pts.append((x, y))
    return pts


@dataclass
class AttackResult:
    strategy: str
    enemy_gold: Optional[int]
    enemy_elixir: Optional[int]
    enemy_dark: Optional[int]
    loot_gold: Optional[int]
    loot_elixir: Optional[int]
    loot_dark: Optional[int]
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class AttackEngine:
    _MAX_SEARCHES = 50
    _BATTLE_TIMEOUT = 240  # seconds
    _POLL_INTERVAL = 2.0

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
        self._zone_detector = DeploymentZoneDetector()

    def run_attack_cycle(self) -> Optional[AttackResult]:
        if not self.navigator.go_to_matchmaking():
            logger.error("Failed to reach matchmaking")
            return None

        # Search for a suitable base
        enemy_gold = enemy_elixir = enemy_dark = None
        thresholds = self.config.get("thresholds", {})
        min_gold = thresholds.get("gold", 0)
        min_elixir = thresholds.get("elixir", 0)
        min_dark = thresholds.get("dark", 0)

        found = False
        for search_num in range(self._MAX_SEARCHES):
            frame = self.adb.screenshot()
            enemy_gold = self.ocr.read_region(frame, "enemy_gold")
            enemy_elixir = self.ocr.read_region(frame, "enemy_elixir")
            enemy_dark = self.ocr.read_region(frame, "enemy_dark")
            logger.debug("Search %d: gold=%s elixir=%s dark=%s", search_num, enemy_gold, enemy_elixir, enemy_dark)

            gold_ok = (enemy_gold or 0) >= min_gold
            elixir_ok = (enemy_elixir or 0) >= min_elixir
            dark_ok = (enemy_dark or 0) >= min_dark

            if gold_ok and elixir_ok and dark_ok:
                found = True
                break

            # Tap "Next"
            detections = self.detector.detect(frame)
            next_btn = next((d for d in detections if d.label == "btn_next"), None)
            if next_btn:
                self.adb.tap(*next_btn.center)
            else:
                logger.warning("btn_next not found on search %d", search_num)
                self.adb.tap(0.5, 0.9)  # fallback position
            time.sleep(_jitter(1000) / 1000.0)

        if not found:
            logger.warning("No suitable base found after %d searches", self._MAX_SEARCHES)
            return None

        # Detect deployment zone
        frame1 = self.adb.screenshot()
        time.sleep(0.2)
        frame2 = self.adb.screenshot()
        contour = self._zone_detector.detect(frame1, frame2)

        strategy_name = self.config.get("attack", {}).get("strategy", "surround")
        strategy = STRATEGIES.get(strategy_name, STRATEGIES["surround"])

        if contour is not None and len(contour) > 0:
            deploy_points = strategy.generate_points(contour, n=20)
            logger.info("Deployment zone detected: %d contour points, strategy=%s", len(contour), strategy_name)
        else:
            logger.warning("No deployment zone detected — using fallback ring")
            deploy_points = _fallback_ring()

        # Deploy troops
        army = self.read_army()
        attack_config = self.config.get("attack", {})
        delay_base = attack_config.get("delay_base_ms", 150)
        heroes_enabled = attack_config.get("heroes_enabled", True)
        spells_enabled = attack_config.get("spells_enabled", True)

        self._deploy_troops(deploy_points, army, delay_base)

        # Deploy heroes
        if heroes_enabled:
            self._deploy_heroes()

        # Deploy spells
        if spells_enabled:
            self._deploy_spells()

        # Wait for battle end
        battle_end = self._wait_for_battle_end()
        if not battle_end:
            logger.warning("Battle timeout — forcing end")

        # Tap end battle
        frame = self.adb.screenshot()
        detections = self.detector.detect(frame)
        end_btn = next((d for d in detections if d.label == "btn_end_battle"), None)
        if end_btn:
            self.adb.tap(*end_btn.center)
            time.sleep(2.0)

        # OCR loot gained
        frame = self.adb.screenshot()
        loot_gold = self.ocr.read_region(frame, "enemy_gold")
        loot_elixir = self.ocr.read_region(frame, "enemy_elixir")
        loot_dark = self.ocr.read_region(frame, "enemy_dark")

        result = AttackResult(
            strategy=strategy_name,
            enemy_gold=enemy_gold,
            enemy_elixir=enemy_elixir,
            enemy_dark=enemy_dark,
            loot_gold=loot_gold,
            loot_elixir=loot_elixir,
            loot_dark=loot_dark,
        )
        logger.info("Attack complete: loot gold=%s elixir=%s dark=%s", loot_gold, loot_elixir, loot_dark)

        # Tap continue / return home
        time.sleep(1.0)
        self.navigator.go_home()
        return result

    def _deploy_troops(
        self,
        deploy_points: list[tuple[float, float]],
        army: dict[str, int],
        delay_base: float,
    ) -> None:
        frame = self.adb.screenshot()
        detections = self.detector.detect(frame)
        troop_icons = [d for d in detections if d.label == "troop_icon"]

        for i, icon in enumerate(troop_icons):
            # Tap troop icon to select it
            self.adb.tap(*icon.center)
            time.sleep(_jitter(200) / 1000.0)

            # Tap each deployment point
            for rx, ry in deploy_points:
                jx = rx + random.uniform(-0.005, 0.005)
                jy = ry + random.uniform(-0.005, 0.005)
                self.adb.tap(max(0.0, min(1.0, jx)), max(0.0, min(1.0, jy)))
                time.sleep(_jitter(delay_base) / 1000.0)

    def _deploy_heroes(self) -> None:
        frame = self.adb.screenshot()
        detections = self.detector.detect(frame)
        heroes = [d for d in detections if d.label == "hero_icon"]
        for hero in heroes:
            self.adb.tap(*hero.center)
            time.sleep(_jitter(300) / 1000.0)
            # Tap center of base for hero
            self.adb.tap(
                0.5 + random.uniform(-0.03, 0.03),
                0.5 + random.uniform(-0.03, 0.03),
            )
            time.sleep(_jitter(200) / 1000.0)

    def _deploy_spells(self) -> None:
        frame = self.adb.screenshot()
        detections = self.detector.detect(frame)
        spells = [d for d in detections if d.label == "spell_icon"]
        for spell in spells:
            self.adb.tap(*spell.center)
            time.sleep(_jitter(200) / 1000.0)
            self.adb.tap(
                0.5 + random.uniform(-0.04, 0.04),
                0.5 + random.uniform(-0.04, 0.04),
            )
            time.sleep(_jitter(300) / 1000.0)

    def _wait_for_battle_end(self) -> bool:
        start = time.time()
        while time.time() - start < self._BATTLE_TIMEOUT:
            frame = self.adb.screenshot()
            detections = self.detector.detect(frame)
            if any(d.label == "btn_end_battle" for d in detections):
                return True
            timer = self.ocr.read_region(frame, "battle_timer")
            if timer is not None and timer == 0:
                return True
            time.sleep(self._POLL_INTERVAL)
        return False

    def read_army(self) -> dict[str, int]:
        frame = self.adb.screenshot()
        detections = self.detector.detect(frame)
        army: dict[str, int] = {}
        for d in detections:
            if d.label == "troop_icon":
                x1, y1, x2, y2 = d.bbox
                # OCR the count badge slightly below/right of icon
                count_bbox = (x2 - 0.03, y2 - 0.04, x2 + 0.01, y2 + 0.01)
                count = self.ocr.read_raw(frame, count_bbox)
                label = f"troop_{len(army)}"
                army[label] = count or 0
        return army

    def log_result(self, result: AttackResult, session_id: int) -> None:
        if self.db:
            self.db.log_attack(session_id, result)
