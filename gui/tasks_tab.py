import logging
from typing import Optional

import customtkinter as ctk

from engines.task_engine import FarmTask, UpgradeTask, CollectTask, SequenceTask

logger = logging.getLogger(__name__)

_TASK_TYPES = ["FarmTask", "UpgradeTask", "CollectTask"]


class TasksTab(ctk.CTkFrame):
    def __init__(self, parent, task_engine=None, tasks_path: str = "tasks.toml", **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.task_engine = task_engine
        self.tasks_path = tasks_path
        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        # Top: add task controls
        add_frame = ctk.CTkFrame(self)
        add_frame.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(add_frame, text="Add Task:").pack(side="left", padx=6)
        self._type_menu = ctk.CTkOptionMenu(add_frame, values=_TASK_TYPES, command=self._on_type_change)
        self._type_menu.pack(side="left", padx=6)

        self._param_frame = ctk.CTkFrame(add_frame)
        self._param_frame.pack(side="left", padx=6)

        ctk.CTkButton(add_frame, text="Add", command=self._add_task).pack(side="left", padx=6)

        # Queue display
        self._list_frame = ctk.CTkScrollableFrame(self, label_text="Task Queue")
        self._list_frame.pack(fill="both", expand=True, padx=10, pady=4)

        # Bottom: save/load
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=10, pady=6)
        ctk.CTkButton(btn_frame, text="Save Queue", command=self._save).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Load Queue", command=self._load).pack(side="left", padx=6)

        self._build_param_fields("FarmTask")

    def _on_type_change(self, value: str) -> None:
        for w in self._param_frame.winfo_children():
            w.destroy()
        self._build_param_fields(value)

    def _build_param_fields(self, task_type: str) -> None:
        self._param_entries: dict[str, ctk.CTkEntry] = {}
        if task_type == "FarmTask":
            for label, key in [("N Attacks", "n_attacks"), ("Until Gold", "until_gold"),
                                ("Until Elixir", "until_elixir"), ("Until Dark", "until_dark")]:
                ctk.CTkLabel(self._param_frame, text=label).pack(side="left")
                entry = ctk.CTkEntry(self._param_frame, width=70)
                entry.insert(0, "0")
                entry.pack(side="left", padx=2)
                self._param_entries[key] = entry
        elif task_type == "UpgradeTask":
            ctk.CTkLabel(self._param_frame, text="Target").pack(side="left")
            entry = ctk.CTkEntry(self._param_frame, width=120)
            entry.pack(side="left", padx=2)
            self._param_entries["target"] = entry

    def _add_task(self) -> None:
        if not self.task_engine:
            return
        task_type = self._type_menu.get()
        try:
            if task_type == "FarmTask":
                task = FarmTask(
                    task_type=task_type,
                    n_attacks=int(self._param_entries.get("n_attacks", _ZeroEntry()).get() or 0),
                    until_gold=int(self._param_entries.get("until_gold", _ZeroEntry()).get() or 0),
                    until_elixir=int(self._param_entries.get("until_elixir", _ZeroEntry()).get() or 0),
                    until_dark=int(self._param_entries.get("until_dark", _ZeroEntry()).get() or 0),
                )
            elif task_type == "UpgradeTask":
                target = self._param_entries.get("target", _ZeroEntry()).get().strip()
                task = UpgradeTask(task_type=task_type, target=target)
            else:
                task = CollectTask(task_type=task_type)

            self.task_engine.queue.append(task)
            self._refresh_list()
        except Exception as exc:
            logger.error("Add task error: %s", exc)

    def _refresh_list(self) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()
        if not self.task_engine:
            return
        for i, task in enumerate(self.task_engine.queue):
            row = ctk.CTkFrame(self._list_frame)
            row.pack(fill="x", padx=4, pady=2)
            summary = self._task_summary(task)
            ctk.CTkLabel(row, text=f"{i+1}. {summary}", anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="↑", width=30, command=lambda idx=i: self._move_up(idx)).pack(side="left")
            ctk.CTkButton(row, text="↓", width=30, command=lambda idx=i: self._move_down(idx)).pack(side="left")
            ctk.CTkButton(row, text="✕", width=30, fg_color="#7a1a1a",
                          command=lambda idx=i: self._remove(idx)).pack(side="left")

    def _task_summary(self, task) -> str:
        if isinstance(task, FarmTask):
            parts = []
            if task.n_attacks:
                parts.append(f"{task.n_attacks} attacks")
            if task.until_gold:
                parts.append(f"gold≥{task.until_gold:,}")
            if task.until_elixir:
                parts.append(f"elixir≥{task.until_elixir:,}")
            return f"FarmTask({', '.join(parts) or 'unlimited'})"
        elif isinstance(task, UpgradeTask):
            return f"UpgradeTask({task.target})"
        elif isinstance(task, CollectTask):
            return "CollectTask"
        elif isinstance(task, SequenceTask):
            return f"SequenceTask({len(task.tasks)} subtasks)"
        return task.task_type

    def _remove(self, idx: int) -> None:
        if self.task_engine and 0 <= idx < len(self.task_engine.queue):
            del self.task_engine.queue[idx]
            self._refresh_list()

    def _move_up(self, idx: int) -> None:
        q = self.task_engine.queue if self.task_engine else []
        if idx > 0:
            q[idx - 1], q[idx] = q[idx], q[idx - 1]
            self._refresh_list()

    def _move_down(self, idx: int) -> None:
        q = self.task_engine.queue if self.task_engine else []
        if idx < len(q) - 1:
            q[idx], q[idx + 1] = q[idx + 1], q[idx]
            self._refresh_list()

    def _save(self) -> None:
        if self.task_engine:
            self.task_engine.save_queue(self.tasks_path)

    def _load(self) -> None:
        if self.task_engine:
            self.task_engine.load_queue(self.tasks_path)
            self._refresh_list()


class _ZeroEntry:
    """Dummy entry that returns '0' — used as fallback for missing param entries."""
    def get(self):
        return "0"
