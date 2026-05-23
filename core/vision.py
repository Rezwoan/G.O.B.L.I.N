import logging
import tomllib
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class TemplateMatcher:
    def __init__(self, templates_dir: str = "templates") -> None:
        self.templates_dir = Path(templates_dir)
        self.threshold = 0.8
        self._all_regions: dict[str, tuple[float, float, float, float]] = {}
        self.templates: dict[str, dict] = {}
        self._load_templates()

    def _load_templates(self) -> None:
        toml_path = self.templates_dir / "regions.toml"
        try:
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
        except FileNotFoundError:
            logger.error("regions.toml not found at %s", toml_path)
            return
        except Exception as exc:
            logger.error("Failed to load regions.toml: %s", exc)
            return

        for name, rd in data.get("regions", {}).items():
            region = (float(rd["x1"]), float(rd["y1"]), float(rd["x2"]), float(rd["y2"]))
            self._all_regions[name] = region

            png_path = self.templates_dir / f"{name}.png"
            if not png_path.exists():
                logger.warning("Template PNG missing for '%s' — skipping", name)
                continue
            img = cv2.imread(str(png_path))
            if img is None:
                logger.warning("Failed to load template image '%s' — skipping", png_path)
                continue
            self.templates[name] = {"img": img, "region": region}

        logger.info(
            "Loaded %d/%d templates from %s",
            len(self.templates), len(self._all_regions), toml_path,
        )

    def find(self, frame: np.ndarray, name: str) -> tuple[float, float] | None:
        entry = self.templates.get(name)
        if entry is None:
            return None
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = entry["region"]
        region_w = (x2 - x1) * w
        region_h = (y2 - y1) * h
        if region_w < 1 or region_h < 1:
            return None
        scaled = cv2.resize(entry["img"], (int(region_w), int(region_h)))
        result = cv2.matchTemplate(frame, scaled, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val >= self.threshold:
            cx = (max_loc[0] + region_w / 2) / w
            cy = (max_loc[1] + region_h / 2) / h
            return (float(cx), float(cy))
        return None

    def find_all(
        self, frame: np.ndarray, name: str, threshold: float | None = None
    ) -> list[tuple[float, float]]:
        entry = self.templates.get(name)
        if entry is None:
            return []
        thresh = threshold if threshold is not None else self.threshold
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = entry["region"]
        region_w = (x2 - x1) * w
        region_h = (y2 - y1) * h
        if region_w < 1 or region_h < 1:
            return []
        scaled = cv2.resize(entry["img"], (int(region_w), int(region_h)))
        result = cv2.matchTemplate(frame, scaled, cv2.TM_CCOEFF_NORMED)
        locs = np.where(result >= thresh)
        centers = []
        for pt_y, pt_x in zip(*locs):
            cx = (pt_x + region_w / 2) / w
            cy = (pt_y + region_h / 2) / h
            centers.append((float(cx), float(cy)))
        return centers

    def is_visible(self, frame: np.ndarray, name: str) -> bool:
        return self.find(frame, name) is not None

    def detect_state(self, frame: np.ndarray) -> str:
        checks = [
            ("loading",         "supercell_loading_screen"),
            ("connection_lost", "connection_lost_warning_popup_area"),
            ("post_battle",     "attack_end_return_home_button"),
            ("attacking",       "attack_screen_surrender_button"),
            ("searching",       "attack_screen_next_button"),
            ("attack_menu",     "multiplayer_find_a_match_button"),
            ("upgrading",       "home_screen_upgrade_window_area"),
            ("home",            "home_screen_attack_button"),
        ]
        for state_str, template_name in checks:
            if self.is_visible(frame, template_name):
                return state_str
        return "unknown"

    def get_region_bbox(self, frame: np.ndarray, name: str) -> tuple[int, int, int, int] | None:
        region = self._all_regions.get(name)
        if region is None:
            return None
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = region
        return (int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h))


class DeploymentZoneDetector:
    _LOWER_RED1 = np.array([0, 120, 70])
    _UPPER_RED1 = np.array([10, 255, 255])
    _LOWER_RED2 = np.array([170, 120, 70])
    _UPPER_RED2 = np.array([180, 255, 255])

    def detect(self, frame1: np.ndarray, frame2: np.ndarray) -> np.ndarray | None:
        """
        Detect the red deployment boundary using HSV masking + frame differencing.
        Returns the largest contour as a numpy array of relative-coordinate points,
        or None if the boundary is not found.
        """
        h, w = frame1.shape[:2]
        total_area = h * w

        mask1 = self._red_mask(frame1)
        mask2 = self._red_mask(frame2)

        diff = cv2.absdiff(mask1, mask2)
        _, diff_bin = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)

        contours, _ = cv2.findContours(diff_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        if area < 0.15 * total_area:
            logger.debug("Largest red contour area %.1f%% < 15%% threshold", 100 * area / total_area)
            return None

        pts = largest.reshape(-1, 2).astype(float)
        pts[:, 0] /= w
        pts[:, 1] /= h
        return pts

    def _red_mask(self, frame: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask1 = cv2.inRange(hsv, self._LOWER_RED1, self._UPPER_RED1)
        mask2 = cv2.inRange(hsv, self._LOWER_RED2, self._UPPER_RED2)
        return cv2.bitwise_or(mask1, mask2)
