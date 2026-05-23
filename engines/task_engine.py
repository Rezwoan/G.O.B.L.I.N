import logging
import threading
import time
import tomllib
from dataclasses import dataclass, field
from typing import Optional

from core.adb import ADBInterface
from core.navigator import Navigator
from core.ocr import OCRReader
from engines.attack_engine import AttackEngine
from engines.collect_engine import CollectEngine
from engines.upgrade_engine import UpgradeEngine

logger = logging.getLogger(__name__)


# ─── Task dataclasses ───────────────────────────────────────────────────────

@dataclass
class Task:
    task_type: str
    max_retries: int = 3
    retry_count: int = field(default=0, init=False)


@dataclass
class FarmTask(Task):
    n_attacks: int = 0
    until_gold: int = 0
    until_elixir: int = 0
    until_dark: int = 0

    def __post_init__(self):
        self.task_type = "FarmTask"


@dataclass
class UpgradeTask(Task):
    target: str = ""

    def __post_init__(self):
        self.task_type = "UpgradeTask"


@dataclass
class CollectTask(Task):
    def __post_init__(self):
        self.task_type = "CollectTask"


@dataclass
class SequenceTask(Task):
    tasks: list = field(default_factory=list)

    def __post_init__(self):
        self.task_type = "SequenceTask"


# ─── Task Engine ─────────────────────────────────────────────────────────────

