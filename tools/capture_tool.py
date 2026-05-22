"""
Standalone screenshot collector for YOLO training data.
Press F9 to save a screenshot. Ctrl+C to exit.
"""
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import keyboard

from core.adb import ADBInterface

OUTPUT_DIR = Path("training_data/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_count = 0


def save_screenshot(adb: ADBInterface) -> None:
    global _count
    try:
        frame = adb.screenshot()
        from PIL import Image
        import numpy as np
        rgb = frame[:, :, ::-1]
        img = Image.fromarray(rgb.astype("uint8"))
        filename = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".png"
        path = OUTPUT_DIR / filename
        img.save(str(path))
        _count += 1
        print(f"[{_count}] Saved: {path}")
    except Exception as exc:
        print(f"Error saving screenshot: {exc}")


def main() -> None:
    print("G.O.B.L.I.N Capture Tool")
    print(f"Output directory: {OUTPUT_DIR.resolve()}")
    print("Press F9 to capture. Ctrl+C to exit.\n")

    adb = ADBInterface()
    try:
        adb.connect()
        print("ADB connected.")
    except ConnectionError as exc:
        print(f"ADB connection failed: {exc}")
        sys.exit(1)

    keyboard.add_hotkey("F9", lambda: save_screenshot(adb))
    print("Hotkey registered. Ready.")

    try:
        keyboard.wait()
    except KeyboardInterrupt:
        print(f"\nCapture session ended. Total screenshots: {_count}")


if __name__ == "__main__":
    main()
