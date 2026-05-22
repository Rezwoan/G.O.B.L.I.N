import logging
import tomllib
from typing import Optional

import customtkinter as ctk

logger = logging.getLogger(__name__)

_STRATEGIES = ["surround", "one_side", "one_corner"]


class ArmyTab(ctk.CTkFrame):
    def __init__(self, parent, armies_path: str = "armies.toml", **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.armies_path = armies_path
        self._profiles: list[dict] = []
        self._selected_idx: Optional[int] = None
        self._load()
        self._build_ui()

    def _load(self) -> None:
        try:
            with open(self.armies_path, "rb") as f:
                data = tomllib.load(f)
            self._profiles = list(data.get("profiles", []))
        except FileNotFoundError:
            self._profiles = []

    def _build_ui(self) -> None:
        left = ctk.CTkFrame(self, width=220)
        left.pack(side="left", fill="y", padx=8, pady=8)

        ctk.CTkLabel(left, text="Profiles", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=6)
        self._profile_list = ctk.CTkScrollableFrame(left, width=200, height=400)
        self._profile_list.pack(fill="both", expand=True)

        btn_row = ctk.CTkFrame(left)
        btn_row.pack(fill="x", pady=4)
        ctk.CTkButton(btn_row, text="+ New", command=self._new_profile).pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text="Delete", fg_color="#7a1a1a", command=self._delete_profile).pack(side="left", padx=4)

        right = ctk.CTkFrame(self)
        right.pack(side="right", fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(right, text="Edit Profile", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=6)

        name_row = ctk.CTkFrame(right)
        name_row.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(name_row, text="Name:").pack(side="left")
        self._name_entry = ctk.CTkEntry(name_row, width=160)
        self._name_entry.pack(side="left", padx=4)

        strat_row = ctk.CTkFrame(right)
        strat_row.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(strat_row, text="Strategy:").pack(side="left")
        self._strat_menu = ctk.CTkOptionMenu(strat_row, values=_STRATEGIES)
        self._strat_menu.pack(side="left", padx=4)

        ctk.CTkLabel(right, text="Troops (name, count):").pack(anchor="w", padx=6)
        self._troops_frame = ctk.CTkScrollableFrame(right, height=250)
        self._troops_frame.pack(fill="both", expand=True, padx=6)

        troop_add_row = ctk.CTkFrame(right)
        troop_add_row.pack(fill="x", padx=6, pady=4)
        self._troop_name_entry = ctk.CTkEntry(troop_add_row, width=120, placeholder_text="Troop name")
        self._troop_name_entry.pack(side="left", padx=4)
        self._troop_count_entry = ctk.CTkEntry(troop_add_row, width=60, placeholder_text="Count")
        self._troop_count_entry.pack(side="left", padx=4)
        ctk.CTkButton(troop_add_row, text="Add Troop", command=self._add_troop).pack(side="left")

        btn_row2 = ctk.CTkFrame(right)
        btn_row2.pack(fill="x", padx=6, pady=4)
        ctk.CTkButton(btn_row2, text="Save Profile", command=self._save_profile).pack(side="left", padx=4)
        ctk.CTkButton(btn_row2, text="Save All", command=self._save_all).pack(side="left", padx=4)

        self._refresh_profile_list()

    def _refresh_profile_list(self) -> None:
        for w in self._profile_list.winfo_children():
            w.destroy()
        for i, p in enumerate(self._profiles):
            btn = ctk.CTkButton(
                self._profile_list,
                text=p.get("name", f"Profile {i}"),
                command=lambda idx=i: self._select_profile(idx),
                fg_color="#1a3a5c" if i == self._selected_idx else "gray25",
            )
            btn.pack(fill="x", pady=2)

    def _select_profile(self, idx: int) -> None:
        self._selected_idx = idx
        p = self._profiles[idx]
        self._name_entry.delete(0, "end")
        self._name_entry.insert(0, p.get("name", ""))
        self._strat_menu.set(p.get("strategy", "surround"))
        self._refresh_troops(p.get("troops", []))
        self._refresh_profile_list()

    def _refresh_troops(self, troops: list) -> None:
        for w in self._troops_frame.winfo_children():
            w.destroy()
        for j, t in enumerate(troops):
            row = ctk.CTkFrame(self._troops_frame)
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=f"{t.get('name','')} × {t.get('count',0)}", anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="✕", width=28, fg_color="#7a1a1a",
                          command=lambda jj=j: self._remove_troop(jj)).pack(side="right")

    def _add_troop(self) -> None:
        if self._selected_idx is None:
            return
        name = self._troop_name_entry.get().strip()
        try:
            count = int(self._troop_count_entry.get())
        except ValueError:
            return
        if not name:
            return
        troops = self._profiles[self._selected_idx].setdefault("troops", [])
        troops.append({"name": name, "count": count})
        self._troop_name_entry.delete(0, "end")
        self._troop_count_entry.delete(0, "end")
        self._refresh_troops(troops)

    def _remove_troop(self, idx: int) -> None:
        if self._selected_idx is None:
            return
        troops = self._profiles[self._selected_idx].get("troops", [])
        if 0 <= idx < len(troops):
            del troops[idx]
            self._refresh_troops(troops)

    def _new_profile(self) -> None:
        self._profiles.append({"name": f"Profile {len(self._profiles)+1}", "strategy": "surround", "troops": []})
        self._selected_idx = len(self._profiles) - 1
        self._select_profile(self._selected_idx)

    def _delete_profile(self) -> None:
        if self._selected_idx is not None and 0 <= self._selected_idx < len(self._profiles):
            del self._profiles[self._selected_idx]
            self._selected_idx = None
            self._refresh_profile_list()

    def _save_profile(self) -> None:
        if self._selected_idx is None:
            return
        self._profiles[self._selected_idx]["name"] = self._name_entry.get().strip()
        self._profiles[self._selected_idx]["strategy"] = self._strat_menu.get()
        self._refresh_profile_list()

    def _save_all(self) -> None:
        self._save_profile()
        lines = []
        for p in self._profiles:
            lines.append("[[profiles]]")
            lines.append(f'name = "{p.get("name","")}"')
            lines.append(f'strategy = "{p.get("strategy","surround")}"')
            for t in p.get("troops", []):
                lines.append("")
                lines.append("[[profiles.troops]]")
                lines.append(f'name = "{t.get("name","")}"')
                lines.append(f'count = {t.get("count",0)}')
            lines.append("")
        with open(self.armies_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info("Saved armies to %s", self.armies_path)
