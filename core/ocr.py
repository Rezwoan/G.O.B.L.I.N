import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# All regions as relative (x1, y1, x2, y2) — calibrate on actual screenshots.
# Values here are reasonable starting points for a 1920x1080 layout.
OCR_REGIONS: dict[str, tuple[float, float, float, float]] = {
    "home_gold":      (0.040, 0.035, 0.180, 0.065),  # Gold counter top-left
    "home_elixir":    (0.040, 0.065, 0.180, 0.095),  # Elixir counter
    "home_dark":      (0.040, 0.095, 0.180, 0.125),  # Dark elixir counter
    "enemy_gold":     (0.040, 0.035, 0.200, 0.065),  # Enemy base gold in search screen
    "enemy_elixir":   (0.040, 0.065, 0.200, 0.095),  # Enemy base elixir
    "enemy_dark":     (0.040, 0.095, 0.200, 0.125),  # Enemy dark elixir
    "upgrade_cost":   (0.350, 0.600, 0.650, 0.640),  # Cost in upgrade confirmation dialog
    "upgrade_timer":  (0.350, 0.640, 0.650, 0.680),  # Timer in upgrade confirmation
    "troop_count":    (0.000, 0.000, 0.050, 0.050),  # Per-icon; overridden at runtime
    "builder_count":  (0.870, 0.030, 0.940, 0.070),  # Builder count badge
    "battle_timer":   (0.440, 0.020, 0.560, 0.055),  # Battle countdown timer
}

_TESS_CONFIG = "--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789,"


class OCRReader:
    def __init__(self, tesseract_cmd: Optional[str] = None) -> None:
        try:
            import pytesseract
            self._pytesseract = pytesseract
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        except ImportError:
            logger.error("pytesseract not installed — OCR will not work.")
            self._pytesseract = None

    def read_region(self, frame: np.ndarray, region_id: str) -> Optional[int]:
        if region_id not in OCR_REGIONS:
            logger.warning("Unknown OCR region: %s", region_id)
            return None
        return self.read_raw(frame, OCR_REGIONS[region_id])

    def read_raw(self, frame: np.ndarray, bbox_rel: tuple[float, float, float, float]) -> Optional[int]:
        if self._pytesseract is None:
            return None
        try:
            crop = self._crop(frame, bbox_rel)
            processed = self._preprocess(crop)
            text = self._pytesseract.image_to_string(processed, config=_TESS_CONFIG)
            return self._parse(text)
        except Exception as exc:
            logger.debug("OCR read_raw failed for bbox %s: %s", bbox_rel, exc)
            return None

    def _crop(self, frame: np.ndarray, bbox_rel: tuple[float, float, float, float]) -> np.ndarray:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = bbox_rel
        x1p, y1p = max(0, int(x1 * w)), max(0, int(y1 * h))
        x2p, y2p = min(w, int(x2 * w)), min(h, int(y2 * h))
        return frame[y1p:y2p, x1p:x2p]

    def _preprocess(self, crop: np.ndarray) -> np.ndarray:
        # Scale 3x
        scaled = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        # Grayscale
        gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY) if len(scaled.shape) == 3 else scaled
        # CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        # Adaptive threshold
        thresh = cv2.adaptiveThreshold(
            enhanced, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=11,
            C=2,
        )
        # Invert if background is mostly dark
        if np.mean(thresh) < 128:
            thresh = cv2.bitwise_not(thresh)
        return thresh

    def _parse(self, text: str) -> Optional[int]:
        cleaned = text.strip().replace(",", "").replace(" ", "")
        if not cleaned:
            return None
        try:
            return int(cleaned)
        except ValueError:
            logger.debug("OCR parse failed for text: %r", text)
            return None
