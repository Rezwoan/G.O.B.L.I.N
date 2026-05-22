import logging
import os
import random
import subprocess
import tempfile
import time

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

_ADB_TIMEOUT = 10


def _jitter(base_ms: float) -> float:
    """Return base_ms ± 30% random jitter."""
    factor = 1.0 + random.uniform(-0.3, 0.3)
    return base_ms * factor


class ADBInterface:
    def __init__(self, host: str = "127.0.0.1", port: int = 5555, adb_path: str = "adb") -> None:
        self.host = host
        self.port = port
        self._adb = adb_path
        self._device = f"{host}:{port}"
        self._resolution: tuple[int, int] | None = None

    def _run(self, args: list[str], input_data: bytes = None) -> subprocess.CompletedProcess:
        cmd = [self._adb, "-s", self._device] + args
        result = subprocess.run(
            cmd,
            capture_output=True,
            input=input_data,
            timeout=_ADB_TIMEOUT,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace")
            logger.warning("ADB command failed: %s\nstderr: %s", " ".join(cmd), stderr)
            # Auto-reconnect on offline errors, then retry once
            if "offline" in stderr or "not found" in stderr or "no devices" in stderr.lower():
                logger.info("Device offline — attempting reconnect")
                try:
                    self.connect()
                    result = subprocess.run(cmd, capture_output=True, input=input_data, timeout=_ADB_TIMEOUT)
                except Exception as exc:
                    logger.error("Reconnect failed: %s", exc)
        return result

    def connect(self) -> None:
        result = subprocess.run(
            [self._adb, "connect", self._device],
            capture_output=True,
            timeout=_ADB_TIMEOUT,
        )
        output = result.stdout.decode(errors="replace").strip()
        logger.info("adb connect: %s", output)
        if "connected" not in output.lower() and "already" not in output.lower():
            raise ConnectionError(f"Failed to connect to ADB device {self._device}: {output}")

    def is_connected(self) -> bool:
        try:
            result = subprocess.run(
                [self._adb, "-s", self._device, "get-state"],
                capture_output=True,
                timeout=_ADB_TIMEOUT,
            )
            state = result.stdout.decode(errors="replace").strip()
            if state == "device":
                return True
            logger.warning("ADB device state: %s — attempting reconnect", state)
            self.connect()
            return True
        except Exception as exc:
            logger.error("ADB is_connected check failed: %s", exc)
            return False

    def get_resolution(self) -> tuple[int, int]:
        if self._resolution:
            return self._resolution
        result = self._run(["shell", "wm", "size"])
        output = result.stdout.decode(errors="replace").strip()
        # Expected: "Physical size: 1920x1080"
        try:
            size_part = output.split(":")[-1].strip()
            w, h = size_part.split("x")
            self._resolution = (int(w), int(h))
            return self._resolution
        except Exception as exc:
            logger.error("Failed to parse resolution from '%s': %s", output, exc)
            raise RuntimeError(f"Cannot determine resolution: {output}") from exc

    def screenshot(self) -> np.ndarray:
        # Save PNG on device then pull — more reliable than exec-out on Windows
        device_path = "/sdcard/goblin_screen.png"
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(tmp_fd)
        try:
            result = self._run(["shell", "screencap", "-p", device_path])
            if result.returncode != 0:
                raise RuntimeError(f"screencap on device failed: {result.stderr.decode(errors='replace').strip()}")
            pull = subprocess.run(
                [self._adb, "-s", self._device, "pull", device_path, tmp_path],
                capture_output=True,
                timeout=30,
            )
            if pull.returncode != 0:
                raise RuntimeError(f"adb pull failed: {pull.stderr.decode(errors='replace').strip()}")
            image = Image.open(tmp_path).convert("RGB")
            arr = np.array(image)
            return arr[:, :, ::-1].copy()  # RGB → BGR
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def tap(self, rx: float, ry: float) -> None:
        w, h = self.get_resolution()
        x = int(rx * w)
        y = int(ry * h)
        self._run(["shell", "input", "tap", str(x), str(y)])
        delay = _jitter(150)
        time.sleep(delay / 1000.0)

    def swipe(
        self,
        rx1: float,
        ry1: float,
        rx2: float,
        ry2: float,
        duration_ms: int = 300,
    ) -> None:
        w, h = self.get_resolution()
        x1, y1 = int(rx1 * w), int(ry1 * h)
        x2, y2 = int(rx2 * w), int(ry2 * h)
        self._run(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)])
        delay = _jitter(100)
        time.sleep(delay / 1000.0)

    def long_press(self, rx: float, ry: float, duration_ms: int = 800) -> None:
        self.swipe(rx, ry, rx, ry, duration_ms=duration_ms)

    def pinch_in(self, cx: float, cy: float, spread: float = 0.3) -> None:
        """Two-finger pinch (zoom in / max zoom)."""
        w, h = self.get_resolution()
        cx_abs, cy_abs = int(cx * w), int(cy * h)
        x1_start = int((cx - spread) * w)
        x2_start = int((cx + spread) * w)
        y_abs = cy_abs
        # Simultaneous two-pointer swipe — use sendevent-based multitouch via two slots
        # Fallback: sequential swipes that approximate a pinch
        proc1 = subprocess.Popen(
            [self._adb, "-s", self._device, "shell", "input", "swipe",
             str(x1_start), str(y_abs), str(cx_abs), str(y_abs), "400"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        proc2 = subprocess.Popen(
            [self._adb, "-s", self._device, "shell", "input", "swipe",
             str(x2_start), str(y_abs), str(cx_abs), str(y_abs), "400"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        proc1.wait(timeout=5)
        proc2.wait(timeout=5)
        time.sleep(0.5)

    def pinch_out(self, cx: float, cy: float, spread: float = 0.3) -> None:
        """Two-finger spread (zoom out)."""
        w, h = self.get_resolution()
        cx_abs, cy_abs = int(cx * w), int(cy * h)
        x1_end = int((cx - spread) * w)
        x2_end = int((cx + spread) * w)
        y_abs = cy_abs
        proc1 = subprocess.Popen(
            [self._adb, "-s", self._device, "shell", "input", "swipe",
             str(cx_abs), str(y_abs), str(x1_end), str(y_abs), "400"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        proc2 = subprocess.Popen(
            [self._adb, "-s", self._device, "shell", "input", "swipe",
             str(cx_abs), str(y_abs), str(x2_end), str(y_abs), "400"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        proc1.wait(timeout=5)
        proc2.wait(timeout=5)
        time.sleep(0.5)
