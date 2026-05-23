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
from core.vision import TemplateMatcher, DeploymentZoneDetector
from strategies import STRATEGIES

logger = logging.getLogger(__name__)

# Training not required — game handles troop availability automatically

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
        self._zone_detector = DeploymentZoneDetector()

    def run_attack_cycle(self) -> Optional[AttackResult]:
        if not self.navigator.go_to_matchmaking():
            logger.error("Failed to reach matchmaking")
            return None

        enemy_gold = enemy_elixir = enemy_dark = None
        found = True  # attack every base, no threshold filtering

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

        attack_config = self.config.get("attack", {})
        delay_base = attack_config.get("delay_base_ms", 150)
        heroes_enabled = attack_config.get("heroes_enabled", True)
        spells_enabled = attack_config.get("spells_enabled", True)

        self._deploy_troops(deploy_points, delay_base)

        if heroes_enabled:
            self._deploy_heroes()

        if spells_enabled:
            self._deploy_spells()

        battle_end = self._wait_for_battle_end()
        if not battle_end:
            logger.warning("Battle timeout — forcing end")

        frame = self.adb.screenshot()
        center = self.matcher.find(frame, "attack_screen_end_battle_button")
        if center:
            self.adb.tap(*center)
            time.sleep(2.0)

        loot_gold = loot_elixir = loot_dark = 0

        result = AttackResult(
            strategy=strategy_name,
            enemy_gold=enemy_gold,
            enemy_elixir=enemy_elixir,
            enemy_dark=enemy_dark,
            loot_gold=loot_gold,
            loot_elixir=loot_elixir,
            loot_dark=loot_dark,
        )
        logger.info("Attack complete: loot gold=0 elixir=0 dark=0 (OCR disabled)")

        time.sleep(1.0)
        self.navigator.go_home()
        return result

    def _deploy_troops(
        self,
        deploy_points: list[tuple[float, float]],
        delay_base: float,
    ) -> None:
        frame = self.adb.screenshot()
        bar_bbox = self.matcher.get_region_bbox(frame, "troops_siege_hero_spells_deployment_bar_area")
        if bar_bbox is None:
            logger.warning("Deployment bar region not found — skipping troop deployment")
            return
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = bar_bbox
        n_slots = 8
        for i in range(n_slots):
            slot_x = (x1 + (x2 - x1) * (i + 0.5) / n_slots) / w
            slot_y = ((y1 + y2) / 2) / h
            self.adb.tap(slot_x, slot_y)
            time.sleep(_jitter(200) / 1000.0)
            for rx, ry in deploy_points:
                jx = rx + random.uniform(-0.005, 0.005)
                jy = ry + random.uniform(-0.005, 0.005)
                self.adb.tap(max(0.0, min(1.0, jx)), max(0.0, min(1.0, jy)))
                time.sleep(_jitter(delay_base) / 1000.0)

    def _deploy_heroes(self) -> None:
        frame = self.adb.screenshot()
        bar_bbox = self.matcher.get_region_bbox(frame, "troops_siege_hero_spells_deployment_bar_area")
        if bar_bbox is None:
            return
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = bar_bbox
        # Heroes occupy the rightmost slots of the deployment bar
        for frac in (0.82, 0.89, 0.95):
            slot_x = (x1 + (x2 - x1) * frac) / w
            slot_y = ((y1 + y2) / 2) / h
            self.adb.tap(slot_x, slot_y)
            time.sleep(_jitter(300) / 1000.0)
            self.adb.tap(
                0.5 + random.uniform(-0.03, 0.03),
                0.5 + random.uniform(-0.03, 0.03),
            )
            time.sleep(_jitter(200) / 1000.0)

    def _deploy_spells(self) -> None:
        frame = self.adb.screenshot()
        bar_bbox = self.matcher.get_region_bbox(frame, "troops_siege_hero_spells_deployment_bar_area")
        if bar_bbox is None:
            return
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = bar_bbox
        # Spells occupy mid-right slots between troops and heroes
        for frac in (0.62, 0.70, 0.77):
            slot_x = (x1 + (x2 - x1) * frac) / w
            slot_y = ((y1 + y2) / 2) / h
            self.adb.tap(slot_x, slot_y)
            time.sleep(_jitter(200) / 1000.0)
            self.adb.tap(
                0.5 + random.uniform(-0.04, 0.04),
                0.5 + random.uniform(-0.04, 0.04),
            )
            time.sleep(_jitter(300) / 1000.0)

    def _wait_for_battle_end(self) -> bool:
        start = time.time()
        while time.time() - start < 180:
            frame = self.adb.screenshot()
            if self.matcher.is_visible(frame, "attack_screen_end_battle_button"):
                return True
            time.sleep(self._POLL_INTERVAL)
        return True  # fixed 3-minute timeout

    def read_army(self) -> dict[str, int]:
        return {}

    def log_result(self, result: AttackResult, session_id: int) -> None:
        if self.db:
            self.db.log_attack(session_id, result)
