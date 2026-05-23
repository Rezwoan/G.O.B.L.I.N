"""
Live GOBLIN vision overlay — shows template match results on live ADB frames.

Controls:
  Q / Escape  quit
  F           toggle not-found (dim red) rectangles
  S           save current annotated frame to tools/test_output.png
"""
import sys
import time
import threading
import tomllib
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.adb import ADBInterface
from core.vision import TemplateMatcher

WINDOW_TITLE = "GOBLIN Vision Test — Q to quit"
OUTPUT_PATH = Path(__file__).parent / "test_output.png"
CAPTURE_INTERVAL = 1.5  # seconds between ADB screencaps


def load_config() -> dict:
    path = PROJECT_ROOT / "config.toml"
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        print(f"config.toml not found at {path} — using defaults")
        return {}


def get_monitor_size() -> tuple[int, int]:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    except Exception:
        return 1920, 1080


class FrameStore:
    """Shared state between screencap thread and display loop."""

    def __init__(self) -> None:
        self.frame: Optional[np.ndarray] = None
        self.matches: dict[str, Optional[tuple[float, float]]] = {}
        self.state_str: str = "unknown"
        self.timestamp: float = 0.0
        self._lock = threading.Lock()

    def update(
        self,
        frame: np.ndarray,
        matches: dict[str, Optional[tuple[float, float]]],
        state_str: str,
    ) -> None:
        with self._lock:
            self.frame = frame
            self.matches = matches
            self.state_str = state_str
            self.timestamp = time.time()

    def snapshot(self) -> tuple[Optional[np.ndarray], dict, str, float]:
        with self._lock:
            return self.frame, dict(self.matches), self.state_str, self.timestamp


def screencap_loop(
    adb: ADBInterface,
    matcher: TemplateMatcher,
    store: FrameStore,
    stop: threading.Event,
) -> None:
    while not stop.is_set():
        try:
            frame = adb.screenshot()
            matches = {name: matcher.find(frame, name) for name in matcher._all_regions}
            state_str = matcher.detect_state(frame)
            store.update(frame, matches, state_str)
        except Exception as exc:
            print(f"Screencap/match error: {exc}", flush=True)
        stop.wait(CAPTURE_INTERVAL)


def annotate(
    frame: np.ndarray,
    matcher: TemplateMatcher,
    matches: dict[str, Optional[tuple[float, float]]],
    show_not_found: bool,
    state_str: str,
    fps: float,
    stale_secs: float,
) -> np.ndarray:
    out = frame.copy()
    h, w = out.shape[:2]

    for name, region in matcher._all_regions.items():
        rx1, ry1, rx2, ry2 = region
        rw = rx2 - rx1
        rh = ry2 - ry1
        center = matches.get(name)

        if center is not None:
            cx, cy = center
            bx1 = int((cx - rw / 2) * w)
            by1 = int((cy - rh / 2) * h)
            bx2 = int((cx + rw / 2) * w)
            by2 = int((cy + rh / 2) * h)
            # Clamp to frame bounds
            bx1, bx2 = max(0, bx1), min(w - 1, bx2)
            by1, by2 = max(0, by1), min(h - 1, by2)
            cv2.rectangle(out, (bx1, by1), (bx2, by2), (0, 255, 0), 2)
            label_y = max(by1 - 4, 10)
            cv2.putText(
                out, name, (bx1, label_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA,
            )
        elif show_not_found:
            ex1 = int(rx1 * w)
            ey1 = int(ry1 * h)
            ex2 = int(rx2 * w)
            ey2 = int(ry2 * h)
            # Skip if region is entirely outside frame
            if ex1 >= w or ey1 >= h or ex2 <= 0 or ey2 <= 0:
                continue
            cv2.rectangle(out, (ex1, ey1), (ex2, ey2), (0, 0, 150), 1)

    # State — large yellow, top-left
    cv2.putText(
        out, f"State: {state_str}", (10, 36),
        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2, cv2.LINE_AA,
    )

    # Stale indicator — orange, below state
    if stale_secs > 3.0:
        cv2.putText(
            out, f"STALE  {stale_secs:.0f}s", (10, 70),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 120, 255), 2, cv2.LINE_AA,
        )

    # Bottom-left: FPS + timestamp
    ts = datetime.now().strftime("%H:%M:%S")
    bottom_text = f"FPS: {fps:.1f}   last capture: {ts}"
    cv2.putText(
        out, bottom_text, (10, h - 10),
        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA,
    )

    return out


