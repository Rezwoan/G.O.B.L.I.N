import logging
import tomllib
from pathlib import Path
from typing import Optional

import customtkinter as ctk

logger = logging.getLogger(__name__)


class UpgradesTab(ctk.CTkFrame):
    def __init__(self, parent, priorities_path: str = "priorities.toml", **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.priorities_path = priorities_path
        self._priorities: list[str] = []
        self._load()
        self._build_ui()

    def _load(self) -> None:
        try:
            with open(self.priorities_path, "rb") as f:
                data = tomllib.load(f)
            self._priorities = list(data.get("priorities", []))
        except FileNotFoundError:
            self._priorities = []

    def _build_ui(self) -> None:
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(top, text="Add item:").pack(side="left", padx=6)
        self._add_entry = ctk.CTkEntry(top, width=200, placeholder_text="e.g. Cannon")
        self._add_entry.pack(side="left", padx=6)
        ctk.CTkButton(top, text="Add", command=self._add).pack(side="left", padx=4)

        self._list_frame = ctk.CTkScrollableFrame(self, label_text="Upgrade Priority (top = highest priority)")
        self._list_frame.pack(fill="both", expand=True, padx=10, pady=4)

        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=10, pady=6)
        ctk.CTkButton(btn_frame, text="Save", command=self._save).pack(side="left", padx=6)

        self._refresh()

    def _add(self) -> None:
        text = self._add_entry.get().strip()
        if text and text not in self._priorities:
            self._priorities.append(text)
            self._add_entry.delete(0, "end")
            self._refresh()

    def _refresh(self) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()
        for i, item in enumerate(self._priorities):
            row = ctk.CTkFrame(self._list_frame)
            row.pack(fill="x", padx=4, pady=2)
            ctk.CTkLabel(row, text=f"{i+1}. {item}", anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="↑", width=30, command=lambda idx=i: self._move_up(idx)).pack(side="left")
            ctk.CTkButton(row, text="↓", width=30, command=lambda idx=i: self._move_down(idx)).pack(side="left")
            ctk.CTkButton(row, text="✕", width=30, fg_color="#7a1a1a",
                          command=lambda idx=i: self._remove(idx)).pack(side="left")

    def _remove(self, idx: int) -> None:
        if 0 <= idx < len(self._priorities):
            del self._priorities[idx]
            self._refresh()

    def _move_up(self, idx: int) -> None:
        if idx > 0:
            self._priorities[idx - 1], self._priorities[idx] = self._priorities[idx], self._priorities[idx - 1]
            self._refresh()

    def _move_down(self, idx: int) -> None:
        if idx < len(self._priorities) - 1:
            self._priorities[idx], self._priorities[idx + 1] = self._priorities[idx + 1], self._priorities[idx]
            self._refresh()

    def _save(self) -> None:
        lines = ["priorities = [\n"]
        for p in self._priorities:
            lines.append(f'  "{p}",\n')
        lines.append("]\n")
        with open(self.priorities_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        logger.info("Saved priorities to %s", self.priorities_path)
