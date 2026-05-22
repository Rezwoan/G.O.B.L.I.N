import logging
import os
from dataclasses import dataclass, field

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2 relative 0–1

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


class YOLODetector:
    def __init__(self, model_path: str, confidence: float = 0.6) -> None:
        self.model_path = model_path
        self.confidence = confidence
        self._model = None
        self._load_model()

    def _load_model(self) -> None:
        if not os.path.exists(self.model_path):
            logger.warning(
                "YOLO model not found at '%s' — detector will return empty results until model is trained.",
                self.model_path,
            )
            return
        try:
            from ultralytics import YOLO
            self._model = YOLO(self.model_path)
            logger.info("Loaded YOLO model from %s", self.model_path)
        except Exception as exc:
            logger.error("Failed to load YOLO model: %s", exc)

    def detect(self, frame: np.ndarray) -> list[Detection]:
        if self._model is None:
            return []
        try:
            h, w = frame.shape[:2]
            results = self._model(frame, conf=self.confidence, verbose=False)
            detections: list[Detection] = []
            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    label = result.names[int(box.cls[0])]
                    conf = float(box.conf[0])
                    detections.append(Detection(
                        label=label,
                        confidence=conf,
                        bbox=(x1 / w, y1 / h, x2 / w, y2 / h),
                    ))
            return detections
        except Exception as exc:
            logger.error("YOLO inference failed: %s", exc)
            return []


class DeploymentZoneDetector:
    # HSV ranges for red
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

        # Convert to relative coordinates
        pts = largest.reshape(-1, 2).astype(float)
        pts[:, 0] /= w
        pts[:, 1] /= h
        return pts

    def _red_mask(self, frame: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask1 = cv2.inRange(hsv, self._LOWER_RED1, self._UPPER_RED1)
        mask2 = cv2.inRange(hsv, self._LOWER_RED2, self._UPPER_RED2)
        return cv2.bitwise_or(mask1, mask2)