class TaskEngine:
    def __init__(
        self,
        adb: ADBInterface,
        navigator: Navigator,
        attack_engine: AttackEngine,
        upgrade_engine: UpgradeEngine,
        collect_engine: CollectEngine,
        ocr: OCRReader,
        notifier,
        db=None,
    ) -> None:
        self.adb = adb
        self.navigator = navigator
        self.attack_engine = attack_engine
        self.upgrade_engine = upgrade_engine
        self.collect_engine = collect_engine
        self.ocr = ocr
        self.notifier = notifier
        self.db = db

        self.queue: list[Task] = []
        self.running = False
        self.paused = False
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # not paused initially
        self._session_id: Optional[int] = None

    # ── Queue management ──────────────────────────────────────────────────

    def load_queue(self, path: str) -> None:
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
            self.queue = [self._build_task(t) for t in data.get("tasks", [])]
            logger.info("Loaded %d tasks from %s", len(self.queue), path)
        except FileNotFoundError:
            logger.warning("Task queue file not found: %s", path)
        except Exception as exc:
            logger.error("Failed to load task queue: %s", exc)

    def save_queue(self, path: str) -> None:
        try:
            import tomli_w  # type: ignore
        except ImportError:
            # Fallback: write minimal TOML manually
            self._save_queue_manual(path)
            return
        tasks_data = [self._task_to_dict(t) for t in self.queue]
        with open(path, "wb") as f:
            tomli_w.dump({"tasks": tasks_data}, f)
        logger.info("Saved %d tasks to %s", len(self.queue), path)

    def _save_queue_manual(self, path: str) -> None:
        lines = []
        for t in self.queue:
            d = self._task_to_dict(t)
            lines.append("[[tasks]]")
            for k, v in d.items():
                if isinstance(v, str):
                    lines.append(f'{k} = "{v}"')
                else:
                    lines.append(f"{k} = {v}")
            lines.append("")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _build_task(self, data: dict) -> Task:
        t = data.get("type", "")
        if t == "FarmTask":
            return FarmTask(
                task_type=t,
                n_attacks=data.get("n_attacks", 0),
                until_gold=data.get("until_gold", 0),
                until_elixir=data.get("until_elixir", 0),
                until_dark=data.get("until_dark", 0),
                max_retries=data.get("max_retries", 3),
            )
        elif t == "UpgradeTask":
            return UpgradeTask(task_type=t, target=data.get("target", ""), max_retries=data.get("max_retries", 3))
        elif t == "CollectTask":
            return CollectTask(task_type=t, max_retries=data.get("max_retries", 3))
        elif t == "SequenceTask":
            sub = [self._build_task(s) for s in data.get("tasks", [])]
            return SequenceTask(task_type=t, tasks=sub, max_retries=data.get("max_retries", 3))
        else:
            logger.warning("Unknown task type: %s", t)
            return Task(task_type=t)

    def _task_to_dict(self, task: Task) -> dict:
        if isinstance(task, FarmTask):
            return {"type": "FarmTask", "n_attacks": task.n_attacks,
                    "until_gold": task.until_gold, "until_elixir": task.until_elixir,
                    "until_dark": task.until_dark}
        elif isinstance(task, UpgradeTask):
            return {"type": "UpgradeTask", "target": task.target}
        elif isinstance(task, CollectTask):
            return {"type": "CollectTask"}
        elif isinstance(task, SequenceTask):
            return {"type": "SequenceTask", "tasks": [self._task_to_dict(s) for s in task.tasks]}
        return {"type": task.task_type}

    # ── Execution ─────────────────────────────────────────────────────────

    def run(self) -> None:
        self.running = True
        self._stop_event.clear()
        if self.db:
            self._session_id = self.db.start_session()
        if self.notifier:
            self.notifier.notify("TASK_STARTED", {"tasks": len(self.queue)})

        for task in list(self.queue):
            if self._stop_event.is_set():
                break
            self._wait_if_paused()

            success = False
            while task.retry_count <= task.max_retries:
                try:
                    success = self.execute_task(task)
                    if success:
                        break
                except Exception as exc:
                    logger.exception("Task execution error: %s", exc)
                task.retry_count += 1
                logger.warning("Task %s failed, retry %d/%d", task.task_type, task.retry_count, task.max_retries)
                time.sleep(2.0)

            if not success:
                logger.error("Task %s failed after %d retries — skipping", task.task_type, task.max_retries)
                if self.notifier:
                    self.notifier.notify("ERROR", {"task": task.task_type, "retries": task.retry_count})

        self.running = False
        if self.db and self._session_id:
            self.db.end_session(self._session_id, {})
        if self.notifier:
            self.notifier.notify("TASK_COMPLETED", {"queue_size": len(self.queue)})
        logger.info("Task queue complete")

    def execute_task(self, task: Task) -> bool:
        if isinstance(task, FarmTask):
            return self._execute_farm(task)
        elif isinstance(task, UpgradeTask):
            return self.upgrade_engine.run_upgrade(task.target)
        elif isinstance(task, CollectTask):
            self.collect_engine.collect_all()
            return True
        elif isinstance(task, SequenceTask):
            for sub in task.tasks:
                if not self.execute_task(sub):
                    return False
            return True
        logger.warning("Unknown task type: %s", task.task_type)
        return False

    def _execute_farm(self, task: FarmTask) -> bool:
        attacks_done = 0
        while not self._stop_event.is_set():
            self._wait_if_paused()

            if task.n_attacks > 0 and attacks_done >= task.n_attacks:
                logger.info("FarmTask: completed %d attacks", attacks_done)
                return True

            if self._check_loot_thresholds(task):
                logger.info("FarmTask: loot thresholds met")
                return True

            result = self.attack_engine.run_attack_cycle()
            if result:
                attacks_done += 1
                if self._session_id:
                    self.attack_engine.log_result(result, self._session_id)
            else:
                logger.warning("Attack cycle returned None")
                return False

        return False

    def _check_loot_thresholds(self, task: FarmTask) -> bool:
        if task.until_gold == 0 and task.until_elixir == 0 and task.until_dark == 0:
            return False
        logger.warning(
            "FarmTask has loot thresholds (gold=%d elixir=%d dark=%d) but OCR is disabled — "
            "farming by n_attacks only",
            task.until_gold, task.until_elixir, task.until_dark,
        )
        return False

    def _wait_if_paused(self) -> None:
        while self.paused and not self._stop_event.is_set():
            time.sleep(0.5)

    def stop(self) -> None:
        logger.info("TaskEngine: stop requested")
        self._stop_event.set()
        self.running = False

    def pause(self) -> None:
        logger.info("TaskEngine: pause requested")
        self.paused = True

    def resume(self) -> None:
        logger.info("TaskEngine: resume requested")
        self.paused = False
