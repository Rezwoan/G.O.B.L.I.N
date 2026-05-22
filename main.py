import logging
import sys
import threading
import tomllib
from pathlib import Path

# ── Logging setup (before any imports that use logging) ──────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────
CONFIG_PATH = "config.toml"
PRIORITIES_PATH = "priorities.toml"
TASKS_PATH = "tasks.toml"
ARMIES_PATH = "armies.toml"
DB_PATH = "data/autoloot.db"


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        logger.warning("config.toml not found — using defaults")
        return {}


def main() -> None:
    config = load_config()

    # ── Database ─────────────────────────────────────────────────────────────
    from data.db import Database
    db = Database(DB_PATH)
    db.init_schema()

    # ── ADB ──────────────────────────────────────────────────────────────────
    from core.adb import ADBInterface
    adb_cfg = config.get("adb", {})
    adb = ADBInterface(
        host=adb_cfg.get("host", "127.0.0.1"),
        port=adb_cfg.get("port", 5555),
        adb_path=adb_cfg.get("path", "adb"),
    )
    try:
        adb.connect()
    except ConnectionError as exc:
        logger.error("ADB connection failed: %s — continuing without ADB", exc)

    # ── Vision ───────────────────────────────────────────────────────────────
    from core.vision import YOLODetector
    yolo_cfg = config.get("yolo", {})
    detector = YOLODetector(
        model_path=yolo_cfg.get("model_path", "models/coc_yolo.pt"),
        confidence=yolo_cfg.get("confidence", 0.6),
    )

    # ── OCR ──────────────────────────────────────────────────────────────────
    from core.ocr import OCRReader
    tess_cfg = config.get("tesseract", {})
    ocr = OCRReader(tesseract_cmd=tess_cfg.get("cmd") or None)

    # ── State Machine ────────────────────────────────────────────────────────
    from core.state_machine import StateMachine
    state_machine = StateMachine(detector)

    # ── Navigator ────────────────────────────────────────────────────────────
    from core.navigator import Navigator
    navigator = Navigator(adb, state_machine, detector)

    # ── Notifications ────────────────────────────────────────────────────────
    from notify import Notifier
    from notify.discord import DiscordNotifier
    from notify.telegram import TelegramNotifier

    notify_cfg = config.get("notify", {})
    discord = DiscordNotifier(notify_cfg.get("discord_webhook", "")) if notify_cfg.get("discord_webhook") else None
    telegram = None
    tg_token = notify_cfg.get("telegram_token", "")
    tg_chat = notify_cfg.get("telegram_chat_id", "")
    if tg_token and tg_chat:
        telegram = TelegramNotifier(tg_token, tg_chat)

    notifier = Notifier(discord=discord, telegram=telegram)

    # ── Engines ──────────────────────────────────────────────────────────────
    from engines.attack_engine import AttackEngine
    from engines.upgrade_engine import UpgradeEngine
    from engines.collect_engine import CollectEngine

    attack_engine = AttackEngine(adb, navigator, detector, ocr, state_machine, config, notifier, db)
    upgrade_engine = UpgradeEngine(adb, navigator, detector, ocr, state_machine, config, notifier, db)
    collect_engine = CollectEngine(adb, detector, state_machine)

    # ── Task Engine ──────────────────────────────────────────────────────────
    from engines.task_engine import TaskEngine
    task_engine = TaskEngine(
        adb, navigator, attack_engine, upgrade_engine, collect_engine, ocr, notifier, db
    )
    task_engine.load_queue(TASKS_PATH)

    # ── Telegram polling ─────────────────────────────────────────────────────
    if telegram:
        telegram.on_status(lambda: notifier.notify("TASK_STARTED", {"status": task_engine.running}))
        telegram.on_stop(task_engine.stop)
        telegram.start_polling()

    # ── GUI ──────────────────────────────────────────────────────────────────
    from gui.app import App
    from gui.log_view import GUILogHandler

    app = App(
        adb=adb,
        task_engine=task_engine,
        state_machine=state_machine,
        config=config,
        config_path=CONFIG_PATH,
        priorities_path=PRIORITIES_PATH,
        armies_path=ARMIES_PATH,
        tasks_path=TASKS_PATH,
    )

    # Wire GUI log handler to root logger
    gui_handler = GUILogHandler(app.log_view)
    gui_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    logging.getLogger().addHandler(gui_handler)

    logger.info("G.O.B.L.I.N starting")

    try:
        app.mainloop()
    finally:
        logger.info("GUI closed — shutting down")
        task_engine.stop()
        if telegram:
            telegram.stop_polling()
        db.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
