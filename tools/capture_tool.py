"""
Standalone screenshot collector for YOLO training data.
Press F9 to save a screenshot. Ctrl+C to exit.
"""
import sys
import tomllib
from datetime import datetime
from pathlib import Path

# Always resolve paths relative to the project root (one level up from tools/)
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import keyboard

from core.adb import ADBInterface

OUTPUT_DIR = PROJECT_ROOT / "training_data" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_count = 0


def load_adb_config() -> dict:
    config_path = PROJECT_ROOT / "config.toml"
    try:
        with open(config_path, "rb") as f:
            return tomllib.load(f).get("adb", {})
    except FileNotFoundError:
        print(f"Warning: config.toml not found at {config_path} — using defaults")
        return {}


def save_screenshot(adb: ADBInterface) -> None:
    global _count
    try:
        frame = adb.screenshot()
        from PIL import Image
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
    print(f"Output directory: {OUTPUT_DIR}")
    print("Press F9 to capture. Ctrl+C to exit.\n")

    adb_cfg = load_adb_config()
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

    keyboard.add_hotkey("F9", lambda: save_screenshot(adb))
    print("Hotkey registered. Ready.")

    try:
        keyboard.wait()
    except KeyboardInterrupt:
        print(f"\nCapture session ended. Total screenshots: {_count}")


if __name__ == "__main__":
    main()