def scale_to_fit(frame: np.ndarray, max_w: int, max_h: int) -> np.ndarray:
    fh, fw = frame.shape[:2]
    scale = min(max_w / fw, max_h / fh, 1.0)
    if scale >= 1.0:
        return frame
    return cv2.resize(frame, (int(fw * scale), int(fh * scale)), interpolation=cv2.INTER_LINEAR)


def main() -> None:
    config = load_config()
    adb_cfg = config.get("adb", {})
    adb = ADBInterface(
        host=adb_cfg.get("host", "127.0.0.1"),
        port=adb_cfg.get("port", 5555),
        adb_path=adb_cfg.get("path", "adb"),
    )
    try:
        adb.connect()
        print(f"ADB connected to {adb.host}:{adb.port}")
    except ConnectionError as exc:
        print(f"ADB connection failed: {exc}")
        sys.exit(1)

    matcher = TemplateMatcher(str(PROJECT_ROOT / "templates"))
    total = len(matcher._all_regions)
    loaded = len(matcher.templates)
    print(f"Templates: {loaded}/{total} have PNG images ({total - loaded} region-only, no matching yet)")
    print("Controls: Q/Esc=quit  F=toggle not-found  S=save frame")

    store = FrameStore()
    stop_event = threading.Event()
    thread = threading.Thread(
        target=screencap_loop,
        args=(adb, matcher, store, stop_event),
        daemon=True,
    )
    thread.start()

    print("Waiting for first frame...", end="", flush=True)
    deadline = time.time() + 15.0
    while store.snapshot()[0] is None:
        if time.time() > deadline:
            print("\nTimeout waiting for first frame — is the device reachable?")
            stop_event.set()
            sys.exit(1)
        time.sleep(0.1)
        print(".", end="", flush=True)
    print(" ready\n")

    monitor_w, monitor_h = get_monitor_size()
    max_w = int(monitor_w * 0.9)
    max_h = int(monitor_h * 0.9)

    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)

    show_not_found = True
    fps_times: deque[float] = deque(maxlen=30)
    last_annotated: Optional[np.ndarray] = None

    while True:
        t0 = time.time()
        frame, matches, state_str, frame_ts = store.snapshot()

        if frame is not None:
            stale = time.time() - frame_ts
            fps_times.append(t0)
            fps = (
                (len(fps_times) - 1) / (fps_times[-1] - fps_times[0] + 1e-6)
                if len(fps_times) > 1 else 0.0
            )

            annotated = annotate(frame, matcher, matches, show_not_found, state_str, fps, stale)
            last_annotated = annotated
            cv2.imshow(WINDOW_TITLE, scale_to_fit(annotated, max_w, max_h))

        key = cv2.waitKey(33) & 0xFF  # ~30 fps
        if key in (ord("q"), ord("Q"), 27):
            break
        elif key in (ord("f"), ord("F")):
            show_not_found = not show_not_found
            state = "ON" if show_not_found else "OFF"
            print(f"Not-found regions: {state}")
        elif key in (ord("s"), ord("S")):
            if last_annotated is not None:
                cv2.imwrite(str(OUTPUT_PATH), last_annotated)
                print(f"Saved: {OUTPUT_PATH}")

    stop_event.set()
    cv2.destroyAllWindows()
    print("Done.")


if __name__ == "__main__":
    main()
