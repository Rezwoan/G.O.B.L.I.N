import logging
import threading
from typing import Optional

import customtkinter as ctk

from gui.dashboard import DashboardTab
from gui.tasks_tab import TasksTab
from gui.upgrades_tab import UpgradesTab
from gui.army_tab import ArmyTab
from gui.settings_tab import SettingsTab
from gui.log_view import LogView

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class App(ctk.CTk):
    def __init__(
        self,
        adb=None,
        task_engine=None,
        state_machine=None,
        config: dict = None,
        config_path: str = "config.toml",
        priorities_path: str = "priorities.toml",
        armies_path: str = "armies.toml",
        tasks_path: str = "tasks.toml",
    ) -> None:
        super().__init__()
        self.title("G.O.B.L.I.N — AutoLoot CoC v3")
        self.geometry("1200x800")
        self.minsize(1200, 800)

        self.adb = adb
        self.task_engine = task_engine
        self.state_machine = state_machine
        self.config = config or {}
        self.config_path = config_path
        self.priorities_path = priorities_path
        self.armies_path = armies_path
        self.tasks_path = tasks_path

        self._engine_thread: Optional[threading.Thread] = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        self.tab_view = ctk.CTkTabview(self, width=1180, height=760)
        self.tab_view.pack(fill="both", expand=True, padx=10, pady=10)

        for name in ("Dashboard", "Tasks", "Upgrades", "Army", "Settings", "Logs"):
            self.tab_view.add(name)

        self.log_view = LogView(self.tab_view.tab("Logs"))
        self.log_view.pack(fill="both", expand=True)

        self.dashboard = DashboardTab(
            self.tab_view.tab("Dashboard"),
            adb=self.adb,
            state_machine=self.state_machine,
            on_start=self._start_engine,
            on_pause=self._pause_engine,
            on_stop=self._stop_engine,
        )
        self.dashboard.pack(fill="both", expand=True)

        self.tasks_tab = TasksTab(
            self.tab_view.tab("Tasks"),
            task_engine=self.task_engine,
            tasks_path=self.tasks_path,
        )
        self.tasks_tab.pack(fill="both", expand=True)

        self.upgrades_tab = UpgradesTab(
            self.tab_view.tab("Upgrades"),
            priorities_path=self.priorities_path,
        )
        self.upgrades_tab.pack(fill="both", expand=True)

        self.army_tab = ArmyTab(
            self.tab_view.tab("Army"),
            armies_path=self.armies_path,
        )
        self.army_tab.pack(fill="both", expand=True)

        self.settings_tab = SettingsTab(
            self.tab_view.tab("Settings"),
            adb=self.adb,
            config=self.config,
            config_path=self.config_path,
        )
        self.settings_tab.pack(fill="both", expand=True)

    def _start_engine(self) -> None:
        if self.task_engine and not self.task_engine.running:
            self._engine_thread = threading.Thread(
                target=self._run_engine_safe, daemon=True, name="EngineThread"
            )
            self._engine_thread.start()
            logger.info("Engine thread started")

    def _run_engine_safe(self) -> None:
        try:
            self.task_engine.run()
        except Exception as exc:
            logger.exception("Engine thread crashed: %s", exc)
            self.after(0, lambda: self.log_view.append("ERROR", f"Engine crashed: {exc}", ""))

    def _pause_engine(self) -> None:
        if self.task_engine:
            if self.task_engine.paused:
                self.task_engine.resume()
            else:
                self.task_engine.pause()

    def _stop_engine(self) -> None:
        if self.task_engine:
            self.task_engine.stop()

    def _on_close(self) -> None:
        logger.info("GUI closing")
        if self.task_engine:
            self.task_engine.stop()
        self.destroy()
