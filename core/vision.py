"""
Computer vision: template matching and deploy-zone detection.

Uses OpenCV matchTemplate for button detection and HSV filtering
for the red deploy border.
"""

import cv2
import numpy as np
from pathlib import Path

from .config import AppConfig
from .screen import GameScreen


class Vision:
    """Template matching and visual state detection."""

    def __init__(self, screen: GameScreen, config: AppConfig):
        self.screen = screen
        self.config = config

    # ── Template matching ─────────────────────────────────────────────────

    def match_slot(self, slot: dict) -> tuple[bool, float, tuple[int, int]]:
        """
        Match a slot's template against the current game screen.

        Returns
        -------
        (found, confidence, (abs_x, abs_y))
            found:      True if confidence >= threshold
            confidence: raw matchTemplate score
            abs_x/y:    absolute screen coords of the match centre
        """
        tpl_path = slot.get("template", "")
        if not tpl_path or not Path(tpl_path).exists():
            return False, 0.0, (0, 0)

        img, ox, oy = self.screen.grab_game()
        tmpl = cv2.imread(tpl_path)
        if tmpl is None:
            return False, 0.0, (0, 0)

        res = cv2.matchTemplate(img, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        threshold = self.config.settings.get("match_threshold", 0.8)

        if max_val >= threshold:
            th, tw = tmpl.shape[:2]
            return True, max_val, (max_loc[0] + tw // 2 + ox,
                                   max_loc[1] + th // 2 + oy)
        return False, max_val, (0, 0)

    def detect_on_screen(self, slot: dict) -> bool:
        """Return True if the slot's template is currently visible."""
        if slot.get("mode") != "IMAGE":
            return False
        found, _, _ = self.match_slot(slot)
        return found

    # ── Deploy-zone detection ─────────────────────────────────────────────

    def detect_deploy_zone(self, n_points: int = 12) -> list[list[int]]:
        """
        Detect the pulsing red deploy border on the attack screen.

        Filters out small solid red UI elements (surrender button etc.)
        by requiring the contour to span >=15 % of the image in both axes.

        Returns a list of [abs_x, abs_y] deploy positions.
        """
        img, ox, oy = self.screen.grab_game()
        h_img, w_img = img.shape[:2]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Red wraps in HSV — capture both ends of the hue wheel
        m1   = cv2.inRange(hsv, np.array([0,   120, 80]), np.array([12,  255, 255]))
        m2   = cv2.inRange(hsv, np.array([165, 120, 80]), np.array([180, 255, 255]))
        mask = cv2.bitwise_or(m1, m2)

        # Close gaps in the pulsing border, then dilate to connect fragments
        k    = np.ones((7, 7), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,  k)
        mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, k)

        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

        # Keep only contours that span a significant portion of the screen
        valid = []
        for c in cnts:
            area = cv2.contourArea(c)
            if area < 1000:
                continue
            _, _, bw, bh = cv2.boundingRect(c)
            if bw < w_img * 0.15 or bh < h_img * 0.15:
                continue
            valid.append((area, c))

        if not valid:
            return []

        cnt = max(valid, key=lambda t: t[0])[1]
        M   = cv2.moments(cnt)
        if M["m00"] == 0:
            return []
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])

        # Sample points along the contour, offset 25 px toward centroid
        step = max(1, len(cnt) // n_points)
        pts: list[list[int]] = []
        for i in range(0, len(cnt), step):
            px, py = int(cnt[i][0][0]), int(cnt[i][0][1])
            dx, dy = cx - px, cy - py
            dist   = max(1.0, (dx**2 + dy**2) ** 0.5)
            pts.append([int(px + dx / dist * 25) + ox,
                        int(py + dy / dist * 25) + oy])
            if len(pts) >= n_points:
                break
        return pts

    # ── Test preview ──────────────────────────────────────────────────────

    def test_slot_preview(self, slot: dict) -> tuple[np.ndarray, str]:
        """
        Run template match / coord check and return:
          (annotated_bgr_image, human-readable result string)
        """
        img, ox, oy = self.screen.grab_game()

        if slot.get("mode") == "IMAGE":
            tpl = slot.get("template", "")
            if not tpl or not Path(tpl).exists():
                return img, "No template captured"
            tmpl = cv2.imread(tpl)
            if tmpl is None:
                return img, "Template file unreadable"
            res = cv2.matchTemplate(img, tmpl, cv2.TM_CCOEFF_NORMED)
            _, mv, _, ml = cv2.minMaxLoc(res)
            th, tw = tmpl.shape[:2]
            thr = self.config.settings.get("match_threshold", 0.8)
            if mv >= thr:
                cv2.rectangle(img, ml, (ml[0]+tw, ml[1]+th), (0,230,118), 3)
                cv2.putText(img, f"FOUND {mv:.2f}", (ml[0], max(ml[1]-8, 14)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,230,118), 2)
                return img, f"FOUND  conf={mv:.3f}  abs=({ml[0]+ox},{ml[1]+oy})"
            else:
                cv2.putText(img, f"NOT FOUND  best={mv:.2f}", (20, 48),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (60,60,255), 2)
                return img, f"NOT FOUND  best={mv:.3f}"
        else:
            coord = slot.get("coord")
            if not coord:
                return img, "No position set"
            x, y   = int(coord[0]), int(coord[1])
            ix, iy = x - ox, y - oy
            h_img, w_img = img.shape[:2]
            if 0 <= ix < w_img and 0 <= iy < h_img:
                cv2.circle(img, (ix, iy), 22, (64,180,255), 3)
                cv2.circle(img, (ix, iy),  6, (64,180,255), -1)
                cv2.putText(img, f"({x},{y})", (ix+28, iy+8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.85, (64,180,255), 2)
            return img, f"COORD ({x},{y})"
